"""Issue #5 integration: generator -> seed -> SQLite -> repository -> HTTP API with MOCK_DATA=0."""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.data import repository
from backend.data.generator import generate_persona
from backend.data.seed import seed
from backend.main import app
from contracts import schemas

ROOT = Path(__file__).parent.parent


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "it.db"))
    seed()
    return TestClient(app)


def test_stored_data_equals_generated_data(seeded):
    user, txs, pots = generate_persona("sam", 42)
    assert repository.get_user("sam") == user
    assert repository.get_transactions("sam") == sorted(txs, key=lambda t: (t.date, t.id))
    assert repository.get_pots("sam") == sorted(pots, key=lambda p: p.id)


def test_data_endpoints_return_seeded_data(seeded):
    user, txs, pots = generate_persona("sam", 42)
    assert schemas.User(**seeded.get("/users/sam").json()) == user
    api_txs = [schemas.Transaction(**t) for t in seeded.get("/users/sam/transactions").json()]
    assert len(api_txs) == len(txs)
    api_pots = [schemas.Pot(**p) for p in seeded.get("/users/sam/pots").json()]
    assert {p.id for p in api_pots} == {p.id for p in pots}


def test_transactions_endpoint_date_filter(seeded):
    r = seeded.get("/users/sam/transactions", params={"start": "2026-11-01", "end": "2026-11-07"})
    assert r.status_code == 200
    rows = r.json()
    assert rows and all("2026-11-01" <= t["date"] <= "2026-11-07" for t in rows)


def test_post_pot_persists_and_shows_up_in_get(seeded):
    body = {"id": "p-new", "user_id": "sam", "name": "Holiday", "amount": 120.0, "due_date": "2027-03-01"}
    assert seeded.post("/users/sam/pots", json=body).status_code == 200
    ids = [p["id"] for p in seeded.get("/users/sam/pots").json()]
    assert "p-new" in ids


def test_data_survives_a_new_process(seeded, tmp_path):
    """Persistence across restarts: a separate Python process reads what we seeded."""
    out = subprocess.run(
        [sys.executable, "-c",
         "from backend.data import repository as r; print(len(r.get_transactions('sam')))"],
        cwd=ROOT, capture_output=True, text=True,
        env={"MOCK_DATA": "0", "DB_PATH": config.DB_PATH, "PATH": ""},
    )
    assert out.returncode == 0, out.stderr
    assert int(out.stdout) == len(generate_persona("sam", 42)[1])


def test_seed_cli_runs_and_is_rerunnable(tmp_path):
    env = {"DB_PATH": str(tmp_path / "cli.db"), "PATH": ""}
    for _ in range(2):
        out = subprocess.run([sys.executable, "-m", "backend.data.seed"], cwd=ROOT,
                             capture_output=True, text=True, env=env)
        assert out.returncode == 0, out.stderr
        assert "seeded sam" in out.stdout


def test_other_modules_still_work_with_real_data(seeded):
    """Existing smoke endpoints must not break with MOCK_DATA=0 for the data module."""
    assert seeded.get("/health").status_code == 200
