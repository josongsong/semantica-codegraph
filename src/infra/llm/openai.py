"""
OpenAI Adapter

Provides embeddings and chat completions using OpenAI SDK.
"""

from typing import Any

try:
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenAIAdapter:
    """Production adapter for OpenAI embeddings and chat."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        """
        Initialize OpenAI adapter.

        Args:
            api_key: OpenAI API key
            model: Chat model (default: gpt-4o-mini)
            embedding_model: Embedding model (default: text-embedding-3-small)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI SDK not installed. Install with: pip install openai")

        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model
        self.client = AsyncOpenAI(api_key=api_key)

    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding as list of floats
        """
        response = await self.client.embeddings.create(model=self.embedding_model, input=text)
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        if not texts:
            return []

        response = await self.client.embeddings.create(model=self.embedding_model, input=texts)
        return [item.embedding for item in response.data]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Optional model override
            temperature: Sampling temperature (default: 0.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        response = await self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
