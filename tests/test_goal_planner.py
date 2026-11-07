"""Unit tests for the goal / emergency-fund planner core (issue #42). Hand-calculated numbers.

Fixed plan date for all tests: TODAY = 2026-11-07. Forecast helper P(offset_days, low, exp).
"""
import copy
import datetime as dt
from pathlib import Path

import pytest

from backend.planner import goal
from backend.planner.goal import (
    months_between, monthly_essentials, plan_emergency_fund_core, plan_goal_core,
)
from contracts.schemas import ForecastPoint, Transaction

TODAY = dt.date(2026, 11, 7)


def P(offset, low, exp, high=None):
    return ForecastPoint(date=TODAY + dt.timedelta(days=offset), low=low, expected=exp,
                         high=exp if high is None else high)


def D(y, m, d):
    return dt.date(y, m, d)


# Forecast with +300 expected over 90 days.
# surplus/month = 300 * 30.4375 / 90 = 9131.25 / 90 = 101.458333 -> rounded DOWN to 101.45
RISING = [P(0, 1000, 1000), P(90, 900, 1300)]
YEAR = D(2027, 11, 7)  # exactly 12 months after TODAY


# ---- monthly saving maths ----------------------------------------------------------------
def test_exact_monthly_saving_and_fit():
    # 1200 / 12 months = 100.00 <= 101.45. Deposits by day 90 (2027-02-05): 2026-12-07, 2027-01-07
    # => 2 x 100 = 200 <= low 900, so the low band stays positive.
    p = plan_goal_core(1200, YEAR, 0, RISING, TODAY)
    assert (p.months, p.required_monthly, p.available_monthly) == (12, 100.00, 101.45)
    assert p.feasible and p.reason == "ok" and p.shortfall == 0 and p.low_band_gap == 0
    assert "100.00" in p.explanation and "101.45" in p.explanation


def test_required_saving_rounds_up_to_the_penny():
    # 1000 / 12 = 83.3333 -> 83.34 (up, never understated)
    assert plan_goal_core(1000, YEAR, 0, RISING, TODAY).required_monthly == 83.34
    # remaining 1000 - 0.10 = 999.90 / 12 = 83.325 -> 83.33 (ceil to pence)
    assert plan_goal_core(1000, YEAR, 0.10, RISING, TODAY).required_monthly == 83.33


def test_existing_savings_reduce_the_requirement():
    # (1200 - 300) / 12 = 75.00
    p = plan_goal_core(1200, YEAR, 300, RISING, TODAY)
    assert (p.already_saved, p.remaining, p.required_monthly) == (300.0, 900.0, 75.0)


# ---- month counting ----------------------------------------------------------------------
def test_month_counting_with_month_end_clamping():
    # Jan 31 + 1 month = Feb 28 (2027): counts as 1 month on Feb 28
    assert months_between(D(2027, 1, 31), D(2027, 2, 28)) == 1
    # Jan 31 + 2 months = Mar 31, so Mar 30 is only 1 whole month, Mar 31 is 2
    assert months_between(D(2027, 1, 31), D(2027, 3, 30)) == 1
    assert months_between(D(2027, 1, 31), D(2027, 3, 31)) == 2
    # leap year: Jan 31 2028 + 1 month = Feb 29
    assert months_between(D(2028, 1, 31), D(2028, 2, 29)) == 1
    assert months_between(D(2028, 1, 31), D(2028, 2, 28)) == 1  # (part month rounds to min 1)
    # under a month away still pays once
    assert months_between(TODAY, TODAY + dt.timedelta(days=10)) == 1
    assert months_between(TODAY, YEAR) == 12


# ---- already funded ----------------------------------------------------------------------
def test_already_funded_goal_needs_nothing_even_without_a_forecast():
    p = plan_goal_core(1200, YEAR, 1500, [], TODAY)
    assert p.feasible and p.reason == "already_funded" and p.required_monthly == 0
    assert "Already funded" in p.explanation and p.suggested_pot is None
    assert plan_goal_core(1200, YEAR, 1200, [], TODAY).required_monthly == 0  # exactly met


# ---- infeasible with explanation ---------------------------------------------------------
def test_infeasible_when_surplus_too_small_reports_shortfall():
    # +150 over 90 days: 150 * 30.4375 / 90 = 4565.625 / 90 = 50.7291 -> 50.72
    # required 100.00 -> shortfall 100.00 - 50.72 = 49.28
    p = plan_goal_core(1200, YEAR, 0, [P(0, 1000, 1000), P(90, 900, 1150)], TODAY)
    assert not p.feasible and p.reason == "exceeds_surplus"
    assert (p.required_monthly, p.available_monthly, p.shortfall) == (100.0, 50.72, 49.28)
    for n in ("100.00", "50.72", "49.28"):
        assert n in p.explanation


def test_falling_balance_has_zero_available():
    p = plan_goal_core(1200, YEAR, 0, [P(0, 1000, 1000), P(56, 100, 200)], TODAY)
    assert not p.feasible and p.available_monthly == 0 and p.shortfall == 100.0
    assert "£0.00" in p.explanation and "100.00" in p.explanation


def test_low_band_breach_is_infeasible_even_if_surplus_covers_it():
    # surplus 101.45 >= 100, but by day 90 two deposits (200) vs low 150 -> gap 50.00
    p = plan_goal_core(1200, YEAR, 0, [P(0, 1000, 1000), P(90, 150, 1300)], TODAY)
    assert not p.feasible and p.reason == "breaches_low_band"
    assert p.low_band_gap == 50.0 and "50.00" in p.explanation


def test_no_usable_forecast_is_infeasible_not_a_crash():
    for pts in ([], [P(0, 1, 1)], [P(0, 1, 1), P(0, 2, 2)]):
        p = plan_goal_core(1200, YEAR, 0, pts, TODAY)
        assert not p.feasible and p.reason == "no_forecast" and p.required_monthly == 100.0
        assert "no usable forecast" in p.explanation


# ---- validation --------------------------------------------------------------------------
@pytest.mark.parametrize("amount,saved,date", [
    (0, 0, YEAR), (-5, 0, YEAR), (100, -1, YEAR), (100, 0, TODAY), (100, 0, TODAY - dt.timedelta(days=1)),
])
def test_invalid_input_raises(amount, saved, date):
    with pytest.raises(ValueError):
        plan_goal_core(amount, date, saved, RISING, TODAY)


def test_invalid_build_months_raises():
    with pytest.raises(ValueError):
        plan_emergency_fund_core([], 0, RISING, TODAY, build_months=0)


# ---- emergency fund ----------------------------------------------------------------------
def tx(i, date, amount, kind, cat="x"):
    return Transaction(id=f"t{i}", user_id="u", date=date, merchant="m", amount=amount, category=cat, kind=kind)


def history(first_day):
    """Months May..Oct 2026 (+ Nov): first row is income (ignored) on `first_day` of May.

    Needs: 600 rent each of May..Oct, plus a 150.50 need in Oct. Wants / income / positive
    need amounts and November needs must all be ignored.
    """
    rows = [tx(0, D(2026, 5, first_day), 3000, "income", "salary")]
    for i, m in enumerate(range(5, 11), start=1):
        rows.append(tx(10 + i, D(2026, m, 2 if m != 5 else 8), -600, "need", "rent"))
        rows.append(tx(20 + i, D(2026, m, 15), -80, "want", "treats"))
    rows.append(tx(30, D(2026, 10, 20), -150.50, "need", "groceries"))
    rows.append(tx(31, D(2026, 10, 21), 25, "need", "refund"))  # positive need: ignored
    rows.append(tx(32, D(2026, 11, 3), -999, "need", "bills"))  # current (incomplete) month: ignored
    return rows


def test_essentials_use_need_kind_only_over_complete_months():
    # History starts on the 1st: May..Oct are 6 complete months.
    # needs = 6 x 600 + 150.50 = 3750.50 ; avg = 625.0833 -> 625.08
    avg, n = monthly_essentials(history(1), TODAY)
    assert (n, float(avg)) == (6, 625.08)


def test_partial_first_month_is_skipped():
    # History starts on May 7 (partial May): window Jun..Oct = 5 months.
    # needs = 5 x 600 + 150.50 = 3150.50 ; avg = 630.10
    avg, n = monthly_essentials(history(7), TODAY)
    assert (n, float(avg)) == (5, 630.10)


def test_emergency_target_is_three_times_essentials():
    # 3 x 630.10 = 1890.30 over 12 months: 1890.30 / 12 = 157.525 -> 157.53 (ceil)
    rich = [P(0, 1000, 1000), P(90, 1000, 2000)]  # surplus 1000*30.4375/90 = 338.19
    r = plan_emergency_fund_core(history(7), 0, rich, TODAY)
    assert r.monthly_essentials == 630.10 and r.window_months == 5 and r.target_amount == 1890.30
    assert r.plan.required_monthly == 157.53 and r.plan.target_date == D(2027, 11, 7)
    assert r.feasible and "1890.30" in r.explanation and "630.10" in r.explanation


def test_existing_emergency_pot_is_credited():
    # target 1890.30 - 300 = 1590.30 ; / 12 = 132.525 -> 132.53
    rich = [P(0, 1000, 1000), P(90, 1000, 2000)]
    r = plan_emergency_fund_core(history(7), 300, rich, TODAY)
    assert r.plan.remaining == 1590.30 and r.plan.required_monthly == 132.53
    done = plan_emergency_fund_core(history(7), 1890.30, [], TODAY)
    assert done.feasible and done.plan.reason == "already_funded"


def test_emergency_fund_infeasible_has_explanation():
    r = plan_emergency_fund_core(history(7), 0, [P(0, 1000, 1000), P(90, 900, 1150)], TODAY)
    assert not r.feasible and r.reason == "exceeds_surplus"
    assert "157.53" in r.explanation and "50.72" in r.explanation


def test_no_history_gives_infeasible_with_explanation():
    for rows in ([], [tx(1, D(2026, 11, 2), -50, "need")], [tx(1, D(2026, 5, 7), 100, "income")]):
        r = plan_emergency_fund_core(rows, 0, RISING, TODAY)
        assert not r.feasible and r.reason == "no_history" and r.plan is None and r.explanation


# ---- determinism, no mutation, purity ----------------------------------------------------
def test_deterministic_and_inputs_not_mutated():
    pts, rows = list(RISING), history(7)
    before = (copy.deepcopy(pts), copy.deepcopy(rows))
    a = plan_goal_core(1200, YEAR, 0, pts, TODAY)
    b = plan_goal_core(1200, YEAR, 0, pts, TODAY)
    assert a == b
    assert plan_emergency_fund_core(rows, 0, pts, TODAY) == plan_emergency_fund_core(rows, 0, pts, TODAY)
    assert (pts, rows) == before


def test_module_source_is_pure():
    src = Path(goal.__file__).read_text()
    for banned in ("sqlite3", "anthropic", "repository", "requests", "urllib", "random", "import os"):
        assert banned not in src, banned
