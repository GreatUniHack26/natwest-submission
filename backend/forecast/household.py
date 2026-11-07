"""Household oversight of separately owned balances, not a shared bank account.

Repository balances/pots must each have one owner. Duplicate pot IDs are
rejected. Per-member low/high bounds add (perfectly correlated uncertainty),
while risk events are recomputed from aggregate daily balances and protection.
Safe amounts add conservatively: another member's future income is not treated
as money already available to pay an individual's bills.
"""
import datetime as dt

from backend import config
from backend.data import repository
from contracts.schemas import BreakdownItem, Forecast, ForecastPoint, SafeToSpend
from .engine import project, risks_for_daily, validate_horizon
from .inputs import ForecastDataUnavailable, load_inputs
from .money import pence, pounds
from .pots import safe_from_inputs
from .recurring import patterns
from .reservations import bill_schedule, protected_on


def household_inputs(household_id: str):
    if config.MOCK_FORECAST:
        raise ForecastDataUnavailable('Household forecasts require real forecast mode and household repository access')
    lookup = getattr(repository, 'get_household_members', None)
    if lookup is None:
        raise ForecastDataUnavailable('Data repository must provide get_household_members(household_id)')
    members = lookup(household_id)
    if not members:
        raise LookupError('Unknown or empty household')
    if any(member.household_id != household_id for member in members):
        raise LookupError('Household membership could not be verified')
    ids = [member.id for member in members]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate household members')
    data = [load_inputs(uid, config.TODAY, household_id=household_id) for uid in sorted(ids)]
    pot_ids = [pot.id for item in data for pot in item.pots]
    if len(pot_ids) != len(set(pot_ids)):
        raise ValueError('Shared pots must be represented once under a single balance owner')
    return data


def household_forecast(household_id: str, horizon: int = 90) -> Forecast:
    validate_horizon(horizon)
    data = household_inputs(household_id)
    daily = [project(item, horizon) for item in data]
    dates = [p.date for p in daily[0]]
    if any([p.date for p in points] != dates for points in daily):
        raise ValueError('Household forecast dates must align')
    combined = [ForecastPoint(date=day, **{field: pounds(sum(pence(getattr(points[index], field)) for points in daily))
                                          for field in ('low','expected','high')}) for index, day in enumerate(dates)]
    protected = {day: 0 for day in dates}
    for item in data:
        bills = bill_schedule([p for p, _ in patterns(item.transactions)], item.as_of + dt.timedelta(days=1), dates[-1])
        for day in dates:
            protected[day] += protected_on(item.pots, bills, day)
    assumptions = [
        'Household expected balances and low/high bounds sum members at matching dates; bands assume perfectly correlated uncertainty.',
        'Each account balance and pot must have exactly one owner. Internal transfers are excluded from consumption/income patterns; no voluntary future transfers are assumed.',
        'Household risk events are recalculated from aggregate daily balances and protected money, not copied from individual warnings.',
        'This is oversight of separately owned money; safe-to-spend conservatively sums individual reservations, without promising transfers between members.',
    ]
    assumptions += [f'Member {item.user_id}: opening contribution £{pounds(item.balance):.2f}; final expected contribution £{points[-1].expected:.2f}.' for item, points in zip(data, daily)]
    return Forecast(user_id=household_id,horizon_days=horizon,points=[p for i,p in enumerate(combined) if i % 7 == 0 or i == horizon],
                    risk_events=risks_for_daily(combined,protected),assumptions=assumptions)


def household_safe_to_spend(household_id: str) -> SafeToSpend:
    data = household_inputs(household_id)
    results = [(item.user_id, safe_from_inputs(item)) for item in data]
    totals = {field: pounds(sum(pence(getattr(result,field)) for _,result in results))
              for field in ('balance','pots_total','upcoming_bills','safe_amount')}
    breakdown = [BreakdownItem(label=f'{uid}: {line.label}',amount=line.amount) for uid,result in results for line in result.breakdown]
    return SafeToSpend(**totals,breakdown=breakdown)
