"""Full-duplex voice coach on ElevenLabs Conversational AI (Agents).

ElevenLabs runs streaming ASR, turn-taking, barge-in and streaming TTS over one
WebSocket. FinTime keeps the brains: the same system prompt, guardrails and
live digital-twin context as the text coach (injected per session through
conversation overrides), and the same deterministic tools (registered on the
agent as *client* tools, executed by the browser via POST /voice/tool).

The agent and its tools are created once and cached (in memory and in a small
JSON file under the gitignored audio_cache/). A hash of the desired config is
cached too, so a config change here re-syncs the remote agent on next use.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

import httpx

from backend import config
from backend.agent import context, orchestrator, tools, voice

API_BASE = "https://api.elevenlabs.io"
TIMEOUT_SECONDS = 15.0

AGENT_NAME = "Nat"
# Fast LLM hosted by ElevenLabs (Claude Haiku class); override with CONVAI_LLM.
LLM_MODEL = os.getenv("CONVAI_LLM", "claude-haiku-4-5")
# Lowest-latency ElevenLabs TTS model. English agents must use a "v2" turbo/flash model
# (the API rejects eleven_flash_v2_5 for language "en"), so Flash v2 it is.
TTS_MODEL = os.getenv("CONVAI_TTS_MODEL", "eleven_v4_turbo")
LANGUAGE = "en"

CACHE_FILE = Path(os.getenv("CONVAI_CACHE_FILE", str(Path(voice.CACHE_DIR) / "convai_agent.json")))

# FinTime tools mirrored as ElevenLabs client tools (only those that are active are registered).
VOICE_TOOL_NAMES: tuple[str, ...] = (
    "get_safe_to_spend",
    "simulate_purchase",
    "get_forecast",
    "get_alerts",
    "run_twin_simulations",
    "get_spending_forecast",
    "get_deposit_ideas",
    "plan_savings_goal",
    "plan_emergency_fund",
    "plan_debt_payoff",
    "get_upcoming_sales",
    "get_tips",
    "get_economic_news",
    "lookup_gov_uk",
    "get_money_owed",
    "get_benchmark",
)

# Server events the browser needs: audio + transcripts, barge-in, client tools, VAD for latency.
CLIENT_EVENTS = [
    "conversation_initiation_metadata",
    "asr_initiation_metadata",
    "ping",
    "audio",
    "interruption",
    "user_transcript",
    "agent_response",
    "agent_response_correction",
    "client_tool_call",
    "vad_score",
]

VOICE_ADDENDUM = """## Voice mode
You are speaking out loud in a live, two-way voice call. The user can interrupt you at any time.
- Reply in 1 to 3 short spoken sentences. Lead with the answer, then one practical next step.
- No markdown, lists, headings, emoji or symbols. Plain spoken English only.
- Say numbers naturally: "about two hundred and ten pounds", "the twenty-sixth of December". Round pence away unless they matter.
- Still take every figure from the live context or a tool, and briefly say which figure you used.
- If you need a tool, call it straight away; a short filler like "Let me check" is fine.
- If you are interrupted, stop and answer the new question. Invite the user to cut in if they want more detail.
- If the user's speech was unclear, ask them to repeat rather than guessing."""


class ConvAIUnavailable(RuntimeError):
    """ElevenLabs Conversational AI cannot be used (no key, no permission, API error)."""


_lock = threading.Lock()
_state: dict[str, Any] = {}


# ---------------------------------------------------------------- HTTP helpers

def _api_key() -> str:
    key = (config.ELEVENLABS_API_KEY or "").strip()
    if not key:
        raise ConvAIUnavailable("ELEVENLABS_API_KEY is not configured, so live voice with Nat is off.")
    return key


def _request(method: str, path: str, *, params: Optional[dict] = None, body: Optional[dict] = None) -> dict:
    try:
        response = httpx.request(
            method,
            f"{API_BASE}{path}",
            headers={"xi-api-key": _api_key(), "content-type": "application/json"},
            params=params,
            json=body,
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise ConvAIUnavailable(f"Could not reach ElevenLabs: {exc.__class__.__name__}") from exc

    if response.status_code in (401, 403):
        raise ConvAIUnavailable(
            "The ElevenLabs API key is not allowed to use Conversational AI "
            f"(HTTP {response.status_code}). Enable the 'ElevenLabs Agents' permission on the key."
        )
    if response.status_code >= 400:
        detail = response.text[:300]
        raise ConvAIUnavailable(f"ElevenLabs {method} {path} failed (HTTP {response.status_code}): {detail}")
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------- desired config

_FALLBACK_PARAM_DOCS = {
    "amount": "Purchase amount in pounds, e.g. 30",
    "date": "Planned purchase date, YYYY-MM-DD. Omit for today.",
    "within_days": "How many days ahead to look",
    "horizon_days": "How many days ahead to project, e.g. 30, 60 or 90",
    "topic": "Optional topic such as energy, fuel, rates, inflation, wages or benefits",
    "limit": "Maximum number of headlines",
    "target_amount": "Goal amount in pounds",
    "target_date": "Goal date, YYYY-MM-DD",
    "goal_name": "Short name of the goal",
    "build_months": "Months to build the fund over",
    "category": "Spending category",
    "household_size": "Number of people in the household",
}


def _el_property(name: str, schema: dict) -> dict:
    """Convert one JSON-schema property into ElevenLabs' tool parameter format."""
    ptype = schema.get("type", "string")
    desc = schema.get("description") or _FALLBACK_PARAM_DOCS.get(name) or name.replace("_", " ")
    if schema.get("format") == "date" and "YYYY-MM-DD" not in desc:
        desc = f"{desc} (YYYY-MM-DD)"
    if ptype == "object":
        return {"type": "object", "description": desc, **_el_object(schema)}
    if ptype == "array":
        return {"type": "array", "description": desc, "items": _el_property(f"{name} item", schema.get("items") or {})}
    if ptype not in ("string", "number", "integer", "boolean"):
        ptype = "string"
    prop: dict[str, Any] = {"type": ptype, "description": desc}
    if schema.get("enum"):
        prop["enum"] = list(schema["enum"])
    return prop


def _el_object(schema: dict) -> dict:
    props = schema.get("properties") or {}
    return {
        "properties": {k: _el_property(k, v) for k, v in props.items()},
        "required": [r for r in schema.get("required", []) if r in props],
    }


def voice_tool_configs() -> list[dict]:
    """ElevenLabs client-tool configs mirroring the active FinTime tools."""
    by_name = {t["name"]: t for t in tools.get_active_tools()}
    configs = []
    for name in VOICE_TOOL_NAMES:
        tool = by_name.get(name)
        if tool is None:
            continue
        cfg: dict[str, Any] = {
            "type": "client",
            "name": name,
            "description": tool.get("description", name),
            "expects_response": True,
            "response_timeout_secs": 20,
            "execution_mode": "immediate",
            "pre_tool_speech": "auto",
        }
        schema = tool.get("input_schema") or {}
        if schema.get("properties"):
            cfg["parameters"] = {"type": "object", "description": f"Arguments for {name}", **_el_object(schema)}
        configs.append(cfg)
    return configs


def agent_body(tool_ids: list[str]) -> dict:
    """Create/patch body for the Nat voice agent, tuned for low latency."""
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": "Hey, it's me, Nat! What would you like to check?",
                "language": LANGUAGE,
                "prompt": {
                    # Real prompt (base + tone + live context) arrives per session via overrides.
                    "prompt": orchestrator.build_system_prompt("friendly") + "\n\n" + VOICE_ADDENDUM,
                    "llm": LLM_MODEL,
                    "temperature": 0.2,
                    "tool_ids": tool_ids,
                },
            },
            "tts": {
                "model_id": TTS_MODEL,
                "voice_id": voice.resolve_voice_id(),
                "optimize_streaming_latency": 3,
                "agent_output_audio_format": "pcm_16000",
            },
            "asr": {"quality": "high", "user_input_audio_format": "pcm_16000"},
            "turn": {"mode": "turn", "turn_eagerness": "normal", "speculative_turn": True},
            "conversation": {"client_events": CLIENT_EVENTS, "max_duration_seconds": 600},
        },
        "platform_settings": {
            # Only our backend can mint a session (signed URL), so the agent can't be used anonymously.
            "auth": {"enable_auth": True},
            "overrides": {
                "conversation_config_override": {
                    "agent": {"first_message": True, "language": True, "prompt": {"prompt": True}},
                }
            },
        },
    }


def _config_hash() -> str:
    desired = {"tools": voice_tool_configs(), "agent": agent_body(["<ids>"])}
    return hashlib.sha256(json.dumps(desired, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- cache

def _load_cache() -> dict:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(data: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass


def reset_cache() -> None:
    """Forget the cached agent (memory and disk)."""
    with _lock:
        _state.clear()
        try:
            CACHE_FILE.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- remote sync

def _sync_tools() -> dict[str, str]:
    """Create or update the client tools; return {name: tool_id}."""
    existing: dict[str, str] = {}
    listing = _request("GET", "/v1/convai/tools", params={"types": "client", "page_size": 100})
    for item in listing.get("tools") or []:
        cfg = item.get("tool_config") or {}
        if cfg.get("type", "client") == "client" and cfg.get("name") and item.get("id"):
            existing.setdefault(cfg["name"], item["id"])

    ids: dict[str, str] = {}
    for cfg in voice_tool_configs():
        tool_id = existing.get(cfg["name"])
        if tool_id:
            _request("PATCH", f"/v1/convai/tools/{tool_id}", body={"tool_config": cfg})
        else:
            tool_id = _request("POST", "/v1/convai/tools", body={"tool_config": cfg}).get("id")
            if not tool_id:
                raise ConvAIUnavailable(f"ElevenLabs did not return an id for tool {cfg['name']}")
        ids[cfg["name"]] = tool_id
    return ids


def _find_agent_id() -> Optional[str]:
    listing = _request("GET", "/v1/convai/agents", params={"search": AGENT_NAME, "page_size": 30})
    for agent in listing.get("agents") or []:
        if agent.get("name") == AGENT_NAME and not agent.get("archived"):
            return agent.get("agent_id")
    return None


def ensure_agent() -> str:
    """Return the Nat voice agent_id, creating or re-syncing it on first use."""
    with _lock:
        if _state.get("agent_id"):
            return _state["agent_id"]

        want_hash = _config_hash()
        cached = _load_cache()
        if cached.get("agent_id") and cached.get("config_hash") == want_hash:
            _state.update(cached)
            return cached["agent_id"]

        tool_ids = _sync_tools()
        body = agent_body(list(tool_ids.values()))
        agent_id = cached.get("agent_id") or _find_agent_id()
        if agent_id:
            try:
                _request("PATCH", f"/v1/convai/agents/{agent_id}", body=body)
            except ConvAIUnavailable as exc:
                if "HTTP 404" not in str(exc):
                    raise
                agent_id = None
        if not agent_id:
            agent_id = _request("POST", "/v1/convai/agents/create", body=body).get("agent_id")
            if not agent_id:
                raise ConvAIUnavailable("ElevenLabs did not return an agent_id")

        data = {"agent_id": agent_id, "tool_ids": tool_ids, "config_hash": want_hash, "llm": LLM_MODEL, "tts": TTS_MODEL}
        _state.update(data)
        _save_cache(data)
        return agent_id


def get_signed_url(agent_id: str) -> str:
    payload = _request("GET", "/v1/convai/conversation/get-signed-url", params={"agent_id": agent_id})
    url = payload.get("signed_url")
    if not url:
        raise ConvAIUnavailable("ElevenLabs did not return a signed URL")
    return url


# ---------------------------------------------------------------- per-session prompt

def _first_risk(snapshot: dict) -> Optional[str]:
    """The single most important risk in the snapshot, as a short phrase, or None."""
    for alert in snapshot.get("active_alerts") or []:
        if alert.get("severity") == "high" and alert.get("message"):
            return str(alert["message"]).rstrip(".")
    for risk in snapshot.get("upcoming_risks") or []:
        if risk.get("severity") == "high" and risk.get("reason"):
            return str(risk["reason"]).rstrip(".")
    for alert in snapshot.get("active_alerts") or []:
        if alert.get("message"):
            return str(alert["message"]).rstrip(".")
    for risk in snapshot.get("upcoming_risks") or []:
        if risk.get("reason"):
            return str(risk["reason"]).rstrip(".")
    return None


_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _spoken_dates(text: str) -> str:
    """'2026-12-26: Balance falls below zero' -> 'around 26 December, balance falls below zero'."""
    def spoken(match: re.Match) -> str:
        try:
            day = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return match.group(0)
        return f"{day.day} {day:%B}"

    lead = re.match(r"\s*(\d{4}-\d{2}-\d{2})\s*:\s*(.+)", text)
    if lead:
        rest = lead.group(2)
        text = f"around {lead.group(1)}, {rest[:1].lower()}{rest[1:]}"
    return _ISO_DATE_RE.sub(spoken, text)


def first_message(snapshot: dict) -> str:
    name = ((snapshot.get("profile") or {}).get("name") or "").split(" ")[0]
    hello = (f"Hey {name}, it's me, Nat! " if name else "Hey, it's me, Nat! ") + (
        "I know your spending habits and income patterns inside out, "
        "and I've already lived a thousand versions of your next ninety days.")
    risk = _first_risk(snapshot)
    if risk:
        risk = _spoken_dates(risk)
        return f"{hello} One thing I'm watching: {risk}. Want to talk it through? Cut in whenever you like."
    return f"{hello} What would you like to check? Cut in whenever you like."


def build_prompt(user_id: str, tone: Optional[str]) -> tuple[str, dict]:
    resolved = orchestrator.resolve_tone(user_id, tone)  # raises ValueError on a bad tone
    prompt = orchestrator.build_system_prompt(resolved)
    try:
        live = context.render(user_id)
    except Exception:
        live = ""
    try:
        snapshot = context.build_snapshot(user_id)
    except Exception:
        snapshot = {}
    if live:
        prompt = f"{prompt}\n\n{live}"
    return f"{prompt}\n\n{VOICE_ADDENDUM}", snapshot


def create_session(user_id: str, tone: Optional[str] = None) -> dict:
    """Everything the browser needs to open a live voice session."""
    prompt, snapshot = build_prompt(user_id, tone)
    agent_id = ensure_agent()
    try:
        signed_url = get_signed_url(agent_id)
    except ConvAIUnavailable as exc:
        if "HTTP 404" not in str(exc):
            raise
        reset_cache()  # agent was deleted remotely: recreate once
        agent_id = ensure_agent()
        signed_url = get_signed_url(agent_id)
    return {
        "agent_id": agent_id,
        "signed_url": signed_url,
        "prompt": prompt,
        "first_message": first_message(snapshot),
        "language": LANGUAGE,
        "client_tools": [cfg["name"] for cfg in voice_tool_configs()],
        "llm": LLM_MODEL,
        "tts_model": TTS_MODEL,
    }


# ---------------------------------------------------------------- client tool calls

def _clean_args(name: str, args: Any) -> Any:
    """Drop nulls/blank strings the voice LLM sends for optional params; make whole floats ints where needed."""
    if not isinstance(args, dict):
        return args
    schema = next((t.get("input_schema") or {} for t in tools.get_active_tools() if t["name"] == name), {})
    props = schema.get("properties") or {}
    cleaned = {}
    for key, val in args.items():
        if val is None or (isinstance(val, str) and not val.strip() and key not in schema.get("required", [])):
            continue
        if (props.get(key) or {}).get("type") == "integer" and isinstance(val, float) and val.is_integer():
            val = int(val)
        cleaned[key] = val
    return cleaned


def run_voice_tool(user_id: str, name: str, args: Any) -> Any:
    return tools.run_tool(user_id, name, _clean_args(name, args))
