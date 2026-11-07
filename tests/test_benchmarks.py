"""Unit tests for backend.benchmarks (issue #40). Static ONS data; no network."""
import inspect
import math

import pytest

from backend import benchmarks
from backend.benchmarks import data, lookup
from backend.benchmarks import get_benchmark

PERSONAS = [("Manchester", 1, "North West"), ("Bristol", 1, "South West"),
            ("Leeds", 4, "Yorkshire and The Humber")]


@pytest.mark.parametrize("city,size,ons", PERSONAS)
def test_city_lookup(city, size, ons):
    b = get_benchmark(city, size)
    assert b.region.label == ons
    assert b.region.cut == "region"
    assert b.household_composition.cut == "household_composition"


def test_size_mapping():
    assert get_benchmark("Leeds", 1).household_composition.label == "Non-retired: one person"
    assert get_benchmark("Leeds", 4).household_composition.label == "Two adults with two children"


def test_ons_region_names_and_case_insensitive():
    for q in ["North West", "north west", "  NORTH WEST "]:
        assert get_benchmark(q, 1).region.label == "North West"
    assert get_benchmark("yorkshire and the humber", 4).region.label == "Yorkshire and The Humber"
    assert get_benchmark("MANCHESTER", 1).region.label == "North West"
    assert get_benchmark("east", 1).region.label == "East of England"


def test_every_ons_region_resolves():
    for name in data.REGION_FIGURES:
        assert get_benchmark(name, 1).region.label == name


def test_unknown_region_raises_helpful():
    with pytest.raises(ValueError) as e:
        get_benchmark("Atlantis", 1)
    assert "North West" in str(e.value) and "Manchester" in str(e.value)


@pytest.mark.parametrize("size", [0, 3, 5, -1, True])
def test_unknown_size_raises_helpful(size):
    with pytest.raises(ValueError) as e:
        get_benchmark("Leeds", size)
    assert "Valid sizes" in str(e.value) and "4" in str(e.value)


def test_every_figure_has_source_reference():
    for region in data.REGION_FIGURES:
        for size in lookup.HOUSEHOLD_SIZE_TO_COMPOSITION:
            b = get_benchmark(region, size)
            for cut in (b.region, b.household_composition):
                assert cut.source.table.strip() and cut.source.url.startswith("https://www.ons.gov.uk/")
                assert cut.source.publication and cut.source.edition and cut.source.file_url
                for f in cut.figures:
                    assert f.source == cut.source
                    assert f.source.table.strip() and f.source.url.startswith("https://www.ons.gov.uk/")


def test_source_mentions_table_ids():
    assert "A33" in data.SOURCES["ons_region"]["table"]
    assert "Table 5" in data.SOURCES["ons_composition"]["table"]


def test_monthly_is_weekly_times_52_over_12():
    b = get_benchmark("Manchester", 4)
    for cut in (b.region, b.household_composition):
        for f in cut.figures:
            assert f.monthly_gbp == round(f.weekly_gbp * 52 / 12, 2)
    assert lookup.monthly_from_weekly(12.0) == 52.0


def test_numbers_positive_and_finite():
    for table in (data.REGION_FIGURES, data.COMPOSITION_FIGURES):
        for label, figs in table.items():
            for code, v in figs.items():
                if v is None:
                    continue
                assert isinstance(v, float) and math.isfinite(v) and v > 0, (label, code)
    for persons in (data.REGION_PERSONS_PER_HOUSEHOLD, data.COMPOSITION_PERSONS_PER_HOUSEHOLD):
        assert all(math.isfinite(v) and v > 0 for v in persons.values())


def test_region_groups_sum_to_published_subtotal():
    # Region table publishes all 12 groups: they sum to "All expenditure groups" (ONS rounding, +-0.3)
    # and groups 1-12 + group 13 equal "Total expenditure" (+-0.2).
    for region, f in data.REGION_FIGURES.items():
        assert abs(sum(f[str(i)] for i in range(1, 13)) - f["1-12"]) <= 0.3, region
        assert abs(f["1-12"] + f["13"] - f["Total"]) <= 0.2, region


def test_composition_totals_consistent():
    # Health (6) and Education (10) are suppressed, so groups can only sum to LESS than 1-12.
    for label, f in data.COMPOSITION_FIGURES.items():
        assert f["6"] is None and f["10"] is None
        published = sum(f[str(i)] for i in range(1, 13) if f[str(i)] is not None)
        assert published <= f["1-12"] + 0.3, label
        assert abs(f["1-12"] + f["13"] - f["Total"]) <= 0.2, label


def test_suppressed_categories_reported_not_zero():
    b = get_benchmark("Leeds", 4)
    assert set(b.household_composition.suppressed_categories) == {"Health", "Education"}
    assert "Health" not in {f.category for f in b.household_composition.figures}
    assert b.region.suppressed_categories == []


def test_app_category_mapping_is_conservative():
    b = get_benchmark("Bristol", 1)
    mapped = {f.category: f.app_category for f in b.region.figures if f.app_category}
    assert mapped == {"Food & non-alcoholic drinks": "groceries", "Clothing & footwear": "clothing",
                      "Transport": "transport"}


def test_spot_values_match_source_tables():
    # Spot checks against the cells read from the ONS workbooks.
    assert data.REGION_FIGURES["North West"]["Total"] == 554.7
    assert data.REGION_FIGURES["Yorkshire and The Humber"]["1"] == 66.0
    assert data.COMPOSITION_FIGURES["Non-retired: one person"]["1"] == 40.3
    assert data.COMPOSITION_FIGURES["Two adults with two children"]["Total"] == 883.2


def test_deterministic():
    assert get_benchmark("Leeds", 4) == get_benchmark("leeds", 4).model_copy(
        update={"region_query": "Leeds"})
    assert get_benchmark("Leeds", 4).model_dump() == get_benchmark("Leeds", 4).model_dump()


def test_no_network_db_or_llm_imports():
    src = "".join(inspect.getsource(m) for m in (benchmarks, lookup, data))
    for banned in ("requests", "httpx", "urllib", "sqlite3", "anthropic", "socket", "aiohttp"):
        assert f"import {banned}" not in src and f"from {banned}" not in src, banned
