"""
Retriever DI Registration

Registers retriever components:
- V3 Orchestrator & Service
- Legacy Retriever Service
- Intent Analyzer, Scope Selector
- Multi-Index Orchestrator, Fusion Engine
- Context Builder
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from src.common.factory_helpers import safe_factory_call, validate_factory
from src.common.types import RepoMapStoreFactory

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.context_builder import ContextBuilder
    from src.contexts.retrieval_search.infrastructure.fusion import FusionEngine
    from src.contexts.retrieval_search.infrastructure.intent import IntentAnalyzer
    from src.contexts.retrieval_search.infrastructure.multi_index import (
        LexicalIndexClient,
        MultiIndexOrchestrator,
        SymbolIndexClient,
        VectorIndexClient,
    )
    from src.contexts.retrieval_search.infrastructure.scope import ScopeSelector
    from src.contexts.retrieval_search.infrastructure.service import RetrieverService
    from src.contexts.retrieval_search.infrastructure.v3.orchestrator import RetrieverV3Orchestrator
    from src.contexts.retrieval_search.infrastructure.v3.service import RetrieverV3Service
from src.common.observability import get_logger

logger = get_logger(__name__)


class RetrieverContainer:
    """
    Retriever components container.

    All components are lazy-loaded singletons via @cached_property.
    """

    def __init__(
        self,
        settings,
        infra_container,
        index_container,
        foundation_container,
        repomap_store_factory: RepoMapStoreFactory,
    ):
        """
        Args:
            settings: Application settings
            infra_container: InfraContainer for LLM, Redis
            index_container: IndexContainer for search indexes
            foundation_container: FoundationContainer for chunk_store
            repomap_store_factory: Factory function to get repomap store (lazy)

        Raises:
            TypeError: If factory function is not callable
        """
        # Validate factory
        validate_factory(repomap_store_factory, "repomap_store_factory", required=True)

        self._settings = settings
        self._infra = infra_container
        self._index = index_container
        self._foundation = foundation_container
        self._repomap_store_factory = repomap_store_factory

    # ========================================================================
    # V3 Retriever (High-Performance)
    # ========================================================================

    @cached_property
    def v3_orchestrator(self) -> RetrieverV3Orchestrator:
        """
        Retriever V3 orchestrator with async parallel search.

        High-performance retrieval with:
        - Async parallel search across 4 strategies
        - V3 fusion engine with intent-aware ranking
        - 2-tier caching (L1 in-memory + L2 Redis)
        - ML logging (optional)
        """
        from src.contexts.retrieval_search.infrastructure.v3.orchestrator import RetrieverV3Orchestrator

        return RetrieverV3Orchestrator(
            symbol_index=self._index.symbol_index if self._settings.indexing_enable_symbol else None,
            vector_index=self._index.vector_index if self._settings.indexing_enable_vector else None,
            lexical_index=self._index.lexical_index if self._settings.indexing_enable_lexical else None,
            graph_index=None,
            enable_async=True,
            search_logger=self.search_logger,  # Inject search logger
        )

    @cached_property
    def v3_service(self) -> RetrieverV3Service:
        """Retriever V3 service with L2 Redis caching."""
        from src.contexts.retrieval_search.infrastructure.v3.service import RetrieverV3Service

        try:
            redis_client = self._infra.redis.client
        except (ConnectionError, AttributeError):
            redis_client = None

        return RetrieverV3Service(cache_client=redis_client)

    # ========================================================================
    # Legacy Retriever Service
    # ========================================================================

    @cached_property
    def service(self) -> RetrieverService:
        """
        Retriever service coordinating complete retrieval pipeline.

        Pipeline: Intent → Scope → Multi-index → Fusion → Context
        """
        from src.contexts.retrieval_search.infrastructure.service import RetrieverService

        return RetrieverService(
            intent_analyzer=self.intent_analyzer,
            scope_selector=self.scope_selector,
            orchestrator=self.multi_index_orchestrator,
            fusion_engine=self.fusion_engine,
            context_builder=self.context_builder,
            repomap_port=safe_factory_call(
                self._repomap_store_factory,
                factory_name="repomap_store_factory",
                default=None,
            ),
        )

    # ========================================================================
    # Pipeline Components
    # ========================================================================

    @cached_property
    def intent_analyzer(self) -> IntentAnalyzer:
        """Intent analyzer for query classification."""
        from src.contexts.retrieval_search.infrastructure.intent import IntentAnalyzer

        return IntentAnalyzer(
            llm_client=self._infra.llm,
            timeout_seconds=1.5,
            enable_llm=True,
        )

    @cached_property
    def scope_selector(self) -> ScopeSelector:
        """Scope selector for RepoMap-based search scoping."""
        from src.contexts.retrieval_search.infrastructure.scope import ScopeSelector

        return ScopeSelector(
            repomap_port=safe_factory_call(
                self._repomap_store_factory,
                factory_name="repomap_store_factory",
                default=None,
            ),
            default_top_k=20,
            max_chunk_ids=500,
        )

    @cached_property
    def multi_index_orchestrator(self) -> MultiIndexOrchestrator:
        """Multi-index search orchestrator."""
        from src.contexts.retrieval_search.infrastructure.multi_index import MultiIndexOrchestrator

        return MultiIndexOrchestrator(
            lexical_client=self.lexical_client,
            vector_client=self.vector_client,
            symbol_client=self.symbol_client,
            graph_client=self.graph_expansion_client,
        )

    @cached_property
    def fusion_engine(self) -> FusionEngine:
        """Fusion engine for multi-index result combination."""
        from src.contexts.retrieval_search.infrastructure.fusion import FusionEngine

        return FusionEngine(enable_dedup=True)

    @cached_property
    def context_builder(self) -> ContextBuilder:
        """Context builder for LLM context generation."""
        from src.contexts.retrieval_search.infrastructure.context_builder import ContextBuilder

        return ContextBuilder(
            chunk_store=self._foundation.chunk_store,
            token_counter=None,
            enable_trimming=True,
            enable_dedup=True,
        )

    # ========================================================================
    # Index Clients
    # ========================================================================

    @cached_property
    def lexical_client(self) -> LexicalIndexClient:
        """Lexical index client wrapper."""
        from src.contexts.retrieval_search.infrastructure.multi_index import LexicalIndexClient

        return LexicalIndexClient(lexical_index=self._index.lexical_index)

    @cached_property
    def vector_client(self) -> VectorIndexClient:
        """Vector index client wrapper."""
        from src.contexts.retrieval_search.infrastructure.multi_index import VectorIndexClient

        return VectorIndexClient(vector_index=self._index.vector_index)

    @cached_property
    def symbol_client(self) -> SymbolIndexClient:
        """Symbol index client wrapper."""
        from src.contexts.retrieval_search.infrastructure.multi_index import SymbolIndexClient

        return SymbolIndexClient(symbol_index=self._index.symbol_index)

    @cached_property
    def graph_expansion_client(self):
        """Graph expansion client for flow tracing."""
        from src.contexts.retrieval_search.infrastructure.graph_runtime_expansion import GraphExpansionClient

        return GraphExpansionClient(symbol_index=self._index.symbol_index)

    # ========================================================================
    # ML Logging (for tuning)
    # ========================================================================

    @cached_property
    def search_logger(self):
        """Search logger for ML tuning.

        Note: PostgresStore must be initialized before using search_logger.
        Call `await container.postgres.initialize()` first.
        """
        from src.contexts.retrieval_search.infrastructure.logging import SearchLogger

        return SearchLogger(
            db_pool=self._infra.postgres,  # Pass PostgresStore directly
            enable_async=True,
            buffer_size=100,
        )
