"""Regional spending benchmarks (issue #40): "is my spending normal for where I live?".

Pure and deterministic: static committed ONS data only, no network, DB or LLM.

Modelling: ONS publishes spending BY REGION and BY HOUSEHOLD COMPOSITION as separate tables,
not as a cross-tab. We do not multiply or blend them. `get_benchmark` returns both cuts, each
with its own source reference and an explicit `cut` field saying where it came from.

Household size -> ONS composition (approximate; ONS has no plain "n people" category):
    1 -> "Non-retired: one person"
    2 -> "Non-retired: two adults"             (assumes two adults, no children, not retired)
    4 -> "Two adults with two children"       (the family persona)
Other sizes raise ValueError (3 is ambiguous: one adult + two children, or two adults + one child).

Monthly figures are derived: weekly * 52 / 12, rounded to pence.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from . import data

Cut = Literal["region", "household_composition"]

HOUSEHOLD_SIZE_TO_COMPOSITION: dict[int, str] = {
    1: "Non-retired: one person",
    2: "Non-retired: two adults",
    4: "Two adults with two children",
}

# ONS region names (as published, except "East" -> "East of England"), plus the UK total.
_REGIONS: tuple[str, ...] = tuple(data.REGION_FIGURES)
_REGION_ALIASES: dict[str, str] = {"east": "East of England", "uk": "United Kingdom",
                                   "yorkshire and the humber": "Yorkshire and The Humber"}

# Cities (User.region holds a city). Only mappings that are unambiguous.
CITY_TO_REGION: dict[str, str] = {
    "manchester": "North West",
    "liverpool": "North West",
    "leeds": "Yorkshire and The Humber",
    "sheffield": "Yorkshire and The Humber",
    "newcastle": "North East",
    "nottingham": "East Midlands",
    "leicester": "East Midlands",
    "birmingham": "West Midlands",
    "coventry": "West Midlands",
    "norwich": "East of England",
    "cambridge": "East of England",
    "london": "London",
    "brighton": "South East",
    "bristol": "South West",
    "cardiff": "Wales",
    "glasgow": "Scotland",
    "edinburgh": "Scotland",
    "belfast": "Northern Ireland",
}


class SourceRef(BaseModel):
    publication: str
    edition: str
    table: str
    url: str
    file_url: str


class BenchmarkFigure(BaseModel):
    category: str  # ONS category name (source of truth)
    ons_code: str  # ONS sequential group number: "1".."12", "1-12", "13", "Total"
    app_category: Optional[str] = None  # categoriser category, only where clearly equivalent
    weekly_gbp: float  # average weekly household expenditure
    monthly_gbp: float  # DERIVED: weekly * 52 / 12
    source: SourceRef


class CutBenchmark(BaseModel):
    cut: Cut
    label: str  # ONS region or composition name
    period: str
    persons_per_household: float
    figures: list[BenchmarkFigure]
    suppressed_categories: list[str]  # published by ONS as unavailable (not zero)
    source: SourceRef


class Benchmark(BaseModel):
    region_query: str
    household_size: int
    region: CutBenchmark
    household_composition: CutBenchmark
    note: str


def monthly_from_weekly(weekly: float) -> float:
    return round(weekly * 52 / 12, 2)


def _resolve_region(region: str) -> str:
    key = region.strip().lower()
    for name in _REGIONS:
        if name.lower() == key:
            return name
    if key in _REGION_ALIASES:
        return _REGION_ALIASES[key]
    if key in CITY_TO_REGION:
        return CITY_TO_REGION[key]
    raise ValueError(
        f"Unknown region {region!r}. Valid ONS regions: {', '.join(_REGIONS)}. "
        f"Known cities: {', '.join(c.title() for c in CITY_TO_REGION)}."
    )


def _cut(cut: Cut, label: str, source_key: str, figures: dict, persons: float, period: str) -> CutBenchmark:
    src = SourceRef(**data.SOURCES[source_key])
    out: list[BenchmarkFigure] = []
    suppressed: list[str] = []
    for code, name in data.CATEGORY_NAMES.items():
        v = figures[code]
        if v is None:
            suppressed.append(name)
            continue
        out.append(BenchmarkFigure(
            category=name, ons_code=code, app_category=data.APP_CATEGORY.get(code),
            weekly_gbp=v, monthly_gbp=monthly_from_weekly(v), source=src))
    return CutBenchmark(cut=cut, label=label, period=period, persons_per_household=persons,
                        figures=out, suppressed_categories=suppressed, source=src)


def get_benchmark(region: str, household_size: int) -> Benchmark:
    """Benchmark average weekly household spend for a region (ONS name or city) and household size."""
    name = _resolve_region(region)
    if isinstance(household_size, bool) or household_size not in HOUSEHOLD_SIZE_TO_COMPOSITION:
        raise ValueError(
            f"Unsupported household size {household_size!r}. Valid sizes: "
            + ", ".join(f"{k} ({v})" for k, v in HOUSEHOLD_SIZE_TO_COMPOSITION.items())
        )
    comp = HOUSEHOLD_SIZE_TO_COMPOSITION[household_size]
    return Benchmark(
        region_query=region,
        household_size=household_size,
        region=_cut("region", name, "ons_region", data.REGION_FIGURES[name],
                    data.REGION_PERSONS_PER_HOUSEHOLD[name], "FYE 2023 to FYE 2025 (3-year average)"),
        household_composition=_cut("household_composition", comp, "ons_composition",
                                   data.COMPOSITION_FIGURES[comp],
                                   data.COMPOSITION_PERSONS_PER_HOUSEHOLD[comp], "FYE 2025"),
        note=("ONS publishes region and household composition separately; these are two independent "
              "UK averages, not a region x size cross-tab. The household size mapping is approximate."),
    )


__all__ = ["get_benchmark", "Benchmark", "CutBenchmark", "BenchmarkFigure", "SourceRef",
           "CITY_TO_REGION", "HOUSEHOLD_SIZE_TO_COMPOSITION", "monthly_from_weekly"]
