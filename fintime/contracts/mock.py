"""Loads JSON fixtures. Used by every module when its MOCK_* flag is on."""
import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((_DIR / f"{name}.json").read_text())
