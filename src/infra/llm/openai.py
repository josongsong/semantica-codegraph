"""
OpenAI Adapter (stub)

Expose minimal methods for embeddings and chat completions. Replace with actual
OpenAI client calls via litellm or openai SDK.
"""

from typing import Any, Optional


class OpenAIAdapter:
    """Placeholder adapter for LLM interactions."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("OpenAIAdapter.embed is not implemented yet")

    async def chat(self, messages: list[dict[str, Any]], model: Optional[str] = None) -> str:
        raise NotImplementedError("OpenAIAdapter.chat is not implemented yet")
