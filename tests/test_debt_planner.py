"""Issue #43 unit tests: debt planner. Expected numbers are hand-calculated, month by month."""
import datetime as dt
import random

import pytest
from pydantic import ValidationError

from backend.planner import Debt, plan_debt

START = dt.date(2026, 11, 7)


def plan(debts, budget, **kw):
    return plan_debt(debts, budget, start_date=START, **kw)


def totals(strategy, month):
    return round(sum(p.payment for p in strategy.payments if p.month == month), 2)


# Two debts. A: £200 @24% (2%/mo) min 20.  B: £100 @12% (1%/mo) min 10.  Budget £100.
TWO = [Debt(name="A", balance=200, apr=24, minimum=20), Debt(name="B", balance=100, apr=12, minimum=10)]


# ---- hand-calculated examples (acceptance: matches hand-calculated examples) -------------

def test_single_debt_matches_hand_calculation():
    """£1,000 @12%, £100/month: balance 910.00, 819.10, ... final month pays 58.98 incl. 0.58 interest."""
    s = plan([Debt(name="X", balance=1000, apr=12, minimum=25)], 100).avalanche
    assert (s.months, s.total_interest, s.total_paid) == (11, 58.98, 1058.98)
    assert s.payments[0].interest == 10.00 and s.payments[0].balance_after == 910.00
    assert s.payments[1].interest == 9.10 and s.payments[1].balance_after == 819.10
    assert s.payments[-1].interest == 0.58 and s.payments[-1].payment == 58.98
    assert s.payments[-1].balance_after == 0
    assert s.payoff_date == dt.date(2027, 10, 7)


def test_avalanche_hand_calculation():
    """m1: A 204->114.00, B 101->91.00; m2: A 116.28->26.28, B 91.91->81.91;
    m3: A cleared with 26.81, B 82.73->9.54; m4: B 9.64 cleared. Interest 6.81 + 2.83."""
    a = plan(TWO, 100).avalanche
    assert (a.months, a.total_interest, a.total_paid) == (4, 9.64, 309.64)
    assert a.payoff_order == ["A", "B"]
    after = {(p.month, p.debt): p.balance_after for p in a.payments}
    assert after[(1, "A")] == 114.00 and after[(1, "B")] == 91.00
    assert after[(2, "A")] == 26.28 and after[(2, "B")] == 81.91
    assert after[(3, "A")] == 0 and after[(3, "B")] == 9.54
    assert after[(4, "B")] == 0
    assert [totals(a, m) for m in (1, 2, 3, 4)] == [100, 100, 100, 9.64]


def test_snowball_hand_calculation():
    """m1: B 101->21.00, A 204->184.00; m2: B cleared 21.21, A 187.68->108.89;
    m3: A 111.07->11.07; m4: A 11.29 cleared. Interest 11.29."""
    s = plan(TWO, 100).snowball
    assert (s.months, s.total_interest, s.total_paid) == (4, 11.29, 311.29)
    assert s.payoff_order == ["B", "A"]
    after = {(p.month, p.debt): p.balance_after for p in s.payments}
    assert after[(1, "B")] == 21.00 and after[(1, "A")] == 184.00
    assert after[(2, "B")] == 0 and after[(2, "A")] == 108.89
    assert after[(3, "A")] == 11.07 and after[(4, "A")] == 0
    assert [totals(s, m) for m in (1, 2, 3, 4)] == [100, 100, 100, 11.29]


def test_avalanche_saves_interest_and_the_difference_is_reported():
    p = plan(TWO, 100)
    assert p.interest_saved_by_avalanche == 1.65
    assert p.avalanche.payoff_date == p.snowball.payoff_date == dt.date(2027, 3, 7)


def test_payment_dates_step_monthly_and_clamp_month_end():
    s = plan([Debt(name="X", balance=300, apr=0, minimum=10)], 100, ).avalanche
    assert [p.date for p in s.payments] == [dt.date(2026, 12, 7), dt.date(2027, 1, 7), dt.date(2027, 2, 7)]
    jan31 = plan_debt([Debt(name="X", balance=300, apr=0, minimum=10)], 100, start_date=dt.date(2027, 1, 31))
    assert [p.date for p in jan31.avalanche.payments] == [dt.date(2027, 2, 28), dt.date(2027, 3, 31), dt.date(2027, 4, 30)]


def test_zero_apr_is_simple_division():
    s = plan([Debt(name="X", balance=250, apr=0, minimum=10)], 100).avalanche
    assert (s.months, s.total_interest, s.total_paid) == (3, 0, 250)


# ---- the cap: essentials and pots are protected ---------------------------------------------

def test_month_one_is_capped_by_safe_to_spend_later_months_by_budget():
    p = plan(TWO, 100, safe_to_spend=50)
    for s in (p.avalanche, p.snowball):
        assert s.feasible and totals(s, 1) == 50 and totals(s, 2) == 100
    assert p.cap_month_1 == 50 and p.monthly_budget == 100
    # hand check, avalanche month 1: mins 30 + extra 20 to A -> A 204-40=164.00, B 101-10=91.00
    after = {(x.month, x.debt): x.balance_after for x in p.avalanche.payments}
    assert after[(1, "A")] == 164.00 and after[(1, "B")] == 91.00


def test_safe_to_spend_above_budget_does_not_raise_the_cap():
    assert totals(plan(TWO, 100, safe_to_spend=5000).avalanche, 1) == 100


def test_never_schedules_more_than_safe_to_spend_in_month_one():
    for safe in (0, 1, 15, 29.99, 30, 31, 99.99):
        for s in plan(TWO, 100, safe_to_spend=safe).avalanche, plan(TWO, 100, safe_to_spend=safe).snowball:
            assert totals(s, 1) <= safe + 1e-9, (safe, s.strategy)


def test_cap_below_minimums_is_flagged_with_shortfall_and_explanation():
    p = plan(TWO, 100, safe_to_spend=20)
    for s in (p.avalanche, p.snowball):
        assert not s.feasible and s.reason == "minimums_exceed_cap"
        assert s.shortfall == 10.00 and s.months is None and s.payoff_date is None
        assert "£30.00" in s.explanation and "£20.00" in s.explanation and "£10.00" in s.explanation
        assert totals(s, 1) == 20 and s.first_month_total == 20
        assert {x.month for x in s.payments} == {1}  # stops: nothing is scheduled after a failure
    # shortfall protects the dearest debt: A (24%) is paid before B (12%)
    paid = {x.debt: x.payment for x in p.avalanche.payments}
    assert paid == {"A": 20.00, "B": 0.0}
    assert p.interest_saved_by_avalanche == 0.0


def test_negative_safe_to_spend_means_nothing_can_be_paid():
    p = plan(TWO, 100, safe_to_spend=-80)
    assert p.cap_month_1 == 0 and not p.avalanche.feasible
    assert p.avalanche.first_month_total == 0 and p.avalanche.shortfall == 30.00


def test_budget_below_minimums_is_infeasible():
    s = plan(TWO, 25).avalanche
    assert not s.feasible and s.reason == "minimums_exceed_cap" and s.shortfall == 5.00


def test_never_pays_off_is_reported_not_looped_forever():
    s = plan([Debt(name="X", balance=10_000, apr=30, minimum=100)], 200).avalanche
    assert not s.feasible and s.reason == "never_pays_off" and s.months is None
    assert len(s.payments) == 600 and "not paid off" in s.explanation


def test_max_months_is_respected():
    s = plan([Debt(name="X", balance=1000, apr=12, minimum=25)], 100, max_months=5).avalanche
    assert not s.feasible and s.reason == "never_pays_off" and len(s.payments) == 5


# ---- allocation rules ------------------------------------------------------------------------

def test_avalanche_targets_highest_apr_and_snowball_smallest_balance():
    a = plan(TWO, 100).avalanche
    s = plan(TWO, 100).snowball
    first = lambda st, d: next(x for x in st.payments if x.month == 1 and x.debt == d).payment
    assert (first(a, "A"), first(a, "B")) == (90, 10)
    assert (first(s, "A"), first(s, "B")) == (20, 80)


def test_ties_are_broken_deterministically():
    same = [Debt(name="Z", balance=100, apr=10, minimum=5), Debt(name="A", balance=100, apr=10, minimum=5)]
    p1, p2 = plan(same, 50), plan(list(reversed(same)), 50)
    assert p1.avalanche.payments == p2.avalanche.payments  # input order does not matter
    assert p1.avalanche.payoff_order == p2.avalanche.payoff_order


def test_extra_rolls_over_when_a_target_is_cleared():
    d = [Debt(name="Small", balance=30, apr=0, minimum=5), Debt(name="Big", balance=500, apr=0, minimum=5)]
    s = plan(d, 100).snowball
    month1 = {x.debt: x.payment for x in s.payments if x.month == 1}
    assert month1 == {"Small": 30.00, "Big": 70.00}  # Small cleared, the rest flows to Big


def test_minimum_is_never_more_than_the_balance():
    s = plan([Debt(name="X", balance=8, apr=0, minimum=50)], 100).avalanche
    assert s.months == 1 and s.payments[0].payment == 8.00


def test_zero_minimum_still_gets_extra_money():
    s = plan([Debt(name="X", balance=100, apr=0, minimum=0)], 50).avalanche
    assert s.months == 2


# ---- edge cases and validation --------------------------------------------------------------

def test_no_debts_is_a_trivial_plan():
    p = plan([], 100)
    for s in (p.avalanche, p.snowball):
        assert s.feasible and s.payments == [] and s.total_interest == 0 and s.payoff_date == START


def test_zero_balance_debts_are_ignored():
    p = plan([Debt(name="Paid", balance=0, apr=20, minimum=10), *TWO], 100)
    assert p.avalanche.total_interest == 9.64 and "Paid" not in {x.debt for x in p.avalanche.payments}


def test_zero_budget_with_debts_is_infeasible():
    assert plan(TWO, 0).avalanche.reason == "minimums_exceed_cap"


@pytest.mark.parametrize("bad", [
    {"name": "", "balance": 1, "apr": 1, "minimum": 1},
    {"name": "x", "balance": -1, "apr": 1, "minimum": 1},
    {"name": "x", "balance": 1, "apr": -1, "minimum": 1},
    {"name": "x", "balance": 1, "apr": 1, "minimum": -1},
    {"name": "x", "balance": 1, "apr": 5000, "minimum": 1},
])
def test_invalid_debts_are_rejected(bad):
    with pytest.raises(ValidationError):
        Debt(**bad)


def test_negative_budget_and_duplicate_names_raise():
    with pytest.raises(ValueError, match="budget"):
        plan(TWO, -1)
    with pytest.raises(ValueError, match="unique"):
        plan([TWO[0], TWO[0]], 100)


def test_defaults_start_date_to_config_today(monkeypatch):
    from backend import config

    monkeypatch.setattr(config, "TODAY", dt.date(2030, 1, 15))
    s = plan_debt([Debt(name="X", balance=50, apr=0, minimum=10)], 100).avalanche
    assert s.payments[0].date == dt.date(2030, 2, 15)


def test_inputs_are_not_mutated_and_result_is_deterministic():
    snapshot = [d.model_copy() for d in TWO]
    first = plan(TWO, 100)
    assert TWO == snapshot and plan(TWO, 100) == first


# ---- invariants over many random inputs -------------------------------------------------------

def _random_case(rng):
    debts = [
        Debt(name=f"d{i}", balance=round(rng.uniform(50, 5000), 2), apr=round(rng.uniform(0, 40), 1),
             minimum=round(rng.uniform(5, 120), 2))
        for i in range(rng.randint(1, 5))
    ]
    budget = round(sum(d.minimum for d in debts) + rng.uniform(0, 600), 2)
    safe = rng.choice([None, round(rng.uniform(0, 1500), 2)])
    return debts, budget, safe


@pytest.mark.parametrize("seed", range(40))
def test_invariants_hold_for_random_inputs(seed):
    debts, budget, safe = _random_case(random.Random(seed))
    p = plan(debts, budget, safe_to_spend=safe)
    principal = round(sum(d.balance for d in debts), 2)
    for s in (p.avalanche, p.snowball):
        cap1 = p.cap_month_1
        for m in {x.month for x in s.payments}:
            assert totals(s, m) <= (cap1 if m == 1 else budget) + 1e-6          # never above the cap
        assert all(x.payment >= 0 and x.balance_after >= 0 for x in s.payments)  # no negatives
        by_debt = {}
        for x in s.payments:
            by_debt.setdefault(x.debt, []).append(x)
        for name, rows in by_debt.items():  # balances chain: previous + interest - payment
            prev = next(d.balance for d in debts if d.name == name)
            for r in rows:
                assert r.balance_after == pytest.approx(prev + r.interest - r.payment, abs=0.005)
                prev = r.balance_after
        if s.feasible:
            assert all(r[-1].balance_after == 0 for r in by_debt.values())
            assert s.total_paid == pytest.approx(principal + s.total_interest, abs=0.01)  # money adds up
            assert s.months == max(x.month for x in s.payments) and s.payoff_date == s.payments[-1].date
            assert set(s.payoff_order) == {d.name for d in debts}
    if p.avalanche.feasible and p.snowball.feasible:
        assert p.avalanche.total_interest <= p.snowball.total_interest + 0.05  # avalanche is never worse
        assert p.avalanche.months <= p.snowball.months + 1


def test_planner_is_pure_no_database_or_llm_imports():
    import backend.planner.debt as mod
    import inspect

    src = inspect.getsource(mod)
    assert "sqlite3" not in src and "anthropic" not in src and "repository" not in src
