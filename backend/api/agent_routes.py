from fastapi import APIRouter

from backend import agent
from contracts.schemas import ChatReply, ChatRequest

router = APIRouter(prefix="/users/{user_id}", tags=["agent"])


@router.post("/chat", response_model=ChatReply)
def chat(user_id: str, req: ChatRequest):
    return agent.chat(user_id, req.message, req.tone, [t.model_dump() for t in req.history])
