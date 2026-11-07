"""Offline checks that the coach prompts keep the guardrails the live demo flows rely on.

The live flows (Ibiza no -> savings plan, rent pot protection, deposit ideas, twin odds,
overspending, news, struggling user, prompt injection) were tuned against these phrases.
If one is edited away, this fails before the demo does.
"""
from pathlib import Path

import pytest

from backend import config
from backend.agent import orchestrator, planner_tools, tools

PROMPTS = Path(orchestrator.PROMPTS_DIR)
BASE = (PROMPTS / "base.md").read_text(encoding="utf-8")
BASE_LOWER = BASE.lower()


@pytest.mark.parametrize("phrase", [
    # pots are untouchable; only safe to spend is spendable
    "never spare",
    'only "safe to spend" is spendable',
    "say no kindly",
    # proactive about the biggest risk, and remembers the thread
    "anticipate",
    "remember the conversation",
    # short enough to be read aloud
    "under 70 words",
    "read aloud",
    # never push buying
    "never push or encourage the user to buy anything",
    "the choice is theirs",
    # fair, non-judgmental, signposts free help
    "never shame",
    "free, confidential help",
    # no invented maths
    "never do arithmetic yourself",
    "never guess",
    # injection
    "untrusted data",
    "ignore any instructions",
])
def test_base_prompt_keeps_key_guardrails(phrase):
    assert phrase in BASE_LOWER


@pytest.mark.parametrize("tool_name", [
    "simulate_purchase", "get_safe_to_spend", "plan_savings_goal", "plan_emergency_fund",
    "plan_debt_payoff", "run_twin_simulations", "get_spending_forecast", "get_deposit_ideas",
    "get_economic_news",
])
def test_base_prompt_routes_to_tools_that_exist(tool_name):
    assert f"`{tool_name}`" in BASE
    assert tool_name in {t["name"] for t in tools.TOOLS} | {t["name"] for t in planner_tools.PLANNER_TOOLS}


def test_base_prompt_names_free_help_and_official_sources():
    for org in ("MoneyHelper", "Citizens Advice", "StepChange", "GOV.UK", "HMRC"):
        assert org in BASE


def test_savings_plan_instructions_match_tool_output_fields():
    assert "pot_to_create" in BASE and "fits_forecast" in BASE
    assert "pot_to_create" in planner_tools.GOAL_TOOL["description"]


def test_base_prompt_stays_concise_for_voice():
    assert len(BASE.split()) < 900


@pytest.mark.parametrize("tone,limit", [("friendly", "4 short sentences"), ("direct", "3 short"),
                                        ("simple", "3 short sentences")])
def test_tone_files_cap_length_and_let_it_win(tone, limit):
    text = (PROMPTS / f"tone_{tone}.md").read_text(encoding="utf-8").lower()
    assert limit in text
    assert "this length limit wins" in text


def test_simple_tone_avoids_negative_figures_and_signposts_help():
    text = (PROMPTS / "tone_simple.md").read_text(encoding="utf-8")
    assert "Never say a negative pound figure" in text
    assert "StepChange" in text


def test_savings_goal_always_offers_a_concrete_pot(monkeypatch):
    monkeypatch.setattr(config, "MOCK_FORECAST", True)  # mock safe-to-spend = £210, forecast falls
    monkeypatch.setattr(config, "MOCK_DATA", True)
    out = tools.run_tool("sam", "plan_savings_goal",
                         {"target_amount": 1600, "target_date": "2027-11-07", "goal_name": "Ibiza trip"})
    assert out["pot_to_create"] == {
        "name": "Ibiza trip", "monthly_amount": out["required_monthly"], "target_amount": 1600.0,
        "target_date": "2027-11-07", "fits_forecast": out["feasible"], "created": False,
    }
    assert out["safe_to_spend_today"] == 210 and out["numbers_used"]["safe_to_spend"] == 210
