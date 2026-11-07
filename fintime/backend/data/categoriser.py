"""P1: need/want categorisation. Rules first, cached LLM only for unknown merchants.

Pre-compute labels (don't call the LLM live in the demo).
"""
from contracts.schemas import Transaction

# substring (lowercase) -> (category, kind)
RULES: dict[str, tuple[str, str]] = {
    "tesco": ("groceries", "need"),
    "lidl": ("groceries", "need"),
    "rent": ("housing", "need"),
    "metrolink": ("transport", "need"),
    "tfl": ("transport", "need"),
    "deliveroo": ("eating out", "want"),
    "greggs": ("eating out", "want"),
    "uniqlo": ("clothes", "want"),
}


def llm_label(merchant: str) -> tuple[str, str]:
    """TODO(P1): batch unknown merchants into ONE LLM call returning JSON, cache on disk."""
    return ("other", "want")


def categorise(transactions: list[Transaction]) -> list[Transaction]:
    out = []
    for t in transactions:
        if t.amount > 0:
            out.append(t.model_copy(update={"category": "income", "kind": "income"}))
            continue
        name = t.merchant.lower()
        match = next((v for k, v in RULES.items() if k in name), None)
        category, kind = match or llm_label(t.merchant)
        out.append(t.model_copy(update={"category": category, "kind": kind}))
    return out
