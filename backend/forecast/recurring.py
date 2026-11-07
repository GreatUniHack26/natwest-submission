"""Infer weekly/monthly schedules; amounts are signed GBP.

At least three observations are required. Bills must stay within 10% of
their median; income with stable timing may vary and carries its observed
population standard deviation. Users and signs are never pooled.
"""
import calendar
import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, pstdev

from .money import pence, pounds

from contracts.schemas import Transaction


@dataclass
class Recurring:
    merchant: str
    amount: float
    next_due: dt.date
    every_days: int  # monthly schedules use 30; private metadata retains calendar semantics

    def __post_init__(self):
        # Private anchor preserves the four-field public shape across short months.
        self._monthly = self.every_days == 30
        self._month_day = self.next_due.day
        if self.next_due.day == calendar.monthrange(self.next_due.year, self.next_due.month)[1]:
            self._month_day = 31


def add_month(day: dt.date, anchor: int | None = None) -> dt.date:
    """Preserve the original day (31 for month-end) across short months."""
    year, month = day.year + day.month // 12, day.month % 12 + 1
    return dt.date(year, month, min(anchor or day.day, calendar.monthrange(year, month)[1]))


def occurrences(item: Recurring, start: dt.date, end: dt.date):
    """Yield due dates inclusively, advancing stale schedules without drift."""
    day = item.next_due
    anchor = item._month_day
    while day <= end:
        if day >= start:
            yield day
        day = add_month(day, anchor) if item._monthly else day + dt.timedelta(days=item.every_days)


def _nearest_month_day(day: dt.date, anchor: int) -> dt.date:
    candidates = []
    for offset in (-1, 0, 1):
        year, month0 = divmod(day.year * 12 + day.month - 1 + offset, 12)
        if 1 <= year <= 9999:
            candidates.append(dt.date(year, month0 + 1,
                              min(anchor, calendar.monthrange(year, month0 + 1)[1])))
    return min(candidates, key=lambda due: (abs((day - due).days), due))


def _monthly_schedule(observations: list[Transaction]) -> tuple[int, dt.date] | None:
    """Fit clamped calendar dates, assigning early/late posts to their due month."""
    dates = [t.date for t in observations]
    # Adjacent monthly dates differ by 28..31 days, with up to three days' jitter each.
    if any(not 22 <= (b - a).days <= 37 for a, b in zip(dates, dates[1:])):
        return None
    center = median(day.day for day in dates)
    candidates = []
    for anchor in range(1, 32):
        assigned = [_nearest_month_day(day, anchor) for day in dates]
        slots = [day.year * 12 + day.month for day in assigned]
        errors = [abs((actual - due).days) for actual, due in zip(dates, assigned)]
        if max(errors) <= 3 and all(b == a + 1 for a, b in zip(slots, slots[1:])):
            candidates.append(((sum(errors), abs(anchor - center), anchor), assigned[-1]))
    if not candidates:
        return None
    score, last_due = min(candidates)
    return score[2], last_due


def patterns(transactions: list[Transaction]) -> list[tuple[Recurring, list[Transaction]]]:
    groups = defaultdict(list)
    for tx in transactions:
        pence(tx.amount)
        if tx.amount and not (tx.amount > 0 and tx.kind != 'income'):
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
            monthly = False
            if all(4 <= gap <= 10 for gap in gaps) and (not income or 6 <= mean(gaps) <= 8):
                every, due = 7, candidate[-1].date + dt.timedelta(days=7)
                anchor = None
            elif income and all(gap == 28 for gap in gaps):
                # Four-weekly benefits are not calendar-month income.
                every, due, anchor = 28, candidate[-1].date + dt.timedelta(days=28), None
            elif (schedule := _monthly_schedule(candidate)) is not None:
                every, monthly = 30, True
                anchor, last_due = schedule
                due = add_month(last_due, anchor)
            elif income and all(1 <= gap <= 45 for gap in gaps) and max(gaps) <= 3 * min(gaps):
                # Irregular shifts: mean observed cadence and mean receipt; no guarantee.
                every = max(1, round(mean(gaps)))
                due, anchor = candidate[-1].date + dt.timedelta(days=every), None
            else:
                continue
            item = Recurring(merchant, pounds(pence(mean(t.amount for t in candidate))), due, every)
            item._monthly = monthly
            if anchor is not None:
                item._month_day = anchor
            result.append((item, candidate))
            break
    return result


def detect_recurring(transactions: list[Transaction]) -> list[Recurring]:
    return [item for item, _ in patterns(transactions)]


def recurring_ids(transactions: list[Transaction]) -> set[str]:
    """Exclude only detected observations, rather than all merchant purchases."""
    return {tx.id for _, observations in patterns(transactions) for tx in observations}


def amount_std(observations: list[Transaction]) -> float:
    return pstdev(t.amount for t in observations)


def payment_std(item: Recurring, observations: list[Transaction]) -> float:
    """Receipt × relative timing variation; monthly dates remove calendar clamping."""
    amount_variance = amount_std(observations) ** 2
    if item.amount <= 0:
        return math.sqrt(amount_variance)
    dates = sorted(t.date for t in observations)
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    if item._monthly:
        # Known calendar/clamping changes are certain; posted-date jitter is not.
        deviations = [(day - _nearest_month_day(day, item._month_day)).days for day in dates]
        timing_variation = pstdev(deviations)
    else:
        timing_variation = pstdev(gaps)
    timing_std = timing_variation / mean(gaps) * item.amount
    return math.sqrt(amount_variance + timing_std ** 2)
