"""Live voice coach (ElevenLabs Conversational AI): session bootstrap + client-tool bridge."""
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from backend.agent import convai

router = APIRouter(prefix="/users/{user_id}/voice", tags=["voice"])


class VoiceToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


@router.get("/session")
def voice_session(user_id: str, tone: Optional[str] = None):
    """Signed WebSocket URL + per-session prompt/first message for the browser SDK."""
    try:
        return convai.create_session(user_id, tone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except convai.ConvAIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/tool")
def voice_tool(user_id: str, call: VoiceToolCall):
    """Run a FinTime tool for the voice agent. Failures come back as {error} (200) so the agent can say so."""
    try:
        return jsonable_encoder(convai.run_voice_tool(user_id, call.name, call.args))
    except Exception as exc:  # the agent must hear what failed, never a guessed number
        return {"error": f"{call.name} failed: {exc}"}
