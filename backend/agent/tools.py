"""P3: tools exposed to the LLM. Each is a thin wrapper over a forecast, rules, or benchmark function."""
import datetime as dt
import math
from typing import Any

from backend import config, rules
from backend import forecast as fc
from backend.agent import benchmark_adapter, planner_tools

TOOLS = [
    {
        "name": "get_safe_to_spend",
        "description": "Money the user can spend today after pots and upcoming bills.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "simulate_purchase",
        "description": "Check whether a purchase is affordable and suggest better timing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "date": {"type": "string", "format": "date"},
            },
            "required": ["amount"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_upcoming_sales",
        "description": "Major sales events in the next N days.",
        "input_schema": {
            "type": "object",
            "properties": {"within_days": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_alerts",
        "description": "Current spending alerts and risks.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_forecast",
        "description": "Projected balance and risk events over the next N days.",
        "input_schema": {
            "type": "object",
            "properties": {"horizon_days": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_tips",
        "description": "General savings and tax-efficiency information relevant to the user's spending patterns (information, not regulated advice).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    *planner_tools.PLANNER_TOOLS,
]

_TOOL_SCHEMAS = {tool["name"]: tool["input_schema"] for tool in TOOLS}
_TOOL_SCHEMAS["get_benchmark"] = benchmark_adapter.BENCHMARK_TOOL_SCHEMA["input_schema"]


def get_active_tools() -> list[dict[str, Any]]:
    """Return tools exposed to the LLM, including get_benchmark only when backend.benchmarks is available."""
    active = list(TOOLS)
    if benchmark_adapter.is_benchmarks_available():
        active.append(benchmark_adapter.BENCHMARK_TOOL_SCHEMA)
    return active


def _is_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)


def _is_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _validate_args(name: str, args: Any) -> dict[str, Any]:
    if name not in _TOOL_SCHEMAS:
        raise ValueError(f"Unknown tool: {name}")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ValueError(f"Invalid arguments for {name}: expected an object/dict")

    schema = _TOOL_SCHEMAS[name]
    allowed_props = set(schema.get("properties", {}).keys())
    unknown_keys = set(args.keys()) - allowed_props
    if unknown_keys:
        raise ValueError(f"Unexpected arguments for {name}: {sorted(unknown_keys)}")

    for req_key in schema.get("required", []):
        if req_key not in args or args[req_key] is None:
            raise ValueError(f"Missing required argument '{req_key}' for {name}")

    return args


def get_upcoming_sales(within_days: int = 60) -> list[dict]:
    return fc.upcoming_sales(within_days)


def run_tool(user_id: str, name: str, args: dict):
    """Dispatch an LLM tool call. Return JSON-serialisable data."""
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id must be a non-empty string")

    validated = _validate_args(name, args)

    if name == "get_safe_to_spend":
        return fc.safe_to_spend(user_id, config.TODAY).model_dump(mode="json")

    if name == "simulate_purchase":
        raw_amount = validated["amount"]
        if not _is_number(raw_amount) or float(raw_amount) <= 0:
            raise ValueError("amount must be a positive number")
        amount = float(raw_amount)

        raw_date = validated.get("date")
        if raw_date is not None:
            if not isinstance(raw_date, str):
                raise ValueError("date must be an ISO date string (YYYY-MM-DD)")
            try:
                on = dt.date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(f"Invalid ISO date '{raw_date}'") from exc
        else:
            on = config.TODAY

        return fc.simulate_purchase(user_id, amount, on).model_dump(mode="json")

    if name == "get_upcoming_sales":
        within_days = validated.get("within_days", 60)
        if within_days is None:
            within_days = 60
        return get_upcoming_sales(within_days)

    if name == "get_alerts":
        return [a.model_dump(mode="json") for a in fc.detect_alerts(user_id)]

    if name == "get_forecast":
        horizon_days = validated.get("horizon_days", 90)
        if horizon_days is None:
            horizon_days = 90
        if not _is_int(horizon_days) or horizon_days < 1 or horizon_days > 365:
            raise ValueError("horizon_days must be an integer between 1 and 365")
        return fc.forecast(user_id, horizon_days).model_dump(mode="json")

    if name == "get_tips":
        return [t.model_dump(mode="json") for t in rules.all_tips(user_id)]

    if name == "get_benchmark":
        return benchmark_adapter.run_get_benchmark(user_id, validated)

    if name == "plan_debt_payoff":
        return planner_tools.debt_payoff(user_id, validated)

    if name == "plan_savings_goal":
        return planner_tools.savings_goal(user_id, validated)

    if name == "plan_emergency_fund":
        return planner_tools.emergency_fund(user_id, validated)

    raise ValueError(f"Unknown tool: {name}")
