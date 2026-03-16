"""LLM abstraction: Claude primary, GPT-4o-mini fallback.

Will be implemented in Phase 2 (Week 7).
Responsibilities:
- Route requests to Claude API with 5s timeout
- Fallback to OpenAI on timeout/error
- Track token usage and latency in api_logs
- Enforce max_history_messages window
"""

from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


async def generate_response(
    system_prompt: str,
    messages: list[dict],
    emotion_state: str = "cold",
) -> LLMResponse:
    """Generate character response. Stub for Phase 2."""
    raise NotImplementedError("LLM integration not yet implemented — Phase 2, Week 7")
