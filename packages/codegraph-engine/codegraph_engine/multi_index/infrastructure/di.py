"""
Index DI Registration

Registers all index adapters:
- Lexical (Tantivy)
- Vector (Qdrant)
- Symbol (Memgraph)
- Fuzzy (PostgreSQL trigram)
- Domain (PostgreSQL)
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.domain_meta.adapter_meta import DomainMetaIndex

    # from codegraph_engine.multi_index.infrastructure.fuzzy.adapter_pgtrgm import PostgresFuzzyIndex  # DEPRECATED RFC-020
    from codegraph_engine.multi_index.infrastructure.service import IndexingService
    from codegraph_engine.multi_index.infrastructure.symbol.adapter_memgraph import MemgraphSymbolIndex
    from codegraph_engine.multi_index.infrastructure.vector.adapter_qdrant import QdrantVectorIndex
from codegraph_shared.common.observability import get_logger

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

    # @cached_property
    # def delta_lexical_index(self):
    #     """DEPRECATED (RFC-020 Phase 3): TantivyCodeIndex 단일화로 Delta 개념 소멸"""
    #     # DeltaLexicalIndex 제거됨 (15 사용처)
    #     return None

    # @cached_property
    # def merging_lexical_index(self):
    #     """DEPRECATED (RFC-020 Phase 4): Tantivy 단일화로 불필요"""
    #     # MergingLexicalIndex 제거됨 (7 사용처)
    #     return None

    # @cached_property
    # def compaction_manager(self):
    #     """DEPRECATED (RFC-020 Phase 4): Tantivy 단일화로 Base/Delta 개념 소멸"""
    #     # CompactionManager 제거됨 (6 사용처)
    #     return None

    @cached_property
    def lexical_index(self):
        """Lexical search index (Tantivy)."""
        from codegraph_engine.multi_index.infrastructure.lexical.tantivy import TantivyCodeIndex

        return TantivyCodeIndex(
            index_dir=self._settings.tantivy_index_path,
            chunk_store=self._foundation.chunk_store,
            heap_size_mb=self._settings.tantivy_heap_size_mb,
            num_threads=self._settings.tantivy_num_threads,
        )

    @cached_property
    def vector_index(self) -> QdrantVectorIndex:
        """Vector search index (Qdrant) with local bge-m3 embeddings."""
        from codegraph_engine.multi_index.infrastructure.vector.adapter_qdrant import QdrantVectorIndex
        from codegraph_shared.infra.llm.local_llm import LocalEmbeddingProvider, LocalLLMAdapter
        from codegraph_shared.infra.vector import create_qdrant_client

        qdrant_client = create_qdrant_client(
            mode=self._settings.qdrant_mode,
            storage_path=self._settings.qdrant_storage_path,
            url=self._settings.qdrant_url,
            host=self._settings.qdrant_host,
            port=self._settings.qdrant_port,
            grpc_port=self._settings.qdrant_grpc_port,
            prefer_grpc=self._settings.qdrant_prefer_grpc,
        )

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
        from codegraph_engine.multi_index.infrastructure.symbol.adapter_memgraph import MemgraphSymbolIndex

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
    def fuzzy_index(self):
        """DEPRECATED (RFC-020 Phase 1): SymbolSearchLayer (SymSpell + Trigram)로 대체"""
        # PostgresFuzzyIndex 제거됨 (18 사용처)
        return None

    @cached_property
    def domain_index(self) -> DomainMetaIndex:
        """Domain/documentation search index."""
        from codegraph_engine.multi_index.infrastructure.domain_meta.adapter_meta import DomainMetaIndex

        return DomainMetaIndex(postgres_store=self._infra.postgres)

    @cached_property
    def embedding_queue(self):
        """Embedding priority queue for background processing."""
        from codegraph_engine.multi_index.infrastructure.vector.embedding_queue import EmbeddingQueue

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
        from codegraph_engine.multi_index.infrastructure.vector.worker_pool import EmbeddingWorkerPool

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
        from codegraph_engine.multi_index.infrastructure.service import IndexingService

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
