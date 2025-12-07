"""
Infrastructure DI Registration

Registers all infrastructure adapters (external dependencies):
- PostgreSQL, Redis, Qdrant, Memgraph
- LLM (Local: Ollama/vLLM/LocalAI), Zoekt
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from src.infra.cache.redis import RedisAdapter
    from src.infra.llm.local_llm import LocalLLMAdapter
    from src.infra.search.zoekt import ZoektAdapter
    from src.infra.storage.postgres import PostgresStore
    from src.infra.vector.qdrant import QdrantAdapter
from src.common.observability import get_logger

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
    def postgres(self) -> PostgresStore:
        """PostgreSQL database adapter with optimized connection pooling."""
        from src.infra.storage.postgres import PostgresStore

        return PostgresStore(
            connection_string=self._settings.database_url,
            min_pool_size=self._settings.postgres_min_pool_size or 5,
            max_pool_size=self._settings.postgres_max_pool_size or 20,
            command_timeout=30.0,
            max_idle_time=300.0,
        )

    @cached_property
    def redis(self) -> RedisAdapter:
        """Redis cache adapter."""
        from src.infra.cache.redis import RedisAdapter

        return RedisAdapter(
            host=self._settings.redis_host,
            port=self._settings.redis_port,
            password=self._settings.redis_password,
            db=self._settings.redis_db,
        )

    # ========================================================================
    # Vector & Graph Stores
    # ========================================================================

    @cached_property
    def qdrant(self) -> QdrantAdapter:
        """Qdrant vector store adapter."""
        from src.infra.vector.qdrant import QdrantAdapter

        parsed = urlparse(self._settings.qdrant_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or self._settings.qdrant_port

        return QdrantAdapter(
            host=host,
            port=port,
            collection=self._settings.qdrant_collection_name,
        )

    @cached_property
    def qdrant_async(self) -> AsyncQdrantClient:
        """Async Qdrant client for vector operations."""
        from qdrant_client import AsyncQdrantClient

        return AsyncQdrantClient(url=self._settings.qdrant_url)

    @cached_property
    def memgraph(self):
        """
        Graph database adapter.

        프로파일에 따라:
        - Memgraph 사용 가능: MemgraphGraphStore
        - 사용 불가: InMemoryGraphStore (fallback)
        """
        from src.infra.config.profiles import get_profile_config

        profile = get_profile_config()

        # 프로파일에서 Memgraph 사용 여부 확인
        if profile.should_use_memgraph():
            try:
                from src.infra.graph.memgraph import MemgraphGraphStore

                logger.info("Using MemgraphGraphStore (full graph features)")
                return MemgraphGraphStore(
                    uri=self._settings.memgraph_uri,
                    username=self._settings.memgraph_username,
                    password=self._settings.memgraph_password,
                    node_batch_size=self._settings.memgraph_node_batch_size,
                    edge_batch_size=self._settings.memgraph_edge_batch_size,
                    delete_batch_size=self._settings.memgraph_delete_batch_size,
                )
            except Exception as e:
                logger.warning(f"Failed to load Memgraph, using fallback: {e}")
                from src.infra.graph.in_memory_store import InMemoryGraphStore

                return InMemoryGraphStore()
        else:
            # Fallback: InMemoryGraphStore
            logger.info("Using InMemoryGraphStore (fallback mode)")
            from src.infra.graph.in_memory_store import InMemoryGraphStore

            return InMemoryGraphStore()

    # ========================================================================
    # Search & LLM
    # ========================================================================

    @cached_property
    def zoekt(self) -> ZoektAdapter:
        """Zoekt code search adapter."""
        from src.infra.search.zoekt import ZoektAdapter

        return ZoektAdapter(
            host=self._settings.zoekt_host,
            port=self._settings.zoekt_port,
        )

    @cached_property
    def llm(self) -> LocalLLMAdapter:
        """LLM provider adapter (Local: Ollama/vLLM/LocalAI)."""
        from src.infra.llm.local_llm import LocalLLMAdapter

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
