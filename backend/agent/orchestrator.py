"""P3: LLM tool-calling loop.

1. Build system prompt = prompts/base.md + prompts/tone_<tone>.md (tone defaults to user's saved tone)
2. Send user message + tools.TOOLS to the LLM (model pinned in config.LLM_MODEL)
3. While the LLM requests a tool: tools.run_tool(...) and feed the result back
4. Return ChatReply(text, numbers_used=<merged numbers_used from tool results>)
5. If the voice toggle is on: audio_url = voice.speak(text)

Guardrails: never push a purchase; always state the numbers used; if a tool fails, say so plainly.
"""
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx

from backend import config, data
from backend.agent import context, fallback, tools, voice
from contracts.schemas import ChatReply, Tone

PROMPTS_DIR = Path(__file__).parent / "prompts"
VALID_TONES: tuple[Tone, ...] = ("friendly", "direct", "simple")
DEFAULT_TONE: Tone = "friendly"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
LLM_TIMEOUT_SECONDS = 15.0
MAX_TOOL_ROUNDS = 5
MAX_TOKENS = 1024

TOOL_FAILURE_APOLOGY = (
    "Sorry, I couldn't retrieve the financial figures needed to answer that right now "
    "because a tool check failed. I won't guess or invent numbers—please try again shortly."
)
LLM_UNAVAILABLE_APOLOGY = (
    "Sorry, the financial coach service is temporarily unavailable. "
    "I won't guess at your numbers—please try again in a moment."
)
MAX_ROUNDS_APOLOGY = (
    "Sorry, I couldn't finish checking all the figures within the allowed steps. "
    "Please try asking a more specific question."
)

_CURRENCY_RE = re.compile(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)")


def resolve_tone(user_id: str, tone: Optional[Tone]) -> Tone:
    """Return explicit tone if provided, otherwise fall back to the user's saved tone."""
    if tone is not None:
        if tone not in VALID_TONES:
            raise ValueError(f"Unsupported tone: {tone}")
        return tone

    try:
        user = data.get_user(user_id)
        if user and user.tone in VALID_TONES:
            return user.tone
    except Exception:
        pass
    return DEFAULT_TONE


def build_system_prompt(tone: Tone) -> str:
    """Combine prompts/base.md and prompts/tone_<tone>.md."""
    if tone not in VALID_TONES:
        raise ValueError(f"Unsupported tone: {tone}")
    base_text = (PROMPTS_DIR / "base.md").read_text(encoding="utf-8").strip()
    tone_text = (PROMPTS_DIR / f"tone_{tone}.md").read_text(encoding="utf-8").strip()
    return f"{base_text}\n\n{tone_text}"


def extract_numbers_used(result: Any) -> dict[str, float]:
    """Extract verified financial numbers from a successful tool result without doing maths."""
    extracted: dict[str, float] = {}
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and "id" in item and "est_saving" in item:
                val = item["est_saving"]
                if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val):
                    extracted[f"tip_{item['id']}_est_saving"] = float(val)
        return extracted

    if not isinstance(result, dict):
        return extracted

    nested = result.get("numbers_used")
    if isinstance(nested, dict):
        for key, val in nested.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val):
                extracted[str(key)] = float(val)
        return extracted

    for key, val in result.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val):
            extracted[str(key)] = float(val)

    return extracted


def _has_unverified_currency(text: str, numbers_used: dict[str, float]) -> bool:
    """Return True if `text` quotes any £ amount not present in `numbers_used`."""
    matches = _CURRENCY_RE.findall(text)
    if not matches:
        return False
    verified_vals = list(numbers_used.values())
    for raw in matches:
        amount = float(raw.replace(",", ""))
        if not any(math.isclose(amount, v, abs_tol=0.01) for v in verified_vals):
            return True
    return False


def call_llm(
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tool_defs: list[dict[str, Any]],
    model: str,
    timeout: float = LLM_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Send a Messages API request to the configured LLM with a strict timeout."""
    if not config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not configured")

    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt,
        "messages": messages,
        "tools": tool_defs,
    }
    headers = {
        "x-api-key": config.LLM_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    response = httpx.post(
        ANTHROPIC_API_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data_json = response.json()
    if not isinstance(data_json, dict):
        raise ValueError("Invalid LLM response payload")
    return data_json


def _parse_llm_response(response: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract text blocks, tool_use blocks, and normalized assistant content blocks."""
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    assistant_content: list[dict[str, Any]] = []

    content = response.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and isinstance(block.get("text"), str):
                text_parts.append(block["text"])
                assistant_content.append(block)
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id", f"tool_{len(tool_calls)}")),
                        "name": str(block.get("name", "")),
                        "input": block.get("input", {}),
                    }
                )
                assistant_content.append(block)
    elif isinstance(content, str):
        text_parts.append(content)
        assistant_content.append({"type": "text", "text": content})
    elif isinstance(response.get("text"), str):
        text_parts.append(response["text"])
        assistant_content.append({"type": "text", "text": response["text"]})

    if isinstance(response.get("tool_calls"), list):
        for tc in response["tool_calls"]:
            if isinstance(tc, dict):
                tc_id = str(tc.get("id", f"tool_{len(tool_calls)}"))
                tc_name = str(tc.get("name", ""))
                tc_input = tc.get("input", tc.get("arguments", {}))
                tool_calls.append({"id": tc_id, "name": tc_name, "input": tc_input})
                assistant_content.append({"type": "tool_use", "id": tc_id, "name": tc_name, "input": tc_input})

    return text_parts, tool_calls, assistant_content


def _safe_speak(text: str) -> Optional[str]:
    """Call voice.speak without ever breaking the chat response.

    Live voice runs through the full-duplex ElevenLabs agent (backend/agent/convai.py);
    per-reply MP3 clips for text chat are off unless TEXT_CHAT_TTS=1.
    """
    if os.getenv("TEXT_CHAT_TTS", "0") != "1":
        return None
    try:
        return voice.speak(text)
    except Exception:
        return None


def _build_reply(text: str, numbers_used: dict[str, float]) -> ChatReply:
    cleaned = text.strip()
    return ChatReply(
        text=cleaned,
        numbers_used=dict(numbers_used),
        audio_url=_safe_speak(cleaned),
    )


MAX_HISTORY_MESSAGES = 12


def _history_messages(history: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Sanitise client-sent prior turns into alternating Messages API turns ending with assistant."""
    cleaned: list[dict[str, Any]] = []
    for turn in (history or [])[-MAX_HISTORY_MESSAGES:]:
        role = turn.get("role") if isinstance(turn, dict) else None
        content = turn.get("content") if isinstance(turn, dict) else None
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        if cleaned and cleaned[-1]["role"] == role:
            cleaned[-1]["content"] += "\n" + content.strip()
        else:
            cleaned.append({"role": role, "content": content.strip()})
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    while cleaned and cleaned[-1]["role"] != "assistant":
        cleaned.pop()
    return cleaned


def _context_numbers(user_id: str) -> dict[str, float]:
    """Headline figures from the live context, so quoting them counts as verified."""
    try:
        money = context.build_snapshot(user_id).get("money_today", {})
        return {k: float(v) for k, v in money.items() if isinstance(v, (int, float)) and math.isfinite(v)}
    except Exception:
        return {}


def _context_section(user_id: str) -> str:
    try:
        return context.render(user_id)
    except Exception:
        return ""


def run_chat(
    user_id: str,
    message: str,
    tone: Optional[Tone] = None,
    history: Optional[list[dict[str, Any]]] = None,
) -> ChatReply:
    resolved_tone = resolve_tone(user_id, tone)

    # In explicit DEMO_MODE, serve snapshot-verified cached or deterministic tool-backed reply.
    if fallback.is_demo_mode():
        cached = fallback.get_cached_reply(user_id, message, resolved_tone)
        if cached is not None:
            return _build_reply(cached.text, cached.numbers_used)
        demo_reply = fallback.build_fallback_reply(user_id, message, resolved_tone)
        if demo_reply is not None:
            return _build_reply(demo_reply.text, demo_reply.numbers_used)

    system_prompt = build_system_prompt(resolved_tone)
    live_context = _context_section(user_id)
    if live_context:
        system_prompt = f"{system_prompt}\n\n{live_context}"
    model = config.LLM_MODEL
    active_tools = tools.get_active_tools()

    messages: list[dict[str, Any]] = [*_history_messages(history), {"role": "user", "content": message}]
    numbers_used: dict[str, float] = {}
    context_numbers = _context_numbers(user_id) if live_context else {}
    had_tool_error = False

    for round_idx in range(MAX_TOOL_ROUNDS + 1):
        try:
            response = call_llm(
                system_prompt=system_prompt,
                messages=messages,
                tool_defs=active_tools,
                model=model,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            if not had_tool_error and round_idx == 0:
                cached = fallback.get_cached_reply(user_id, message, resolved_tone)
                if cached is not None:
                    return _build_reply(cached.text, cached.numbers_used)
                if isinstance(exc, httpx.ConnectError):
                    fb_reply = fallback.build_fallback_reply(user_id, message, resolved_tone)
                    if fb_reply is not None:
                        return _build_reply(fb_reply.text, fb_reply.numbers_used)
            apology = TOOL_FAILURE_APOLOGY if had_tool_error else LLM_UNAVAILABLE_APOLOGY
            return _build_reply(apology, numbers_used)

        text_parts, tool_calls, assistant_content = _parse_llm_response(response)

        if not tool_calls:
            reply_text = "\n".join(part.strip() for part in text_parts if part.strip())
            if not reply_text:
                apology = TOOL_FAILURE_APOLOGY if had_tool_error else LLM_UNAVAILABLE_APOLOGY
                return _build_reply(apology, numbers_used)
            if had_tool_error and _has_unverified_currency(reply_text, {**context_numbers, **numbers_used}):
                return _build_reply(TOOL_FAILURE_APOLOGY, numbers_used)
            final_reply = _build_reply(reply_text, numbers_used)
            if not had_tool_error:
                fallback.cache_reply(user_id, message, resolved_tone, final_reply)
            return final_reply

        # If a tool already failed in an earlier round and the LLM still does not return a final apology, stop cleanly.
        if had_tool_error:
            return _build_reply(TOOL_FAILURE_APOLOGY, numbers_used)

        # Enforce strict maximum number of tool-calling rounds.
        if round_idx >= MAX_TOOL_ROUNDS:
            break

        messages.append({"role": "assistant", "content": assistant_content})

        tool_results_content: list[dict[str, Any]] = []
        for tc in tool_calls:
            tc_id = tc["id"]
            tc_name = tc["name"]
            tc_input = tc["input"]
            try:
                result = tools.run_tool(user_id, tc_name, tc_input)
                numbers_used.update(extract_numbers_used(result))
                tool_results_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc_id,
                        "content": json.dumps(result),
                    }
                )
            except Exception as exc:
                had_tool_error = True
                tool_results_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc_id,
                        "is_error": True,
                        "content": json.dumps({"error": str(exc)}),
                    }
                )

        messages.append({"role": "user", "content": tool_results_content})

    if had_tool_error:
        return _build_reply(TOOL_FAILURE_APOLOGY, numbers_used)
    return _build_reply(MAX_ROUNDS_APOLOGY, numbers_used)
