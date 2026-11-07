"""Agent tools backed by the planner module: debt payoff, savings goal, emergency fund.

Each function takes already-validated top-level arguments (tools._validate_args) and returns
compact, JSON-serialisable data for the LLM. Every figure the model may quote is also placed in
a nested `numbers_used` dict, which the orchestrator verifies replies against.

Nothing here saves anything: a suggested pot is only described, never created. The debt tool
always applies the user's current safe-to-spend as the month-1 cap, so a plan can't ask for money
that is protected for essentials and pots; if safe-to-spend can't be computed the tool fails
(and the agent says so) rather than silently dropping that protection.
"""
import datetime as dt
import math
import re
from typing import Any

from pydantic import ValidationError

from backend import config
from backend import forecast as fc
from backend.planner import Debt, plan_debt, plan_emergency_fund, plan_goal
from backend.planner.debt import StrategyPlan

MAX_DEBTS = 10
MAX_NAME = 60
MAX_BUILD_MONTHS = 60
DEBT_KEYS = {"name", "balance", "apr", "minimum"}

DEBT_TOOL = {
    "name": "plan_debt_payoff",
    "description": (
        "Compare the avalanche (highest interest first) and snowball (smallest balance first) ways of "
        "paying off the user's debts for a monthly budget they state. Always capped by their safe-to-spend, "
        "so it never touches money set aside for essentials and pots. Only use debts the user told you about."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "debts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "balance": {"type": "number", "description": "pounds owed now"},
                        "apr": {"type": "number", "description": "percent per year, e.g. 22.9"},
                        "minimum": {"type": "number", "description": "minimum monthly payment in pounds"},
                    },
                    "required": ["name", "balance", "apr", "minimum"],
                    "additionalProperties": False,
                },
            },
            "monthly_budget": {"type": "number", "description": "pounds per month they can put towards debt"},
        },
        "required": ["debts", "monthly_budget"],
        "additionalProperties": False,
    },
}

GOAL_TOOL = {
    "name": "plan_savings_goal",
    "description": (
        "Work out the monthly saving needed to reach a savings goal (e.g. a holiday) by a date, and whether "
        "the user's forecast can afford it. Suggests a pot but does not create one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "target_amount": {"type": "number"},
            "target_date": {"type": "string", "format": "date"},
            "goal_name": {"type": "string"},
        },
        "required": ["target_amount", "target_date"],
        "additionalProperties": False,
    },
}

EMERGENCY_TOOL = {
    "name": "plan_emergency_fund",
    "description": (
        "Target an emergency fund of 3 months of the user's essential spending and check whether their "
        "forecast can afford building it (default over 12 months). Suggests a pot but does not create one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"build_months": {"type": "integer"}},
        "additionalProperties": False,
    },
}

PLANNER_TOOLS = [DEBT_TOOL, GOAL_TOOL, EMERGENCY_TOOL]


# ---- argument checks ---------------------------------------------------------------------

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "debt"


def _parse_debts(raw: Any) -> list[Debt]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("debts must be a non-empty list")
    if len(raw) > MAX_DEBTS:
        raise ValueError(f"at most {MAX_DEBTS} debts can be planned at once")
    debts = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict) or set(item) != DEBT_KEYS:
            raise ValueError(f"debt {i} must have exactly: name, balance, apr, minimum")
        if not isinstance(item["name"], str) or not item["name"].strip() or len(item["name"]) > MAX_NAME:
            raise ValueError(f"debt {i}: name must be 1-{MAX_NAME} characters")
        for key in ("balance", "apr", "minimum"):
            if not _is_number(item[key]):
                raise ValueError(f"debt {i}: {key} must be a finite number")
        try:
            debts.append(Debt(name=item["name"].strip(), balance=item["balance"], apr=item["apr"],
                              minimum=item["minimum"]))
        except ValidationError as e:
            raise ValueError(f"debt {i} ({item['name']}): {e.errors()[0]['loc'][0]} is out of range") from e
    slugs = [_slug(d.name) for d in debts]
    if len(set(slugs)) != len(slugs):
        raise ValueError("debt names must be unique")
    return debts


# ---- tools --------------------------------------------------------------------------------

def _strategy_summary(s: StrategyPlan) -> dict:
    return {
        "feasible": s.feasible,
        "reason": s.reason,
        "explanation": s.explanation,
        "months": s.months,
        "payoff_date": s.payoff_date.isoformat() if s.payoff_date else None,
        "total_interest": s.total_interest,
        "total_paid": s.total_paid,
        "first_month_total": s.first_month_total,
        "shortfall": s.shortfall,
        "payoff_order": s.payoff_order,
        "first_month_payments": [
            {"debt": p.debt, "payment": p.payment} for p in s.payments if p.month == 1
        ],
    }


def debt_payoff(user_id: str, args: dict) -> dict:
    debts = _parse_debts(args["debts"])
    budget = args["monthly_budget"]
    if not _is_number(budget) or budget < 0:
        raise ValueError("monthly_budget must be a non-negative number")
    safe = fc.safe_to_spend(user_id, config.TODAY).safe_amount
    plan = plan_debt(debts, float(budget), safe_to_spend=safe, start_date=config.TODAY)

    numbers = {"monthly_budget": plan.monthly_budget, "safe_to_spend": safe,
               "cap_month_1": plan.cap_month_1, "interest_saved_by_avalanche": plan.interest_saved_by_avalanche}
    for d in debts:
        numbers[f"{_slug(d.name)}_balance"] = d.balance
        numbers[f"{_slug(d.name)}_minimum"] = d.minimum
    for label, s in (("avalanche", plan.avalanche), ("snowball", plan.snowball)):
        numbers.update({f"{label}_total_interest": s.total_interest, f"{label}_total_paid": s.total_paid,
                        f"{label}_first_month_total": s.first_month_total, f"{label}_shortfall": s.shortfall})
        if s.months is not None:
            numbers[f"{label}_months"] = float(s.months)
        for p in s.payments:
            if p.month == 1:
                numbers[f"{label}_first_payment_{_slug(p.debt)}"] = p.payment
    return {
        "monthly_budget": plan.monthly_budget,
        "safe_to_spend": safe,
        "cap_month_1": plan.cap_month_1,
        "avalanche": _strategy_summary(plan.avalanche),
        "snowball": _strategy_summary(plan.snowball),
        "interest_saved_by_avalanche": plan.interest_saved_by_avalanche,
        "numbers_used": numbers,
    }


def _goal_summary(plan) -> dict:
    pot = plan.suggested_pot
    return {
        "feasible": plan.feasible,
        "reason": plan.reason,
        "explanation": plan.explanation,
        "goal_name": plan.goal_name,
        "target_amount": plan.target_amount,
        "target_date": plan.target_date.isoformat() if plan.target_date else None,
        "already_saved": plan.already_saved,
        "remaining": plan.remaining,
        "months": plan.months,
        "required_monthly": plan.required_monthly,
        "available_monthly": plan.available_monthly,
        "shortfall": plan.shortfall,
        "low_band_gap": plan.low_band_gap,
        "suggested_pot": ({"name": pot.name, "amount": pot.amount, "created": False} if pot else None),
    }


def _goal_numbers(plan) -> dict[str, float]:
    numbers = {k: float(getattr(plan, k)) for k in
               ("target_amount", "already_saved", "remaining", "required_monthly", "available_monthly",
                "shortfall", "low_band_gap", "months")}
    if plan.suggested_pot:
        numbers["suggested_pot_amount"] = plan.suggested_pot.amount
    return numbers


def savings_goal(user_id: str, args: dict) -> dict:
    amount = args["target_amount"]
    if not _is_number(amount) or amount <= 0:
        raise ValueError("target_amount must be a positive number")
    raw_date = args["target_date"]
    if not isinstance(raw_date, str):
        raise ValueError("target_date must be an ISO date string (YYYY-MM-DD)")
    try:
        target = dt.date.fromisoformat(raw_date)
    except ValueError as e:
        raise ValueError(f"Invalid ISO date '{raw_date}'") from e
    name = args.get("goal_name")
    if name is None:
        name = "Savings goal"
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME:
        raise ValueError(f"goal_name must be 1-{MAX_NAME} characters")
    plan = plan_goal(user_id, float(amount), target, name.strip())  # ValueError if date not in future
    out = _goal_summary(plan)
    out["numbers_used"] = _goal_numbers(plan)
    return out


def emergency_fund(user_id: str, args: dict) -> dict:
    months = args.get("build_months")
    if months is None:
        months = 12
    if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= MAX_BUILD_MONTHS:
        raise ValueError(f"build_months must be an integer between 1 and {MAX_BUILD_MONTHS}")
    result = plan_emergency_fund(user_id, months)
    out = {
        "feasible": result.feasible,
        "reason": result.reason,
        "explanation": result.explanation,
        "monthly_essentials": result.monthly_essentials,
        "window_months": result.window_months,
        "target_amount": result.target_amount,
        "plan": _goal_summary(result.plan) if result.plan else None,
    }
    numbers = {"monthly_essentials": result.monthly_essentials, "target_amount": result.target_amount}
    if result.plan:
        numbers.update(_goal_numbers(result.plan))
    out["numbers_used"] = numbers
    return out
