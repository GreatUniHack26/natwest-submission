"""P3: ElevenLabs text-to-speech with an on-disk cache.

speak(text) -> URL/path of an mp3 the frontend can play, or None if voice is unavailable.
Cache by hash(text + voice id) so scripted demo lines work offline.

FastAPI static mount snippet for the API owner (`backend/main.py`):
    from fastapi.staticfiles import StaticFiles
    app.mount("/audio", StaticFiles(directory="audio_cache"), name="audio")
"""
import hashlib
import os
from pathlib import Path
from typing import Optional

import httpx

from backend import config

CACHE_DIR = Path(os.getenv("AUDIO_CACHE_DIR", "audio_cache"))
AUDIO_URL_PREFIX = "/audio"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_TTS_URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
TTS_TIMEOUT_SECONDS = 10.0

DEMO_SCRIPTED_REPLIES: list[str] = [
    (
        "Yes, you can afford the £30 shirt: it leaves you £180 safe to spend "
        "after your rent pot and bills. But Black Friday is on 27 Nov, about 3 weeks away. "
        "If it isn't urgent, waiting could save you money."
    ),
    (
        "Your safe-to-spend balance this week is £210 after setting aside £450 for your "
        "rent pot and £120 for upcoming bills."
    ),
    (
        "You spent 60% more on eating out this week than your 4-week average. "
        "Cap eating out at £25 for the next 7 days to stay on track."
    ),
    (
        "Your low-band balance may go negative around 26 Dec, before January income arrives. "
        "Pick up one extra shift in December or pause one want-spend category."
    ),
]


def resolve_voice_id(voice_id: Optional[str] = None) -> str:
    """Return explicit voice_id, config.ELEVENLABS_VOICE_ID, or DEFAULT_VOICE_ID."""
    candidate = (voice_id if voice_id is not None else config.ELEVENLABS_VOICE_ID) or ""
    cleaned = candidate.strip()
    return cleaned if cleaned else DEFAULT_VOICE_ID


def cache_key(text: str, voice_id: Optional[str] = None) -> str:
    """Compute deterministic SHA-256 hex digest for (resolved_voice_id, normalized_text)."""
    normalized = text.strip()
    resolved = resolve_voice_id(voice_id)
    payload = f"{resolved}:{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def cache_path_for(text: str, voice_id: Optional[str] = None) -> Path:
    """Return the target MP3 file path inside CACHE_DIR for the given text and voice_id."""
    return CACHE_DIR / f"{cache_key(text, voice_id)}.mp3"


def is_audio_route_mounted() -> bool:
    """Check whether /audio is mounted on backend.main.app or ENABLE_AUDIO_URLS is enabled."""
    try:
        from backend.main import app  # type: ignore

        for route in getattr(app, "routes", []):
            if getattr(route, "path", None) == AUDIO_URL_PREFIX:
                return True
    except Exception:
        pass
    return os.getenv("ENABLE_AUDIO_URLS", "1") == "1"


def speak(text: str) -> Optional[str]:
    """Return cached or freshly synthesized `/audio/<hash>.mp3` URL, or None on failure."""
    try:
        if not text or not isinstance(text, str) or not text.strip():
            return None

        normalized = text.strip()
        resolved_voice_id = resolve_voice_id()
        path = cache_path_for(normalized, resolved_voice_id)

        # Offline cache-first check: works without API key or network connectivity
        if path.is_file() and path.stat().st_size > 0:
            return f"{AUDIO_URL_PREFIX}/{path.name}"

        if not config.ELEVENLABS_API_KEY or not config.ELEVENLABS_API_KEY.strip():
            return None

        url = ELEVENLABS_TTS_URL_TEMPLATE.format(voice_id=resolved_voice_id)
        headers = {
            "xi-api-key": config.ELEVENLABS_API_KEY.strip(),
            "accept": "audio/mpeg",
            "content-type": "application/json",
        }
        payload = {
            "text": normalized,
            "model_id": ELEVENLABS_MODEL_ID,
        }

        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=TTS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        if not response.content:
            return None

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return f"{AUDIO_URL_PREFIX}/{path.name}"
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return None


def pregenerate_demo_audio(texts: Optional[list[str]] = None) -> dict[str, Optional[str]]:
    """Pre-generate and cache MP3 files for scripted demo replies so offline playback succeeds."""
    lines = DEMO_SCRIPTED_REPLIES if texts is None else texts
    results: dict[str, Optional[str]] = {}
    for line in lines:
        results[line] = speak(line)
    return results
