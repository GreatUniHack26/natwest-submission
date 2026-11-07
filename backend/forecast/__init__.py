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


def household_forecast(household_id: str, horizon: int = 90) -> Forecast:
    from .household import household_forecast as calculate

    return calculate(household_id, horizon)


def household_safe_to_spend(household_id: str) -> SafeToSpend:
    from .household import household_safe_to_spend as calculate

    return calculate(household_id)


def spending_forecast(user_id: str) -> dict:
    """Per-category month-end projection with overspend alarms (real forecast mode only)."""
    if config.MOCK_FORECAST:
        raise ValueError('Spending forecast requires real forecast mode')
    from .spending import spending_forecast as calculate

    return calculate(user_id)


def deposit_ideas(user_id: str) -> dict:
    """Short-term saver ideas for ring-fenced pots (real forecast mode only)."""
    if config.MOCK_FORECAST:
        raise ValueError('Deposit ideas require real forecast mode')
    from .deposits import deposit_ideas as calculate

    return calculate(user_id)


def simulate_futures(user_id: str, horizon_days: int = 90, sims: int = 1000) -> dict:
    """Monte Carlo twin: odds of going below zero, dipping into pots, and runway (real mode only)."""
    if config.MOCK_FORECAST:
        raise ValueError('Simulations require real forecast mode')
    from .montecarlo import simulate_futures as calculate

    return calculate(user_id, horizon_days, sims)


def timeline(user_id: str, horizon_days: int = 90, overrides: Optional[dict] = None) -> dict:
    """Daily time-travel data: Monte Carlo fan, expected line, pot floor, events, optional what-if."""
    if config.MOCK_FORECAST:
        raise ValueError('Timeline requires real forecast mode')
    from .time_travel import timeline as calculate

    return calculate(user_id, horizon_days, overrides)
