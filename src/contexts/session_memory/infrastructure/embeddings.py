"""
Memory System Embedding Providers

Wraps LLM adapters to implement EmbeddingProvider protocol for memory system.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infra.llm.ollama import OllamaAdapter
    from src.infra.llm.openai import OpenAIAdapter
from src.common.observability import get_logger

logger = get_logger(__name__)


class OpenAIEmbeddingProvider:
    """
    OpenAI embedding provider for memory system.

    Uses text-embedding-3-small (1536 dimensions) by default.
    """

    def __init__(self, adapter: "OpenAIAdapter"):
        """
        Initialize OpenAI embedding provider.

        Args:
            adapter: OpenAIAdapter instance
        """
        self._adapter = adapter
        self._dimension = 1536  # text-embedding-3-small

    @property
    def dimension(self) -> int:
        """Embedding dimension (1536 for text-embedding-3-small)."""
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return await self._adapter.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return await self._adapter.embed_batch(texts)


class OllamaEmbeddingProvider:
    """
    Ollama embedding provider for memory system.

    Uses bge-m3 (1024 dimensions) by default.
    """

    def __init__(self, adapter: "OllamaAdapter"):
        """
        Initialize Ollama embedding provider.

        Args:
            adapter: OllamaAdapter instance
        """
        self._adapter = adapter
        self._dimension = 1024  # bge-m3

    @property
    def dimension(self) -> int:
        """Embedding dimension (1024 for bge-m3)."""
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return await self._adapter.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return await self._adapter.embed_batch(texts)


class MockEmbeddingProvider:
    """
    Mock embedding provider for testing.

    Generates deterministic fake embeddings based on text hash.
    """

    def __init__(self, dimension: int = 1536):
        """
        Initialize mock provider.

        Args:
            dimension: Embedding dimension
        """
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        """Generate fake embedding based on text hash."""
        import hashlib

        # Create deterministic embedding from text hash
        hash_bytes = hashlib.sha256(text.encode()).digest()

        # Expand hash to fill dimension
        embedding = []
        for i in range(self._dimension):
            byte_idx = i % len(hash_bytes)
            # Normalize to [-1, 1] range
            value = (hash_bytes[byte_idx] / 127.5) - 1.0
            embedding.append(value)

        # Normalize to unit vector
        norm = sum(v * v for v in embedding) ** 0.5
        if norm > 0:
            embedding = [v / norm for v in embedding]

        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate fake embeddings for multiple texts."""
        return [await self.embed(text) for text in texts]
