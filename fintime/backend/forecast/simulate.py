"""P2: 'can I afford it?' maths.

1. safe_after = safe_to_spend - amount
2. re-run forecast with an extra one-off cost on `on_date`; affordable only if no new risk event
3. better_date: next entry in the sales calendar (agent/sales_calendar.json) within ~6 weeks, if any
4. Fill numbers_used with every figure the explanation relies on (agent quotes these verbatim)
"""
import datetime as dt

from contracts.schemas import PurchaseVerdict


def simulate(user_id: str, amount: float, on_date: dt.date) -> PurchaseVerdict:
    raise NotImplementedError("P2: see module docstring")
