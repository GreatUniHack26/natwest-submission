"""P2: ring-fenced pots and safe-to-spend.

safe_amount = current balance - sum(pot amounts) - bills due before next income
Fill `breakdown` with one labelled line per component (shown on the dashboard card).
"""
import datetime as dt

from contracts.schemas import SafeToSpend


def compute_safe_to_spend(user_id: str, as_of: dt.date) -> SafeToSpend:
    raise NotImplementedError("P2: see module docstring")
