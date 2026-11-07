"""Daily time-travel view: Monte Carlo fan + expected line + protected-money floor + dated events.

Combines the deterministic projection (engine.project) with the Monte Carlo
futures (montecarlo._run) so the UI can show *why* the line moves (bills, pay)
and *how sure* the twin is (p10-p90 spread, chance below zero each day).
"""
import datetime as dt

from backend import config
from .engine import project, risks_for_daily, validate_horizon
from .inputs import load_inputs
from .money import pence, pounds
from .montecarlo import DEFAULT_SIMS, _quantile, _run
from .recurring import occurrences, patterns
from .reservations import bill_schedule, protected_on, remaining_pots
from .scenarios import parse_overrides


def _label(merchant: str) -> str:
    return merchant.strip() or 'Payment'


def timeline(user_id: str, horizon_days: int = 90, overrides: dict | None = None, sims: int = DEFAULT_SIMS) -> dict:
    validate_horizon(horizon_days)
    if horizon_days > 180:
        raise ValueError('horizon_days must be at most 180')
    as_of = config.TODAY
    data = load_inputs(user_id, as_of)
    end = as_of + dt.timedelta(days=horizon_days)
    days = [as_of + dt.timedelta(days=i) for i in range(horizon_days + 1)]

    expected = project(data, horizon_days)
    items = [item for item, _ in patterns(data.transactions)]
    bills = bill_schedule(items, as_of + dt.timedelta(days=1), end)
    pots = remaining_pots(data.pots, data.transactions, as_of)
    protected = {day: protected_on(pots, bills, day) for day in days}
    risks = risks_for_daily(expected, protected)

    paths = _run(data, horizon_days, sims, income_on=True, tag='base')
    rows = []
    for i, day in enumerate(days):
        column = sorted(path[i] for path in paths)
        rows.append({
            'date': day.isoformat(),
            'expected': expected[i].expected,
            'p10': pounds(_quantile(column, 0.10)),
            'p50': pounds(_quantile(column, 0.50)),
            'p90': pounds(_quantile(column, 0.90)),
            'protected': pounds(protected[day]),
            'chance_below_zero': round(sum(1 for v in column if v < 0) / sims, 3),
        })

    events = []
    for item in items:
        for day in occurrences(item, as_of + dt.timedelta(days=1), end):
            events.append({
                'date': day.isoformat(),
                'label': _label(item.merchant),
                'amount': round(item.amount, 2),
                'kind': 'income' if item.amount > 0 else 'bill',
            })
    for pot in data.pots:
        if pot.due_date and as_of < pot.due_date <= end:
            events.append({'date': pot.due_date.isoformat(), 'label': f'{pot.name} pot due',
                           'amount': round(pot.amount, 2), 'kind': 'pot'})
    events.sort(key=lambda e: (e['date'], e['kind']))

    scenario = None
    if overrides:
        parsed = parse_overrides(overrides, as_of, horizon_days)
        alt = project(data, horizon_days, one_off=parsed.one_off,
                      income_multiplier=parsed.income_multiplier, monthly_cost=parsed.monthly_cost)
        alt_risks = risks_for_daily(alt, protected)
        first_negative = next((p.date.isoformat() for p in alt if p.expected < 0), None)
        scenario = {
            'expected': [p.expected for p in alt],
            'first_below_zero': first_negative,
            'risks': [{'date': r.date.isoformat(), 'severity': r.severity, 'reason': r.reason} for r in alt_risks],
            'assumptions': parsed.assumptions,
            'end_difference': round(alt[-1].expected - expected[-1].expected, 2),
        }

    return {
        'user_id': user_id,
        'horizon_days': horizon_days,
        'simulations': sims,
        'days': rows,
        'events': events,
        'risks': [{'date': r.date.isoformat(), 'severity': r.severity, 'reason': r.reason} for r in risks],
        'first_below_zero': next((r['date'] for r in rows if r['expected'] < 0), None),
        'scenario': scenario,
    }
