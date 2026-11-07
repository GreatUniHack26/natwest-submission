"""Rule: Full-time Student Council Tax exemption / discount (GOV.UK guidance)."""
from typing import Optional

from backend import data
from contracts.schemas import Tip

SOURCE_URL = "https://www.gov.uk/council-tax/who-has-to-pay"
DISCLAIMER = "General information, not financial or tax advice."


def check(user_id: str) -> Optional[Tip]:
    """Return a Council Tax student exemption tip when a student persona has housing spend."""
    if not user_id or not isinstance(user_id, str):
        return None
    try:
        user = data.get_user(user_id)
        txs = data.get_transactions(user_id)
    except Exception:
        return None

    if "student" not in user.persona.lower():
        return None

    housing_txs = [
        t for t in txs
        if t.category.lower() == "housing" and t.amount < 0
    ]
    if not housing_txs:
        return None

    total_housing_spend = round(sum(abs(t.amount) for t in housing_txs), 2)
    if total_housing_spend <= 0:
        return None

    body = (
        f"Because your profile indicates you are a student paying rent (£{total_housing_spend:.2f} "
        "recorded in housing), it may be worth checking whether your household has applied for a "
        "student Council Tax exemption or discount with your local council. Under UK rules, "
        "full-time students (on a course lasting at least 1 academic year with 21+ hours per week "
        "of study, tuition, or work experience for at least 24 weeks per year) are disregarded "
        "for Council Tax: all-student households qualify for a 100% exemption, and a household "
        "with one non-student adult living alongside full-time students may qualify for a 25% "
        f"discount. Source: {SOURCE_URL}"
    )

    return Tip(
        id="student_council_tax",
        title="Student Council Tax Exemption or Discount",
        body=body,
        est_saving=None,
        disclaimer=DISCLAIMER,
    )
