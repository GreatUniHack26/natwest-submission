"""P2: overspend / sudden-change alerts.

- sudden_change: category spend this week > mean + 2*std (z-score) -> message with % vs average
- overspend: month-to-date spend ahead of forecast
- risk: copy high-severity RiskEvents from the forecast
Every alert needs a plain-language `message` AND a concrete `suggested_action`.
"""
from contracts.schemas import Alert


def find_alerts(user_id: str) -> list[Alert]:
    raise NotImplementedError("P2: see module docstring")
