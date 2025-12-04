"""
Indexing DI Registration

Registers indexing system components:
- Mode System (hash store, metadata, change detector, scope expander)
- IndexingOrchestrator with full pipeline
- Job orchestrator, file watcher, background scheduler
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from src.common.factory_helpers import safe_factory_call
from src.common.observability import get_logger
from src.common.types import GraphStoreFactory, PyrightDaemonFactory, RepoMapStoreFactory

if TYPE_CHECKING:
    from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator

logger = get_logger(__name__)


class IndexingContainer:
    """
    Indexing system container.

    All components are lazy-loaded singletons via @cached_property.
    """

    def __init__(
        self,
        settings,
        infra_container,
        index_container,
        foundation_container,
        graph_store_factory: GraphStoreFactory,
        repomap_store_factory: RepoMapStoreFactory,
        pyright_daemon_factory: PyrightDaemonFactory | None = None,
    ):
        """
        Args:
            settings: Application settings
            infra_container: InfraContainer for Redis, PostgreSQL
            index_container: IndexContainer for index adapters
            foundation_container: FoundationContainer for chunk_store
            graph_store_factory: Factory function to get graph store (lazy)
            repomap_store_factory: Factory function to get repomap store (lazy)
            pyright_daemon_factory: Factory function to create Pyright daemon (optional)

        Raises:
            TypeError: If factory functions are not callable
        """
        from src.common.factory_helpers import validate_factory

        # Validate factories
        validate_factory(graph_store_factory, "graph_store_factory", required=True)
        validate_factory(repomap_store_factory, "repomap_store_factory", required=True)
        validate_factory(pyright_daemon_factory, "pyright_daemon_factory", required=False)

        self._settings = settings
        self._infra = infra_container
        self._index = index_container
        self._foundation = foundation_container
        self._graph_store_factory = graph_store_factory
        self._repomap_store_factory = repomap_store_factory
        self._pyright_daemon_factory = pyright_daemon_factory

    # ========================================================================
    # Mode System Components
    # ========================================================================

    @cached_property
    def file_hash_store(self):
        """File hash store for incremental change detection."""
        from src.contexts.analysis_indexing.infrastructure.content_hash_checker import RedisHashStore

        return RedisHashStore(
            redis_adapter=self._infra.redis,
            key_prefix="file_hash",
            expire_seconds=86400 * 7,  # 7 days TTL
        )

    @cached_property
    def metadata_store(self):
        """Indexing metadata store for mode tracking."""
        from src.infra.metadata import PostgresIndexingMetadataStore

        return PostgresIndexingMetadataStore(db_pool=self._infra.postgres)

    @cached_property
    def version_store(self):
        """Index version store for version tracking (P0-1)."""
        from src.contexts.multi_index.infrastructure.version.store import IndexVersionStore

        return IndexVersionStore(postgres_store=self._infra.postgres)

    @cached_property
    def snapshot_gc(self):
        """Snapshot garbage collector."""
        from src.contexts.analysis_indexing.infrastructure.snapshot_gc import (
            SnapshotGarbageCollector,
            SnapshotRetentionPolicy,
        )

        policy = SnapshotRetentionPolicy(
            keep_latest_count=10,
            keep_days=30,
            keep_tagged=True,
        )

        return SnapshotGarbageCollector(
            postgres_store=self._infra.postgres,
            graph_store=self._main.graph_store,
            policy=policy,
        )

    @cached_property
    def change_detector(self):
        """Change detector for incremental indexing."""
        from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeDetector

        return ChangeDetector(
            git_helper=None,  # Created at runtime with repo_path
            file_hash_store=self.file_hash_store,
        )

    @cached_property
    def scope_expander(self):
        """Scope expander for mode-based file selection."""
        from src.contexts.analysis_indexing.infrastructure.scope_expander import ScopeExpander

        graph_store = self._main.graph_store if self._settings.indexing_enable_symbol else None
        return ScopeExpander(graph_store=graph_store)

    @cached_property
    def mode_manager(self):
        """Mode manager for indexing mode selection."""
        from src.contexts.analysis_indexing.infrastructure.mode_manager import ModeManager

        return ModeManager(
            change_detector=self.change_detector,
            scope_expander=self.scope_expander,
            metadata_store=self.metadata_store,
        )

    @cached_property
    def schema_version_manager(self):
        """Schema version manager for repair mode."""
        from src.infra.metadata.schema_version import SchemaVersionManager

        return SchemaVersionManager(metadata_store=self.metadata_store)

    @cached_property
    def background_scheduler(self):
        """Background scheduler for idle-triggered deep indexing."""
        from src.contexts.analysis_indexing.infrastructure.background_scheduler import BackgroundScheduler

        return BackgroundScheduler(indexing_callback=None)

    # ========================================================================
    # Job & Watcher Services
    # ========================================================================

    @cached_property
    def job_orchestrator(self):
        """
        Job-based indexing orchestrator with distributed locking.

        Provides single writer guarantee, job queuing, idempotent retries.
        """
        # 테스트 환경에서는 Lock 비활성화 (빠른 테스트, Lock 경합 방지)
        import os

        from src.contexts.analysis_indexing.infrastructure.job_orchestrator import IndexJobOrchestrator

        enable_lock = os.getenv("SEMANTICA_ENABLE_DISTRIBUTED_LOCK", "true").lower() == "true"

        return IndexJobOrchestrator(
            orchestrator=self.orchestrator,
            postgres_store=self._infra.postgres,
            redis_client=self._infra.redis,  # RedisAdapter itself has async get/set methods
            lock_ttl=300,
            lock_extend_interval=60,
            enable_distributed_lock=enable_lock,
        )

    @cached_property
    def file_watcher_service(self):
        """File watcher service for real-time file system monitoring."""
        from src.contexts.analysis_indexing.infrastructure.watcher_service import FileWatcherService

        return FileWatcherService(
            job_orchestrator=self.job_orchestrator,
            scheduler=self.background_scheduler,
            scope_expander=self.scope_expander,
            hash_store=self.file_hash_store,
            enable_hash_check=True,
            enable_scope_expansion=self._settings.indexing_enable_symbol,
        )

    @cached_property
    def mode_controller(self):
        """Mode controller for event-driven indexing."""
        from src.contexts.analysis_indexing.infrastructure.mode_controller import ModeController

        return ModeController(
            orchestrator=self.orchestrator,
            mode_manager=self.mode_manager,
            schema_version_manager=self.schema_version_manager,
            background_scheduler=None,
        )

    # ========================================================================
    # Main Orchestrator
    # ========================================================================

    @cached_property
    def orchestrator(self) -> IndexingOrchestrator:
        """
        IndexingOrchestrator with all required dependencies.

        Wires up the complete indexing pipeline including:
        - Parser registry (Tree-sitter parsers)
        - IR builders (language-specific generators)
        - Semantic IR builders (CFG, DFG, types)
        - Graph builders (code graph generation)
        - Chunk builders (LLM-friendly chunking)
        - RepoMap components (tree, PageRank, summaries)
        - All index adapters (lexical, vector, symbol, fuzzy, domain)
        """
        from src.contexts.analysis_indexing.infrastructure.models import IndexingConfig
        from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator
        from src.contexts.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from src.contexts.code_foundation.infrastructure.chunk.id_generator import ChunkIdGenerator
        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder
        from src.contexts.code_foundation.infrastructure.parsing.parser_registry import ParserRegistry
        from src.contexts.code_foundation.infrastructure.semantic_ir import DefaultSemanticIrBuilder
        from src.contexts.repo_structure.infrastructure.models import RepoMapBuildConfig
        from src.contexts.repo_structure.infrastructure.pagerank import PageRankEngine
        from src.contexts.repo_structure.infrastructure.summarizer import (
            CostController,
            InMemorySummaryCache,
            LLMSummarizer,
        )
        from src.contexts.repo_structure.infrastructure.tree import RepoMapTreeBuilder

        # Parser registry
        parser_registry = ParserRegistry()

        # IR builder
        ir_builder = PythonIRGenerator(repo_id="codegraph")

        # Semantic IR builder
        semantic_ir_builder = DefaultSemanticIrBuilder()

        # Graph builder
        graph_builder = GraphBuilder()

        # Chunk builder
        chunk_builder = ChunkBuilder(id_generator=ChunkIdGenerator())

        # Indexing configuration
        indexing_config = IndexingConfig(
            enable_lexical_index=self._settings.indexing_enable_lexical,
            enable_vector_index=self._settings.indexing_enable_vector,
            enable_symbol_index=self._settings.indexing_enable_symbol,
            enable_fuzzy_index=self._settings.indexing_enable_fuzzy,
            enable_domain_index=self._settings.indexing_enable_domain,
            chunk_batch_size=self._settings.indexing_chunk_batch_size,
            vector_batch_size=self._settings.indexing_vector_batch_size,
        )

        # RepoMap components
        repomap_tree_builder_class = RepoMapTreeBuilder

        repomap_build_config = RepoMapBuildConfig(
            pagerank_enabled=True,
            summary_enabled=indexing_config.repomap_use_llm_summaries,
        )
        repomap_pagerank_engine = PageRankEngine(config=repomap_build_config)

        repomap_summarizer = None
        if indexing_config.repomap_use_llm_summaries:
            repomap_summarizer = LLMSummarizer(
                llm=self._infra.llm,
                cache=InMemorySummaryCache(),
                cost_controller=CostController(),
                chunk_store=self._foundation.chunk_store,
                repo_path=None,
            )

        # Create orchestrator
        orchestrator = IndexingOrchestrator(
            parser_registry=parser_registry,
            ir_builder=ir_builder,
            version_store=self.version_store,  # P0-1: Index version tracking
            semantic_ir_builder=semantic_ir_builder,
            graph_builder=graph_builder,
            chunk_builder=chunk_builder,
            repomap_tree_builder_class=repomap_tree_builder_class,
            repomap_pagerank_engine=repomap_pagerank_engine,
            repomap_summarizer=repomap_summarizer,
            graph_store=safe_factory_call(
                self._graph_store_factory,
                factory_name="graph_store_factory",
                default=None,
            )
            if self._settings.indexing_enable_symbol
            else None,
            chunk_store=self._foundation.chunk_store,
            repomap_store=safe_factory_call(
                self._repomap_store_factory,
                factory_name="repomap_store_factory",
                default=None,
            ),
            lexical_index=self._index.lexical_index if self._settings.indexing_enable_lexical else None,
            vector_index=self._index.vector_index if self._settings.indexing_enable_vector else None,
            symbol_index=self._index.symbol_index if self._settings.indexing_enable_symbol else None,
            fuzzy_index=self._index.fuzzy_index if self._settings.indexing_enable_fuzzy else None,
            domain_index=self._index.domain_index if self._settings.indexing_enable_domain else None,
            config=indexing_config,
            pyright_daemon_factory=self._pyright_daemon_factory,  # Factory for Pyright integration
        )

        # Initialize Mode System
        orchestrator.initialize_mode_system(
            metadata_store=self.metadata_store,
            file_hash_store=self.file_hash_store,
        )

        return orchestrator
