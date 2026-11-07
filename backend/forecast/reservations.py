"""Shared pot policy.

Open pots reserve indefinitely. Dated pots reserve through their due date.
A dated pot funds a bill only when its case-insensitive name exactly equals
the bill's merchant and its due date equals the payment date. No fuzzy name
matching: other pots are separate goals. Allocation is capped at both amounts.
Once that payment posts, its allocated reserve is consumed, not reserved twice.
"""
import datetime as dt
from collections import defaultdict

from .money import pence
from .recurring import occurrences


def bill_schedule(items, start: dt.date, end: dt.date):
    return sorted([(day, item.merchant, -pence(item.amount))
                   for item in items if item.amount < 0 for day in occurrences(item, start, end)])


def allocations(pots, bills):
    remaining = {p.id: pence(p.amount) for p in pots}
    credits = defaultdict(int)
    consumed = defaultdict(int)
    for day, merchant, amount in bills:
        for pot in sorted(pots, key=lambda p: p.id):
            if pot.due_date == day and pot.name.strip().casefold() == merchant.strip().casefold():
                funded = min(remaining[pot.id], amount - credits[(day, merchant)])
                remaining[pot.id] -= funded
                credits[(day, merchant)] += funded
                consumed[(pot.id, day)] += funded
    return credits, consumed


def protected_on(pots, bills, on_date: dt.date) -> int:
    _, consumed = allocations(pots, bills)
    return sum(pence(p.amount) - sum(amount for (pid, day), amount in consumed.items() if pid == p.id and day <= on_date)
               for p in pots if p.due_date is None or p.due_date >= on_date)
