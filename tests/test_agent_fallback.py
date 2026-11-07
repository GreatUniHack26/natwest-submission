"""Tests for offline demo reliability, snapshot fingerprinting, cache invalidation,
and deterministic tool-backed fallback replies (Issue #19).
"""
from __future__ import annotations

import datetime as dt
import math
import re

import httpx
import pytest

from backend import config
from backend import forecast as fc
from backend.agent import fallback
from contracts.schemas import (
    Alert,
    BreakdownItem,
    ChatReply,
    Forecast,
    ForecastPoint,
    PurchaseVerdict,
    RiskEvent,
    SafeToSpend,
)

CURRENCY_RE = re.compile(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)")
BANNED_BUY_PHRASES = (
    "you should buy",
    "buy it now",
    "go ahead and buy",
    "treat yourself",
    "definitely buy",
    "must buy",
    "recommend buying",
)
BANNED_SIMPLE_JARGON = (
    "discretionary",
    "liquidity",
    "cashflow",
    "allocation",
    "variance",
    "amortisation",
    "volatility",
    "deficit",
    "obligations",
)


@pytest.fixture(autouse=True)
def _clean_cache_and_block_network(monkeypatch: pytest.MonkeyPatch):
    """Clear cache before/after each test and ensure no network/LLM calls ever occur."""
    fallback.clear_cache()

    def _forbidden_post(*args, **kwargs):
        raise AssertionError("Network/LLM call attempted during offline fallback test!")

    monkeypatch.setattr(httpx, "post", _forbidden_post)
    yield
    fallback.clear_cache()


def _assert_all_quoted_currency_verified(reply: ChatReply) -> None:
    """Every £ amount appearing in reply.text must exist in reply.numbers_used."""
    matches = CURRENCY_RE.findall(reply.text)
    verified = list(reply.numbers_used.values())
    for raw in matches:
        val = float(raw.replace(",", ""))
        assert any(math.isclose(val, v, abs_tol=0.01) for v in verified), (
            f"Unverified currency £{raw} in fallback reply '{reply.text}' "
            f"not found in numbers_used={reply.numbers_used}"
        )


def _count_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def test_is_demo_mode_env_and_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr(config, "DEMO_MODE", False, raising=False)
    assert fallback.is_demo_mode() is False

    monkeypatch.setenv("DEMO_MODE", "0")
    assert fallback.is_demo_mode() is False

    monkeypatch.setenv("DEMO_MODE", "1")
    assert fallback.is_demo_mode() is True

    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setattr(config, "DEMO_MODE", True, raising=False)
    assert fallback.is_demo_mode() is True


@pytest.mark.parametrize(
    "question,expected_keys",
    [
        ("Can I afford a £30 shirt?", {"price", "safe_to_spend", "safe_after"}),
        ("What is my safe to spend?", {"balance", "pots_total", "upcoming_bills", "safe_amount", "safe_to_spend"}),
        ("Why did I get this alert?", {"balance", "pots_total", "upcoming_bills", "safe_amount", "safe_to_spend"}),
        ("What happens in December?", {"balance", "pots_total", "upcoming_bills", "safe_to_spend", "forecast_low", "forecast_expected"}),
    ],
)
def test_scripted_demo_questions_offline_with_complete_numbers(question: str, expected_keys: set[str]):
    reply = fallback.build_fallback_reply("sam", question, "friendly")
    assert reply is not None
    assert isinstance(reply, ChatReply)
    assert reply.text.strip()
    assert expected_keys.issubset(set(reply.numbers_used.keys()))
    _assert_all_quoted_currency_verified(reply)

    lowered = reply.text.lower()
    for phrase in BANNED_BUY_PHRASES:
        assert phrase not in lowered


def test_no_hardcoded_numbers_dynamic_safe_to_spend_and_simulation(monkeypatch: pytest.MonkeyPatch):
    """When forecast returns custom numbers (e.g. 999.0 and 949.0), fallback replies reflect them dynamically."""
    custom_sts = SafeToSpend(
        balance=2450.0,
        pots_total=1100.0,
        upcoming_bills=351.0,
        safe_amount=999.0,
        breakdown=[
            BreakdownItem(label="Account balance", amount=2450.0),
            BreakdownItem(label="Set aside in pots", amount=-1100.0),
            BreakdownItem(label="Bills due before next income", amount=-351.0),
        ],
    )
    custom_verdict = PurchaseVerdict(
        affordable=True,
        safe_after=949.0,
        better_date=dt.date(2026, 11, 27),
        reason="Dynamic test verdict.",
        numbers_used={"price": 50.0, "safe_to_spend": 999.0, "safe_after": 949.0},
    )

    monkeypatch.setattr(fc, "safe_to_spend", lambda user_id, as_of: custom_sts)
    monkeypatch.setattr(fc, "simulate_purchase", lambda user_id, amount, on_date: custom_verdict)

    sts_reply = fallback.build_fallback_reply("sam", "What is my safe to spend?", "friendly")
    assert sts_reply is not None
    assert sts_reply.numbers_used["safe_amount"] == 999.0
    assert sts_reply.numbers_used["balance"] == 2450.0
    assert sts_reply.numbers_used["pots_total"] == 1100.0
    assert sts_reply.numbers_used["upcoming_bills"] == 351.0
    assert "£999" in sts_reply.text
    assert "£2450" in sts_reply.text
    assert "£210" not in sts_reply.text
    assert "£1640" not in sts_reply.text
    _assert_all_quoted_currency_verified(sts_reply)

    sim_reply = fallback.build_fallback_reply("sam", "Can I afford a £50 jacket?", "direct")
    assert sim_reply is not None
    assert sim_reply.numbers_used["price"] == 50.0
    assert sim_reply.numbers_used["safe_to_spend"] == 999.0
    assert sim_reply.numbers_used["safe_after"] == 949.0
    assert "£999" in sim_reply.text
    assert "£949" in sim_reply.text
    assert "2026-11-27" in sim_reply.text
    assert "£210" not in sim_reply.text
    assert "£180" not in sim_reply.text
    _assert_all_quoted_currency_verified(sim_reply)


def test_cache_hit_and_stale_cache_invalidation_on_snapshot_change(monkeypatch: pytest.MonkeyPatch):
    """When safe_to_spend changes from £210 to £125, fingerprint changes and stale £210 cache is not served."""
    current_safe = {"amount": 210.0, "balance": 1640.0}

    def _dynamic_sts(user_id: str, as_of: dt.date) -> SafeToSpend:
        return SafeToSpend(
            balance=current_safe["balance"],
            pots_total=1250.0,
            upcoming_bills=180.0,
            safe_amount=current_safe["amount"],
            breakdown=[],
        )

    monkeypatch.setattr(fc, "safe_to_spend", _dynamic_sts)

    fp_initial = fallback.compute_snapshot_fingerprint("sam")
    assert fp_initial != "unavailable"

    # Build and cache reply at safe_amount = 210.0
    reply_210 = fallback.build_fallback_reply("sam", "What is my safe to spend?", "friendly")
    assert reply_210 is not None
    assert "£210" in reply_210.text
    assert reply_210.numbers_used["safe_to_spend"] == 210.0

    # Cache hit returns a copy with numbers_used intact
    cached_hit = fallback.get_cached_reply("sam", "  what is my safe to spend? ", "friendly")
    assert cached_hit is not None
    assert cached_hit.text == reply_210.text
    assert cached_hit.numbers_used == reply_210.numbers_used
    cached_hit.numbers_used["safe_to_spend"] = -1.0
    assert fallback.get_cached_reply("sam", "What is my safe to spend?", "friendly").numbers_used["safe_to_spend"] == 210.0

    # Now mutate user's underlying balance / safe_amount from 210.0 -> 125.0
    current_safe["amount"] = 125.0
    current_safe["balance"] = 1555.0

    fp_updated = fallback.compute_snapshot_fingerprint("sam")
    assert fp_updated != fp_initial

    # Stale £210 reply must NOT be served
    stale_lookup = fallback.get_cached_reply("sam", "What is my safe to spend?", "friendly")
    assert stale_lookup is None

    # Rebuilding fallback reply reflects the new £125 snapshot
    reply_125 = fallback.build_fallback_reply("sam", "What is my safe to spend?", "friendly")
    assert reply_125 is not None
    assert "£125" in reply_125.text
    assert "£210" not in reply_125.text
    assert reply_125.numbers_used["safe_to_spend"] == 125.0


@pytest.mark.parametrize("tone", ["friendly", "direct", "simple"])
@pytest.mark.parametrize(
    "question",
    [
        "Can I afford a £30 shirt?",
        "What is my safe to spend?",
        "Why did I get this alert?",
        "What happens in December?",
        "How much income tax do I owe?",
    ],
)
def test_all_three_tones_and_simple_tone_constraints(tone: str, question: str):
    reply = fallback.build_fallback_reply("sam", question, tone)  # type: ignore[arg-type]
    assert reply is not None
    assert reply.text.strip()
    _assert_all_quoted_currency_verified(reply)

    lowered = reply.text.lower()
    for phrase in BANNED_BUY_PHRASES:
        assert phrase not in lowered

    if tone == "simple":
        sentences = _count_sentences(reply.text)
        assert 1 <= len(sentences) <= 3, f"Expected <= 3 sentences in simple tone, got {len(sentences)}: {reply.text}"
        for sentence in sentences:
            assert len(sentence.split()) <= 25, f"Sentence too long for simple tone: '{sentence}'"
        for jargon in BANNED_SIMPLE_JARGON:
            assert jargon not in lowered, f"Jargon '{jargon}' found in simple tone reply: {reply.text}"


def test_tax_benefits_legal_redirect_and_failure_returns_none(monkeypatch: pytest.MonkeyPatch):
    tax_reply = fallback.build_fallback_reply("sam", "Can I claim Universal Credit or get tax advice?", "friendly")
    assert tax_reply is not None
    assert tax_reply.numbers_used == {}
    assert any(src in tax_reply.text for src in ("GOV.UK", "HMRC", "Citizens Advice", "MoneyHelper"))

    # When forecast raises an error, fingerprint is 'unavailable' and build_fallback_reply returns None
    def _boom(*args, **kwargs):
        raise RuntimeError("Database down")

    monkeypatch.setattr(fc, "safe_to_spend", _boom)
    assert fallback.compute_snapshot_fingerprint("sam") == "unavailable"
    assert fallback.build_fallback_reply("sam", "What is my safe to spend?", "friendly") is None
