"""Tests for Issue #17: Base & Tone System Prompts and Responsible-AI Guardrails."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from backend import config
from backend.agent import orchestrator, tools
from contracts.schemas import Tone

PROMPTS_DIR = Path(orchestrator.PROMPTS_DIR)
CURRENCY_RE = re.compile(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)")

FORBIDDEN_PURCHASE_PHRASES = (
    "you should buy",
    "go ahead and buy",
    "treat yourself",
    "buy it right now",
)

FORBIDDEN_SIMPLE_JARGON = (
    "amortisation",
    "amortization",
    "liquidity",
    "discretionary",
    "ring-fenced",
    "volatility",
    "variance",
    "collateral",
)

REPRESENTATIVE_QUESTIONS = (
    "Can I afford a £30 shirt?",
    "What is my safe to spend today?",
    "Why did I get this alert?",
    "What happens to my money in December?",
    "How can I reduce my income tax or claim Universal Credit?",
    "Can I afford a car when my data is missing?",
)

ALL_TONES: tuple[Tone, ...] = ("friendly", "direct", "simple")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, ignoring dots inside numbers or URLs like GOV.UK."""
    protected = re.sub(r"(\d)\.(\d)", r"\1<DECIMAL>\2", text.strip())
    protected = re.sub(r"GOV\.UK", "GOV<DOT>UK", protected, flags=re.IGNORECASE)
    parts = [s.strip() for s in re.split(r"[.!?]+(?:\s+|$)", protected) if s.strip()]
    return [p.replace("<DECIMAL>", ".").replace("<DOT>", ".") for p in parts]


def test_base_prompt_contains_all_responsible_ai_guardrails():
    """Verify base.md includes all required Responsible-AI rules and exact substrings."""
    base_text = (PROMPTS_DIR / "base.md").read_text(encoding="utf-8")
    lower = base_text.lower()

    # Exact substrings required by existing and current tests
    assert "You are FinTime" in base_text
    assert "Never do arithmetic yourself" in base_text

    # State numbers used and explain why
    assert "numbers_used" in base_text
    assert "why you reached your answer" in lower

    # Never push a purchase
    assert "you should buy" in lower
    assert "waiting" in lower and "not buying" in lower

    # Information, not regulated advice + official UK redirects
    assert "not regulated financial" in lower
    assert "tax" in lower and "benefits" in lower and "legal" in lower
    for source in ("GOV.UK", "HMRC", "Citizens Advice", "MoneyHelper"):
        assert source in base_text

    # Missing data / tool failure
    assert "missing" in lower
    assert "never guess" in lower or "do not guess" in lower

    # Neutral benchmark framing (#41)
    assert "regional" in lower or "household" in lower
    assert "non-judgmentally" in lower or "neutrally" in lower

    # Prompt-injection resistance
    assert "untrusted data" in lower
    assert "ignore any instructions" in lower


def test_tone_files_and_build_system_prompt():
    """Verify each tone file and orchestrator.build_system_prompt(tone) for all 3 tones."""
    expected_substrings: dict[Tone, str] = {
        "friendly": "supportive friend",
        "direct": "direct and concise",
        "simple": "reading age ~9",
    }

    built_prompts: dict[Tone, str] = {}
    for tone, phrase in expected_substrings.items():
        tone_file = PROMPTS_DIR / f"tone_{tone}.md"
        assert tone_file.exists(), f"Missing {tone_file}"
        tone_content = tone_file.read_text(encoding="utf-8")
        assert phrase in tone_content

        full_prompt = orchestrator.build_system_prompt(tone)
        assert "You are FinTime" in full_prompt
        assert "Never do arithmetic yourself" in full_prompt
        assert phrase in full_prompt
        built_prompts[tone] = full_prompt

    # All three built system prompts must be distinct
    assert len(set(built_prompts.values())) == 3

    # Simple tone explicitly forbids financial jargon and limits to 3 short sentences
    simple_lower = built_prompts["simple"].lower()
    assert "3 short sentences" in simple_lower
    assert "one clear idea" in simple_lower or "one idea per sentence" in simple_lower
    assert "jargon" in simple_lower

    with pytest.raises(ValueError, match="Unsupported tone"):
        orchestrator.build_system_prompt("aggressive")  # type: ignore[arg-type]


def _scripted_llm_for_question_and_tone(question: str, tone: Tone) -> list[dict[str, Any]]:
    """Return realistic multi-step LLM responses adhering to base.md + tone_<tone>.md."""
    if question == "Can I afford a £30 shirt?":
        replies: dict[Tone, str] = {
            "friendly": (
                "You can afford the £30 shirt because your safe-to-spend is £210, "
                "which leaves £180 afterwards. Black Friday is on 27 Nov, so waiting "
                "a few weeks or skipping it for now is a great option too."
            ),
            "direct": (
                "Affordable: a £30 purchase leaves £180 from your £210 safe-to-spend. "
                "Black Friday is on 27 Nov if you prefer to wait or not buy today."
            ),
            "simple": (
                "You have £210 safe to spend today. "
                "Buying the £30 shirt leaves £180 safe to spend. "
                "You can also wait for the 27 Nov sale or not buy it."
            ),
        }
        return [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_shirt",
                        "name": "simulate_purchase",
                        "input": {"amount": 30},
                    }
                ]
            },
            {"content": [{"type": "text", "text": replies[tone]}]},
        ]

    if question == "What is my safe to spend today?":
        replies = {
            "friendly": (
                "You have £210 safe to spend today! That comes from your £1640 balance "
                "minus £1250 set aside in pots and £180 for upcoming bills."
            ),
            "direct": (
                "Your safe-to-spend today is £210. "
                "This is calculated from your £1640 balance minus £1250 in pots and £180 in upcoming bills."
            ),
            "simple": (
                "You have £210 safe to spend today. "
                "Your bank balance is £1640 right now. "
                "We keep £1250 in your savings pots and £180 for bills."
            ),
        }
        return [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_safe",
                        "name": "get_safe_to_spend",
                        "input": {},
                    }
                ]
            },
            {"content": [{"type": "text", "text": replies[tone]}]},
        ]

    if question == "Why did I get this alert?":
        replies = {
            "friendly": (
                "You got an eating-out alert because this week's spend was 60% above your 4-week average, "
                "and a balance alert because your low forecast band dips negative around 26 Dec. "
                "Pausing one want category is an easy, pressure-free way to keep a buffer."
            ),
            "direct": (
                "Two alerts triggered: eating out is 60% above your 4-week average, "
                "and your low-band balance may drop below zero around 26 Dec. "
                "Suggested actions are capping eating out or picking up one extra December shift."
            ),
            "simple": (
                "You spent more on eating out this week than usual. "
                "Also, your money might run low around 26 Dec before January pay. "
                "Spending a little less on eating out this week can help."
            ),
        }
        return [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_alerts",
                        "name": "get_alerts",
                        "input": {},
                    }
                ]
            },
            {"content": [{"type": "text", "text": replies[tone]}]},
        ]

    if question == "What happens to my money in December?":
        replies = {
            "friendly": (
                "Based on the 56-day forecast, your expected balance moves from £1260 on 5 Dec "
                "to £180 on 26 Dec as bills go out before January pay. "
                "The low band could dip below zero around 26 Dec, so keeping a buffer helps."
            ),
            "direct": (
                "Over the 56-day forecast, your expected December balance drops from £1260 on 5 Dec "
                "to £180 on 26 Dec. "
                "There is a medium risk event on 26 Dec where the low band falls below zero before January income."
            ),
            "simple": (
                "Our 56 day check shows your money drops through December as bills are paid. "
                "Your money could get very low around 26 Dec before January pay arrives. "
                "Saving a little extra now can help cover the end of December."
            ),
        }
        return [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_forecast",
                        "name": "get_forecast",
                        "input": {"horizon_days": 56},
                    }
                ]
            },
            {"content": [{"type": "text", "text": replies[tone]}]},
        ]

    if question == "How can I reduce my income tax or claim Universal Credit?":
        replies = {
            "friendly": (
                "I can only share general information rather than personalised tax or benefits advice. "
                "For accurate guidance on income tax or Universal Credit eligibility, please check "
                "GOV.UK, HMRC, Citizens Advice, or MoneyHelper."
            ),
            "direct": (
                "I provide general information only, not regulated tax or benefits advice. "
                "Check GOV.UK, HMRC, Citizens Advice, or MoneyHelper for official Universal Credit and income tax rules."
            ),
            "simple": (
                "I cannot give personal advice about tax or benefits. "
                "Please check GOV.UK or Citizens Advice for help with Universal Credit. "
                "MoneyHelper also has free guides in plain English."
            ),
        }
        return [{"content": [{"type": "text", "text": replies[tone]}]}]

    if question == "Can I afford a car when my data is missing?":
        replies = {
            "friendly": (
                "Sorry, your account data is missing right now because the tool check failed. "
                "I never guess or invent numbers, so please try again once your data is available."
            ),
            "direct": (
                "Cannot answer: required balance and forecast data is missing due to a tool failure. "
                "I do not guess or estimate figures."
            ),
            "simple": (
                "Sorry, your money data is missing right now. "
                "I never guess your numbers. "
                "Please try asking again in a little while."
            ),
        }
        return [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_missing",
                        "name": "simulate_purchase",
                        "input": {"amount": 2000},
                    }
                ]
            },
            {"content": [{"type": "text", "text": replies[tone]}]},
        ]

    raise ValueError(f"Unhandled question: {question}")


@pytest.mark.parametrize("question", REPRESENTATIVE_QUESTIONS)
@pytest.mark.parametrize("tone", ALL_TONES)
def test_six_questions_across_three_tones_adhere_to_guardrails(monkeypatch, question: str, tone: Tone):
    """Run all 6 representative questions x 3 tones through orchestrator.run_chat."""
    monkeypatch.setattr(config, "MOCK_FORECAST", True)

    if "data is missing" in question:
        def failing_run_tool(user_id: str, name: str, args: dict):
            raise RuntimeError("Missing user balance and transaction history")

        monkeypatch.setattr(tools, "run_tool", failing_run_tool)

    scripted_turns = iter(_scripted_llm_for_question_and_tone(question, tone))
    captured_calls: list[dict[str, Any]] = []

    def fake_call_llm(**kwargs):
        captured_calls.append(kwargs)
        return next(scripted_turns)

    monkeypatch.setattr(orchestrator, "call_llm", fake_call_llm)

    reply = orchestrator.run_chat("sam", question, tone=tone)

    # 1. System prompt passed to LLM matches build_system_prompt(tone)
    assert len(captured_calls) >= 1
    expected_system_prompt = orchestrator.build_system_prompt(tone)
    assert captured_calls[0]["system_prompt"] == expected_system_prompt

    lower_reply = reply.text.lower()

    # 2. Never push a purchase in any tone or question
    for forbidden in FORBIDDEN_PURCHASE_PHRASES:
        assert forbidden not in lower_reply, f"Found forbidden phrase '{forbidden}' in reply: {reply.text}"

    # 3. Question-specific responsible-AI checks
    if question == "Can I afford a £30 shirt?":
        assert reply.numbers_used == {"price": 30.0, "safe_to_spend": 210.0, "safe_after": 180.0}
        assert "£30" in reply.text
        assert "£210" in reply.text
        assert "£180" in reply.text
    elif question == "What is my safe to spend today?":
        assert reply.numbers_used["safe_amount"] == 210.0
        assert reply.numbers_used["balance"] == 1640.0
        assert "£210" in reply.text
        assert "£1640" in reply.text
    elif question == "How can I reduce my income tax or claim Universal Credit?":
        assert reply.numbers_used == {}
        assert CURRENCY_RE.findall(reply.text) == []
        assert any(
            src in reply.text for src in ("GOV.UK", "HMRC", "Citizens Advice", "MoneyHelper")
        )
    elif question == "Can I afford a car when my data is missing?":
        assert reply.numbers_used == {}
        assert CURRENCY_RE.findall(reply.text) == []
        assert "missing" in lower_reply or "failed" in lower_reply
        assert "guess" in lower_reply

    # 4. Simple tone strict readability checks: <= 3 short sentences, zero financial jargon
    if tone == "simple":
        sentences = _split_sentences(reply.text)
        assert 1 <= len(sentences) <= 3, f"Simple tone must have <= 3 sentences, got {len(sentences)}: {sentences}"
        for sentence in sentences:
            word_count = len(sentence.split())
            assert word_count <= 18, f"Simple sentence too long ({word_count} words): '{sentence}'"
        for jargon in FORBIDDEN_SIMPLE_JARGON:
            assert jargon not in lower_reply, f"Found jargon '{jargon}' in simple reply: {reply.text}"
