"""
BGE Embedding Model

LocalLLM의 BGE-M3 모델을 사용하는 임베딩 모델.
Phase 3 Day 26-28: SimpleEmbeddingModel(난수) 교체
"""

import numpy as np

from src.infra.llm.embedding_cache import get_embedding_cache
from src.infra.observability import get_logger

logger = get_logger(__name__)


class BGEEmbeddingModel:
    """
    BGE-M3 기반 임베딩 모델 (LocalLLM 사용).

    Features:
    - 실제 의미 기반 임베딩 (vs SimpleEmbeddingModel 난수)
    - LocalLLM BGE-M3 활용
    - Redis 캐시 통합
    - Query/Document 별도 처리
    """

    def __init__(
        self,
        local_llm,
        embedding_cache=None,
        use_cache: bool = True,
    ):
        """
        Initialize BGE embedding model.

        Args:
            local_llm: LocalLLMAdapter instance
            embedding_cache: Optional embedding cache
            use_cache: Enable/disable cache (벤치마킹 시 False)
        """
        self.llm = local_llm
        self.cache = embedding_cache or get_embedding_cache()
        self.use_cache = use_cache and (self.cache is not None)
        self.model_name = "bge-m3:latest"

    async def encode_query(self, text: str) -> np.ndarray:
        """
        Encode query into token embeddings.

        Query는 캐시하지 않음 (매번 새로운 쿼리).

        Args:
            text: Query text

        Returns:
            Array of shape (embedding_dim,) - single embedding for query
        """
        try:
            # BGE-M3는 sentence embedding을 반환 (token-level 아님)
            embedding = await self.llm.embed(text)

            return np.array(embedding, dtype=np.float32)

        except Exception as e:
            logger.error(
                "bge_query_encoding_failed",
                error=str(e),
                text_len=len(text),
            )
            # Fallback: zero vector
            return np.zeros(1024, dtype=np.float32)

    async def encode_document(self, text: str) -> np.ndarray:
        """
        Encode document into token embeddings.

        Document는 캐시 사용 (재사용 많음).

        Args:
            text: Document text

        Returns:
            Array of shape (embedding_dim,) - single embedding for document
        """
        # Cache check
        if self.use_cache and self.cache and self.cache.enabled:
            cached = await self.cache.get(self.model_name, text)
            if cached is not None:
                logger.debug("bge_document_cache_hit", text_len=len(text))
                return cached

        try:
            # Encode
            embedding = await self.llm.embed(text)
            embedding_array = np.array(embedding, dtype=np.float32)

            # Cache set
            if self.use_cache and self.cache and self.cache.enabled:
                await self.cache.set(self.model_name, text, embedding_array)

            return embedding_array

        except Exception as e:
            logger.error(
                "bge_document_encoding_failed",
                error=str(e),
                text_len=len(text),
            )
            # Fallback: zero vector
            return np.zeros(1024, dtype=np.float32)

    def get_embedding_dim(self) -> int:
        """Get embedding dimension."""
        return 1024  # BGE-M3
