"""Issue #6 integration: generator -> categorise -> seed -> SQLite -> API, with no live LLM."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.data import categoriser, repository
from backend.data.generator import generate_household, generate_persona
from backend.data.seed import seed
from backend.main import app

VALID_KINDS = {"need", "want", "income"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Real-mode DB + isolated cache; a key is set but any LLM call fails the test."""
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "cat.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    calls = []

    def forbidden(prompt):
        calls.append(prompt)
        raise AssertionError("live LLM call during seeding")

    monkeypatch.setattr(categoriser, "_call_llm", forbidden)
    return tmp_path, calls


def test_seeding_makes_zero_llm_calls(env):
    _, calls = env
    seed()
    seed()  # re-running too
    assert calls == []
    assert not (env[0] / "cache.json").exists()  # nothing unknown, nothing cached


def test_seeded_db_labels_match_the_generators(env):
    seed()
    members = [generate_persona("sam"), generate_persona("salaried"), generate_persona("pete"), *generate_household("family")]
    for user, txs, _ in members:
        stored = repository.get_transactions(user.id)
        assert {t.id: (t.category, t.kind) for t in stored} == {t.id: (t.category, t.kind) for t in txs}


def test_every_stored_transaction_is_labelled(env):
    seed()
    for uid in ("sam", "alex", "maya", "dan", "pete"):
        stored = repository.get_transactions(uid)
        assert stored
        assert all(t.category and t.kind in VALID_KINDS for t in stored)
        assert all(t.category != "other" for t in stored)
        assert all((t.kind == "income") == (t.amount > 0) for t in stored)


def test_api_returns_labelled_transactions(env):
    seed()
    rows = TestClient(app).get("/users/maya/transactions").json()
    assert {"childcare", "school", "debt"} <= {r["category"] for r in rows}
    assert {r["kind"] for r in rows} <= VALID_KINDS


def test_unknown_merchant_end_to_end_then_offline(env, monkeypatch):
    """First run with a key labels via ONE mocked call and caches; then it works with no key."""
    tmp, _ = env
    user, txs, pots = generate_persona("sam")
    extra = txs[1].model_copy(update={"id": "x1", "merchant": "Boots", "amount": -9.5})
    extra2 = txs[1].model_copy(update={"id": "x2", "merchant": "Vue Cinema", "amount": -11.0})
    calls = []

    def fake(prompt):
        calls.append(prompt)
        return json.dumps({"Boots": {"category": "health", "kind": "need"},
                           "Vue Cinema": {"category": "entertainment", "kind": "want"}})

    monkeypatch.setattr(categoriser, "_call_llm", fake)
    first = categoriser.categorise([*txs, extra, extra2])
    assert len(calls) == 1
    assert {t.id: (t.category, t.kind) for t in first if t.id in ("x1", "x2")} == {
        "x1": ("health", "need"), "x2": ("entertainment", "want")}
    assert set(json.loads((tmp / "cache.json").read_text())) == {"boots", "vue cinema"}

    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(categoriser, "_call_llm", lambda p: pytest.fail("cache miss"))
    assert categoriser.categorise([*txs, extra, extra2]) == first
    assert len(calls) == 1


def test_seed_cli_runs_with_no_key_and_no_cache(tmp_path):
    """Fresh clone, no API key: `make seed` works (the demo path)."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).parent.parent
    out = subprocess.run(
        [sys.executable, "-m", "backend.data.seed"], cwd=root, capture_output=True, text=True,
        env={"DB_PATH": str(tmp_path / "cli.db"), "LABEL_CACHE_PATH": str(tmp_path / "none.json"),
             "LLM_API_KEY": "", "PATH": ""},
    )
    assert out.returncode == 0, out.stderr
    assert "seeded maya" in out.stdout
    assert not (tmp_path / "none.json").exists()


def test_committed_cache_is_valid_json_object():
    from pathlib import Path

    path = Path(categoriser.__file__).with_name("label_cache.json")
    assert path.exists(), "label_cache.json must be committed so the demo works without a key"
    assert isinstance(json.loads(path.read_text()), dict)
