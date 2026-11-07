"""Live voice coach routes: ElevenLabs agent bootstrap, session payload and the client-tool bridge.

All ElevenLabs HTTP calls are faked; no network.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.agent import context, convai, tools
from backend.main import app

SNAPSHOT = {
    "profile": {"name": "Sam Taylor"},
    "active_alerts": [{"severity": "high", "message": "2026-12-26: Expected balance falls below zero"}],
}
LIVE_CONTEXT = "## Live context for this conversation\nsafe_to_spend 210"


class FakeElevenLabs:
    """Minimal stand-in for the ConvAI REST API, recording every call."""

    def __init__(self, agents=(), tools_listing=(), status=200):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.agents = list(agents)
        self.tools_listing = list(tools_listing)
        self.status = status
        self.next_tool = 0

    def __call__(self, method, url, *, headers=None, params=None, json=None, timeout=None):
        path = url.replace(convai.API_BASE, "")
        self.calls.append((method, path, json))
        assert headers["xi-api-key"] == "test-key"
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "nope"})
        if method == "GET" and path == "/v1/convai/tools":
            return httpx.Response(200, json={"tools": self.tools_listing, "has_more": False})
        if method == "POST" and path == "/v1/convai/tools":
            self.next_tool += 1
            return httpx.Response(200, json={"id": f"tool_{self.next_tool}"})
        if method == "PATCH" and path.startswith("/v1/convai/tools/"):
            return httpx.Response(200, json={"id": path.rsplit("/", 1)[1]})
        if method == "GET" and path == "/v1/convai/agents":
            return httpx.Response(200, json={"agents": self.agents, "has_more": False})
        if method == "POST" and path == "/v1/convai/agents/create":
            return httpx.Response(200, json={"agent_id": "agent_new"})
        if method == "PATCH" and path.startswith("/v1/convai/agents/"):
            return httpx.Response(200, json={"agent_id": path.rsplit("/", 1)[1]})
        if method == "GET" and path == "/v1/convai/conversation/get-signed-url":
            return httpx.Response(200, json={"signed_url": f"wss://example.test/convai?agent={params['agent_id']}&sig=x"})
        return httpx.Response(404, json={"detail": "not found"})

    def paths(self, method=None):
        return [p for m, p, _ in self.calls if method is None or m == method]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(convai, "CACHE_FILE", tmp_path / "convai_agent.json")
    monkeypatch.setattr(context, "render", lambda user_id: LIVE_CONTEXT)
    monkeypatch.setattr(context, "build_snapshot", lambda user_id: SNAPSHOT)
    convai._state.clear()
    yield TestClient(app)
    convai._state.clear()


def install(monkeypatch, fake):
    monkeypatch.setattr(convai.httpx, "request", fake)
    return fake


def test_creates_agent_with_low_latency_config_and_client_tools(client, monkeypatch):
    fake = install(monkeypatch, FakeElevenLabs())

    r = client.get("/users/sam/voice/session?tone=friendly")

    assert r.status_code == 200
    assert r.json()["agent_id"] == "agent_new"
    create = next(body for m, p, body in fake.calls if p == "/v1/convai/agents/create")
    conv = create["conversation_config"]
    assert create["name"] == "Nat"
    assert conv["agent"]["prompt"]["llm"] == convai.LLM_MODEL
    assert conv["tts"]["model_id"] == convai.TTS_MODEL
    assert "interruption" in conv["conversation"]["client_events"]
    assert "client_tool_call" in conv["conversation"]["client_events"]
    overrides = create["platform_settings"]["overrides"]["conversation_config_override"]["agent"]
    assert overrides == {"first_message": True, "language": True, "prompt": {"prompt": True}}
    assert create["platform_settings"]["auth"]["enable_auth"] is True

    tool_bodies = [body["tool_config"] for m, p, body in fake.calls if m == "POST" and p == "/v1/convai/tools"]
    names = {t["name"] for t in tool_bodies}
    for required in ("get_safe_to_spend", "simulate_purchase", "get_forecast", "get_alerts", "run_twin_simulations",
                     "get_spending_forecast", "get_deposit_ideas", "plan_savings_goal", "get_economic_news"):
        assert required in names
    assert all(t["type"] == "client" and t["expects_response"] for t in tool_bodies)
    sim = next(t for t in tool_bodies if t["name"] == "simulate_purchase")
    assert sim["parameters"]["required"] == ["amount"]
    assert sim["parameters"]["properties"]["amount"]["type"] == "number"
    assert sorted(conv["agent"]["prompt"]["tool_ids"]) == sorted(f"tool_{i}" for i in range(1, len(tool_bodies) + 1))


def test_second_session_reuses_cached_agent_without_resyncing(client, monkeypatch):
    fake = install(monkeypatch, FakeElevenLabs())
    client.get("/users/sam/voice/session")
    convai._state.clear()  # simulate a process restart: only the disk cache remains
    fake.calls.clear()

    r = client.get("/users/sam/voice/session")

    assert r.status_code == 200 and r.json()["agent_id"] == "agent_new"
    assert fake.paths() == ["/v1/convai/conversation/get-signed-url"]


def test_existing_remote_agent_is_found_and_patched_not_duplicated(client, monkeypatch):
    fake = install(monkeypatch, FakeElevenLabs(
        agents=[{"agent_id": "agent_old", "name": "Nat", "archived": False}],
        tools_listing=[{"id": "tool_existing", "tool_config": {"type": "client", "name": "get_alerts"}}],
    ))

    r = client.get("/users/sam/voice/session")

    assert r.json()["agent_id"] == "agent_old"
    assert "/v1/convai/agents/create" not in fake.paths()
    assert "/v1/convai/agents/agent_old" in fake.paths("PATCH")
    assert "/v1/convai/tools/tool_existing" in fake.paths("PATCH")
    assert json.loads(convai.CACHE_FILE.read_text())["agent_id"] == "agent_old"


def test_session_payload_carries_prompt_with_context_and_personal_first_message(client, monkeypatch):
    install(monkeypatch, FakeElevenLabs())

    body = client.get("/users/sam/voice/session?tone=direct").json()

    assert body["signed_url"].startswith("wss://")
    assert "You are Nat" in body["prompt"]
    assert "Tone:" in body["prompt"]
    assert LIVE_CONTEXT in body["prompt"]
    assert "## Voice mode" in body["prompt"]
    assert body["first_message"].startswith("Hey Sam, it's me, Nat!")
    assert "around 26 December, expected balance falls below zero" in body["first_message"]
    assert "get_safe_to_spend" in body["client_tools"]


def test_bad_tone_is_400(client, monkeypatch):
    install(monkeypatch, FakeElevenLabs())
    assert client.get("/users/sam/voice/session?tone=shouty").status_code == 400


def test_missing_permission_is_503_with_clear_message(client, monkeypatch):
    install(monkeypatch, FakeElevenLabs(status=401))
    r = client.get("/users/sam/voice/session")
    assert r.status_code == 503
    assert "Conversational AI" in r.json()["detail"]


def test_missing_key_is_503(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    r = client.get("/users/sam/voice/session")
    assert r.status_code == 503 and "ELEVENLABS_API_KEY" in r.json()["detail"]


def test_tool_endpoint_dispatches_with_cleaned_args(client, monkeypatch):
    seen = {}

    def fake_run_tool(user_id, name, args):
        seen.update(user_id=user_id, name=name, args=args)
        return {"affordable": True, "safe_after": 180.0}

    monkeypatch.setattr(tools, "run_tool", fake_run_tool)
    r = client.post("/users/sam/voice/tool", json={"name": "get_forecast", "args": {"horizon_days": 30.0, "unused": None}})

    assert r.status_code == 200 and r.json() == {"affordable": True, "safe_after": 180.0}
    assert seen == {"user_id": "sam", "name": "get_forecast", "args": {"horizon_days": 30}}
    assert isinstance(seen["args"]["horizon_days"], int)


def test_tool_endpoint_errors_are_200_with_error_field(client, monkeypatch):
    def boom(user_id, name, args):
        raise ValueError("Unknown tool: nope")

    monkeypatch.setattr(tools, "run_tool", boom)
    r = client.post("/users/sam/voice/tool", json={"name": "nope", "args": {}})

    assert r.status_code == 200
    assert r.json() == {"error": "nope failed: Unknown tool: nope"}
