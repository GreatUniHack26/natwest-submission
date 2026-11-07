"""Household oversight of separately owned balances, not a shared bank account.

Repository balances/pots must each have one owner. Duplicate pot IDs are
rejected. Per-member low/high bounds add (perfectly correlated uncertainty),
while risk events are recomputed from aggregate daily balances and protection.
Reservations use each member's income cutoff; shared funding is allocated once.
Another member's future income is not promised to pay an individual's bills.
"""
import datetime as dt

from backend import config
from backend.data import repository
from contracts.schemas import BreakdownItem, Forecast, ForecastPoint, SafeToSpend
from .engine import project, risks_for_daily, validate_horizon
from .inputs import ForecastDataUnavailable, load_inputs
from .money import pence, pounds
from .pots import bill_reservations
from .recurring import patterns
from .reservations import allocations, bill_schedule, protected_on, unfunded_bills, remaining_pots


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
    pots = remaining_pots([pot for item in data for pot in item.pots],
                          [tx for item in data for tx in item.transactions], data[0].as_of)
    bills = [bill for item in data for bill in bill_schedule([p for p, _ in patterns(item.transactions)], item.as_of + dt.timedelta(days=1), dates[-1])]
    protected = {day: protected_on(pots, bills, day) for day in dates}
    assumptions = [
        'Household expected balances and low/high bounds sum members at matching dates; bands assume perfectly correlated uncertainty.',
        'Each account balance and pot must have exactly one owner. Internal transfers are excluded from consumption/income patterns; no voluntary future transfers are assumed.',
        'Household risk events are recalculated from aggregate daily balances and protected money, not copied from individual warnings.',
        'This is oversight of separately owned money; safe-to-spend uses individual income cutoffs and allocates shared pot funding once across members, without promising transfers between members.',
    ]
    assumptions += [f'Member {item.user_id}: opening contribution £{pounds(item.balance):.2f}; final expected contribution £{points[-1].expected:.2f}.' for item, points in zip(data, daily)]
    return Forecast(user_id=household_id,horizon_days=horizon,points=[p for i,p in enumerate(combined) if i % 7 == 0 or i == horizon],
                    risk_events=risks_for_daily(combined,protected),assumptions=assumptions)


def household_safe_to_spend(household_id: str) -> SafeToSpend:
    data = household_inputs(household_id)
    prepared = [(item, bill_reservations(item)) for item in data]
    # Reconcile actual shared payments globally; member-local consumed copies
    # from bill_reservations must not consume a partial payment twice.
    pots = [pot for pot in remaining_pots([p for item in data for p in item.pots],
                                        [tx for item in data for tx in item.transactions], data[0].as_of)
            if pot.due_date is None or pot.due_date >= data[0].as_of]
    records = sorted([(*bill, item.user_id) for item, (_, bills, _) in prepared for bill in bills])
    bills = [record[:3] for record in records]
    credits, _ = allocations(pots, bills)
    unfunded = unfunded_bills(bills, credits)
    balance = sum(item.balance for item in data)
    pots_total = sum(pence(pot.amount) for pot in pots)
    upcoming = sum(amount for _, _, amount in unfunded)
    breakdown = [BreakdownItem(label=f'{item.user_id}: balance at close of {item.as_of}',amount=pounds(item.balance)) for item in data]
    breakdown += [BreakdownItem(label=f'{pot.user_id}: protected pot {pot.name}',amount=-pounds(pence(pot.amount))) for pot in sorted(pots,key=lambda p:p.id)]
    breakdown += [BreakdownItem(label=f'{record[3]}: unfunded {merchant} on {day}',amount=-pounds(amount)) for record,(day,merchant,amount) in zip(records,unfunded)]
    breakdown += [BreakdownItem(label=f'{item.user_id}: no certain income; reserving 90 days of bills',amount=0) for item,(_,_,has_income) in prepared if not has_income]
    if balance - pots_total - upcoming < 0:
        breakdown.append(BreakdownItem(label='Household safe amount is negative: commitments exceed balances',amount=0))
    return SafeToSpend(balance=pounds(balance),pots_total=pounds(pots_total),upcoming_bills=pounds(upcoming),
                       safe_amount=pounds(balance-pots_total-upcoming),breakdown=breakdown)
