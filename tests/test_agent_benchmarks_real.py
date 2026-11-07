"""The get_benchmark agent tool against the REAL backend.benchmarks module and seeded data.

The adapter's own tests mock the module; these use the real return shape so the two can't drift apart.
"""
import json
import math
import re

import pytest

from backend import config
from backend.agent import orchestrator, tools
from backend.benchmarks import get_benchmark
from backend.data import categoriser
from backend.data.seed import seed


@pytest.fixture(autouse=True)
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "MOCK_FORECAST", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "bm.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    seed()


def _fig(region, size, cut, app_category):
    bench = get_benchmark(region, size)
    figures = getattr(bench, cut).figures
    return next(f for f in figures if f.app_category == app_category)


def run(uid, args):
    return tools.run_tool(uid, "get_benchmark", args)


# ---- category queries -----------------------------------------------------------------------------

def test_groceries_are_comparable_and_use_the_published_figures():
    out = run("sam", {"category": "groceries"})
    reg, comp = _fig("Manchester", 1, "region", "groceries"), _fig("Manchester", 1, "household_composition", "groceries")
    assert out["comparable"] and out["region"] == "Manchester" and out["household_size"] == 1
    assert out["benchmark_amount"] == reg.monthly_gbp == out["numbers_used"]["benchmark_groceries"]
    assert out["household_benchmark_amount"] == comp.monthly_gbp == out["numbers_used"]["benchmark_household_groceries"]
    assert out["benchmark"]["region"]["label"] == "North West"
    assert out["benchmark"]["household_type"]["label"] == "Non-retired: one person"
    assert "Office for National Statistics" in out["benchmark"]["region"]["source"]
    assert out["user_spend_30d"] == out["numbers_used"]["user_groceries_spend"] > 0


def test_unmapped_categories_are_not_comparable_and_nothing_is_invented():
    out = run("sam", {"category": "eating out"})
    assert not out["comparable"] and out["benchmark"] is None
    assert "clothing, groceries, transport" in out["explanation"]
    assert set(out["numbers_used"]) == {"user_eating_out_spend"}   # no benchmark number fabricated


def test_ons_category_names_can_be_asked_for_directly():
    out = run("sam", {"category": "Food & non-alcoholic drinks"})
    assert out["comparable"] and out["benchmark"]["region"]["ons_category"] == "Food & non-alcoholic drinks"


def test_each_persona_resolves_through_the_real_module():
    for uid in ("sam", "alex", "maya", "dan"):
        out = run(uid, {"category": "transport"})
        assert out["comparable"], uid


# ---- household size ------------------------------------------------------------------------------

def test_family_with_explicit_size_four_gets_the_family_composition():
    out = run("maya", {"category": "groceries", "household_size": 4})
    assert out["household_size_source"] == "provided" and "household_size_note" not in out
    assert out["benchmark"]["household_type"]["label"] == "Two adults with two children"
    assert out["household_benchmark_amount"] == _fig("Leeds", 4, "household_composition", "groceries").monthly_gbp


def test_inferred_household_size_is_flagged_so_the_agent_can_ask():
    out = run("maya", {"category": "groceries"})
    assert out["household_size"] == 2 and out["household_size_source"] == "household members"
    assert "children are not recorded" in out["household_size_note"] and "household_size" in out["household_size_note"]


def test_single_person_default_needs_no_caveat():
    out = run("sam", {"category": "groceries"})
    assert out["household_size_source"] == "default (one person)" and "household_size_note" not in out


@pytest.mark.parametrize("size", [3, 5, 10])
def test_unsupported_household_sizes_give_an_answer_not_an_exception(size):
    out = run("maya", {"household_size": size})
    assert not out["comparable"] and out["benchmark"] is None
    assert "Valid sizes: 1" in out["explanation"] and out["numbers_used"] == {}


# ---- no category: the overview ------------------------------------------------------------------------

def test_overview_compares_only_categories_the_app_can_map():
    out = run("alex", {})
    assert out["comparable"] and [c["category"] for c in out["comparisons"]] == ["clothing", "groceries", "transport"]
    groceries = next(c for c in out["comparisons"] if c["category"] == "groceries")
    assert groceries["region_monthly_gbp"] == _fig("Bristol", 1, "region", "groceries").monthly_gbp
    assert out["region_label"] == "South West" and out["household_type_label"] == "Non-retired: one person"
    assert "eating out" not in out["numbers_used"] and "benchmark_eating_out" not in out["numbers_used"]


# ---- shape: compact, honest, serialisable -------------------------------------------------------------

@pytest.mark.parametrize("uid,args", [("sam", {}), ("sam", {"category": "groceries"}), ("maya", {"household_size": 4}),
                                      ("alex", {"category": "transport"})])
def test_results_are_compact_json_with_finite_numbers_and_the_framing_note(uid, args):
    out = run(uid, args)
    text = json.dumps(out)
    assert len(text) < 3000                       # the raw ONS blob was ~20x this
    assert "figures" not in text and "ons_code" not in text
    assert out["framing_note"] and "not directly comparable" in out["periods_note"]
    assert out["numbers_used"] and all(isinstance(v, float) and math.isfinite(v) for v in out["numbers_used"].values())


# ---- through the chat loop ------------------------------------------------------------------------------

def test_chat_quotes_only_figures_that_are_in_numbers_used(monkeypatch):
    monthly = _fig("Manchester", 1, "region", "groceries").monthly_gbp
    responses = iter([
        {"id": "m", "role": "assistant", "stop_reason": "tool_use",
         "content": [{"type": "tool_use", "id": "t1", "name": "get_benchmark", "input": {"category": "groceries"}}]},
        {"id": "m2", "role": "assistant", "stop_reason": "end_turn",
         "content": [{"type": "text", "text": f"The average household in your region spends about £{monthly:.2f} a month on food."}]},
    ])
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kw: next(responses))
    reply = orchestrator.run_chat("sam", "Is my food spending normal?")
    quoted = [float(x) for x in re.findall(r"£(\d+\.\d+)", reply.text)]
    assert quoted == [monthly] and monthly in reply.numbers_used.values()
