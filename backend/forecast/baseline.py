"""Twelve complete trailing seven-day periods, ending before as_of.

Days with no recorded spending count as zero; population standard deviation
(ddof=0) describes observed variability, not confidence in the mean. Positive
transactions (including refunds) do not predict spending or recurring income
unless labelled income. Histories spanning less than a week use the overall
daily mean for unobserved weekdays. Callers must scope input to one user.
"""
import datetime as dt
from collections import defaultdict
from statistics import mean, pstdev

from backend import config
from contracts.schemas import Transaction
from .money import pence
from .recurring import recurring_ids

LOOKBACK_DAYS = 84


def history(transactions: list[Transaction], as_of: dt.date) -> list[Transaction]:
    users = {t.user_id for t in transactions}
    if len(users) > 1:
        raise ValueError('Spending baselines require a single user')
    return [t for t in transactions if as_of - dt.timedelta(days=LOOKBACK_DAYS) <= t.date < as_of]


def everyday(transactions: list[Transaction], as_of: dt.date) -> list[Transaction]:
    data = history(transactions, as_of)
    excluded = recurring_ids([t for t in transactions if as_of - dt.timedelta(days=180) <= t.date < as_of])
    return [t for t in data if t.amount < 0 and t.kind != 'income' and t.id not in excluded]


def weekday_baseline(transactions: list[Transaction], as_of: dt.date | None = None) -> dict[int, tuple[float, float]]:
    as_of = as_of or config.TODAY
    data = history(transactions, as_of)
    totals = defaultdict(int)
    for tx in everyday(transactions, as_of):
        totals[tx.date] += -pence(tx.amount)
    samples = defaultdict(list)
    for offset in range(1, LOOKBACK_DAYS + 1):
        day = as_of - dt.timedelta(days=offset)
        samples[day.weekday()].append(totals[day])
    sparse = bool(data) and (as_of - min(t.date for t in data)).days < 7
    overall = sum(totals.values()) / LOOKBACK_DAYS / 100
    return {day: (overall if sparse and not any(values) else mean(values) / 100, pstdev(values) / 100)
            for day, values in sorted(samples.items())}


def category_weekly_mean(transactions: list[Transaction], as_of: dt.date | None = None) -> dict[str, tuple[float, float]]:
    as_of = as_of or config.TODAY
    totals = defaultdict(lambda: [0] * 12)
    for tx in everyday(transactions, as_of):
        index = ((as_of - tx.date).days - 1) // 7
        totals[tx.category][index] += -pence(tx.amount)
    return {category: (mean(values) / 100, pstdev(values) / 100) for category, values in sorted(totals.items())}
