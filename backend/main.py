from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import config
from backend.agent import voice
from backend.api import agent_routes, data_routes, forecast_routes, household_routes, voice_routes

app = FastAPI(title="Nat API")


@app.on_event("startup")
def _seed_if_empty() -> None:
    """Demo safety: in real-data mode, build the persona database on first start (Sam, Alex, Pete, Maya & Dan)."""
    if config.MOCK_DATA:
        return
    try:
        from backend.data import repository

        repository.get_user("pete")
    except Exception:
        from backend.data.seed import seed

        seed()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(data_routes.router)
app.include_router(forecast_routes.router)
app.include_router(agent_routes.router)
app.include_router(household_routes.router)
app.include_router(voice_routes.router)
app.include_router(__import__("backend.api.insight_routes", fromlist=["router"]).router)  # tips + benchmarks

# Serve cached ElevenLabs replies so ChatReply.audio_url (/audio/<hash>.mp3) is playable.
Path(voice.CACHE_DIR).mkdir(parents=True, exist_ok=True)
app.mount(voice.AUDIO_URL_PREFIX, StaticFiles(directory=voice.CACHE_DIR), name="audio")


@app.get("/health")
def health():
    return {
        "ok": True,
        "mock": {"data": config.MOCK_DATA, "forecast": config.MOCK_FORECAST, "agent": config.MOCK_AGENT},
        "voice": bool(config.ELEVENLABS_API_KEY),
        "llm": bool(config.LLM_API_KEY),
    }
