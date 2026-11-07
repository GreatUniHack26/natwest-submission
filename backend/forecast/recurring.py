"""Infer weekly/monthly schedules; amounts are signed GBP.

At least three observations are required. Bills must stay within 10% of
their median; income with stable timing may vary and carries its observed
population standard deviation. Users and signs are never pooled.
"""
import calendar
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, pstdev

from contracts.schemas import Transaction


@dataclass
class Recurring:
    merchant: str
    amount: float
    next_due: dt.date
    every_days: int  # 30 denotes calendar months, never thirty-day arithmetic


def add_month(day: dt.date, anchor: int | None = None) -> dt.date:
    """Preserve the original day (31 for month-end) across short months."""
    year, month = day.year + day.month // 12, day.month % 12 + 1
    return dt.date(year, month, min(anchor or day.day, calendar.monthrange(year, month)[1]))


def occurrences(item: Recurring, start: dt.date, end: dt.date):
    """Yield due dates inclusively, advancing stale schedules without drift."""
    day = item.next_due
    anchor = day.day
    if day.day == calendar.monthrange(day.year, day.month)[1]:
        anchor = 31
    while day <= end:
        if day >= start:
            yield day
        day = add_month(day, anchor) if item.every_days == 30 else day + dt.timedelta(days=item.every_days)


def patterns(transactions: list[Transaction]) -> list[tuple[Recurring, list[Transaction]]]:
    groups = defaultdict(list)
    for tx in transactions:
        if tx.amount:
            groups[(tx.user_id, tx.merchant, tx.amount > 0)].append(tx)
    result = []
    for (_, merchant, income), group in sorted(groups.items()):
        group = sorted(group, key=lambda t: (t.date, t.id))
        candidates = [group] if income else [
            [t for t in group if abs(abs(t.amount) - abs(p.amount)) <= abs(p.amount) * .1 + 1e-9]
            for p in group
        ]
        candidates.sort(key=lambda c: (-len(c), tuple(t.id for t in c)))
        for candidate in candidates:
            if len(candidate) < 3:
                continue
            center = median(t.amount for t in candidate)
            if not income and any(abs(t.amount - center) > abs(center) * .1 + 1e-9 for t in candidate):
                continue
            gaps = [(b.date - a.date).days for a, b in zip(candidate, candidate[1:])]
            if all(4 <= gap <= 10 for gap in gaps):
                every, due = 7, candidate[-1].date + dt.timedelta(days=7)
            elif all(abs((b.date - add_month(a.date)).days) <= 3 for a, b in zip(candidate, candidate[1:])):
                every = 30
                month_end = all(abs((t.date - dt.date(t.date.year, t.date.month, calendar.monthrange(t.date.year, t.date.month)[1])).days) <= 3 for t in candidate)
                anchor = 31 if month_end else round(median(t.date.day for t in candidate))
                due = add_month(candidate[-1].date, anchor)
            else:
                continue
            result.append((Recurring(merchant, round(mean(t.amount for t in candidate), 2), due, every), candidate))
            break
    return result


def detect_recurring(transactions: list[Transaction]) -> list[Recurring]:
    return [item for item, _ in patterns(transactions)]


def recurring_ids(transactions: list[Transaction]) -> set[str]:
    """Exclude only detected observations, rather than all merchant purchases."""
    return {tx.id for _, observations in patterns(transactions) for tx in observations}


def amount_std(observations: list[Transaction]) -> float:
    return pstdev(t.amount for t in observations)
