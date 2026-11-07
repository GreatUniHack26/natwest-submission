"""Issue #43 integration: planner fed by the forecast module's safe-to-spend and the seeded data."""
import datetime as dt

import pytest

from backend import config, forecast
from backend.data import categoriser, repository
from backend.data.seed import seed
from backend.planner import Debt, plan_debt


def test_month_one_cap_comes_from_the_forecast_safe_to_spend():
    """Mock-mode safe-to-spend card (£210) is the real contract shape the planner will be fed."""
    sts = forecast.safe_to_spend("sam", config.TODAY)
    debts = [Debt(name="Card", balance=1800, apr=29.9, minimum=45), Debt(name="Loan", balance=900, apr=9.9, minimum=40)]
    p = plan_debt(debts, monthly_budget=400, safe_to_spend=sts.safe_amount, start_date=config.TODAY)
    assert p.cap_month_1 == sts.safe_amount == 210
    for s in (p.avalanche, p.snowball):
        assert s.feasible
        assert s.first_month_total == 210  # never above safe-to-spend
        assert sum(x.payment for x in s.payments if x.month == 2) <= 400


def test_negative_safe_to_spend_card_blocks_all_payments():
    sts = forecast.safe_to_spend("sam", config.TODAY).model_copy(update={"safe_amount": -35.0})
    p = plan_debt([Debt(name="Card", balance=500, apr=20, minimum=25)], 200, safe_to_spend=sts.safe_amount)
    assert not p.avalanche.feasible and p.avalanche.first_month_total == 0


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "debt.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    seed()


def test_family_loan_payment_in_seeded_data_drives_a_plan(seeded):
    """The seeded family has a recurring £85 'debt' payment; use it as the loan's minimum."""
    debt_txs = [t for t in repository.get_transactions("maya") if t.category == "debt"]
    assert debt_txs
    minimum = -debt_txs[0].amount
    loan = Debt(name="Provident Loan", balance=1200, apr=39.9, minimum=minimum)
    p = plan_debt([loan], monthly_budget=minimum + 40, start_date=config.TODAY)
    assert p.avalanche.feasible and p.avalanche.total_interest > 0
    assert p.avalanche.payments[0].payment == minimum + 40


def test_plan_respects_a_cap_derived_from_seeded_household_money(seeded):
    """Household money left after pots, as the API serves it, caps month 1."""
    members = repository.get_household_members("h1")
    assert {u.id for u in members} == {"maya", "dan"}
    balance = sum(t.amount for u in members for t in repository.get_transactions(u.id))
    pots = sum(p.amount for u in members for p in repository.get_pots(u.id))
    headroom = round(balance - pots, 2)
    loan = Debt(name="Provident Loan", balance=1200, apr=39.9, minimum=85)
    p = plan_debt([loan], monthly_budget=250, safe_to_spend=headroom, start_date=config.TODAY)
    assert p.avalanche.first_month_total <= max(headroom, 0)
    if headroom < 85:
        assert not p.avalanche.feasible and p.avalanche.reason == "minimums_exceed_cap"


def test_plan_serialises_to_json_for_the_api_or_agent():
    import json

    p = plan_debt([Debt(name="Card", balance=300, apr=20, minimum=20)], 100, start_date=dt.date(2026, 11, 7))
    data = json.loads(p.model_dump_json())
    assert data["avalanche"]["payoff_date"] and isinstance(data["avalanche"]["payments"][0]["date"], str)
    assert type(p).model_validate(data) == p
