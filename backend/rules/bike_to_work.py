"""Example rule: UK Cycle to Work scheme (check eligibility and current rules before shipping)."""
from typing import Optional

from contracts.schemas import Tip


def check(user_id: str) -> Optional[Tip]:
    # TODO: trigger when the user has recurring transport spend or a bike-shop purchase
    return None
