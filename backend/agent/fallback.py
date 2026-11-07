"""Deterministic offline fallback, response cache, and snapshot fingerprinting for FinTime.

Provides reliable demo and offline operation when the LLM API is slow, rate-limited,
or unconfigured. Every financial number in a fallback reply is fetched dynamically at
runtime from `backend.forecast` and recorded in `ChatReply.numbers_used`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Optional

from backend import config
from backend import forecast as fc
from contracts.schemas import Alert, ChatReply, Forecast, PurchaseVerdict, SafeToSpend, Tone

VALID_TONES: tuple[Tone, ...] = ("friendly", "direct", "simple")
DEFAULT_TONE: Tone = "friendly"

# In-memory response cache keyed by (user_id, normalized_question, tone, snapshot_fingerprint)
_REPLY_CACHE: dict[tuple[str, str, str, str], ChatReply] = {}

_AMOUNT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:pounds?|gbp|quid)\b", re.IGNORECASE),
    re.compile(r"\bfor\s+(\d+(?:,\d{3})*(?:\.\d+)?)\b", re.IGNORECASE),
)

_TAX_BENEFITS_LEGAL_KEYWORDS: tuple[str, ...] = (
    "tax",
    "hmrc",
    "universal credit",
    "benefit",
    "benefits",
    "council tax",
    "pip",
    "housing benefit",
    "jobseeker",
    "self assessment",
    "tax return",
    "national insurance",
    "legal advice",
    "solicitor",
    "lawsuit",
    "court",
    "insolvency",
    "bankruptcy",
)

_PURCHASE_KEYWORDS: tuple[str, ...] = (
    "afford",
    "buy",
    "purchase",
    "spend on",
    "shirt",
    "laptop",
    "trainers",
    "shoes",
    "coat",
    "jacket",
    "phone",
    "tv",
    "ticket",
    "gift",
    "wait",
    "worth buying",
)

_ALERT_KEYWORDS: tuple[str, ...] = (
    "alert",
    "alerts",
    "warning",
    "warnings",
    "notification",
    "overspend",
    "overspending",
    "sudden change",
    "spike",
    "eating out",
)

_FORECAST_KEYWORDS: tuple[str, ...] = (
    "forecast",
    "december",
    "january",
    "next month",
    "christmas",
    "outlook",
    "project",
    "projection",
    "future",
    "coming weeks",
    "56 days",
    "90 days",
    "low-band",
    "low band",
    "negative",
    "run out",
    "shortfall",
)

_SAFE_TO_SPEND_KEYWORDS: tuple[str, ...] = (
    "safe to spend",
    "safe-to-spend",
    "safe amount",
    "spend today",
    "can i spend",
    "how much can i spend",
    "balance",
    "pots",
    "upcoming bills",
    "left to spend",
    "available to spend",
)


def is_demo_mode() -> bool:
    """Return True when DEMO_MODE is enabled via config attribute or environment variable."""
    if bool(getattr(config, "DEMO_MODE", False)):
        return True
    return os.getenv("DEMO_MODE", "0") == "1"


def normalize_question(message: str) -> str:
    """Normalize a user message for cache lookups and intent matching."""
    if not isinstance(message, str):
        return ""
    collapsed = re.sub(r"\s+", " ", message.strip().lower())
    return collapsed.rstrip("?.! ")


def compute_snapshot_fingerprint(user_id: str) -> str:
    """Compute a SHA-256 fingerprint of the user's current financial snapshot.

    Returns 'unavailable' if `safe_to_spend` fails, ensuring stale cached replies
    are never served when underlying financial data changes or becomes unavailable.
    """
    if not user_id or not isinstance(user_id, str):
        return "unavailable"
    try:
        sts = fc.safe_to_spend(user_id, config.TODAY)
        sts_dump = sts.model_dump(mode="json")
    except Exception:
        return "unavailable"

    forecast_dump: Any = None
    try:
        fc_obj = fc.forecast(user_id)
        forecast_dump = fc_obj.model_dump(mode="json")
    except Exception:
        forecast_dump = None

    payload = (
        config.TODAY.isoformat(),
        bool(getattr(config, "MOCK_DATA", False)),
        bool(getattr(config, "MOCK_FORECAST", False)),
        sts_dump,
        forecast_dump,
    )
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _copy_reply(reply: ChatReply) -> ChatReply:
    return ChatReply(
        text=reply.text,
        numbers_used=dict(reply.numbers_used),
        audio_url=reply.audio_url,
    )


def get_cached_reply(user_id: str, message: str, tone: Optional[Tone] = None) -> Optional[ChatReply]:
    """Return a copy of the cached ChatReply if the snapshot fingerprint still matches."""
    resolved_tone: Tone = tone if tone in VALID_TONES else DEFAULT_TONE  # type: ignore[assignment]
    fingerprint = compute_snapshot_fingerprint(user_id)
    if fingerprint == "unavailable":
        return None
    key = (user_id, normalize_question(message), resolved_tone, fingerprint)
    cached = _REPLY_CACHE.get(key)
    if cached is None:
        return None
    return _copy_reply(cached)


def cache_reply(user_id: str, message: str, tone: Optional[Tone], reply: ChatReply) -> None:
    """Store a ChatReply in the cache under the user's current snapshot fingerprint."""
    resolved_tone: Tone = tone if tone in VALID_TONES else DEFAULT_TONE  # type: ignore[assignment]
    fingerprint = compute_snapshot_fingerprint(user_id)
    if fingerprint == "unavailable":
        return
    key = (user_id, normalize_question(message), resolved_tone, fingerprint)
    _REPLY_CACHE[key] = _copy_reply(reply)


def clear_cache() -> None:
    """Clear all cached replies."""
    _REPLY_CACHE.clear()


def _fmt_gbp(value: float) -> str:
    """Format a GBP figure cleanly without trailing '.0' when whole."""
    rounded = round(float(value), 2)
    sign = "-" if rounded < 0 else ""
    abs_val = abs(rounded)
    if abs_val.is_integer():
        return f"{sign}£{int(abs_val)}"
    return f"{sign}£{abs_val:.2f}"


def _parse_purchase_amount(message: str) -> Optional[float]:
    """Extract a positive GBP amount from a user message if present."""
    for pattern in _AMOUNT_PATTERNS:
        match = pattern.search(message)
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                if val > 0:
                    return val
            except ValueError:
                continue
    return None


def _is_tax_benefits_legal(norm_msg: str) -> bool:
    return any(kw in norm_msg for kw in _TAX_BENEFITS_LEGAL_KEYWORDS)


def _is_purchase_question(message: str, norm_msg: str) -> Optional[float]:
    amount = _parse_purchase_amount(message)
    if amount is not None and (any(kw in norm_msg for kw in _PURCHASE_KEYWORDS) or "£" in message):
        return amount
    return None


def _is_alert_question(norm_msg: str) -> bool:
    return any(kw in norm_msg for kw in _ALERT_KEYWORDS)


def _is_forecast_question(norm_msg: str) -> bool:
    return any(kw in norm_msg for kw in _FORECAST_KEYWORDS)


def _is_safe_to_spend_question(norm_msg: str) -> bool:
    return any(kw in norm_msg for kw in _SAFE_TO_SPEND_KEYWORDS)


def _format_tax_benefits_legal_reply(tone: Tone) -> ChatReply:
    if tone == "simple":
        text = (
            "I only share general money tips and cannot give tax, benefits, or legal advice. "
            "Please check GOV UK, HMRC, Citizens Advice, or MoneyHelper for free official help."
        )
    elif tone == "direct":
        text = (
            "FinTime provides general financial information, not regulated tax, benefits, or legal advice. "
            "Consult official sources: GOV.UK, HMRC, Citizens Advice, or MoneyHelper."
        )
    else:
        text = (
            "I can only share general information rather than regulated tax, benefits, or legal advice. "
            "For accurate guidance on your situation, please check official sources such as GOV.UK, HMRC, "
            "Citizens Advice, or MoneyHelper."
        )
    return ChatReply(text=text, numbers_used={})


def _format_purchase_reply(
    verdict: PurchaseVerdict,
    amount: float,
    sts: Optional[SafeToSpend],
    tone: Tone,
) -> ChatReply:
    numbers_used: dict[str, float] = {"price": float(amount)}
    if sts is not None:
        numbers_used["safe_to_spend"] = float(sts.safe_amount)
    if isinstance(verdict.numbers_used, dict):
        for k, v in verdict.numbers_used.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                numbers_used[str(k)] = float(v)
    numbers_used["price"] = float(amount)
    numbers_used["safe_after"] = float(verdict.safe_after)
    if "safe_to_spend" not in numbers_used and sts is not None:
        numbers_used["safe_to_spend"] = float(sts.safe_amount)

    price_val = numbers_used["price"]
    safe_after_val = numbers_used["safe_after"]
    if safe_after_val < 0:
        numbers_used["shortfall"] = abs(float(safe_after_val))
    safe_now_val = numbers_used.get("safe_to_spend", safe_after_val + price_val)
    numbers_used["safe_to_spend"] = float(safe_now_val)

    price_str = _fmt_gbp(price_val)
    safe_now_str = _fmt_gbp(safe_now_val)
    safe_after_str = _fmt_gbp(safe_after_val)
    better_date_str = verdict.better_date.isoformat() if verdict.better_date else None

    if tone == "simple":
        if verdict.affordable:
            s1 = f"You have {safe_now_str} left to spend right now"
            s2 = f"A {price_str} item leaves you with {safe_after_str}"
            if better_date_str:
                s3 = f"You can also wait until {better_date_str} for a sale if you want to save money."
            else:
                s3 = "Waiting is always fine if you want to keep more money saved."
            text = f"{s1}. {s2}. {s3}"
        else:
            s1 = f"You have {safe_now_str} left to spend right now"
            s2 = f"A {price_str} item would take you to {safe_after_str}, which is more than you have free"
            if better_date_str:
                s3 = f"Waiting until {better_date_str} is a safer option."
            else:
                s3 = "Holding off for now will protect your money for bills."
            text = f"{s1}. {s2}. {s3}"
    elif tone == "direct":
        if verdict.affordable:
            base = (
                f"Affordable: yes. Price: {price_str}. Current safe-to-spend: {safe_now_str}. "
                f"Safe-to-spend after purchase: {safe_after_str}."
            )
            if better_date_str:
                text = f"{base} Option: wait until {better_date_str} for an upcoming sale to keep safe-to-spend higher."
            else:
                text = f"{base} Waiting remains an option to preserve your safe-to-spend."
        else:
            base = (
                f"Affordable: no. Price: {price_str} exceeds current safe-to-spend of {safe_now_str} "
                f"(safe-to-spend after purchase would be {safe_after_str})."
            )
            if better_date_str:
                text = f"{base} Consider waiting until {better_date_str} or skipping this purchase."
            else:
                text = f"{base} Holding off protects your upcoming bills and pots."
    else:
        if verdict.affordable:
            base = (
                f"A {price_str} purchase fits within your current safe-to-spend of {safe_now_str}, "
                f"leaving you with {safe_after_str} afterwards."
            )
            if better_date_str:
                text = (
                    f"{base} However, waiting until {better_date_str} is a great option if you'd like "
                    f"to catch an upcoming sale and keep more of your {safe_now_str} available in the meantime."
                )
            else:
                text = f"{base} There is no rush to buy today if you prefer to keep {safe_now_str} available."
        else:
            base = (
                f"A {price_str} purchase is above your current safe-to-spend of {safe_now_str} "
                f"and would leave your safe-to-spend at {safe_after_str}."
            )
            if better_date_str:
                text = f"{base} Waiting until {better_date_str} or pausing this purchase will help protect your bills and pots."
            else:
                text = f"{base} Waiting or skipping this purchase for now will keep your bills and pots covered."

    return ChatReply(text=text, numbers_used=numbers_used)


def _format_safe_to_spend_reply(sts: SafeToSpend, tone: Tone) -> ChatReply:
    numbers_used: dict[str, float] = {
        "balance": float(sts.balance),
        "pots_total": float(sts.pots_total),
        "upcoming_bills": float(sts.upcoming_bills),
        "safe_amount": float(sts.safe_amount),
        "safe_to_spend": float(sts.safe_amount),
    }
    safe_str = _fmt_gbp(sts.safe_amount)
    bal_str = _fmt_gbp(sts.balance)
    pots_str = _fmt_gbp(sts.pots_total)
    bills_str = _fmt_gbp(sts.upcoming_bills)

    if tone == "simple":
        text = (
            f"You can safely spend {safe_str} today. "
            f"You have {bal_str} in your account, with {pots_str} saved in pots and {bills_str} kept for bills."
        )
    elif tone == "direct":
        text = (
            f"Safe-to-spend today: {safe_str} (balance {bal_str} minus {pots_str} in pots "
            f"and {bills_str} in upcoming bills)."
        )
    else:
        text = (
            f"Your safe-to-spend today is {safe_str}. "
            f"That comes from your {bal_str} account balance minus {pots_str} set aside in pots "
            f"and {bills_str} reserved for upcoming bills before your next income."
        )

    return ChatReply(text=text, numbers_used=numbers_used)


def _format_alerts_reply(alerts: list[Alert], sts: SafeToSpend, tone: Tone) -> ChatReply:
    numbers_used: dict[str, float] = {
        "balance": float(sts.balance),
        "pots_total": float(sts.pots_total),
        "upcoming_bills": float(sts.upcoming_bills),
        "safe_amount": float(sts.safe_amount),
        "safe_to_spend": float(sts.safe_amount),
    }
    safe_str = _fmt_gbp(sts.safe_amount)
    bal_str = _fmt_gbp(sts.balance)
    bills_str = _fmt_gbp(sts.upcoming_bills)

    if not alerts:
        if tone == "simple":
            text = (
                f"You have no spending warnings right now. "
                f"You have {safe_str} left to spend from your {bal_str} account after {bills_str} for bills."
            )
        elif tone == "direct":
            text = f"Active alerts: none. Current safe-to-spend is {safe_str} from a {bal_str} balance ({bills_str} upcoming bills)."
        else:
            text = (
                f"You don't have any active alerts right now. "
                f"Your safe-to-spend is {safe_str} from your {bal_str} balance after {bills_str} in upcoming bills."
            )
        return ChatReply(text=text, numbers_used=numbers_used)

    # Extract any £ figures mentioned in alert messages/actions so every quoted £ is in numbers_used
    currency_re = re.compile(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)")
    for idx, alert in enumerate(alerts):
        for raw in currency_re.findall(f"{alert.message} {alert.suggested_action}"):
            val = float(raw.replace(",", ""))
            numbers_used[f"alert_{idx + 1}_amount"] = val

    if tone == "simple":
        first = alerts[0]
        cat_part = f" on {first.category}" if first.category else ""
        text = (
            f"You got a warning because spending{cat_part} went up recently. "
            f"You now have {safe_str} left to spend from your {bal_str} account after {bills_str} for bills. "
            f"Slowing down on extra spending this week will help keep your money safe."
        )
    elif tone == "direct":
        summaries = [f"{a.message} Action: {a.suggested_action}" for a in alerts]
        joined = " | ".join(summaries)
        text = (
            f"Active alerts ({len(alerts)}): {joined} "
            f"Current safe-to-spend: {safe_str} (balance {bal_str}, upcoming bills {bills_str})."
        )
    else:
        summaries = [f"{a.message} ({a.suggested_action})" for a in alerts]
        joined = " ".join(summaries)
        text = (
            f"Here is why you received that alert: {joined} "
            f"Right now your safe-to-spend is {safe_str} from a {bal_str} balance with {bills_str} reserved for upcoming bills."
        )

    return ChatReply(text=text, numbers_used=numbers_used)


def _format_forecast_reply(forecast_obj: Forecast, sts: SafeToSpend, tone: Tone) -> ChatReply:
    numbers_used: dict[str, float] = {
        "balance": float(sts.balance),
        "pots_total": float(sts.pots_total),
        "upcoming_bills": float(sts.upcoming_bills),
        "safe_amount": float(sts.safe_amount),
        "safe_to_spend": float(sts.safe_amount),
    }

    points = forecast_obj.points or []
    dec_points = [p for p in points if p.date.month == 12]
    target_points = dec_points if dec_points else points

    if points:
        numbers_used["start_expected"] = float(points[0].expected)
        min_point = min(points, key=lambda p: p.low)
        numbers_used["min_low"] = float(min_point.low)
    if target_points:
        min_target = min(target_points, key=lambda p: p.low)
        numbers_used["forecast_low"] = float(min_target.low)
        if min_target.low < 0:
            numbers_used["forecast_shortfall"] = abs(float(min_target.low))
        numbers_used["forecast_expected"] = float(min_target.expected)
        low_date_str = min_target.date.isoformat()
    else:
        numbers_used["forecast_low"] = float(sts.safe_amount)
        numbers_used["forecast_expected"] = float(sts.balance)
        low_date_str = config.TODAY.isoformat()

    safe_str = _fmt_gbp(sts.safe_amount)
    bal_str = _fmt_gbp(sts.balance)
    low_str = _fmt_gbp(numbers_used["forecast_low"])
    exp_str = _fmt_gbp(numbers_used["forecast_expected"])

    risk_Note = ""
    if forecast_obj.risk_events:
        ev = forecast_obj.risk_events[0]
        risk_Note = f" Risk on {ev.date.isoformat()}: {ev.reason}"

    if tone == "simple":
        text = (
            f"You have {bal_str} now and {safe_str} left to spend today. "
            f"Around {low_date_str}, your money is expected to be {exp_str}, or {low_str} if pay is low. "
            f"Saving a bit now or picking up extra work can stop you running short."
        )
    elif tone == "direct":
        text = (
            f"Forecast ({forecast_obj.horizon_days} days): current balance {bal_str}, safe-to-spend {safe_str}. "
            f"By {low_date_str}, expected balance is {exp_str} with a low-case of {low_str}.{risk_Note}"
        )
    else:
        text = (
            f"Looking at your {forecast_obj.horizon_days}-day forecast from your {bal_str} balance "
            f"({safe_str} safe-to-spend today), around {low_date_str} your expected balance is {exp_str}, "
            f"though the cautious estimate reaches {low_str}.{risk_Note}"
        )

    return ChatReply(text=text, numbers_used=numbers_used)


def build_fallback_reply(
    user_id: str,
    message: str,
    tone: Optional[Tone] = None,
) -> Optional[ChatReply]:
    """Build a deterministic, tool-backed ChatReply without calling the LLM.

    Returns None if required forecast/tool calls fail so the caller can return
    the standard tool-failure apology without guessing numbers.
    """
    if not user_id or not isinstance(user_id, str) or not isinstance(message, str) or not message.strip():
        return None

    resolved_tone: Tone = tone if tone in VALID_TONES else DEFAULT_TONE  # type: ignore[assignment]
    norm_msg = normalize_question(message)

    try:
        # 1. Regulated tax / benefits / legal questions -> deterministic redirect
        if _is_tax_benefits_legal(norm_msg):
            reply = _format_tax_benefits_legal_reply(resolved_tone)
            cache_reply(user_id, message, resolved_tone, reply)
            return reply

        # 2. Affordability / purchase simulation questions
        amount = _is_purchase_question(message, norm_msg)
        if amount is not None:
            from backend.agent import tools as agent_tools

            raw_verdict = agent_tools.run_tool(user_id, "simulate_purchase", {"amount": amount})
            verdict = PurchaseVerdict(**raw_verdict) if isinstance(raw_verdict, dict) else fc.simulate_purchase(user_id, amount, config.TODAY)
            sts: Optional[SafeToSpend] = None
            if not isinstance(verdict.numbers_used, dict) or "safe_to_spend" not in verdict.numbers_used:
                raw_sts = agent_tools.run_tool(user_id, "get_safe_to_spend", {})
                sts = SafeToSpend(**raw_sts) if isinstance(raw_sts, dict) else fc.safe_to_spend(user_id, config.TODAY)
            reply = _format_purchase_reply(verdict, amount, sts, resolved_tone)
            cache_reply(user_id, message, resolved_tone, reply)
            return reply

        # 3. Alerts questions
        if _is_alert_question(norm_msg):
            from backend.agent import tools as agent_tools

            raw_alerts = agent_tools.run_tool(user_id, "get_alerts", {})
            alerts = [Alert(**a) for a in raw_alerts] if isinstance(raw_alerts, list) else fc.detect_alerts(user_id)
            raw_sts = agent_tools.run_tool(user_id, "get_safe_to_spend", {})
            sts = SafeToSpend(**raw_sts) if isinstance(raw_sts, dict) else fc.safe_to_spend(user_id, config.TODAY)
            reply = _format_alerts_reply(alerts, sts, resolved_tone)
            cache_reply(user_id, message, resolved_tone, reply)
            return reply

        # 4. Forecast / December outlook questions
        if _is_forecast_question(norm_msg):
            from backend.agent import tools as agent_tools

            raw_fc = agent_tools.run_tool(user_id, "get_forecast", {"horizon_days": 56})
            forecast_obj = Forecast(**raw_fc) if isinstance(raw_fc, dict) else fc.forecast(user_id, 56)
            raw_sts = agent_tools.run_tool(user_id, "get_safe_to_spend", {})
            sts = SafeToSpend(**raw_sts) if isinstance(raw_sts, dict) else fc.safe_to_spend(user_id, config.TODAY)
            reply = _format_forecast_reply(forecast_obj, sts, resolved_tone)
            cache_reply(user_id, message, resolved_tone, reply)
            return reply

        # 5. Safe-to-spend & general questions -> grounded in safe_to_spend
        from backend.agent import tools as agent_tools

        raw_sts = agent_tools.run_tool(user_id, "get_safe_to_spend", {})
        sts = SafeToSpend(**raw_sts) if isinstance(raw_sts, dict) else fc.safe_to_spend(user_id, config.TODAY)
        reply = _format_safe_to_spend_reply(sts, resolved_tone)
        cache_reply(user_id, message, resolved_tone, reply)
        return reply
    except Exception:
        return None
