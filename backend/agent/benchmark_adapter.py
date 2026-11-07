"""Regional benchmarks tool adapter for the FinTime LLM agent (#41).

Wraps `backend.benchmarks.get_benchmark` (Issue #40, owned by P1 Data) behind a safe
tool schema and execution adapter. Never invents benchmark datasets or numerical
comparisons. If `backend.benchmarks` is unavailable, keeps the extension disabled
by default and works immediately when `backend.benchmarks` is present or mocked.
"""
from __future__ import annotations

import datetime as dt
import importlib
import inspect
import math
import re
from typing import Any

from backend import config, data

BENCHMARK_TOOL_SCHEMA: dict[str, Any] = {
    "name": "get_benchmark",
    "description": "Compare user spending neutrally against regional household benchmarks from official statistics.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "household_size": {"type": "integer"},
        },
        "additionalProperties": False,
    },
}

FRAMING_NOTE = (
    "Neutral comparison for context only; every household's priorities and income patterns differ."
)

_ALLOWED_KEYS = frozenset({"category", "household_size"})
_WINDOW_DAYS = 30


def is_benchmarks_available() -> bool:
    """Return True if `backend.benchmarks` is importable and exposes `get_benchmark`."""
    try:
        mod = importlib.import_module("backend.benchmarks")
    except Exception:
        return False
    return callable(getattr(mod, "get_benchmark", None))


def _is_valid_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _is_finite_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return slug or "total"


def validate_benchmark_args(args: Any) -> dict[str, Any]:
    """Validate arguments for `get_benchmark`."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ValueError("Invalid arguments for get_benchmark: expected an object/dict")

    unknown_keys = set(args.keys()) - _ALLOWED_KEYS
    if unknown_keys:
        raise ValueError(f"Unexpected arguments for get_benchmark: {sorted(unknown_keys)}")

    cleaned: dict[str, Any] = {}

    if "category" in args and args["category"] is not None:
        cat = args["category"]
        if not isinstance(cat, str) or not cat.strip():
            raise ValueError("category must be a non-empty string")
        cleaned["category"] = cat.strip()

    if "household_size" in args and args["household_size"] is not None:
        hh_size = args["household_size"]
        if not _is_valid_int(hh_size) or hh_size < 1 or hh_size > 10:
            raise ValueError("household_size must be an integer between 1 and 10")
        cleaned["household_size"] = hh_size

    return cleaned


def _resolve_household_size(user: Any, explicit_size: int | None) -> int:
    if explicit_size is not None:
        return explicit_size
    household_id = getattr(user, "household_id", None)
    if household_id and hasattr(data, "get_household_members"):
        try:
            members = data.get_household_members(household_id)
            if members:
                return max(1, min(10, len(members)))
        except Exception:
            pass
    return 1


def _compute_user_category_spend(user_id: str) -> dict[str, float]:
    """Compute actual 30-day spending per category from user transactions."""
    window_start = config.TODAY - dt.timedelta(days=_WINDOW_DAYS)
    txs = data.get_transactions(user_id, start=window_start, end=config.TODAY)
    totals_pence: dict[str, int] = {}
    for tx in txs:
        if tx.date <= config.TODAY and tx.amount < 0 and tx.kind != "income":
            cat_key = tx.category.strip().lower()
            totals_pence[cat_key] = totals_pence.get(cat_key, 0) + round(-float(tx.amount) * 100)
    return {cat: round(pence / 100.0, 2) for cat, pence in sorted(totals_pence.items())}


def _normalize_raw_benchmark(raw: Any) -> Any:
    if hasattr(raw, "model_dump") and callable(raw.model_dump):
        return raw.model_dump(mode="json")
    if isinstance(raw, dict):
        return {str(k): _normalize_raw_benchmark(v) for k, v in raw.items()}
    if isinstance(raw, (list, tuple)):
        return [_normalize_raw_benchmark(item) for item in raw]
    return raw


def _call_backend_get_benchmark(
    fn: Any, region: str, household_size: int, category: str | None
) -> Any:
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
        if category is not None and ("category" in sig.parameters or has_var_kw):
            return fn(region, household_size, category=category)
        pos_params = [
            p
            for p in params
            if p.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if category is not None and len(pos_params) >= 3:
            return fn(region, household_size, category)
    except (ValueError, TypeError):
        pass
    return fn(region, household_size)


def _extract_category_map(normalized: Any) -> dict[str, float]:
    """Extract a mapping of lowercase category name -> numeric benchmark figure."""
    if not isinstance(normalized, dict):
        return {}

    for container_key in ("categories", "spending", "benchmarks", "by_category"):
        sub = normalized.get(container_key)
        if isinstance(sub, dict):
            extracted = {
                str(k).strip().lower(): round(float(v), 2)
                for k, v in sub.items()
                if _is_finite_number(v)
            }
            if extracted:
                return extracted

    if "category" in normalized and isinstance(normalized["category"], str):
        cat_name = normalized["category"].strip().lower()
        for val_key in ("amount", "benchmark", "monthly_gbp", "weekly_gbp", "value", "spend"):
            val = normalized.get(val_key)
            if _is_finite_number(val):
                return {cat_name: round(float(val), 2)}

    metadata_keys = {"region", "household_size", "source", "period", "unit", "year"}
    direct: dict[str, float] = {}
    for k, v in normalized.items():
        if k.lower() in metadata_keys:
            continue
        if _is_finite_number(v):
            direct[str(k).strip().lower()] = round(float(v), 2)
    return direct


def run_get_benchmark(user_id: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute the `get_benchmark` tool for `user_id`."""
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id must be a non-empty string")

    validated = validate_benchmark_args(args)

    if not is_benchmarks_available():
        raise RuntimeError("Regional benchmarks module (backend.benchmarks) is not available")

    mod = importlib.import_module("backend.benchmarks")
    get_benchmark_fn = getattr(mod, "get_benchmark")

    user = data.get_user(user_id)
    region = user.region
    household_size = _resolve_household_size(user, validated.get("household_size"))
    category: str | None = validated.get("category")

    user_spend_by_cat = _compute_user_category_spend(user_id)
    raw_result = _call_backend_get_benchmark(get_benchmark_fn, region, household_size, category)
    normalized_benchmark = _normalize_raw_benchmark(raw_result)
    category_benchmarks = _extract_category_map(normalized_benchmark)

    numbers_used: dict[str, float] = {}

    if category is not None:
        cat_lower = category.lower()
        cat_slug = _slugify(cat_lower)
        user_cat_spend = user_spend_by_cat.get(cat_lower, 0.0)
        numbers_used[f"user_{cat_slug}_spend"] = user_cat_spend

        matched_value: float | None = None
        if cat_lower in category_benchmarks:
            matched_value = category_benchmarks[cat_lower]
        elif _is_finite_number(normalized_benchmark):
            matched_value = round(float(normalized_benchmark), 2)

        if matched_value is None:
            return {
                "region": region,
                "household_size": household_size,
                "category": category,
                "comparable": False,
                "benchmark": None,
                "user_spend_30d": user_cat_spend,
                "explanation": (
                    f"No comparable regional benchmark category '{category}' is available "
                    f"for {region} (household size {household_size})."
                ),
                "framing_note": FRAMING_NOTE,
                "numbers_used": numbers_used,
            }

        numbers_used[f"benchmark_{cat_slug}"] = matched_value
        return {
            "region": region,
            "household_size": household_size,
            "category": category,
            "comparable": True,
            "benchmark": normalized_benchmark,
            "benchmark_amount": matched_value,
            "user_spend_30d": user_cat_spend,
            "framing_note": FRAMING_NOTE,
            "numbers_used": numbers_used,
        }

    # No single category specified: include all available benchmark categories and user spend
    if not category_benchmarks:
        return {
            "region": region,
            "household_size": household_size,
            "comparable": False,
            "benchmark": normalized_benchmark,
            "user_spend_30d": user_spend_by_cat,
            "explanation": (
                f"No regional benchmark figures are available for {region} "
                f"(household size {household_size})."
            ),
            "framing_note": FRAMING_NOTE,
            "numbers_used": numbers_used,
        }

    for cat_key, bench_val in sorted(category_benchmarks.items()):
        slug = _slugify(cat_key)
        numbers_used[f"benchmark_{slug}"] = bench_val
        numbers_used[f"user_{slug}_spend"] = user_spend_by_cat.get(cat_key, 0.0)

    for cat_key, spend_val in sorted(user_spend_by_cat.items()):
        slug = _slugify(cat_key)
        numbers_used.setdefault(f"user_{slug}_spend", spend_val)

    return {
        "region": region,
        "household_size": household_size,
        "comparable": True,
        "benchmark": normalized_benchmark,
        "user_spend_30d": user_spend_by_cat,
        "framing_note": FRAMING_NOTE,
        "numbers_used": numbers_used,
    }
