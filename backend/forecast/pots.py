"""Balance minus active pots minus unfunded bills through next certain income.

Bills on the same date as income are reserved (conservatively, bills first).
Variable income is not a guaranteed boundary: reserve 90 days of bills when
no fixed-amount income occurs. The policy is included in the breakdown.
"""
import datetime as dt

from contracts.schemas import BreakdownItem, SafeToSpend
from .inputs import Inputs, load_inputs
from .money import pence, pounds
from .recurring import occurrences, patterns, payment_std
from .reservations import allocations, bill_schedule, remaining_pots, unfunded_bills


def bill_reservations(data: Inputs):
    detected = patterns(data.transactions)
    start = data.as_of + dt.timedelta(days=1)
    fallback = data.as_of + dt.timedelta(days=90)
    incomes = [day for item, observations in detected if item.amount > 0 and payment_std(item, observations) == 0
               for day in occurrences(item, start, fallback)]
    cutoff = min(incomes, default=fallback)
    pots = [p for p in remaining_pots(data.pots, data.transactions, data.as_of) if p.due_date is None or p.due_date >= data.as_of]
    bills = bill_schedule([item for item, _ in detected], start, cutoff)
    return pots, bills, bool(incomes)


def safe_from_inputs(data: Inputs) -> SafeToSpend:
    pots, bills, has_income = bill_reservations(data)
    credits, _ = allocations(pots, bills)
    unfunded = unfunded_bills(bills, credits)
    pots_total = sum(pence(p.amount) for p in pots)
    upcoming = sum(amount for _, _, amount in unfunded)
    safe = data.balance - pots_total - upcoming
    lines = [BreakdownItem(label=f'Balance at close of {data.as_of}', amount=pounds(data.balance))]
    lines += [BreakdownItem(label=f'Protected pot: {p.name}', amount=-pounds(pence(p.amount))) for p in sorted(pots, key=lambda p: p.id)]
    lines += [BreakdownItem(label=f'Unfunded bill: {merchant} on {day}', amount=-pounds(amount)) for day, merchant, amount in unfunded]
    if not has_income:
        lines.append(BreakdownItem(label='No certain income: conservatively reserving 90 days of bills', amount=0))
    if safe < 0:
        lines.append(BreakdownItem(label='Safe amount is negative: commitments exceed the balance', amount=0))
    return SafeToSpend(balance=pounds(data.balance), pots_total=pounds(pots_total), upcoming_bills=pounds(upcoming),
                       safe_amount=pounds(safe), breakdown=lines)


def compute_safe_to_spend(user_id: str, as_of: dt.date) -> SafeToSpend:
    return safe_from_inputs(load_inputs(user_id, as_of))
