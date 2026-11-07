"""Vercel entrypoint: serves the FastAPI backend under /api."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DB_PATH", "/tmp/fintime.db")
os.environ.setdefault("AUDIO_CACHE_DIR", "/tmp/audio_cache")

from fastapi import FastAPI  # noqa: E402

from backend import config  # noqa: E402

if not config.MOCK_DATA and not Path(config.DB_PATH).exists():
    from backend.data.seed import seed

    seed()

from backend.main import app as backend_app  # noqa: E402

app = FastAPI()
app.mount("/api", backend_app)
