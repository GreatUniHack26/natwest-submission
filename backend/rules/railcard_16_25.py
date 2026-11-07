"""Rule: 16-25 Railcard (including full-time students of any age)."""
from typing import Optional

from backend import data
from contracts.schemas import Tip

SOURCE_URL = "https://www.16-25railcard.co.uk"
NATIONAL_RAIL_URL = "https://www.nationalrail.co.uk/railcards/16-25-railcard/"
DISCLAIMER = "General information, not financial or tax advice."


def check(user_id: str) -> Optional[Tip]:
    """Return a 16-25 Railcard tip when a student persona has transport spend."""
    if not user_id or not isinstance(user_id, str):
        return None
    try:
        user = data.get_user(user_id)
        txs = data.get_transactions(user_id)
    except Exception:
        return None

    if "student" not in user.persona.lower():
        return None

    transport_txs = [
        t for t in txs
        if t.category.lower() == "transport" and t.amount < 0
    ]
    if not transport_txs:
        return None

    total_transport_spend = round(sum(abs(t.amount) for t in transport_txs), 2)
    if total_transport_spend <= 0:
        return None

    est_saving = round(total_transport_spend / 3.0, 2)

    body = (
        f"Based on your student profile and £{total_transport_spend:.2f} in recorded transport "
        "spend, it may be worth checking whether you qualify for a 16-25 Railcard (£35/year or "
        "£80 for 3 years). Anyone aged 16–25, as well as mature students aged 26 or over in "
        "full-time study (over 15 hours per week for at least 20 weeks per year at a recognised "
        "UK institution), can save 1/3 on eligible Standard rail fares across Great Britain (and "
        "off-peak Tube fares when linked to an Oyster card) — an estimated 1/3 reduction of "
        f"£{est_saving:.2f} if your observed transport spend goes toward eligible rail fares. "
        f"Source: {SOURCE_URL} ({NATIONAL_RAIL_URL})"
    )

    return Tip(
        id="railcard_16_25",
        title="16-25 Railcard for Students and Young Travellers",
        body=body,
        est_saving=est_saving,
        disclaimer=DISCLAIMER,
    )
