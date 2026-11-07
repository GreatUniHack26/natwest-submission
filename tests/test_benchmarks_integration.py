"""Integration: benchmarks resolve for every real persona's User.region."""
import math

from backend.benchmarks import get_benchmark
from backend.data.generator import generate_household, generate_persona


def _all_personas():
    out = [generate_persona("sam"), generate_persona("salaried")]
    out += generate_household("family")
    return out


def test_every_persona_region_resolves():
    for user, _txns, _pots in _all_personas():
        b = get_benchmark(user.region, 1)
        assert b.region.figures and b.household_composition.figures
        assert b.region.label  # an ONS region


def test_family_uses_size_four():
    members = generate_household("family")
    b = get_benchmark(members[0][0].region, 4)
    assert b.household_composition.label == "Two adults with two children"


def test_weekly_units_line_up_with_persona_spend():
    user, txns, _ = generate_persona("sam")
    days = (max(t.date for t in txns) - min(t.date for t in txns)).days + 1
    weeks = days / 7
    groceries = -sum(t.amount for t in txns if t.category == "groceries")
    weekly = groceries / weeks
    b = get_benchmark(user.region, 1)
    bench = next(f for f in b.region.figures if f.app_category == "groceries")
    # Smoke check only (structure and finiteness), no verdict on whether Sam is "normal".
    assert math.isfinite(weekly) and weekly >= 0
    assert math.isfinite(bench.weekly_gbp) and bench.weekly_gbp > 0
    assert bench.monthly_gbp > bench.weekly_gbp
    assert bench.source.url.startswith("https://www.ons.gov.uk/")
