"""Planner agent tools: schemas, validation, hand-calculated results and numbers_used (mock mode)."""
import json
import math

import pytest

from backend import config
from backend import forecast as fc
from backend.agent import planner_tools, tools
from contracts.schemas import BreakdownItem, SafeToSpend

# A: £200 @24% min 20; B: £100 @12% min 10; budget £100 (hand-calculated in test_debt_planner.py)
TWO = [
    {"name": "Card A", "balance": 200, "apr": 24, "minimum": 20},
    {"name": "Loan B", "balance": 100, "apr": 12, "minimum": 10},
]


def _sts(amount):
    return SafeToSpend(balance=amount, pots_total=0, upcoming_bills=0, safe_amount=amount,
                       breakdown=[BreakdownItem(label="x", amount=amount)])


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "MOCK_FORECAST", True)  # safe-to-spend fixture = £210
    monkeypatch.setattr(config, "MOCK_DATA", True)


# ---- registration -----------------------------------------------------------------------------

def test_planner_tools_are_registered_alongside_the_existing_ones():
    names = [t["name"] for t in tools.TOOLS]
    assert {"plan_debt_payoff", "plan_savings_goal", "plan_emergency_fund"} <= set(names)
    assert {"get_safe_to_spend", "simulate_purchase", "get_alerts", "get_forecast"} <= set(names)
    assert len(names) == len(set(names))


@pytest.mark.parametrize("tool", planner_tools.PLANNER_TOOLS, ids=lambda t: t["name"])
def test_tool_definitions_are_well_formed(tool):
    assert tool["description"] and tool["input_schema"]["type"] == "object"
    assert tool["input_schema"]["additionalProperties"] is False
    assert set(tool["input_schema"].get("required", [])) <= set(tool["input_schema"]["properties"])
    json.dumps(tool)  # sent to the LLM as JSON
    assert tools._TOOL_SCHEMAS[tool["name"]] is tool["input_schema"]


# ---- plan_debt_payoff -----------------------------------------------------------------------------

def test_debt_payoff_matches_hand_calculation_and_applies_safe_to_spend():
    out = tools.run_tool("sam", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100})
    assert out["safe_to_spend"] == 210 and out["cap_month_1"] == 100  # min(budget, safe-to-spend)
    assert (out["avalanche"]["months"], out["avalanche"]["total_interest"]) == (4, 9.64)
    assert (out["snowball"]["months"], out["snowball"]["total_interest"]) == (4, 11.29)
    assert out["interest_saved_by_avalanche"] == 1.65
    assert out["avalanche"]["payoff_order"] == ["Card A", "Loan B"]
    assert out["snowball"]["payoff_order"] == ["Loan B", "Card A"]
    assert out["avalanche"]["first_month_payments"] == [
        {"debt": "Card A", "payment": 90.0}, {"debt": "Loan B", "payment": 10.0}]


def test_debt_payoff_caps_month_one_at_the_users_safe_to_spend(monkeypatch):
    monkeypatch.setattr(fc, "safe_to_spend", lambda uid, as_of: _sts(50))
    out = tools.run_tool("sam", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100})
    assert out["cap_month_1"] == 50 and out["avalanche"]["first_month_total"] == 50


def test_debt_payoff_reports_infeasible_when_safe_to_spend_cannot_cover_minimums(monkeypatch):
    monkeypatch.setattr(fc, "safe_to_spend", lambda uid, as_of: _sts(20))
    out = tools.run_tool("sam", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100})
    for s in (out["avalanche"], out["snowball"]):
        assert not s["feasible"] and s["reason"] == "minimums_exceed_cap" and s["shortfall"] == 10.0
        assert s["first_month_total"] == 20 and "£10.00" in s["explanation"]


def test_debt_payoff_fails_loudly_if_safe_to_spend_is_unavailable(monkeypatch):
    def boom(uid, as_of):
        raise RuntimeError("no balance")

    monkeypatch.setattr(fc, "safe_to_spend", boom)
    with pytest.raises(RuntimeError):  # never silently drop the protection for essentials and pots
        tools.run_tool("sam", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100})


def test_debt_numbers_used_contains_every_quotable_figure():
    out = tools.run_tool("sam", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100})
    n = out["numbers_used"]
    assert n["avalanche_total_interest"] == 9.64 and n["snowball_total_interest"] == 11.29
    assert n["interest_saved_by_avalanche"] == 1.65 and n["avalanche_months"] == 4
    assert n["card_a_balance"] == 200 and n["loan_b_minimum"] == 10  # the user's own figures too
    assert n["avalanche_first_payment_card_a"] == 90 and n["snowball_first_payment_loan_b"] == 80
    assert n["cap_month_1"] == 100 and n["monthly_budget"] == 100 and n["safe_to_spend"] == 210
    assert all(isinstance(v, float) and math.isfinite(v) for v in n.values())


def test_debt_result_is_compact_and_json_serialisable():
    long = tools.run_tool("sam", "plan_debt_payoff", {
        "debts": [{"name": "X", "balance": 5000, "apr": 20, "minimum": 60}], "monthly_budget": 70})
    text = json.dumps(long)
    assert len(text) < 6000 and "payments" not in long["avalanche"]  # no per-month schedule sent to the LLM


@pytest.mark.parametrize("args", [
    {"debts": [], "monthly_budget": 100},
    {"debts": "card", "monthly_budget": 100},
    {"debts": TWO},                                                      # missing budget
    {"debts": TWO, "monthly_budget": -1},
    {"debts": TWO, "monthly_budget": "100"},
    {"debts": TWO, "monthly_budget": True},
    {"debts": TWO, "monthly_budget": float("inf")},
    {"debts": TWO, "monthly_budget": 100, "extra": 1},
    {"debts": [{"name": "A", "balance": 1, "apr": 1}], "monthly_budget": 10},                       # missing key
    {"debts": [{"name": "A", "balance": 1, "apr": 1, "minimum": 1, "x": 1}], "monthly_budget": 10},  # extra key
    {"debts": [{"name": "", "balance": 1, "apr": 1, "minimum": 1}], "monthly_budget": 10},
    {"debts": [{"name": "A" * 61, "balance": 1, "apr": 1, "minimum": 1}], "monthly_budget": 10},
    {"debts": [{"name": "A", "balance": True, "apr": 1, "minimum": 1}], "monthly_budget": 10},
    {"debts": [{"name": "A", "balance": -5, "apr": 1, "minimum": 1}], "monthly_budget": 10},
    {"debts": [{"name": "A", "balance": 1, "apr": 5000, "minimum": 1}], "monthly_budget": 10},
    {"debts": [{"name": "A", "balance": 1, "apr": "x", "minimum": 1}], "monthly_budget": 10},
    {"debts": [{"name": "Card A", "balance": 1, "apr": 1, "minimum": 1},
               {"name": "card-a", "balance": 1, "apr": 1, "minimum": 1}], "monthly_budget": 10},  # same slug
    {"debts": [{"name": f"d{i}", "balance": 1, "apr": 1, "minimum": 1} for i in range(11)], "monthly_budget": 10},
    {"debts": ["not a dict"], "monthly_budget": 10},
])
def test_debt_payoff_rejects_bad_arguments(args):
    with pytest.raises(ValueError):
        tools.run_tool("sam", "plan_debt_payoff", args)


# ---- plan_savings_goal -----------------------------------------------------------------------------

def test_savings_goal_reports_required_saving_and_infeasibility_with_explanation():
    # mock-mode forecast falls, so the goal cannot be afforded; the maths of the ask is exact:
    # £600 over the 6 whole months from 2026-11-07 to 2027-05-07 = £100.00 a month.
    out = tools.run_tool("sam", "plan_savings_goal", {"target_amount": 600, "target_date": "2027-05-07",
                                                       "goal_name": "Holiday"})
    assert out["goal_name"] == "Holiday" and out["months"] == 6 and out["required_monthly"] == 100.0
    assert not out["feasible"] and out["reason"] == "exceeds_surplus" and out["shortfall"] > 0
    assert "£100.00" in out["explanation"] and out["suggested_pot"] is None
    n = out["numbers_used"]
    assert n["required_monthly"] == 100.0 and n["target_amount"] == 600 and n["shortfall"] == out["shortfall"]
    json.dumps(out)


def test_savings_goal_defaults_the_name():
    out = tools.run_tool("sam", "plan_savings_goal", {"target_amount": 600, "target_date": "2027-05-07"})
    assert out["goal_name"] == "Savings goal"


@pytest.mark.parametrize("args", [
    {"target_date": "2027-05-07"},
    {"target_amount": 600},
    {"target_amount": 0, "target_date": "2027-05-07"},
    {"target_amount": -5, "target_date": "2027-05-07"},
    {"target_amount": "600", "target_date": "2027-05-07"},
    {"target_amount": True, "target_date": "2027-05-07"},
    {"target_amount": 600, "target_date": "next may"},
    {"target_amount": 600, "target_date": 20270507},
    {"target_amount": 600, "target_date": "2026-11-07"},        # today: not in the future
    {"target_amount": 600, "target_date": "2026-01-01"},        # past
    {"target_amount": 600, "target_date": "2027-05-07", "goal_name": ""},
    {"target_amount": 600, "target_date": "2027-05-07", "goal_name": "x" * 61},
    {"target_amount": 600, "target_date": "2027-05-07", "goal_name": 5},
    {"target_amount": 600, "target_date": "2027-05-07", "extra": 1},
])
def test_savings_goal_rejects_bad_arguments(args):
    with pytest.raises(ValueError):
        tools.run_tool("sam", "plan_savings_goal", args)


# ---- plan_emergency_fund -----------------------------------------------------------------------------

def test_emergency_fund_without_history_says_so_plainly():
    out = tools.run_tool("sam", "plan_emergency_fund", {})  # mock fixtures have no complete month
    assert not out["feasible"] and out["reason"] == "no_history" and out["plan"] is None
    assert out["numbers_used"] == {"monthly_essentials": 0.0, "target_amount": 0.0}


@pytest.mark.parametrize("bad", [0, 61, -1, "12", 12.5, True, []])
def test_emergency_fund_rejects_bad_build_months(bad):
    with pytest.raises(ValueError):
        tools.run_tool("sam", "plan_emergency_fund", {"build_months": bad})


def test_emergency_fund_rejects_unknown_arguments():
    with pytest.raises(ValueError):
        tools.run_tool("sam", "plan_emergency_fund", {"months": 12})


# ---- nothing is ever saved -----------------------------------------------------------------------------

def test_tools_never_create_pots(monkeypatch):
    from backend import data

    monkeypatch.setattr(data, "add_pot", lambda pot: pytest.fail("a tool tried to create a pot"))
    tools.run_tool("sam", "plan_savings_goal", {"target_amount": 600, "target_date": "2027-05-07"})
    tools.run_tool("sam", "plan_emergency_fund", {})
    tools.run_tool("sam", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100})
