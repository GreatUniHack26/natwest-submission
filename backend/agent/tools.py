"""P3: tools exposed to the LLM. Each is a thin wrapper over a forecast, rules, or benchmark function."""
import datetime as dt
import math
from typing import Any

from backend import config, rules
from backend import forecast as fc
from backend.agent import benchmark_adapter, planner_tools
from backend.agent.spending_history import spending_history
from backend.integrations import govuk, news

TOOLS = [
    {
        "name": "get_spending_history",
        "description": "Recorded income and spending by category, merchant and month, plus latest transactions. Use for past expenses and follow-up comparisons; not a forecast. Defaults to this month to date. Maximum range 366 days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "format": "date"},
                "end": {"type": "string", "format": "date"},
                "category": {"type": "string", "description": "Exact category, e.g. eating out"},
                "merchant": {"type": "string", "description": "Merchant name substring, e.g. Uniqlo"},
            },
            "additionalProperties": False,
        },
    },
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
    {
        "name": "get_economic_news",
        "description": "Recent UK cost-of-living and economy news (energy, fuel, rates, inflation, wages, benefits) gathered by FinTime's n8n news workflow. Use for context on future costs; headlines are third-party information, not FinTime calculations.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}, "limit": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_gov_uk",
        "description": "Official GOV.UK guidance on UK tax, allowances, benefits and government schemes (e.g. Personal Allowance and tax bands, Marriage Allowance, council tax discounts, Universal Credit, Help to Save, Healthy Start, free school meals, Child Benefit, Tax-Free Childcare, minimum wage, job-expense tax relief). Returns short excerpts with gov.uk links. General information, not personalised advice: quote the page's figures exactly as written and link the page.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Short topic, e.g. 'personal allowance' or 'council tax student discount'"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_spending_forecast",
        "description": "This month's spending per category from the digital twin: spent so far, projected month-end, usual month, and overspend alarms.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_twin_simulations",
        "description": "Run the Monte Carlo digital twin: 1,000 simulated futures with realistic income timing, spending habits and unexpected costs. Returns the chance of going below zero within 30/60/90 days, the chance of dipping into pots, the date it becomes a coin flip, and runway (days the money lasts if income stopped today).",
        "input_schema": {
            "type": "object",
            "properties": {"horizon_days": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_money_owed",
        "description": "UK schemes, discounts and reliefs this person may be missing (e.g. council tax discounts, Universal Credit, Help to Save, childcare help), found from their own data, each with an official GOV.UK link and checker. Possible eligibility only, never a promise.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_deposit_ideas",
        "description": "Short-term deposit ideas for ring-fenced pots: how much idle pot money could earn in an instant-access saver before it is due (illustrative rate, not a product offer).",
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

    if name == "get_spending_history":
        return spending_history(user_id, validated)

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

    if name == "get_spending_forecast":
        return fc.spending_forecast(user_id)

    if name == "run_twin_simulations":
        horizon = validated.get("horizon_days") or 90
        if not _is_int(horizon) or not 7 <= horizon <= 180:
            raise ValueError("horizon_days must be an integer between 7 and 180")
        result = fc.simulate_futures(user_id, horizon)
        result.pop("points", None)
        # Flatten odds into verifiable percentages so they reach numbers_used and the model never converts fractions.
        for days, chance in result.get("chance_below_zero_within", {}).items():
            result[f"chance_below_zero_{days}d_percent"] = round(chance * 100, 1)
        result["chance_dip_into_pots_percent"] = round(result.get("chance_dip_into_pots", 0) * 100, 1)
        return result

    if name == "get_money_owed":
        from backend.rules.entitlements import entitlements_summary

        return entitlements_summary(user_id)

    if name == "get_deposit_ideas":
        return fc.deposit_ideas(user_id)

    if name == "get_tips":
        return [t.model_dump(mode="json") for t in rules.all_tips(user_id)]

    if name == "get_benchmark":
        return benchmark_adapter.run_get_benchmark(user_id, validated)

    if name == "get_economic_news":
        topic = validated.get("topic")
        if topic is not None and not isinstance(topic, str):
            raise ValueError("topic must be a string")
        limit = validated.get("limit", 6)
        if limit is None:
            limit = 6
        if not _is_int(limit) or limit < 1 or limit > 10:
            raise ValueError("limit must be an integer between 1 and 10")
        return news.get_economic_news(topic=topic, limit=limit)

    if name == "lookup_gov_uk":
        query = validated["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if len(query) > govuk.QUERY_MAX:
            raise ValueError(f"query must be at most {govuk.QUERY_MAX} characters")
        return govuk.lookup_gov_uk(query.strip())

    if name == "plan_debt_payoff":
        return planner_tools.debt_payoff(user_id, validated)

    if name == "plan_savings_goal":
        return planner_tools.savings_goal(user_id, validated)

    if name == "plan_emergency_fund":
        return planner_tools.emergency_fund(user_id, validated)

    raise ValueError(f"Unknown tool: {name}")
