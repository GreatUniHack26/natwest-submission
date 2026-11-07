"""Daily cash flows in pence, sampled weekly with exact horizon endpoints.

Opening balance is the repository's close-of-as_of balance. Scheduled flows
start the following day. Daily independent variances add; income amount
variance is added on each due date. Bands are one population standard deviation
and are scenarios, not confidence guarantees. Risks are inspected daily.
"""
import datetime as dt
import math
from decimal import Decimal
from collections import defaultdict

from backend import config
from contracts.schemas import Forecast, ForecastPoint, RiskEvent
from .baseline import weekday_baseline
from .inputs import Inputs, load_inputs
from .money import pence, pounds
from .recurring import add_month, occurrences, patterns, payment_std
from .scenarios import parse_overrides
from .reservations import bill_schedule, protected_on, remaining_pots


def validate_horizon(horizon: int) -> None:
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 7 <= horizon <= 365:
        raise ValueError('horizon_days must be an integer between 7 and 365')


def risks_for_daily(points: list[ForecastPoint], protected: dict[dt.date, int]) -> list[RiskEvent]:
    found = set()
    events = []
    for point in points:
        for key, condition, severity, reason in [
            ('expected', point.expected < 0, 'high', 'Expected balance falls below zero.'),
            ('low', point.low < 0, 'medium', 'Low-band balance falls below zero.'),
            ('pots', protected.get(point.date, 0) > 0 and pence(point.expected) < protected.get(point.date, 0), 'medium', 'Expected balance uses money protected by pots.'),
        ]:
            if condition and key not in found:
                found.add(key)
                events.append(RiskEvent(date=point.date, severity=severity, reason=reason))
    return events


def project(data: Inputs, horizon_days: int, *, one_off: dict[dt.date, int] | None = None, income_multiplier: Decimal = Decimal(1), monthly_cost: int = 0) -> list[ForecastPoint]:
    validate_horizon(horizon_days)
    end = data.as_of + dt.timedelta(days=horizon_days)
    flows = defaultdict(int)
    variances = defaultdict(float)
    for item, observations in patterns(data.transactions):
        for day in occurrences(item, data.as_of + dt.timedelta(days=1), end):
            multiplier = income_multiplier if item.amount > 0 else Decimal(1)
            flows[day] += pence(Decimal(str(item.amount)) * multiplier)
            variances[day] += (payment_std(item, observations) * float(multiplier) * 100) ** 2
    if monthly_cost:
        day = add_month(data.as_of, data.as_of.day)
        while day <= end:
            flows[day] -= monthly_cost
            day = add_month(day, data.as_of.day)
    baseline = weekday_baseline(data.transactions, data.as_of)
    one_off = one_off or {}
    balance, variance = data.balance - one_off.get(data.as_of, 0), 0.0
    points = [ForecastPoint(date=data.as_of, low=pounds(balance), expected=pounds(balance), high=pounds(balance))]
    for offset in range(1, horizon_days + 1):
        day = data.as_of + dt.timedelta(days=offset)
        spend, std = baseline[day.weekday()]
        balance += flows[day] - pence(spend) - one_off.get(day, 0)
        variance += variances[day] + (std * 100) ** 2
        width = round(math.sqrt(variance))
        points.append(ForecastPoint(date=day, low=pounds(balance - width), expected=pounds(balance), high=pounds(balance + width)))
    return points


def response(data: Inputs, daily: list[ForecastPoint], horizon_days: int) -> Forecast:
    bills = bill_schedule([item for item, _ in patterns(data.transactions)], data.as_of + dt.timedelta(days=1), daily[-1].date)
    pots = remaining_pots(data.pots, data.transactions, data.as_of)
    protected = {p.date: protected_on(pots, bills, p.date) for p in daily}
    assumptions = [
        f'Opening balance £{pounds(data.balance):.2f} is the repository balance at close of {data.as_of}.',
        'Recurrences use up to 180 days; everyday spending uses the preceding 84 days; days without recorded spending count as zero. Sparse history may understate spending.',
        'Recurring observations and positive transactions are excluded from everyday spending; refunds do not predict future income.',
        'Monthly schedules preserve calendar dates; irregular income uses its mean observed receipt and cadence, with observed amount variability and income-times-gap-variation timing uncertainty; neither income nor timing is guaranteed.',
        'Low/high bands are expected balance plus/minus one accumulated standard deviation; daily and payment variances are independent.',
        'Pots reserve existing money through their due date. A dated pot funds a bill only with the exact same merchant name and payment date; that allocation is consumed when paid, including matching actual debits already posted on the opening date.',
    ]
    if not data.transactions:
        assumptions.append('No historical transactions: future income and spending are unknown, not proven zero.')
    return Forecast(user_id=data.user_id, horizon_days=horizon_days,
                    points=[p for i, p in enumerate(daily) if i % 7 == 0 or i == horizon_days],
                    risk_events=risks_for_daily(daily, protected), assumptions=assumptions)


def build_forecast(user_id: str, horizon_days: int, overrides: dict, *, as_of: dt.date | None = None) -> Forecast:
    validate_horizon(horizon_days)
    as_of = as_of or config.TODAY
    scenario = parse_overrides(overrides, as_of, horizon_days)
    data = load_inputs(user_id, as_of)
    daily = project(data, horizon_days, one_off=scenario.one_off, income_multiplier=scenario.income_multiplier, monthly_cost=scenario.monthly_cost)
    result = response(data, daily, horizon_days)
    result.assumptions.extend(scenario.assumptions)
    return result
