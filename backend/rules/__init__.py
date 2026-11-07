"""EXTENSION - savings / tax tips engine. Each rule is a function (user_id) -> Optional[Tip].

Add a file per rule and register it in RULES. Keep tips as information, never advice.
"""
from typing import Callable, Optional

from contracts.schemas import Tip

from . import bike_to_work, railcard_16_25, student_council_tax

RULES: list[Callable[[str], Optional[Tip]]] = [
    bike_to_work.check,
    railcard_16_25.check,
    student_council_tax.check,
]


def all_tips(user_id: str) -> list[Tip]:
    tips: list[Tip] = []
    for rule in RULES:
        try:
            tip = rule(user_id)
        except Exception:
            tip = None
        if tip is not None:
            tips.append(tip)
    return tips
