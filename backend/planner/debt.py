"""Debt escape planner (issue #43): avalanche vs snowball payoff schedules.

Pure and deterministic: no DB, no LLM, no network. All maths is in Decimal, rounded to
the penny (half up) every month, so results match hand calculations exactly.

Model (one step per month, month 1 = the first period after `start_date`):
  1. every active debt accrues interest = balance * APR / 12, rounded to pence;
  2. minimums are paid first (capped at the balance), highest APR first;
  3. whatever the cap leaves is the "extra", aimed at one debt at a time:
       avalanche: highest APR first (ties: smaller balance, then name)
       snowball : smallest balance first (ties: higher APR, then name);
     when a target is cleared, the rest of the extra rolls to the next one.

The cap protects the user's essentials and pots:
  * every month is capped at `monthly_budget`;
  * month 1 is additionally capped at `safe_to_spend` (floored at 0), so the plan never
    schedules a payment that would take safe-to-spend negative.
If the cap cannot cover all minimums, the plan is returned as infeasible with the shortfall
and an explanation (it never schedules more than the cap). A plan that cannot pay the debts
off within `max_months` is also returned as infeasible rather than looping forever.
"""
import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from backend import config

PENNY = Decimal("0.01")
MAX_MONTHS = 600  # 50 years

Reason = Literal["ok", "minimums_exceed_cap", "never_pays_off"]


class Debt(BaseModel):
    name: str = Field(min_length=1)
    balance: float = Field(ge=0)  # £ owed today
    apr: float = Field(ge=0, le=1000)  # percent per year, e.g. 22.9 means 22.9% APR
    minimum: float = Field(ge=0)  # £ minimum monthly payment


class DebtPayment(BaseModel):
    month: int  # 1-based
    date: dt.date
    debt: str
    payment: float
    interest: float  # interest added to this debt this month (before the payment)
    balance_after: float


class StrategyPlan(BaseModel):
    strategy: Literal["avalanche", "snowball"]
    feasible: bool
    reason: Reason
    explanation: str
    months: Optional[int] = None  # months until debt-free; None if not reached
    payoff_date: Optional[dt.date] = None
    total_interest: float  # interest accrued over the schedule
    total_paid: float
    first_month_total: float  # what month 1 asks the user to pay (never above the cap)
    shortfall: float = 0.0  # month-1 minimums the cap could not cover
    payoff_order: list[str]  # debts in the order they are cleared
    payments: list[DebtPayment]


class DebtPlan(BaseModel):
    avalanche: StrategyPlan
    snowball: StrategyPlan
    interest_saved_by_avalanche: float  # snowball interest - avalanche interest (feasible plans)
    cap_month_1: float
    monthly_budget: float


class _Names(BaseModel):
    names: list[str]

    @model_validator(mode="after")
    def _unique(self):
        if len(set(self.names)) != len(self.names):
            raise ValueError("Debt names must be unique")
        return self


def _d(x) -> Decimal:
    return Decimal(str(x)).quantize(PENNY, rounding=ROUND_HALF_UP)


def _f(x: Decimal) -> float:
    return float(x)


def _add_months(d: dt.date, months: int) -> dt.date:
    year, month0 = divmod(d.year * 12 + d.month - 1 + months, 12)
    month = month0 + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def plan_debt(
    debts: list[Debt],
    monthly_budget: float,
    safe_to_spend: Optional[float] = None,
    start_date: Optional[dt.date] = None,
    max_months: int = MAX_MONTHS,
) -> DebtPlan:
    """Avalanche and snowball schedules for `debts` under a monthly budget (£).

    `safe_to_spend` (£, optional) additionally caps month 1. `start_date` defaults to
    config.TODAY. Raises ValueError for a negative budget or duplicate debt names.
    """
    if monthly_budget < 0:
        raise ValueError("monthly_budget must not be negative")
    _Names(names=[d.name for d in debts])
    start = start_date or config.TODAY
    budget = _d(monthly_budget)
    cap1 = budget if safe_to_spend is None else min(budget, max(_d(safe_to_spend), Decimal(0)))
    plans = {s: _simulate(s, debts, budget, cap1, start, max_months) for s in ("avalanche", "snowball")}
    both_ok = plans["avalanche"].feasible and plans["snowball"].feasible
    saved = (
        round(plans["snowball"].total_interest - plans["avalanche"].total_interest, 2) if both_ok else 0.0
    )
    return DebtPlan(
        avalanche=plans["avalanche"], snowball=plans["snowball"],
        interest_saved_by_avalanche=saved, cap_month_1=_f(cap1), monthly_budget=_f(budget),
    )


def _target_key(strategy: str, balance: Decimal, apr: Decimal, name: str):
    if strategy == "avalanche":
        return (-apr, balance, name)
    return (balance, -apr, name)


def _simulate(
    strategy: str, debts: list[Debt], budget: Decimal, cap1: Decimal, start: dt.date, max_months: int
) -> StrategyPlan:
    bal = {d.name: _d(d.balance) for d in debts if _d(d.balance) > 0}
    apr = {d.name: Decimal(str(d.apr)) for d in debts}
    mins = {d.name: _d(d.minimum) for d in debts}
    payments: list[DebtPayment] = []
    order: list[str] = []
    total_interest = total_paid = first_total = shortfall = Decimal(0)
    feasible, reason, explanation = True, "ok", ""
    month = 0

    while bal and month < max_months:
        month += 1
        cap = cap1 if month == 1 else budget
        date = _add_months(start, month)
        interest = {n: (b * apr[n] / Decimal(1200)).quantize(PENNY, rounding=ROUND_HALF_UP) for n, b in bal.items()}
        for n in bal:
            bal[n] += interest[n]
        total_interest += sum(interest.values(), Decimal(0))

        # Minimums first, highest APR first (ties: name) so a short cap protects the dearest debt.
        pay = {n: Decimal(0) for n in bal}
        due = {n: min(mins[n], bal[n]) for n in bal}
        left = cap
        for n in sorted(bal, key=lambda n: (-apr[n], n)):
            pay[n] = min(due[n], left)
            left -= pay[n]
        owed = sum(due.values(), Decimal(0))
        if owed > cap:  # cap cannot cover the minimums: report, never overspend
            feasible, reason = False, "minimums_exceed_cap"
            shortfall = owed - cap
            explanation = (
                f"In month {month} the minimum payments total £{owed:.2f} but only £{cap:.2f} can be paid "
                f"without touching essentials and pots (£{shortfall:.2f} short). Payments are limited to £{cap:.2f}."
            )
        else:
            # Extra aimed at one debt at a time, rolling over as each is cleared.
            for n in sorted(bal, key=lambda n: _target_key(strategy, bal[n], apr[n], n)):
                extra = min(left, bal[n] - pay[n])
                pay[n] += extra
                left -= extra

        for n in sorted(bal, key=lambda n: (-apr[n], n)):
            bal[n] -= pay[n]
            payments.append(DebtPayment(
                month=month, date=date, debt=n, payment=_f(pay[n]), interest=_f(interest[n]),
                balance_after=_f(bal[n]),
            ))
        total_paid += sum(pay.values(), Decimal(0))
        if month == 1:
            first_total = sum(pay.values(), Decimal(0))
        order += [n for n in sorted(bal, key=lambda n: (-apr[n], n)) if bal[n] == 0 and n not in order]
        bal = {n: b for n, b in bal.items() if b > 0}
        if not feasible:
            break

    if feasible and bal:
        feasible, reason = False, "never_pays_off"
        explanation = (
            f"These debts are not paid off within {max_months // 12} years at £{budget:.2f} a month: "
            "payments barely cover the interest. A higher budget or lower rates are needed."
        )
    done = feasible and not bal
    if done:
        explanation = (
            f"Debt-free in {month} month{'s' if month != 1 else ''} "
            f"(by {payments[-1].date if payments else start}) paying £{total_interest:.2f} interest."
        )
    if not debts or not payments and not bal:
        done, explanation = feasible, explanation or "No debts to pay off."
    return StrategyPlan(
        strategy=strategy, feasible=feasible, reason=reason, explanation=explanation,
        months=month if done else None,
        payoff_date=(payments[-1].date if payments else start) if done else None,
        total_interest=_f(total_interest), total_paid=_f(total_paid), first_month_total=_f(first_total),
        shortfall=_f(shortfall), payoff_order=order, payments=payments,
    )
