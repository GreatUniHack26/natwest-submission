"""Rule: UK Cycle to Work scheme (official GOV.UK guidance)."""
from typing import Optional

from backend import data
from contracts.schemas import Tip

SOURCE_URL = "https://www.gov.uk/government/publications/cycle-to-work-scheme-implementation-guidance"
DISCLAIMER = "General information, not financial or tax advice."
BIKE_MERCHANTS = ("halfords", "evans cycles", "decathlon", "brompton", "tredz")
NON_EMPLOYMENT_INCOME = ("opening balance", "child benefit")


def check(user_id: str) -> Optional[Tip]:
    """Return a Cycle to Work tip when the user has transport/bike spend and employment income."""
    if not user_id or not isinstance(user_id, str):
        return None
    try:
        data.get_user(user_id)
        txs = data.get_transactions(user_id)
    except Exception:
        return None

    has_employment_income = any(
        t.category.lower() == "income"
        and t.amount > 0
        and t.merchant.strip().lower() not in NON_EMPLOYMENT_INCOME
        for t in txs
    )
    if not has_employment_income:
        return None

    transport_txs = [
        t for t in txs
        if t.amount < 0 and (
            t.category.lower() == "transport"
            or any(m in t.merchant.lower() for m in BIKE_MERCHANTS)
        )
    ]
    if not transport_txs:
        return None

    total_transport_spend = round(sum(abs(t.amount) for t in transport_txs), 2)
    if total_transport_spend <= 0:
        return None

    est_saving = round(total_transport_spend * 0.32, 2)

    body = (
        f"You have £{total_transport_spend:.2f} in recorded transport/cycling spend alongside "
        "employment income, so it may be worth checking whether your employer participates in "
        "the UK Cycle to Work scheme. Through salary sacrifice, eligible PAYE employees can hire "
        "a bike and cycling safety equipment free of Income Tax and National Insurance (saving "
        f"around 32% for basic-rate taxpayers, or roughly £{est_saving:.2f} relative to your "
        "observed transport spend), provided at least 50% of the bike's usage is for qualifying "
        "work commutes and the salary sacrifice does not reduce pay below the National Minimum Wage. "
        f"Source: {SOURCE_URL}"
    )

    return Tip(
        id="bike_to_work",
        title="Cycle to Work Scheme",
        body=body,
        est_saving=est_saving,
        disclaimer=DISCLAIMER,
    )
