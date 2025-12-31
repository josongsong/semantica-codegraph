"""
Embedding Provider Abstraction

다양한 임베딩 제공자를 위한 추상화 레이어.

Implementations:
    - OpenAIEmbeddingProvider: OpenAI text-embedding-3-small
    - LocalEmbeddingProvider: Ollama/local models (src/infra/llm/local_llm.py)

OCP 준수: 새 Provider 추가 시 이 모듈만 수정.
"""

import asyncio
from typing import Protocol, runtime_checkable

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    임베딩 생성 Protocol.

    모든 임베딩 제공자가 구현해야 하는 인터페이스.
    """

    async def embed(self, text: str) -> list[float]:
        """
        단일 텍스트 임베딩 생성.

        Args:
            text: 임베딩할 텍스트

        Returns:
            임베딩 벡터
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        배치 텍스트 임베딩 생성.

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            임베딩 벡터 리스트
        """
        ...


class OpenAIEmbeddingProvider:
    """
    OpenAI embedding provider using text-embedding-3-small.

    Requires: openai library and OPENAI_API_KEY environment variable

    Performance: Uses parallel batch processing with configurable concurrency.
    """

    def __init__(self, model: str = "text-embedding-3-small", concurrency: int = 8):
        """
        Initialize OpenAI embedding provider.

        Args:
            model: OpenAI embedding model (default: text-embedding-3-small)
            concurrency: Max concurrent API requests (default: 8, optimized for performance)
        """
        self.model = model
        self.concurrency = concurrency
        self._client = None

    async def _get_client(self):
        """Lazy initialize OpenAI client"""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI()
        return self._client

    async def embed(self, text: str) -> list[float]:
        """Generate single embedding"""
        client = await self._get_client()
        response = await client.embeddings.create(
            input=text,
            model=self.model,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate batch embeddings with parallel processing.

        Uses asyncio.gather with semaphore for concurrent API calls.
        OpenAI allows up to 2048 texts per batch request.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors in same order as input
        """
        if not texts:
            return []

        client = await self._get_client()

        # OpenAI allows up to 2048 texts per batch
        batch_size = 2048
        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

        if len(batches) == 1:
            # Single batch - no parallelization needed
            response = await client.embeddings.create(input=texts, model=self.model)
            return [data.embedding for data in response.data]

        # Parallel processing for multiple batches
        semaphore = asyncio.Semaphore(self.concurrency)
        results: list[list[list[float]]] = [[] for _ in range(len(batches))]

        async def embed_batch_chunk(idx: int, batch: list[str]) -> None:
            async with semaphore:
                response = await client.embeddings.create(input=batch, model=self.model)
                results[idx] = [data.embedding for data in response.data]

        await asyncio.gather(*[embed_batch_chunk(i, batch) for i, batch in enumerate(batches)])

        # Flatten results maintaining order
        return [emb for batch_result in results for emb in batch_result]


# Re-export for backward compatibility
__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
]
