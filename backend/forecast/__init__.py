"""P2 - FORECAST module. Public interface (the agent and API call ONLY these):

    forecast(user_id, horizon_days, overrides=None) -> Forecast
    safe_to_spend(user_id, as_of)                   -> SafeToSpend
    simulate_purchase(user_id, amount, on_date)     -> PurchaseVerdict
    detect_alerts(user_id)                          -> list[Alert]

RULE: deterministic maths only. No LLM calls in this package.
`overrides` powers the extension 'what if' (e.g. {"income_multiplier": 0, "extra_monthly_cost": 300}).
"""
import datetime as dt
from typing import Optional

from backend import config
from contracts import mock
from contracts.schemas import Alert, Forecast, PurchaseVerdict, SafeToSpend


def forecast(user_id: str, horizon_days: int = 90, overrides: Optional[dict] = None) -> Forecast:
    if config.MOCK_FORECAST:
        return Forecast(**mock.load("forecast"))
    from .engine import build_forecast

    return build_forecast(user_id, horizon_days, overrides if overrides is not None else {})


def safe_to_spend(user_id: str, as_of: dt.date) -> SafeToSpend:
    if config.MOCK_FORECAST:
        return SafeToSpend(**mock.load("safe_to_spend"))
    from .pots import compute_safe_to_spend

    return compute_safe_to_spend(user_id, as_of)


def simulate_purchase(user_id: str, amount: float, on_date: dt.date) -> PurchaseVerdict:
    if config.MOCK_FORECAST:
        return PurchaseVerdict(**mock.load("verdict"))
    from .simulate import simulate

    return simulate(user_id, amount, on_date)


def detect_alerts(user_id: str) -> list[Alert]:
    if config.MOCK_FORECAST:
        return [Alert(**a) for a in mock.load("alerts")]
    from .alerts import find_alerts

    return find_alerts(user_id)


from .sales import upcoming_sales  # shared calendar used by the agent and simulator
