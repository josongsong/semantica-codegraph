"""
Index DI Registration

Registers all index adapters:
- Lexical (Zoekt)
- Vector (Qdrant)
- Symbol (Memgraph)
- Fuzzy (PostgreSQL trigram)
- Domain (PostgreSQL)
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.multi_index.infrastructure.domain_meta.adapter_meta import DomainMetaIndex
    from src.contexts.multi_index.infrastructure.fuzzy.adapter_pgtrgm import PostgresFuzzyIndex
    from src.contexts.multi_index.infrastructure.lexical.adapter_zoekt import ZoektLexicalIndex
    from src.contexts.multi_index.infrastructure.service import IndexingService
    from src.contexts.multi_index.infrastructure.symbol.adapter_memgraph import MemgraphSymbolIndex
    from src.contexts.multi_index.infrastructure.vector.adapter_qdrant import QdrantVectorIndex
from src.common.observability import get_logger

logger = get_logger(__name__)


class IndexContainer:
    """
    Index adapters container.

    All indexes are lazy-loaded singletons via @cached_property.
    """

    def __init__(self, settings, infra_container, foundation_container):
        """
        Args:
            settings: Application settings
            infra_container: InfraContainer for database access
            foundation_container: FoundationContainer for chunk_store
        """
        self._settings = settings
        self._infra = infra_container
        self._foundation = foundation_container

    # ========================================================================
    # Index Adapters
    # ========================================================================

    @cached_property
    def delta_lexical_index(self):
        """Delta Lexical Index (PostgreSQL tsvector) - v4.5."""
        from src.contexts.multi_index.infrastructure.lexical.delta.delta_index import DeltaLexicalIndex
        from src.contexts.multi_index.infrastructure.lexical.delta.tombstone import TombstoneManager

        tombstone = TombstoneManager(db_pool=self._infra.postgres)

        return DeltaLexicalIndex(
            db_pool=self._infra.postgres,
            tombstone_manager=tombstone,
        )

    @cached_property
    def merging_lexical_index(self):
        """Merging Lexical Index (Base + Delta) - v4.5."""
        from src.contexts.multi_index.infrastructure.lexical.merge.merging_index import MergingLexicalIndex

        return MergingLexicalIndex(
            base_index=self.lexical_index,
            delta_index=self.delta_lexical_index,
        )

    @cached_property
    def compaction_manager(self):
        """Compaction Manager - v4.5."""
        from src.contexts.multi_index.infrastructure.lexical.compaction.freeze_buffer import FreezeBuffer
        from src.contexts.multi_index.infrastructure.lexical.compaction.manager import CompactionManager

        freeze_buffer = FreezeBuffer(redis=self._infra.redis)

        return CompactionManager(
            base_index=self.lexical_index,
            delta_index=self.delta_lexical_index,
            freeze_buffer=freeze_buffer,
            trigger_file_count=200,
            trigger_age_hours=24,
        )

    @cached_property
    def lexical_index(self) -> ZoektLexicalIndex:
        """Lexical search index (Zoekt)."""
        from src.contexts.multi_index.infrastructure.lexical.adapter_zoekt import RepoPathResolver, ZoektLexicalIndex
        from src.infra.search.zoekt import ZoektAdapter

        zoekt_adapter = ZoektAdapter(
            host=self._settings.zoekt_host,
            port=self._settings.zoekt_port,
        )

        repo_resolver = RepoPathResolver(repos_root=self._settings.zoekt_repos_root)

        return ZoektLexicalIndex(
            zoekt_adapter=zoekt_adapter,
            chunk_store=self._foundation.chunk_store,
            repo_resolver=repo_resolver,
            zoekt_index_cmd=self._settings.zoekt_index_cmd or "zoekt-index",
            zoekt_index_dir=self._settings.zoekt_index_dir or "./data/zoekt-index",
        )

    @cached_property
    def vector_index(self) -> QdrantVectorIndex:
        """Vector search index (Qdrant) with local bge-m3 embeddings."""
        from qdrant_client import AsyncQdrantClient

        from src.contexts.multi_index.infrastructure.vector.adapter_qdrant import QdrantVectorIndex
        from src.infra.llm.local_llm import LocalEmbeddingProvider, LocalLLMAdapter

        qdrant_client = AsyncQdrantClient(url=self._settings.qdrant_url)

        local_llm_adapter = LocalLLMAdapter(
            base_url=self._settings.local_llm_base_url,
            embedding_model=self._settings.local_embedding_model,
        )

        embedding_provider = LocalEmbeddingProvider(adapter=local_llm_adapter)

        return QdrantVectorIndex(
            client=qdrant_client,
            embedding_provider=embedding_provider,
            collection_prefix=self._settings.qdrant_collection_name or "code_embeddings",
            vector_size=self._settings.local_embedding_dimension,
        )

    @cached_property
    def symbol_index(self) -> MemgraphSymbolIndex:
        """Symbol search index (Memgraph-based) with optional semantic search."""
        from src.contexts.multi_index.infrastructure.symbol.adapter_memgraph import MemgraphSymbolIndex

        embedding_provider = None
        qdrant_client = None

        if self._settings.indexing_enable_symbol_embedding:
            try:
                embedding_provider = self._infra.local_llm
                qdrant_client = self._infra.qdrant_async
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                logger.warning(f"Symbol embedding disabled due to connection error: {e}")

        return MemgraphSymbolIndex(
            graph_store=self._infra.memgraph,
            embedding_provider=embedding_provider,
            qdrant_client=qdrant_client,
            symbol_embedding_collection="symbol_embeddings",
            embedding_dim=self._settings.local_embedding_dimension,
        )

    @cached_property
    def fuzzy_index(self) -> PostgresFuzzyIndex:
        """Fuzzy search index (PostgreSQL trigram)."""
        from src.contexts.multi_index.infrastructure.fuzzy.adapter_pgtrgm import PostgresFuzzyIndex

        return PostgresFuzzyIndex(postgres_store=self._infra.postgres)

    @cached_property
    def domain_index(self) -> DomainMetaIndex:
        """Domain/documentation search index."""
        from src.contexts.multi_index.infrastructure.domain_meta.adapter_meta import DomainMetaIndex

        return DomainMetaIndex(postgres_store=self._infra.postgres)

    @cached_property
    def embedding_queue(self):
        """Embedding priority queue for background processing."""
        from src.contexts.multi_index.infrastructure.vector.embedding_queue import EmbeddingQueue

        # embedding_provider와 vector_index 가져오기
        if not self._settings.indexing_enable_vector:
            logger.info("embedding_queue_disabled_no_vector_index")
            return None

        try:
            # embedding_provider는 vector_index에 이미 있음
            embedding_provider = self.vector_index.embedding_provider

            # chunk_store도 주입
            chunk_store = self._foundation.chunk_store

            return EmbeddingQueue(
                postgres_store=self._infra.postgres,
                embedding_provider=embedding_provider,
                vector_index=self.vector_index,
                chunk_store=chunk_store,
            )
        except Exception as e:
            logger.warning(f"embedding_queue_creation_failed: {e}")
            return None

    @cached_property
    def embedding_worker_pool(self):
        """Embedding worker pool (event-driven)."""
        from src.contexts.multi_index.infrastructure.vector.worker_pool import EmbeddingWorkerPool

        if not self.embedding_queue:
            logger.info("embedding_worker_pool_disabled_no_queue")
            return None

        pool = EmbeddingWorkerPool(
            queue=self.embedding_queue,
            worker_count=3,
            max_retries=3,
        )

        # Circular reference 해결
        self.embedding_queue.worker_pool = pool

        return pool

    # ========================================================================
    # Index Service
    # ========================================================================

    @cached_property
    def indexing_service(self) -> IndexingService:
        """
        Indexing service orchestrating all index types.

        Respects indexing_enable_* flags from settings.
        """
        from src.contexts.multi_index.infrastructure.service import IndexingService

        # IndexingOrchestrator는 lazy하게 주입
        # (순환 참조 방지 위해 setter 사용 또는 runtime에 주입)

        return IndexingService(
            lexical_index=self.lexical_index if self._settings.indexing_enable_lexical else None,
            vector_index=self.vector_index if self._settings.indexing_enable_vector else None,
            symbol_index=self.symbol_index if self._settings.indexing_enable_symbol else None,
            fuzzy_index=self.fuzzy_index if self._settings.indexing_enable_fuzzy else None,
            domain_index=self.domain_index if self._settings.indexing_enable_domain else None,
            runtime_index=None,  # Phase 3
            indexing_orchestrator=None,  # Lazy 주입 (set_indexing_orchestrator로)
        )

    @property
    def search_service(self) -> IndexingService:
        """Unified search service (alias for indexing_service)."""
        return self.indexing_service
