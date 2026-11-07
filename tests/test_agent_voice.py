"""Tests for P3 Voice & Accessibility (`backend/agent/voice.py`)."""
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend import config
from backend.agent import voice


class _DummyResponse:
    def __init__(self, content: bytes = b"ID3-fake-mp3-bytes", status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            req = httpx.Request("POST", "https://api.elevenlabs.io/v1/text-to-speech/voice")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("HTTP error", request=req, response=resp)


def test_speak_returns_none_when_api_key_missing_and_uncached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")

    assert voice.speak("Hello Sam, your safe-to-spend is £210.") is None


@pytest.mark.parametrize("bad_text", ["", "   ", "\n\t  "])
def test_speak_returns_none_for_empty_or_whitespace_text(
    bad_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-eleven-key")

    called = False

    def _unexpected_post(*args: Any, **kwargs: Any) -> Any:
        nonlocal called
        called = True
        return _DummyResponse()

    monkeypatch.setattr(httpx, "post", _unexpected_post)
    assert voice.speak(bad_text) is None
    assert not called


def test_speak_synthesizes_and_writes_mp3_to_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-eleven-key")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "voice_abc")

    captured: dict[str, Any] = {}

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float) -> _DummyResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse(b"FAKE_MP3_CONTENT")

    monkeypatch.setattr(httpx, "post", _fake_post)

    text = "  Yes, you can afford the £30 shirt.  "
    expected_key = voice.cache_key(text, "voice_abc")
    result = voice.speak(text)

    assert result == f"/audio/{expected_key}.mp3"
    cached_file = tmp_path / f"{expected_key}.mp3"
    assert cached_file.is_file()
    assert cached_file.read_bytes() == b"FAKE_MP3_CONTENT"
    assert captured["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voice_abc"
    assert captured["headers"]["xi-api-key"] == "test-eleven-key"
    assert captured["headers"]["accept"] == "audio/mpeg"
    assert captured["json"] == {"text": "Yes, you can afford the £30 shirt.", "model_id": voice.ELEVENLABS_MODEL_ID}
    assert captured["timeout"] == 10.0


def test_cache_hit_works_offline_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "voice_offline")

    text = "Yes, you can afford the £30 shirt."
    cached_path = voice.cache_path_for(text)
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(b"CACHED_OFFLINE_MP3")

    # Remove API key and make httpx.post fail with ConnectError to prove 100% offline cache hit
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")

    def _offline_post(*args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("Network is unreachable")

    monkeypatch.setattr(httpx, "post", _offline_post)

    url = voice.speak(text)
    assert url == f"/audio/{cached_path.name}"


def test_cache_key_changes_with_text_and_voice_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "voice_1")
    k1 = voice.cache_key("Hello world")
    k1_padded = voice.cache_key("  Hello world \n")
    k2_diff_text = voice.cache_key("Hello world!")

    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "voice_2")
    k3_diff_voice = voice.cache_key("Hello world")

    assert k1 == k1_padded
    assert k1 != k2_diff_text
    assert k1 != k3_diff_voice


@pytest.mark.parametrize(
    "failure_mode",
    ["timeout", "http_500", "empty_body"],
)
def test_speak_returns_none_on_network_or_api_failures(
    failure_mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-eleven-key")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "voice_err")

    def _failing_post(*args: Any, **kwargs: Any) -> _DummyResponse:
        if failure_mode == "timeout":
            raise httpx.ReadTimeout("Read timed out")
        if failure_mode == "http_500":
            return _DummyResponse(b"", status_code=500)
        return _DummyResponse(b"", status_code=200)

    monkeypatch.setattr(httpx, "post", _failing_post)

    assert voice.speak("Test error resilience") is None
    assert list(tmp_path.glob("*.mp3")) == []


def test_pregenerate_demo_audio_caches_all_lines_and_works_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-eleven-key")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")

    call_count = 0

    def _fake_post(*args: Any, **kwargs: Any) -> _DummyResponse:
        nonlocal call_count
        call_count += 1
        return _DummyResponse(f"MP3_BYTES_{call_count}".encode("utf-8"))

    monkeypatch.setattr(httpx, "post", _fake_post)

    generated = voice.pregenerate_demo_audio()
    assert len(generated) == len(voice.DEMO_SCRIPTED_REPLIES)
    assert call_count == len(voice.DEMO_SCRIPTED_REPLIES)
    for line, url in generated.items():
        assert url is not None
        assert url.startswith("/audio/")
        assert (tmp_path / Path(url).name).is_file()

    # Now go completely offline with no API key and verify every demo line resolves from disk cache
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")

    def _no_network(*args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("Offline mode")

    monkeypatch.setattr(httpx, "post", _no_network)

    for line in voice.DEMO_SCRIPTED_REPLIES:
        assert voice.speak(line) == generated[line]


def test_is_audio_route_mounted_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIO_URLS", "1")
    assert voice.is_audio_route_mounted() is True
    monkeypatch.setenv("ENABLE_AUDIO_URLS", "0")
    assert isinstance(voice.is_audio_route_mounted(), bool)
