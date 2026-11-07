"""P3: LLM tool-calling loop.

1. Build system prompt = prompts/base.md + prompts/tone_<tone>.md (tone defaults to user's saved tone)
2. Send user message + tools.TOOLS to the LLM (model pinned in config.LLM_MODEL)
3. While the LLM requests a tool: tools.run_tool(...) and feed the result back
4. Return ChatReply(text, numbers_used=<merged numbers_used from tool results>)
5. If the voice toggle is on: audio_url = voice.speak(text)

Guardrails: never push a purchase; always state the numbers used; if a tool fails, say so plainly.
"""
from typing import Optional

from contracts.schemas import ChatReply, Tone


def run_chat(user_id: str, message: str, tone: Optional[Tone]) -> ChatReply:
    raise NotImplementedError("P3: see module docstring")
