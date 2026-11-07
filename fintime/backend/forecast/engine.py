"""P2: core forecast. Day-by-day balance projection.

balance[d] = balance[d-1] + recurring income due on d - recurring bills due on d - baseline spend(weekday(d))
low/high = expected -/+ 1 std-dev accumulated.
Risk events: first date expected < 0 (high), or low < 0 (medium), or balance < sum(pots due) (medium).
`overrides` keys (extension what-if): income_multiplier, extra_monthly_cost, extra_one_off.
Always fill Forecast.assumptions with plain-language strings (shown to the user).
"""
from contracts.schemas import Forecast


def build_forecast(user_id: str, horizon_days: int, overrides: dict) -> Forecast:
    raise NotImplementedError("P2: see module docstring")
