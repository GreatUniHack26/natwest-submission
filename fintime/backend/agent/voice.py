"""P3: ElevenLabs text-to-speech with an on-disk cache.

speak(text) -> URL/path of an mp3 the frontend can play, or None if voice is unavailable.
Cache by hash(text + voice id) so scripted demo lines work offline.
"""
from typing import Optional

from backend import config


def speak(text: str) -> Optional[str]:
    if not config.ELEVENLABS_API_KEY:
        return None
    raise NotImplementedError("P3: POST to ElevenLabs TTS, write mp3 to cache dir, return its URL")
