"""P3: tools exposed to the LLM. Each is a thin wrapper over a forecast function."""
import datetime as dt
import json
from pathlib import Path

from backend import config
from backend import forecast as fc

_SALES = json.loads((Path(__file__).parent / "sales_calendar.json").read_text())

TOOLS = [
    {
        "name": "get_safe_to_spend",
        "description": "Money the user can spend today after pots and upcoming bills.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate_purchase",
        "description": "Check whether a purchase is affordable and suggest better timing.",
        "input_schema": {
            "type": "object",
            "properties": {"amount": {"type": "number"}, "date": {"type": "string", "format": "date"}},
            "required": ["amount"],
        },
    },
    {
        "name": "get_upcoming_sales",
        "description": "Major sales events in the next N days.",
        "input_schema": {"type": "object", "properties": {"within_days": {"type": "integer"}}},
    },
    {
        "name": "get_alerts",
        "description": "Current spending alerts and risks.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def get_upcoming_sales(within_days: int = 60) -> list[dict]:
    end = config.TODAY + dt.timedelta(days=within_days)
    return [s for s in _SALES if config.TODAY <= dt.date.fromisoformat(s["date"]) <= end]


def run_tool(user_id: str, name: str, args: dict):
    """Dispatch an LLM tool call. Return JSON-serialisable data."""
    if name == "get_safe_to_spend":
        return fc.safe_to_spend(user_id, config.TODAY).model_dump(mode="json")
    if name == "simulate_purchase":
        on = dt.date.fromisoformat(args["date"]) if args.get("date") else config.TODAY
        return fc.simulate_purchase(user_id, args["amount"], on).model_dump(mode="json")
    if name == "get_upcoming_sales":
        return get_upcoming_sales(args.get("within_days", 60))
    if name == "get_alerts":
        return [a.model_dump(mode="json") for a in fc.detect_alerts(user_id)]
    raise ValueError(f"Unknown tool: {name}")
