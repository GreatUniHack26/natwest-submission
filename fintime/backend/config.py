"""Central config. Flip MOCK_* flags per module to integrate one module at a time."""
import datetime as dt
import os


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) == "1"


# 1 = module returns fixtures from contracts/fixtures, 0 = real implementation
MOCK_DATA = _flag("MOCK_DATA")
MOCK_FORECAST = _flag("MOCK_FORECAST")
MOCK_AGENT = _flag("MOCK_AGENT")

# Fixed "today" so the demo behaves the same every run
TODAY = dt.date.fromisoformat(os.getenv("DEMO_TODAY", "2026-11-07"))

DB_PATH = os.getenv("DB_PATH", "fintime.db")

# Pin the model in one place so the demo is stable
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
