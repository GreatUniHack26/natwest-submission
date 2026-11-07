"""Recorded spending for coach follow-ups, separate from projected spending."""
import datetime as dt
from collections import defaultdict

from backend import config, data
from backend.data.generator import OPENING_BALANCE_MERCHANT
from backend.forecast.money import pence, pounds


def spending_history(user_id: str, args: dict) -> dict:
    def date_arg(name, default):
        raw = args.get(name, default.isoformat())
        if not isinstance(raw, str):
            raise ValueError(f"{name} must be an ISO date string")
        return dt.date.fromisoformat(raw)

    start = date_arg("start", config.TODAY.replace(day=1))
    end = date_arg("end", config.TODAY)
    if not start <= end <= config.TODAY or (end - start).days > 366:
        raise ValueError("History must be an ordered range of at most 366 days ending today or earlier")
    filters = {}
    for key in ("category", "merchant"):
        value = args.get(key)
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 120:
                raise ValueError(f"{key} must be a non-empty string of at most 120 characters")
            filters[key] = value.strip().casefold()

    data.get_user(user_id)
    history = data.get_transactions(user_id, end=config.TODAY)
    rows = [t for t in history if start <= t.date <= end and t.merchant != OPENING_BALANCE_MERCHANT
            and t.category != "internal_transfer"
            and ("category" not in filters or t.category.casefold() == filters["category"])
            and ("merchant" not in filters or filters["merchant"] in t.merchant.casefold())]
    spend_by_category = defaultdict(int)
    spend_by_merchant = defaultdict(int)
    months = defaultdict(lambda: {"spent": 0, "income": 0})
    income = spent = 0
    for tx in rows:
        amount = pence(tx.amount)
        month = months[tx.date.strftime("%Y-%m")]
        if amount < 0 and tx.kind != "income":
            spent -= amount
            month["spent"] -= amount
            spend_by_category[tx.category] -= amount
            spend_by_merchant[tx.merchant] -= amount
        elif amount > 0 and tx.kind == "income":
            income += amount
            month["income"] += amount

    latest = sorted(rows, key=lambda tx: (tx.date, tx.id), reverse=True)[:20]
    available_from = min((t.date for t in history), default=None)
    prefix = f"history_{start}_{end}_{filters}"
    numbers_used = {f"{prefix}_spent": pounds(spent), f"{prefix}_income": pounds(income),
                    f"{prefix}_net_cash_flow": pounds(income - spent)}
    for label, amounts in (("category", spend_by_category), ("merchant", spend_by_merchant)):
        numbers_used.update({f"{prefix}_{label}_{key}": pounds(value) for key, value in amounts.items()})
    for month, totals in months.items():
        numbers_used.update({f"{prefix}_{month}_{key}": pounds(value) for key, value in totals.items()})
    for tx in latest:
        numbers_used[f"{prefix}_{tx.id}_amount"] = tx.amount
        numbers_used[f"{prefix}_{tx.id}_absolute_amount"] = abs(tx.amount)
    return {
        "start": start.isoformat(), "end": end.isoformat(), "filters": filters,
        "history_available_from": available_from.isoformat() if available_from else None,
        "transaction_count": len(rows), "spent": pounds(spent), "income": pounds(income),
        "net_cash_flow": pounds(income - spent),
        "by_category": {k: pounds(v) for k, v in sorted(spend_by_category.items())},
        "by_merchant": {k: pounds(v) for k, v in sorted(spend_by_merchant.items())},
        "by_month": {k: {"spent": pounds(v["spent"]), "income": pounds(v["income"]),
                         "net_cash_flow": pounds(v["income"] - v["spent"])} for k, v in sorted(months.items())},
        "latest_transactions": [t.model_dump(mode="json") for t in latest],
        "transactions_shown": len(latest),
        "numbers_used": numbers_used,
        "note": "GBP; recorded history only, not a forecast. Opening balance and internal transfers excluded. "
                "Totals cover all matching records; only the latest 20 individual transactions are shown. "
                "Dates outside available history have no recorded data; termly income is not guaranteed future pay.",
    }
