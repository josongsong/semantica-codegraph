"""
Infrastructure DI Registration

Registers all infrastructure adapters (external dependencies):
- PostgreSQL, Qdrant, Tantivy, LLM (Local: Ollama/vLLM/LocalAI)

Laptop Mode (Current):
- Redis: DISABLED (L1 memory-only caching)
- Memgraph: DISABLED (UnifiedGraphIndex 인메모리 사용)

Server Mode (Future):
- Redis: 분산 캐시, Multi-Agent 락 관리
- Memgraph: 대규모 그래프 쿼리, VFG 영속화, Rust Taint Engine 연동
- 연동 시 src/infra/graph/memgraph.py, src/infra/cache/redis.py 참조
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from codegraph_shared.infra.llm.local_llm import LocalLLMAdapter
    from codegraph_shared.infra.storage.postgres import PostgresStore
    from codegraph_shared.infra.vector.qdrant import QdrantAdapter
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class InfraContainer:
    """
    Infrastructure adapters container.

    All adapters are lazy-loaded singletons via @cached_property.
    """

    def __init__(self, settings):
        """
        Args:
            settings: Application settings (src.config.settings)
        """
        self._settings = settings

    # ========================================================================
    # Database Adapters
    # ========================================================================

    @cached_property
    def postgres(self):
        """Database adapter with auto-detection (PostgreSQL or SQLite fallback)."""
        from codegraph_shared.infra.storage.auto import create_auto_store

        return create_auto_store()

    @cached_property
    def redis(self):
        """
        Redis cache adapter - DISABLED for laptop mode.

        Returns None. All caching uses in-memory L1 only.
        Callers must handle redis=None gracefully.

        Laptop Mode:
            - L1 메모리 캐시만 사용 (LRUCacheWithStats)
            - Three-Tier Cache의 L2 레이어 비활성화

        Server Mode (연동 계획):
            - RedisAdapter 활성화 (src/infra/cache/redis.py)
            - 분산 캐시 (L2)
            - Multi-Agent 락 관리 (distributed_lock.py)
            - 세션 간 캐시 공유

        Server 연동 시:
            from codegraph_shared.infra.cache.redis import RedisAdapter
            return RedisAdapter(
                host=self._settings.redis_host,
                port=self._settings.redis_port,
                password=self._settings.redis_password,
            )
        """
        logger.debug("Redis disabled (laptop mode) - using memory-only caching")
        return None

    # ========================================================================
    # Vector & Graph Stores
    # ========================================================================

    @cached_property
    def qdrant(self) -> QdrantAdapter:
        """Qdrant vector store adapter."""
        from codegraph_shared.infra.vector.qdrant import QdrantAdapter

        parsed = urlparse(self._settings.qdrant_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or self._settings.qdrant_port

        return QdrantAdapter(
            mode=self._settings.qdrant_mode,
            storage_path=self._settings.qdrant_storage_path,
            host=host,
            port=port,
            grpc_port=self._settings.qdrant_grpc_port,
            collection=self._settings.qdrant_collection_name,
            prefer_grpc=self._settings.qdrant_prefer_grpc,
            upsert_concurrency=self._settings.qdrant_upsert_concurrency,
        )

    @cached_property
    def qdrant_async(self) -> AsyncQdrantClient:
        """Async Qdrant client for vector operations."""
        from codegraph_shared.infra.vector import create_qdrant_client

        return create_qdrant_client(
            mode=self._settings.qdrant_mode,
            storage_path=self._settings.qdrant_storage_path,
            url=self._settings.qdrant_url,
            host=self._settings.qdrant_host,
            port=self._settings.qdrant_port,
            grpc_port=self._settings.qdrant_grpc_port,
            prefer_grpc=self._settings.qdrant_prefer_grpc,
            timeout=self._settings.qdrant_timeout,
            check_disk_space=self._settings.qdrant_check_disk_space,
            min_disk_space_mb=self._settings.qdrant_min_disk_space_mb,
        )

    @cached_property
    def memgraph(self):
        """
        Graph database adapter - DISABLED for laptop mode.

        Returns None. All graph operations use in-memory UnifiedGraphIndex.
        Callers must handle memgraph=None gracefully.

        Laptop Mode:
            - 정적분석: UnifiedGraphIndex (Python dict 기반)
            - Taint Analysis: 인메모리 그래프 순회
            - 외부 DB 의존성 없이 동작

        Server Mode (연동 계획):
            - MemgraphGraphStore 활성화 (src/infra/graph/memgraph.py)
            - VFG (Value Flow Graph) 영속화
            - Rust Taint Engine과 연동
            - 대규모 코드베이스 그래프 쿼리 최적화

        Server 연동 시:
            from codegraph_shared.infra.graph.memgraph import MemgraphGraphStore
            return MemgraphGraphStore(
                uri=self._settings.memgraph_uri,
                username=self._settings.memgraph_username,
                password=self._settings.memgraph_password,
            )
        """
        logger.debug("Memgraph disabled (laptop mode) - using in-memory graph index")
        return None

    # ========================================================================
    # Search & LLM
    # ========================================================================

    @cached_property
    def llm(self) -> LocalLLMAdapter:
        """LLM provider adapter (Local: Ollama/vLLM/LocalAI)."""
        from codegraph_shared.infra.llm.local_llm import LocalLLMAdapter

        return LocalLLMAdapter(
            base_url=self._settings.local_llm_base_url,
            embedding_model=self._settings.local_embedding_model,
            result_model=self._settings.local_result_model,
            intent_model=self._settings.local_intent_model,
            reranker_model=self._settings.local_reranker_model,
        )

    @cached_property
    def local_llm(self) -> LocalLLMAdapter:
        """Alias for llm."""
        return self.llm


def register_infra(container, settings) -> InfraContainer:
    """
    Register infrastructure adapters to the main container.

    Args:
        container: Main Container instance
        settings: Application settings

    Returns:
        InfraContainer instance (also attached to container._infra)
    """
    infra = InfraContainer(settings)
    container._infra = infra

    # Expose commonly used adapters directly on container
    # These are delegating properties, not copies
    return infra
