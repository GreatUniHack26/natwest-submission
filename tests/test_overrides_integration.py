"""Issue #7 integration: PATCH -> SQLite -> API/restart/re-seed -> categoriser, forecast and alerts."""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.data import categoriser, repository
from backend.data.categoriser import categorise
from backend.data.seed import seed
from backend.main import app

ROOT = Path(__file__).parent.parent


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "ovi.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    seed()
    return TestClient(app)


def _tx(uid, merchant):
    return next(t for t in repository.get_transactions(uid) if t.merchant == merchant)


def test_override_persists_across_a_restart(env):
    tx = _tx("sam", "Tesco")
    assert env.patch(f"/users/sam/transactions/{tx.id}", json={"category": "treats", "kind": "want"}).status_code == 200
    out = subprocess.run(
        [sys.executable, "-c",
         f"from backend.data import repository as r;"
         f"t=[x for x in r.get_transactions('sam') if x.id=='{tx.id}'][0];print(t.category, t.kind)"],
        cwd=ROOT, capture_output=True, text=True,
        env={"MOCK_DATA": "0", "DB_PATH": config.DB_PATH, "PATH": ""},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "treats want"


def test_override_survives_make_seed(env):
    tx = _tx("sam", "Tesco")
    env.patch(f"/users/sam/transactions/{tx.id}", json={"category": "treats", "kind": "want"})
    seed()
    assert (_tx("sam", "Tesco").category, _tx("sam", "Tesco").kind) == ("treats", "want")


def test_categorise_with_stored_overrides_agrees_with_the_api(env):
    """The two ways to read an overridden label must give the same answer."""
    tx = _tx("maya", "Aldi")
    env.patch(f"/users/maya/transactions/{tx.id}", json={"category": "treats", "kind": "want"})
    served = {t.id: (t.category, t.kind) for t in repository.get_transactions("maya")}
    base = [t.model_copy(update={"category": "?", "kind": "want"}) for t in repository.get_transactions("maya")]
    recomputed = {t.id: (t.category, t.kind) for t in categorise(base, repository.get_overrides("maya"))}
    assert recomputed[tx.id] == served[tx.id] == ("treats", "want")


def test_forecast_inputs_see_the_overridden_kind(env, monkeypatch):
    """backend.forecast reads only via repository.get_transactions, so overrides reach it."""
    from backend.forecast.inputs import load_inputs

    monkeypatch.setattr(repository, "get_balance", lambda uid, as_of: 1000.0, raising=False)
    tx = max((t for t in repository.get_transactions("sam") if t.merchant == "Tesco"), key=lambda t: t.date)
    before = {t.id: t for t in load_inputs("sam", config.TODAY).transactions}[tx.id]
    assert before.kind == "need"
    env.patch(f"/users/sam/transactions/{tx.id}", json={"category": "treats", "kind": "want"})
    after = {t.id: t for t in load_inputs("sam", config.TODAY).transactions}[tx.id]
    assert (after.category, after.kind) == ("treats", "want")


def test_alerts_use_the_overridden_kind(env, monkeypatch):
    """Marking this month's eating out as income removes it from spend: the overspend alert goes."""
    from backend.forecast.alerts import find_alerts

    def eating_out_alerts():
        return [a for a in find_alerts("sam") if a.type == "overspend" and a.category == "eating out"]

    monkeypatch.setattr(repository, "get_balance", lambda uid, as_of: 1640.0, raising=False)
    assert eating_out_alerts()
    for t in repository.get_transactions("sam", start=config.TODAY.replace(day=1)):
        if t.category == "eating out":
            env.patch(f"/users/sam/transactions/{t.id}", json={"category": "refund", "kind": "income"})
    assert not eating_out_alerts()
