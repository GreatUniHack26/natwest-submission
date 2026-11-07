"""Tips and regional benchmarks for the "Tips and benchmarks" screen.

GET /users/{id}/tips        -> list[Tip]          (backend.rules.all_tips; information, not advice)
GET /users/{id}/benchmarks  -> BenchmarkSummary   (ONS averages via backend.agent.benchmark_adapter)
GET /users/{id}/entitlements -> EntitlementSummary ("Money you might be owed", backend.rules.entitlements)

Benchmarks are ONS *averages* for the user's region and household type. ONS does not publish
a spread, so there is no "usual range" here; the client must not invent one. When no
comparison is possible (unknown region, unsupported household size) `comparable` is False and
`explanation` says why, so the client can show a missing-data state instead of a guess.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend import data
from backend.agent import benchmark_adapter
from backend.rules import all_tips
from backend.rules import entitlements
from contracts.schemas import Tip

router = APIRouter(prefix="/users/{user_id}", tags=["insights"])

WINDOW_DAYS = 30


class BenchmarkComparison(BaseModel):
    category: str  # app category, e.g. "groceries"
    ons_category: Optional[str] = None  # ONS name, e.g. "Food & non-alcoholic drinks"
    region_monthly_gbp: float  # ONS average for the user's region
    household_type_monthly_gbp: Optional[float] = None  # ONS average for the household type
    user_spend_30d: float  # the user's own spend in the last 30 days


class BenchmarkSource(BaseModel):
    publication: str
    table: str
    url: str


class BenchmarkSummary(BaseModel):
    user_id: str
    region: str  # User.region as stored (a city)
    region_label: Optional[str] = None  # ONS region, e.g. "North West"
    household_size: Optional[int] = None
    household_type_label: Optional[str] = None
    household_size_note: Optional[str] = None
    window_days: int = WINDOW_DAYS
    comparable: bool
    comparisons: list[BenchmarkComparison]
    explanation: Optional[str] = None  # why nothing is comparable, when comparable is False
    framing_note: str
    periods_note: Optional[str] = None
    sources: list[BenchmarkSource]


class Entitlement(BaseModel):
    id: str
    title: str
    why_you: str  # plain-English evidence from the user's own data
    est_value: Optional[int] = None  # annual £, only where GOV.UK gives a defensible figure
    confidence: str  # "likely" | "worth checking"
    how_to_claim: str
    gov_url: str
    checker_url: Optional[str] = None
    depends_on: Optional[str] = None  # id of an item this needs first (e.g. "universal_credit")
    last_checked: str


class EntitlementSummary(BaseModel):
    user_id: str
    items: list[Entitlement]
    total_est_value: int
    disclaimer: str


def _user_or_404(user_id: str):
    try:
        return data.get_user(user_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=e.args[0] if e.args else f"Unknown user: {user_id}")


@router.get("/tips", response_model=list[Tip])
def get_tips(user_id: str):
    _user_or_404(user_id)
    return all_tips(user_id)


@router.get("/entitlements", response_model=EntitlementSummary)
def get_entitlements(user_id: str):
    _user_or_404(user_id)
    return entitlements.entitlements_summary(user_id)


def _sources(region: str, size: Optional[int]) -> list[BenchmarkSource]:
    if size is None:
        return []
    try:
        from backend.benchmarks import get_benchmark

        b = get_benchmark(region, size)
    except Exception:
        return []
    seen, out = set(), []
    for cut in (b.region, b.household_composition):
        if cut.source.url in seen:
            continue
        seen.add(cut.source.url)
        out.append(BenchmarkSource(publication=cut.source.publication, table=cut.source.table, url=cut.source.url))
    return out


@router.get("/benchmarks", response_model=BenchmarkSummary)
def get_benchmarks(user_id: str, household_size: Optional[int] = Query(None, ge=1, le=10)):
    _user_or_404(user_id)
    args = {"household_size": household_size} if household_size is not None else {}
    try:
        raw = benchmark_adapter.run_get_benchmark(user_id, args)
    except RuntimeError as e:  # benchmarks module unavailable
        raise HTTPException(status_code=503, detail=str(e))

    comparisons = [BenchmarkComparison(**c) for c in raw.get("comparisons", [])] if raw.get("comparable") else []
    size = raw.get("household_size")
    return BenchmarkSummary(
        user_id=user_id,
        region=raw.get("region", ""),
        region_label=raw.get("region_label"),
        household_size=size,
        household_type_label=raw.get("household_type_label"),
        household_size_note=raw.get("household_size_note"),
        comparable=bool(comparisons),
        comparisons=comparisons,
        explanation=raw.get("explanation") if not comparisons else None,
        framing_note=raw.get("framing_note", benchmark_adapter.FRAMING_NOTE),
        periods_note=raw.get("periods_note"),
        sources=_sources(raw.get("region", ""), size) if comparisons else [],
    )


@router.get("/alarms")
def get_alarms(user_id: str):
    """One ranked, de-duplicated alert feed in plain words (act / watch / good)."""
    from backend import config as _config
    from backend.insights.alarms import build_alarms

    if _config.MOCK_FORECAST:
        raise HTTPException(503, "Alarms require real forecast mode")
    try:
        data.get_user(user_id)
    except Exception as exc:
        raise HTTPException(404, "Unknown user") from exc
    return {"user_id": user_id, "alarms": build_alarms(user_id)}
