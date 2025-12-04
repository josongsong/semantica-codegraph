"""
Embedding Cache

Redis 기반 임베딩 캐시로 중복 임베딩 생성 방지.
Phase 3 Day 24-25
"""

import hashlib
import pickle

import numpy as np

from src.contexts.retrieval_search.infrastructure.metrics import record_cache_hit, record_cache_miss
from src.infra.observability import get_logger

logger = get_logger(__name__)


class EmbeddingCache:
    """
    Redis 기반 임베딩 캐시.

    Features:
    - Redis storage (persistent across restarts)
    - TTL: 7 days (configurable)
    - LRU eviction (Redis maxmemory policy)
    - Cache hit/miss metrics
    - Enable/disable option (벤치마킹용)
    """

    def __init__(
        self,
        redis_client,
        ttl_seconds: int = 7 * 24 * 3600,  # 7 days
        enabled: bool = True,  # 벤치마킹 시 disable 가능
        key_prefix: str = "embedding:",
    ):
        """
        Initialize embedding cache.

        Args:
            redis_client: Redis client (async)
            ttl_seconds: TTL in seconds (default: 7 days)
            enabled: Enable/disable cache (default: True, 벤치마킹 시 False)
            key_prefix: Cache key prefix
        """
        self.redis = redis_client
        self.ttl = ttl_seconds
        self.enabled = enabled
        self.key_prefix = key_prefix

        # Stats
        self.hits = 0
        self.misses = 0

    async def get(
        self,
        model: str,
        text: str,
        repo_id: str | None = None,
    ) -> np.ndarray | None:
        """
        Get embedding from cache.

        Args:
            model: Model name
            text: Text to embed
            repo_id: Optional repository ID (for metrics)

        Returns:
            Embedding as numpy array, or None if cache miss
        """
        if not self.enabled:
            return None

        try:
            key = self._make_key(model, text)
            cached = await self.redis.get(key)

            if cached:
                # Deserialize
                embedding = pickle.loads(cached)

                # Stats
                self.hits += 1
                record_cache_hit(cache_type="embedding", repo_id=repo_id)

                logger.debug(
                    "embedding_cache_hit",
                    model=model,
                    text_len=len(text),
                )

                return np.array(embedding, dtype=np.float32)

            # Cache miss
            self.misses += 1
            record_cache_miss(cache_type="embedding", repo_id=repo_id)

            return None

        except Exception as e:
            logger.warning(
                "embedding_cache_get_failed",
                model=model,
                error=str(e),
            )
            return None

    async def set(
        self,
        model: str,
        text: str,
        embedding: np.ndarray,
    ) -> None:
        """
        Set embedding in cache.

        Args:
            model: Model name
            text: Text to embed
            embedding: Embedding as numpy array
        """
        if not self.enabled:
            return

        try:
            key = self._make_key(model, text)

            # Serialize
            serialized = pickle.dumps(embedding.tolist())

            # Store with TTL
            await self.redis.setex(key, self.ttl, serialized)

            logger.debug(
                "embedding_cache_set",
                model=model,
                text_len=len(text),
                embedding_dim=len(embedding),
            )

        except Exception as e:
            logger.warning(
                "embedding_cache_set_failed",
                model=model,
                error=str(e),
            )

    def _make_key(self, model: str, text: str) -> str:
        """
        Generate cache key.

        Format: embedding:{model}:{text_hash}

        Args:
            model: Model name
            text: Text to embed

        Returns:
            Cache key
        """
        # Hash text (MD5 for speed)
        text_hash = hashlib.md5(text.encode()).hexdigest()

        # Key format
        return f"{self.key_prefix}{model}:{text_hash}"

    def get_hit_rate(self) -> float:
        """
        Get cache hit rate.

        Returns:
            Hit rate (0.0 to 1.0)
        """
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate
        """
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.get_hit_rate(),
            "enabled": self.enabled,
        }

    async def clear(self, model: str | None = None) -> int:
        """
        Clear cache entries.

        Args:
            model: Optional model name (clear only this model's cache)

        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0

        try:
            if model:
                # Clear specific model
                pattern = f"{self.key_prefix}{model}:*"
            else:
                # Clear all embeddings
                pattern = f"{self.key_prefix}*"

            # Find keys
            keys = []
            cursor = 0
            while True:
                cursor, batch = await self.redis.scan(
                    cursor,
                    match=pattern,
                    count=100,
                )
                keys.extend(batch)
                if cursor == 0:
                    break

            # Delete keys
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(
                    "embedding_cache_cleared",
                    model=model,
                    deleted=deleted,
                )
                return deleted

            return 0

        except Exception as e:
            logger.warning(
                "embedding_cache_clear_failed",
                model=model,
                error=str(e),
            )
            return 0

    def enable(self) -> None:
        """Enable cache (for normal operation)."""
        self.enabled = True
        logger.info("embedding_cache_enabled")

    def disable(self) -> None:
        """Disable cache (for benchmarking)."""
        self.enabled = False
        logger.info("embedding_cache_disabled")


# Global cache instance
_global_embedding_cache: EmbeddingCache | None = None


def get_embedding_cache() -> EmbeddingCache | None:
    """Get global embedding cache instance."""
    return _global_embedding_cache


def setup_embedding_cache(
    redis_client,
    ttl_seconds: int = 7 * 24 * 3600,
    enabled: bool = True,
) -> EmbeddingCache:
    """
    Setup global embedding cache.

    Args:
        redis_client: Redis client
        ttl_seconds: TTL in seconds
        enabled: Enable/disable cache (벤치마킹 시 False)

    Returns:
        EmbeddingCache instance
    """
    global _global_embedding_cache

    _global_embedding_cache = EmbeddingCache(
        redis_client=redis_client,
        ttl_seconds=ttl_seconds,
        enabled=enabled,
    )

    logger.info(
        "embedding_cache_setup",
        ttl_days=ttl_seconds / 86400,
        enabled=enabled,
    )

    return _global_embedding_cache
