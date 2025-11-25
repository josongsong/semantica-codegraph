"""
Dependency Injection Container

Provides lazy singleton instances of all adapters and services.
Follows Port/Adapter pattern with constructor injection.

Usage:
    from src.container import container

    # Access services
    result = container.indexing_service.index_repo_full(...)

    # Access adapters
    docs = container.qdrant.search(...)
"""

from functools import cached_property

from src.config import settings


class Container:
    """
    Application-wide dependency injection container.

    All dependencies are lazy-loaded as singletons using @cached_property.
    Container is the ONLY place where concrete implementations are created.
    """

    # ========================================================================
    # Adapters: Infrastructure Layer
    # ========================================================================

    @cached_property
    def qdrant(self):
        """Qdrant vector store adapter."""
        from src.infra.vector.qdrant import QdrantVectorStore

        return QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection_name,
        )

    @cached_property
    def kuzu(self):
        """Kuzu graph database adapter."""
        from src.infra.graph.kuzu import KuzuGraphStore

        return KuzuGraphStore(
            db_path=settings.kuzu_db_path,
            buffer_pool_size=settings.kuzu_buffer_pool_size,
        )

    @cached_property
    def postgres(self):
        """PostgreSQL database adapter."""
        from src.infra.storage.postgres import PostgresStore

        return PostgresStore(
            connection_string=settings.database_url,
            min_pool_size=settings.postgres_min_pool_size,
            max_pool_size=settings.postgres_max_pool_size,
        )

    @cached_property
    def redis(self):
        """Redis cache adapter."""
        from src.infra.cache.redis import RedisCache

        return RedisCache(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
        )

    @cached_property
    def llm(self):
        """LLM provider adapter (OpenAI via LiteLLM)."""
        from src.infra.llm.openai import OpenAILLM

        return OpenAILLM(
            model=settings.litellm_model,
            api_key=settings.litellm_api_key or settings.openai_api_key,
        )

    # ========================================================================
    # Index Adapters
    # ========================================================================

    @cached_property
    def lexical_index(self):
        """Lexical search index (Zoekt)."""
        from src.index.lexical.adapter_zoekt import (
            RepoPathResolver,
            ZoektLexicalIndex,
        )
        from src.infra.search.zoekt import ZoektAdapter

        # Create Zoekt adapter
        zoekt_adapter = ZoektAdapter(
            host=settings.zoekt_host,
            port=settings.zoekt_port,
        )

        # Create repo path resolver
        repo_resolver = RepoPathResolver(repos_root=settings.zoekt_repos_root)

        return ZoektLexicalIndex(
            zoekt_adapter=zoekt_adapter,
            chunk_store=self.chunk_store,
            repo_resolver=repo_resolver,
            zoekt_index_cmd=settings.zoekt_index_cmd or "zoekt-index",
        )

    @cached_property
    def vector_index(self):
        """Vector search index (Qdrant)."""
        from qdrant_client import AsyncQdrantClient

        from src.index.vector.adapter_qdrant import (
            OpenAIEmbeddingProvider,
            QdrantVectorIndex,
        )

        # Create Qdrant client
        qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)

        # Create embedding provider
        embedding_provider = OpenAIEmbeddingProvider(model=settings.embedding_model or "text-embedding-3-small")

        return QdrantVectorIndex(
            client=qdrant_client,
            embedding_provider=embedding_provider,
            collection_prefix=settings.qdrant_collection_name or "code_embeddings",
        )

    @cached_property
    def symbol_index(self):
        """Symbol search index (Kuzu graph)."""
        from src.index.symbol.adapter_kuzu import KuzuSymbolIndex

        return KuzuSymbolIndex(
            db_path=settings.kuzu_db_path,
        )

    @cached_property
    def fuzzy_index(self):
        """Fuzzy search index (PostgreSQL trigram)."""
        from src.index.fuzzy.adapter_pgtrgm import PostgresFuzzyIndex

        return PostgresFuzzyIndex(
            postgres_store=self.postgres,
        )

    @cached_property
    def domain_index(self):
        """Domain/documentation search index."""
        from src.index.domain_meta.adapter_meta import DomainMetaIndex

        return DomainMetaIndex(
            postgres_store=self.postgres,
        )

    # Note: runtime_index is Phase 3, not implemented yet

    # ========================================================================
    # Services: Business Logic Layer
    # ========================================================================

    @cached_property
    def indexing_service(self):
        """Indexing service orchestrating all index types."""
        from src.index.service import IndexingService

        return IndexingService(
            lexical_index=self.lexical_index,
            vector_index=self.vector_index,
            symbol_index=self.symbol_index,
            fuzzy_index=self.fuzzy_index,
            domain_index=self.domain_index,
            runtime_index=None,  # Phase 3
        )

    @cached_property
    def search_service(self):
        """
        Unified search service (alias for indexing_service.search).

        Provides weighted fusion across all index types.
        """
        return self.indexing_service

    # ========================================================================
    # RepoMap Components
    # ========================================================================

    @cached_property
    def repomap_store(self):
        """RepoMap persistent storage (PostgreSQL)."""
        from src.repomap.storage_postgres import PostgresRepoMapStore

        return PostgresRepoMapStore(
            connection_string=settings.database_url,
        )

    @cached_property
    def repomap_builder(self):
        """RepoMap builder service."""
        from src.repomap import RepoMapBuilder

        return RepoMapBuilder(
            store=self.repomap_store,
            llm=self.llm,
        )

    @cached_property
    def repomap_incremental_updater(self):
        """RepoMap incremental updater."""
        from src.repomap import RepoMapIncrementalUpdater

        return RepoMapIncrementalUpdater(
            store=self.repomap_store,
            llm=self.llm,
        )

    # ========================================================================
    # Foundation Components
    # ========================================================================

    @cached_property
    def chunk_store(self):
        """Chunk storage (PostgreSQL)."""
        # TODO: Implement PostgresChunkStore
        # For now, use in-memory store
        from src.foundation.chunk import InMemoryChunkStore

        return InMemoryChunkStore()

    @cached_property
    def graph_store(self):
        """Graph storage (Kuzu)."""
        return self.kuzu  # Alias for consistency

    @cached_property
    def postgres_store(self):
        """PostgreSQL store (alias for postgres)."""
        return self.postgres

    # ========================================================================
    # RFC-023: Pyright Semantic Analysis
    # ========================================================================

    def create_semantic_ir_builder_with_pyright(self, project_root):
        """
        Create a Pyright-enabled semantic IR builder for a specific project.

        RFC-023 M0: Uses PyrightExternalAnalyzer (adapter over PyrightSemanticDaemon).

        This is a factory method (not cached) - creates a new instance per call.

        Args:
            project_root: Path to project root directory

        Returns:
            DefaultSemanticIrBuilder with PyrightExternalAnalyzer

        Note:
            Used by IndexingOrchestrator when enable_pyright=True in settings.
        """
        from pathlib import Path

        from src.foundation.ir.external_analyzers import PyrightExternalAnalyzer
        from src.foundation.semantic_ir import DefaultSemanticIrBuilder

        # Create Pyright adapter for this project
        pyright = PyrightExternalAnalyzer(Path(project_root))

        # Create semantic IR builder with Pyright
        return DefaultSemanticIrBuilder(external_analyzer=pyright)

    def create_pyright_daemon(self, project_root):
        """
        Create a Pyright daemon for a specific project.

        RFC-023 M0: Direct access to PyrightSemanticDaemon for snapshot management.

        This is a factory method (not cached) - creates a new instance per call.

        Args:
            project_root: Path to project root directory

        Returns:
            PyrightSemanticDaemon instance

        Note:
            Used for direct snapshot-based Pyright integration.
        """
        from pathlib import Path

        from src.foundation.ir.external_analyzers import PyrightSemanticDaemon

        return PyrightSemanticDaemon(Path(project_root))

    @cached_property
    def semantic_snapshot_store(self):
        """
        Create semantic snapshot store.

        RFC-023 M1: PostgreSQL storage for Pyright semantic snapshots.

        Returns:
            SemanticSnapshotStore instance

        Note:
            Requires PostgreSQL store to be initialized.
        """
        from src.foundation.ir.external_analyzers import SemanticSnapshotStore

        return SemanticSnapshotStore(self.postgres_store)

    # ========================================================================
    # Utilities
    # ========================================================================

    def health_check(self) -> dict[str, bool]:
        """
        Check health of all adapters.

        Returns:
            Dictionary mapping adapter name to health status.
        """
        health = {}

        # Check each adapter
        try:
            # TODO: Implement actual health check methods
            health["qdrant"] = True
            health["kuzu"] = True
            health["postgres"] = True
            health["redis"] = True
        except Exception:
            pass

        return health


# Module-level singleton (eager instantiation of container itself)
container = Container()
