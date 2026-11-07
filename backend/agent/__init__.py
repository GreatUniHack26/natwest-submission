"""P3 - AGENT module. Public interface:

    chat(user_id, message, tone=None, history=None) -> ChatReply

The agent NEVER reads the database. It calls forecast functions through tools.py.
"""
from typing import Optional

from backend import config
from contracts import mock
from contracts.schemas import ChatReply, Tone


def chat(user_id: str, message: str, tone: Optional[Tone] = None, history: Optional[list[dict]] = None) -> ChatReply:
    if config.MOCK_AGENT:
        return ChatReply(**mock.load("chat"))
    from .orchestrator import run_chat

    return run_chat(user_id, message, tone, history)
