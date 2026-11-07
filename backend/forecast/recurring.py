"""P2: detect recurring bills/income from history.

Approach: group transactions by merchant; if >=3 occurrences with similar amount (+-10%)
and a stable gap (weekly/monthly +-3 days), treat as recurring. Return next due dates.
"""
import datetime as dt
from dataclasses import dataclass

from contracts.schemas import Transaction


@dataclass
class Recurring:
    merchant: str
    amount: float  # negative = bill, positive = income
    next_due: dt.date
    every_days: int


def detect_recurring(transactions: list[Transaction]) -> list[Recurring]:
    raise NotImplementedError("P2: see module docstring")
