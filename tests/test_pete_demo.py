"""Pete's generated history -> SQLite -> real API, forecast and coach tools."""
import datetime as dt
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend import config, forecast, rules
from backend.agent import tools
from backend.agent.orchestrator import extract_numbers_used
from backend.data import categorise, repository
from backend.data.generator import OPENING_BALANCE_MERCHANT, generate_persona
from backend.data.seed import seed
from backend.main import app

TODAY = dt.date(2026, 11, 7)


@pytest.fixture
def pete(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "MOCK_FORECAST", False)
    monkeypatch.setattr(config, "TODAY", TODAY)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "pete.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    seed(personas=["pete"], households=[])
    return TestClient(app)


def test_pete_history_is_reproducible_labelled_and_reseeds_without_duplicates(pete, monkeypatch):
    from backend.data import categoriser

    def no_network(*args):
        pytest.fail("Pete's committed merchant labels must work offline")

    monkeypatch.setattr(categoriser, "llm_label", no_network)
    user, txs, pots = generate_persona("pete")
    assert generate_persona("pete") == (user, txs, pots)
    assert categorise(txs) == txs
    assert len(txs) == 731 and len({t.id for t in txs}) == 731
    assert len({t.category for t in txs if t.amount < 0}) == 12
    assert (txs[0].date, txs[-1].date) == (dt.date(2025, 11, 7), TODAY)
    assert sum(t.merchant == OPENING_BALANCE_MERCHANT for t in txs) == 1
    balance = Decimal(0)
    for tx in txs:
        balance += Decimal(str(tx.amount))
        assert balance >= 0, "The historical student ledger must never require an unexplained overdraft"
    assert balance == Decimal("1750")
    assert seed(personas=["pete"], households=[]) == {"pete": 731}
    assert repository.get_transactions("pete") == txs
    assert repository.get_pots("pete") == pots
    assert pete.get("/users/pete").json()["name"] == "Pete"


def test_real_purchase_checks_rent_forecast_and_alerts(pete):
    safe = pete.get("/users/pete/safe-to-spend").json()
    assert (safe["balance"], safe["pots_total"], safe["upcoming_bills"], safe["safe_amount"]) == (1750, 1325, 101.8, 323.2)
    assert sum(Decimal(str(line["amount"])) for line in safe["breakdown"]) == Decimal("323.20")
    small = pete.post("/users/pete/simulate", json={"amount": 30}).json()
    assert small["affordable"] is True and small["safe_after"] == 293.2
    assert small["better_date"] == "2026-11-27"
    large = pete.post("/users/pete/simulate", json={"amount": 500}).json()
    assert large["affordable"] is False and large["safe_after"] == -176.8
    alerts = pete.get("/users/pete/alerts").json()
    assert any(a["type"] == "sudden_change" and a["category"] == "eating out" for a in alerts)
    base = forecast.forecast("pete", 90)
    assert any(r.date == dt.date(2027, 2, 1) and "pots" in r.reason for r in base.risk_events)
    reduced = pete.post("/users/pete/forecast/what-if", json={"days": 90, "overrides": {"income_multiplier": 0.5}}).json()
    assert any(r["date"] == "2027-01-14" and r["severity"] == "high" for r in reduced["risk_events"])
    assert reduced["points"][-1]["expected"] < base.points[-1].expected


def test_history_questions_and_filtered_follow_ups_have_verified_numbers(pete):
    october = tools.run_tool("pete", "get_spending_history", {"start": "2026-10-01", "end": "2026-10-31"})
    assert (october["spent"], october["income"], october["net_cash_flow"]) == (1243.09, 900, -343.09)
    assert october["by_category"]["housing"] == 625
    assert october["transaction_count"] == 64 and october["transactions_shown"] == 20
    jacket = tools.run_tool("pete", "get_spending_history", {"start": "2026-10-01", "end": "2026-10-31", "merchant": "UNIQLO"})
    assert jacket["spent"] == 59.9 and jacket["transaction_count"] == 1
    assert jacket["latest_transactions"][0]["merchant"] == "Uniqlo winter jacket"
    full = tools.run_tool("pete", "get_spending_history", {"start": "2025-11-07", "end": "2026-11-07"})
    assert full["transaction_count"] == 730  # opening balance is savings, not income
    assert full["income"] == float(sum(Decimal(str(t.amount)) for t in repository.get_transactions("pete")
                                        if t.kind == "income" and t.merchant != OPENING_BALANCE_MERCHANT))
    empty = tools.run_tool("pete", "get_spending_history", {"merchant": "nonexistent"})
    assert empty["transaction_count"] == 0 and empty["spent"] == 0
    assert 59.9 in extract_numbers_used(jacket).values()
    assert not (set(october["numbers_used"]) & set(jacket["numbers_used"]))
    json.dumps(full)  # actual tool loop serialises without a custom JSON encoder


@pytest.mark.parametrize("args", [
    {"start": "2026-11-08"}, {"start": "2026-11-07", "end": "2026-10-01"},
    {"start": "2024-01-01"}, {"start": 1}, {"end": "invalid"},
    {"category": []}, {"merchant": " "}, {"user_id": "sam"},
])
def test_history_rejects_invalid_ranges_filters_and_other_user_arguments(pete, args):
    with pytest.raises(ValueError):
        tools.run_tool("pete", "get_spending_history", args)


def test_pete_supports_timeline_twin_savings_and_student_tips(pete):
    timeline = pete.post("/users/pete/timeline", json={"days": 90, "overrides": {"income_multiplier": 0.5}})
    assert timeline.status_code == 200
    result = timeline.json()
    assert len(result["days"]) == 91
    assert any(e["label"] == "Campus Cafe weekly wages" for e in result["events"])
    assert result["scenario"]["first_below_zero"] == "2027-01-14"
    simulations = pete.get("/users/pete/simulations?days=90&sims=100")
    assert simulations.status_code == 200 and simulations.json()["simulations"] == 100
    deposits = pete.get("/users/pete/deposit-ideas")
    assert deposits.status_code == 200 and len(deposits.json()["ideas"]) == 4
    assert {"student_council_tax", "railcard_16_25"} <= {t.id for t in rules.all_tips("pete")}
    assert pete.get("/users/pete/spending-forecast").status_code == 200
