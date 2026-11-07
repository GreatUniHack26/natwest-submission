"""Savings-goal and emergency-fund planner (issue #42).

Pure and deterministic: no DB, no LLM, no network. Money is Decimal, rounded to the penny.
The user-level wrappers fetch data ONLY through `backend.data` and `backend.forecast`;
they never persist anything (the suggested pot is returned unsaved, pass it to `add_pot`).

Monthly saving
  months   = number of whole months from today to the target date, counted with month-end
             clamping (Jan 31 + 1 month = Feb 28); at least 1. A part-month at the end is
             ignored, which makes the plan slightly stricter, never looser.
  required = (target - already saved) / months, rounded UP to the penny (never understates).
  If already saved >= target the goal is met: feasible, required 0.

"Fits the forecast" (exact rule, all three must hold)
  Let the forecast points be (date, low, expected, high) and today the plan date.
  1. Usable trajectory: at least two points spanning more than 0 days, else NO_FORECAST.
  2. surplus_per_month = (expected_last - expected_first) / days_between * 365.25/12,
     rounded DOWN to the penny; available = max(surplus_per_month, 0).
     Requires required <= available.            (else EXCEEDS_SURPLUS)
  3. Setting `required` aside at each monthly date (today + 1 month, + 2 months, ... up to
     the target date) must keep the LOW band >= 0 at every forecast point:
     low_i - required * deposits_made_by(date_i) >= 0.   (else BREACHES_LOW_BAND)
  The forecast balance is treated as spendable money; money already in pots is not added.

Emergency fund
  target = 3 x average monthly essential spend. Essential spend = sum of negative amounts of
  transactions with kind == "need". Window = up to the last 6 COMPLETE calendar months
  before today's month; a first history month that starts after the 1st is partial and is
  skipped. Months with no needs still count in the divisor. Existing money is credited
  from a pot named "Emergency fund" (case-insensitive). The remaining amount is spread
  over `build_months` (default 12) and checked with the same rule as any goal.
"""
import calendar
import datetime as dt
import re
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Literal, Optional

from pydantic import BaseModel

from backend import config
from contracts.schemas import ForecastPoint, Pot, Transaction

PENNY = Decimal("0.01")
EMERGENCY_MONTHS = 3
ESSENTIALS_WINDOW = 6
FORECAST_HORIZON_DAYS = 90
EMERGENCY_POT_NAME = "Emergency fund"
AVG_MONTH_DAYS = Decimal("365.25") / Decimal(12)

Reason = Literal[
    "ok", "already_funded", "exceeds_surplus", "breaches_low_band", "no_forecast", "no_history"
]


class GoalPlan(BaseModel):
    feasible: bool
    reason: Reason
    explanation: str
    goal_name: str
    target_amount: float
    target_date: Optional[dt.date] = None
    already_saved: float = 0.0
    remaining: float = 0.0
    months: int = 0
    required_monthly: float = 0.0
    available_monthly: float = 0.0  # projected monthly surplus (floored at 0)
    shortfall: float = 0.0  # required_monthly - available_monthly when surplus is too small
    low_band_gap: float = 0.0  # worst amount by which the low band would dip below 0
    suggested_pot: Optional[Pot] = None  # NOT saved; pass to backend.data.add_pot


class EmergencyFundPlan(BaseModel):
    feasible: bool
    reason: Reason
    explanation: str
    monthly_essentials: float = 0.0
    window_months: int = 0
    target_amount: float = 0.0
    plan: Optional[GoalPlan] = None  # None when there is no essential-spend history


def _d(x) -> Decimal:
    return Decimal(str(x)).quantize(PENNY, rounding=ROUND_HALF_UP)


def _add_months(d: dt.date, months: int) -> dt.date:
    year, month0 = divmod(d.year * 12 + d.month - 1 + months, 12)
    month = month0 + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def months_between(start: dt.date, end: dt.date) -> int:
    """Whole months from start to end (month-end clamped), at least 1 when end > start."""
    k = 0
    while _add_months(start, k + 1) <= end:
        k += 1
    return max(k, 1)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "goal"


def plan_goal_core(
    target_amount: float,
    target_date: dt.date,
    current_saved: float,
    forecast_points: list[ForecastPoint],
    today: dt.date,
    goal_name: str = "Savings goal",
) -> GoalPlan:
    """Pure core: required monthly saving and whether it fits the forecast (see module doc)."""
    if not target_amount or target_amount <= 0:
        raise ValueError("target_amount must be positive")
    if current_saved < 0:
        raise ValueError("current_saved must not be negative")
    if target_date <= today:
        raise ValueError("target_date must be after today")

    target, saved = _d(target_amount), _d(current_saved)
    remaining = max(target - saved, Decimal(0))
    months = months_between(today, target_date)
    base = dict(goal_name=goal_name, target_amount=float(target), target_date=target_date,
                already_saved=float(saved))
    if remaining == 0:
        return GoalPlan(
            feasible=True, reason="already_funded", months=months,
            explanation=f"Already funded: £{saved:.2f} saved covers the £{target:.2f} target, "
                        "so nothing more needs saving each month.", **base)

    required = (remaining / months).quantize(PENNY, rounding=ROUND_CEILING)
    base.update(remaining=float(remaining), months=months, required_monthly=float(required))
    need = (f"£{required:.2f} a month for {months} month{'s' if months != 1 else ''} "
            f"(£{remaining:.2f} still to save by {target_date})")

    pts = sorted(forecast_points, key=lambda p: p.date)
    days = (pts[-1].date - pts[0].date).days if len(pts) >= 2 else 0
    if days <= 0:
        return GoalPlan(
            feasible=False, reason="no_forecast",
            explanation=f"Needs {need}, but there is no usable forecast to check it against, "
                        "so it cannot be confirmed as affordable.", **base)

    surplus = ((_d(pts[-1].expected) - _d(pts[0].expected)) * AVG_MONTH_DAYS / Decimal(days)).quantize(
        PENNY, rounding=ROUND_DOWN)
    available = max(surplus, Decimal(0))
    base["available_monthly"] = float(available)

    worst = Decimal(0)  # largest amount the low band would be below zero
    for p in pts:
        made = min(sum(1 for i in range(1, months + 1) if _add_months(today, i) <= p.date), months)
        worst = max(worst, required * made - _d(p.low))
    base["low_band_gap"] = float(worst)

    if required > available:
        short = required - available
        base["shortfall"] = float(short)
        return GoalPlan(
            feasible=False, reason="exceeds_surplus",
            explanation=f"Needs {need}, but the forecast only leaves about £{available:.2f} a month "
                        f"(projected balance change £{surplus:.2f} a month), "
                        f"£{short:.2f} a month short.", **base)
    if worst > 0:
        return GoalPlan(
            feasible=False, reason="breaches_low_band",
            explanation=f"Needs {need}. The average surplus of £{available:.2f} a month would cover it, "
                        f"but in the worst case the balance would dip £{worst:.2f} below zero "
                        "once the savings are set aside.", **base)
    return GoalPlan(
        feasible=True, reason="ok",
        explanation=f"Affordable: needs {need}; the forecast leaves about £{available:.2f} a month "
                    "and the low band stays above zero.", **base)


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y, m - 1) if m > 1 else (y - 1, 12)


def _next_month(y: int, m: int) -> tuple[int, int]:
    return (y, m + 1) if m < 12 else (y + 1, 1)


def monthly_essentials(
    transactions: list[Transaction], today: dt.date, window: int = ESSENTIALS_WINDOW
) -> tuple[Decimal, int]:
    """(average monthly need-spend, months averaged) over the trailing complete months.

    Only kind == "need" with negative amounts count (income and wants are ignored).
    Returns (0, 0) when there is no complete month of history.
    """
    if not transactions:
        return Decimal(0), 0
    first = min(t.date for t in transactions)
    earliest = (first.year, first.month) if first.day == 1 else _next_month(first.year, first.month)
    months: list[tuple[int, int]] = []
    ym = _prev_month(today.year, today.month)
    while len(months) < window and ym >= earliest:
        months.append(ym)
        ym = _prev_month(*ym)
    if not months:
        return Decimal(0), 0
    wanted = set(months)
    total = sum((-_d(t.amount) for t in transactions
                 if t.kind == "need" and t.amount < 0 and (t.date.year, t.date.month) in wanted), Decimal(0))
    return (total / len(months)).quantize(PENNY, rounding=ROUND_HALF_UP), len(months)


def plan_emergency_fund_core(
    transactions: list[Transaction],
    current_saved: float,
    forecast_points: list[ForecastPoint],
    today: dt.date,
    build_months: int = 12,
) -> EmergencyFundPlan:
    """Pure core: target = 3 x average monthly essentials, spread over `build_months`."""
    if build_months < 1:
        raise ValueError("build_months must be at least 1")
    if current_saved < 0:
        raise ValueError("current_saved must not be negative")
    avg, n = monthly_essentials(transactions, today)
    if n == 0 or avg <= 0:
        return EmergencyFundPlan(
            feasible=False, reason="no_history", window_months=n,
            explanation="There is no complete month of essential (need) spending in the history, "
                        "so an emergency-fund target cannot be worked out yet.")
    target = (avg * EMERGENCY_MONTHS).quantize(PENNY, rounding=ROUND_HALF_UP)
    plan = plan_goal_core(float(target), _add_months(today, build_months), current_saved,
                          forecast_points, today, goal_name=EMERGENCY_POT_NAME)
    return EmergencyFundPlan(
        feasible=plan.feasible, reason=plan.reason, monthly_essentials=float(avg), window_months=n,
        target_amount=float(target), plan=plan,
        explanation=f"Target £{target:.2f} = {EMERGENCY_MONTHS} x £{avg:.2f} essential spend a month "
                    f"(average of the last {n} complete month{'s' if n != 1 else ''}). {plan.explanation}")


def _forecast_points(user_id: str) -> list[ForecastPoint]:
    """Forecast points via the public interface; [] when no usable forecast is available."""
    from backend import forecast as fc

    try:
        return list(fc.forecast(user_id, FORECAST_HORIZON_DAYS).points)
    except Exception:  # forecast data missing/unavailable: report infeasible, never crash
        return []


def _matching_pot(user_id: str, name: str) -> Optional[Pot]:
    from backend import data

    return next((p for p in data.get_pots(user_id) if p.name.strip().lower() == name.strip().lower()), None)


def plan_goal(
    user_id: str, target_amount: float, target_date: dt.date, goal_name: str = "Savings goal"
) -> GoalPlan:
    """Plan a dated savings goal for a user. Never persists; see `suggested_pot`.

    Money already in a pot with the same name as `goal_name` is credited. A pot is suggested
    only when the plan is feasible, still needs saving, and no pot of that name exists; its
    `amount` is the first monthly instalment (`required_monthly`) and `due_date` is the target.
    """
    if not target_amount or target_amount <= 0:  # validate before touching any data source
        raise ValueError("target_amount must be positive")
    if target_date <= config.TODAY:
        raise ValueError("target_date must be after today")
    existing = _matching_pot(user_id, goal_name)
    plan = plan_goal_core(target_amount, target_date, existing.amount if existing else 0.0,
                          _forecast_points(user_id), config.TODAY, goal_name)
    if plan.feasible and plan.required_monthly > 0 and existing is None:
        pot = Pot(id=f"{user_id}-goal-{_slug(goal_name)}", user_id=user_id, name=goal_name,
                  amount=plan.required_monthly, due_date=target_date)
        plan = plan.model_copy(update={"suggested_pot": pot})
    return plan


def plan_emergency_fund(user_id: str, build_months: int = 12) -> EmergencyFundPlan:
    """Emergency-fund plan for a user: 3 x monthly essentials, open-ended pot, never persisted."""
    from backend import data

    existing = _matching_pot(user_id, EMERGENCY_POT_NAME)
    result = plan_emergency_fund_core(
        data.get_transactions(user_id), existing.amount if existing else 0.0,
        _forecast_points(user_id), config.TODAY, build_months)
    p = result.plan
    if p and p.feasible and p.required_monthly > 0 and existing is None:
        pot = Pot(id=f"{user_id}-emergency-fund", user_id=user_id, name=EMERGENCY_POT_NAME,
                  amount=p.required_monthly, due_date=None)
        result = result.model_copy(update={"plan": p.model_copy(update={"suggested_pot": pot})})
    return result
