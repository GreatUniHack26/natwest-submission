"""Text coach reply modes: concise (default) and detailed.

The mode is a ChatRequest field threaded route -> agent.chat -> orchestrator.run_chat, which
appends prompts/detail_<mode>.md after the tone section and before the live context.
"""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import agent, config
from backend.agent import fallback, orchestrator
from backend.main import app
from contracts.schemas import ChatReply, ChatRequest

CONCISE_TEXT = (orchestrator.PROMPTS_DIR / "detail_concise.md").read_text(encoding="utf-8").strip()
DETAILED_TEXT = (orchestrator.PROMPTS_DIR / "detail_detailed.md").read_text(encoding="utf-8").strip()
LIVE_CONTEXT = "## Live context for this conversation\nsafe_to_spend 210"


def test_chat_request_detail_defaults_to_concise_and_validates():
    assert ChatRequest(message="hi").detail == "concise"
    assert ChatRequest(message="hi", detail="detailed").detail == "detailed"
    with pytest.raises(ValidationError):
        ChatRequest(message="hi", detail="verbose")


@pytest.fixture
def captured_prompts(monkeypatch):
    monkeypatch.setattr(config, "MOCK_FORECAST", True)
    monkeypatch.setattr(fallback, "is_demo_mode", lambda: False)
    monkeypatch.setattr(orchestrator, "_context_section", lambda user_id: LIVE_CONTEXT)
    fallback.clear_cache()
    prompts: list[str] = []

    def fake_call_llm(**kwargs):
        prompts.append(kwargs["system_prompt"])
        return {"content": [{"type": "text", "text": "Yes.\n- Safe to spend: £210."}]}

    monkeypatch.setattr(orchestrator, "call_llm", fake_call_llm)
    yield prompts
    fallback.clear_cache()


@pytest.mark.parametrize(
    ("kwargs", "expected", "absent"),
    [
        ({}, CONCISE_TEXT, DETAILED_TEXT),
        ({"detail": "concise"}, CONCISE_TEXT, DETAILED_TEXT),
        ({"detail": "detailed"}, DETAILED_TEXT, CONCISE_TEXT),
    ],
)
def test_run_chat_appends_mode_prompt_after_tone_before_context(captured_prompts, kwargs, expected, absent):
    orchestrator.run_chat("sam", "Can I afford a £30 shirt?", tone="friendly", **kwargs)

    prompt = captured_prompts[0]
    base_and_tone = orchestrator.build_system_prompt("friendly")
    assert prompt.startswith(base_and_tone)
    assert expected in prompt
    assert absent not in prompt
    assert base_and_tone.rfind("Tone:") < prompt.index(expected) < prompt.index(LIVE_CONTEXT)


def test_modes_do_not_share_cached_replies(captured_prompts):
    orchestrator.run_chat("sam", "Can I afford a £30 shirt?", tone="friendly", detail="concise")
    concise_key = orchestrator._cache_key_message("Can I afford a £30 shirt?", "concise")
    detailed_key = orchestrator._cache_key_message("Can I afford a £30 shirt?", "detailed")
    assert fallback.get_cached_reply("sam", concise_key, "friendly") is not None
    assert fallback.get_cached_reply("sam", detailed_key, "friendly") is None


def test_run_chat_rejects_unknown_detail(captured_prompts):
    with pytest.raises(ValueError):
        orchestrator.run_chat("sam", "hi", tone="friendly", detail="verbose")


@pytest.mark.parametrize(("body_extra", "expected"), [({}, "concise"), ({"detail": "detailed"}, "detailed")])
def test_chat_route_passes_detail_through(monkeypatch, body_extra, expected):
    calls = []

    def fake_chat(user_id, message, tone=None, history=None, detail="concise"):
        calls.append({"user_id": user_id, "message": message, "tone": tone, "detail": detail})
        return ChatReply(text="ok")

    monkeypatch.setattr(agent, "chat", fake_chat)
    response = TestClient(app).post("/users/sam/chat", json={"message": "hi", "tone": "direct", **body_extra})

    assert response.status_code == 200
    assert calls == [{"user_id": "sam", "message": "hi", "tone": "direct", "detail": expected}]


def test_chat_route_rejects_unknown_detail():
    response = TestClient(app).post("/users/sam/chat", json={"message": "hi", "detail": "verbose"})
    assert response.status_code == 422


def test_agent_chat_forwards_detail_to_orchestrator(monkeypatch):
    seen = {}

    def fake_run_chat(user_id, message, tone=None, history=None, *, detail="concise"):
        seen["detail"] = detail
        return ChatReply(text="ok")

    monkeypatch.setattr(config, "MOCK_AGENT", False)
    monkeypatch.setattr(orchestrator, "run_chat", fake_run_chat)
    agent.chat("sam", "hi", "friendly", [], detail="detailed")
    assert seen == {"detail": "detailed"}
