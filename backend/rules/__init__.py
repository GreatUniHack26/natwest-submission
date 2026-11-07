"""EXTENSION - savings / tax tips engine. Each rule is a function (user_id) -> Optional[Tip].

Add a file per rule and register it in RULES. Keep tips as information, never advice.
"""
from typing import Optional

from contracts.schemas import Tip

from . import bike_to_work


def all_tips(user_id: str) -> list[Tip]:
    return [t for rule in RULES if (t := rule(user_id)) is not None]


RULES = [bike_to_work.check]
