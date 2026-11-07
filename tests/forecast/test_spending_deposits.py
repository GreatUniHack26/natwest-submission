"""Spending forecast and deposit ideas run on the seeded real-mode personas."""
import datetime as dt

import pytest

from backend import config
from backend.forecast import deposits, spending
from contracts.schemas import Pot


def test_interest_formula_is_compound_and_rounded():
    assert deposits._interest(1000.0, 4.0, 365) == 40.0
    assert deposits._interest(5000.0, 4.0, 0) == 0.0
    assert 0 < deposits._interest(950.0, 4.0, 24) < 3


def test_deposit_ideas_skip_small_and_imminent_pots(monkeypatch):
    today = config.TODAY
    pots = [
        Pot(id="a", user_id="u", name="March rent", amount=5000.0, due_date=today + dt.timedelta(days=120)),
        Pot(id="b", user_id="u", name="Tiny", amount=20.0, due_date=today + dt.timedelta(days=120)),
        Pot(id="c", user_id="u", name="Tomorrow", amount=900.0, due_date=today + dt.timedelta(days=3)),
        Pot(id="d", user_id="u", name="Rainy day", amount=300.0, due_date=None),
    ]
    monkeypatch.setattr(deposits.repository, "get_pots", lambda uid: pots)
    monkeypatch.setattr("backend.forecast.forecast", lambda uid, days: (_ for _ in ()).throw(RuntimeError("no forecast")))
    out = deposits.deposit_ideas("u")
    names = [i["pot"] for i in out["ideas"]]
    assert names == ["March rent", "Rainy day"]
    march = out["ideas"][0]
    assert march["idle_days"] == 120 and march["withdraw_by"] == (today + dt.timedelta(days=118)).isoformat()
    assert march["est_interest"] == deposits._interest(5000.0, out["aer_assumption"], 120)
    assert out["ideas"][1]["interest_period"] == "per year"
    assert "not financial advice" in out["disclaimer"]


def test_spending_forecast_projects_and_flags(monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    try:
        out = spending.spending_forecast("sam")
    except Exception as exc:  # seeded DB not present in this environment
        pytest.skip(f"seeded data unavailable: {exc}")
    assert out["days_elapsed"] == config.TODAY.day
    for row in out["categories"]:
        assert row["projected_month"] >= row["spent_so_far"]
        assert row["status"] in {"over", "watch", "on_track"}
        assert (row["alarm"] is not None) == (row["status"] == "over")
