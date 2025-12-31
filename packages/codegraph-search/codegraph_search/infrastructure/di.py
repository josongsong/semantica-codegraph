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

from codegraph_shared.common.factory_helpers import safe_factory_call, validate_factory
from codegraph_shared.common.types import RepoMapStoreFactory

if TYPE_CHECKING:
    # SOTA 2024 components
    from codegraph_search.infrastructure.adaptive.self_rag import SelfRAGDecider, SelfRAGRetriever
    from codegraph_search.infrastructure.context_builder import ContextBuilder
    from codegraph_search.infrastructure.context_builder.compressor import (
        BatchCompressor,
        ContextualCompressor,
    )
    from codegraph_search.infrastructure.context_builder.position_bias import PositionBiasReorderer
    from codegraph_search.infrastructure.fusion import FusionEngine
    from codegraph_search.infrastructure.intent import IntentAnalyzer
    from codegraph_search.infrastructure.multi_index import (
        LexicalIndexClient,
        MultiIndexOrchestrator,
        SymbolIndexClient,
        VectorIndexClient,
    )
    from codegraph_search.infrastructure.query.hyde import HyDEGenerator, HyDEQueryProcessor
    from codegraph_search.infrastructure.query.multi_query import (
        MultiQueryGenerator,
        MultiQueryRetriever,
    )
    from codegraph_search.infrastructure.scope import ScopeSelector
    from codegraph_search.infrastructure.service import RetrieverService
    from codegraph_search.infrastructure.v3.orchestrator import RetrieverV3Orchestrator
    from codegraph_search.infrastructure.v3.service import RetrieverV3Service
from codegraph_shared.common.observability import get_logger

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
        - SOTA 2024: HyDE, Self-RAG, RAG-Fusion, Compression, Position Bias
        """
        from codegraph_search.infrastructure.v3.orchestrator import RetrieverV3Orchestrator

        return RetrieverV3Orchestrator(
            symbol_index=self._index.symbol_index if self._settings.indexing_enable_symbol else None,
            vector_index=self._index.vector_index if self._settings.indexing_enable_vector else None,
            lexical_index=self._index.lexical_index if self._settings.indexing_enable_lexical else None,
            graph_index=None,
            enable_async=True,
            search_logger=self.search_logger,  # Inject search logger
            # SOTA 2024 components (conditional on config)
            hyde_processor=self.hyde_processor if self._settings.retriever.enable_hyde else None,
            self_rag_retriever=self.self_rag_retriever if self._settings.retriever.enable_self_rag else None,
            multi_query_retriever=self.multi_query_retriever if self._settings.retriever.enable_rag_fusion else None,
            batch_compressor=self.batch_compressor if self._settings.retriever.enable_compression else None,
            position_reorderer=self.position_reorderer if self._settings.retriever.enable_position_reordering else None,
        )

    @cached_property
    def v3_service(self) -> RetrieverV3Service:
        """Retriever V3 service with L2 Redis caching."""
        from codegraph_search.infrastructure.v3.service import RetrieverV3Service

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
        from codegraph_search.infrastructure.service import RetrieverService

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
        from codegraph_search.infrastructure.intent import IntentAnalyzer

        return IntentAnalyzer(
            llm_client=self._infra.llm,
            timeout_seconds=1.5,
            enable_llm=True,
        )

    @cached_property
    def scope_selector(self) -> ScopeSelector:
        """Scope selector for RepoMap-based search scoping."""
        from codegraph_search.infrastructure.scope import ScopeSelector

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
        from codegraph_search.infrastructure.multi_index import MultiIndexOrchestrator

        return MultiIndexOrchestrator(
            lexical_client=self.lexical_client,
            vector_client=self.vector_client,
            symbol_client=self.symbol_client,
            graph_client=self.graph_expansion_client,
        )

    @cached_property
    def fusion_engine(self) -> FusionEngine:
        """Fusion engine for multi-index result combination."""
        from codegraph_search.infrastructure.fusion import FusionEngine

        return FusionEngine(enable_dedup=True)

    @cached_property
    def context_builder(self) -> ContextBuilder:
        """Context builder for LLM context generation."""
        from codegraph_search.infrastructure.context_builder import ContextBuilder

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
        from codegraph_search.infrastructure.multi_index import LexicalIndexClient

        return LexicalIndexClient(lexical_index=self._index.lexical_index)

    @cached_property
    def vector_client(self) -> VectorIndexClient:
        """Vector index client wrapper."""
        from codegraph_search.infrastructure.multi_index import VectorIndexClient

        return VectorIndexClient(vector_index=self._index.vector_index)

    @cached_property
    def symbol_client(self) -> SymbolIndexClient:
        """Symbol index client wrapper."""
        from codegraph_search.infrastructure.multi_index import SymbolIndexClient

        return SymbolIndexClient(symbol_index=self._index.symbol_index)

    @cached_property
    def graph_expansion_client(self):
        """Graph expansion client for flow tracing."""
        from codegraph_search.infrastructure.graph_runtime_expansion import GraphExpansionClient

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
        from codegraph_search.infrastructure.logging import SearchLogger

        return SearchLogger(
            db_pool=self._infra.postgres,  # Pass PostgresStore directly
            enable_async=True,
            buffer_size=100,
        )

    # ========================================================================
    # SOTA 2024 Components
    # ========================================================================

    @cached_property
    def hyde_generator(self) -> HyDEGenerator:
        """HyDE generator for hypothetical document creation."""
        from codegraph_search.infrastructure.query.hyde import HyDEGenerator

        return HyDEGenerator(
            llm=self._infra.llm,
            embedding_provider=self._infra.local_llm,  # Use local embedding
            temperature=self._settings.retriever.hyde_temperature,
            num_hypotheses=self._settings.retriever.hyde_num_hypotheses,
        )

    @cached_property
    def hyde_processor(self) -> HyDEQueryProcessor:
        """HyDE query processor with confidence-based gating."""
        from codegraph_search.infrastructure.query.hyde import HyDEQueryProcessor

        return HyDEQueryProcessor(
            hyde_generator=self.hyde_generator,
            enable_hyde=self._settings.retriever.enable_hyde,
            hyde_threshold=self._settings.retriever.hyde_confidence_threshold,
        )

    @cached_property
    def self_rag_decider(self) -> SelfRAGDecider:
        """Self-RAG decision engine for retrieval gating."""
        from codegraph_search.infrastructure.adaptive.self_rag import SelfRAGDecider

        return SelfRAGDecider(
            llm=self._infra.llm,
            temperature=0.0,  # Deterministic for consistent decisions
        )

    @cached_property
    def self_rag_retriever(self) -> SelfRAGRetriever:
        """Self-RAG retriever with intelligent gating."""
        from codegraph_search.infrastructure.adaptive.self_rag import SelfRAGRetriever

        return SelfRAGRetriever(
            decider=self.self_rag_decider,
            skip_retrieval_threshold=self._settings.retriever.self_rag_skip_threshold,
            relevance_threshold=self._settings.retriever.self_rag_relevance_threshold,
            enable_self_rag=self._settings.retriever.enable_self_rag,
        )

    @cached_property
    def multi_query_generator(self) -> MultiQueryGenerator:
        """Multi-query generator for RAG-Fusion."""
        from codegraph_search.infrastructure.query.multi_query import MultiQueryGenerator

        return MultiQueryGenerator(
            llm=self._infra.llm,
            num_queries=self._settings.retriever.rag_fusion_num_queries,
            temperature=0.7,  # Some diversity for query variations
        )

    @cached_property
    def multi_query_retriever(self) -> MultiQueryRetriever:
        """Multi-query retriever with result fusion."""
        from codegraph_search.infrastructure.query.multi_query import MultiQueryRetriever

        return MultiQueryRetriever(
            query_generator=self.multi_query_generator,
            fusion_method=self._settings.retriever.rag_fusion_method,
            rrf_k=self._settings.retriever.rag_fusion_rrf_k,
        )

    @cached_property
    def contextual_compressor(self) -> ContextualCompressor:
        """Contextual compressor for token reduction."""
        from codegraph_search.infrastructure.context_builder.compressor import ContextualCompressor

        return ContextualCompressor(
            llm=self._infra.llm,
            compression_method=self._settings.retriever.compression_method,
            target_ratio=self._settings.retriever.compression_ratio,
        )

    @cached_property
    def batch_compressor(self) -> BatchCompressor:
        """Batch compressor with token budget management."""
        from codegraph_search.infrastructure.context_builder.compressor import BatchCompressor

        return BatchCompressor(
            compressor=self.contextual_compressor,
            total_token_budget=self._settings.retriever.compression_token_budget,
        )

    @cached_property
    def position_reorderer(self) -> PositionBiasReorderer:
        """Position bias reorderer for Lost-in-Middle mitigation."""
        from codegraph_search.infrastructure.context_builder.position_bias import PositionBiasReorderer

        return PositionBiasReorderer(
            strategy=self._settings.retriever.position_strategy,
            min_chunks_for_reorder=self._settings.retriever.position_min_chunks,
        )


async def create_retriever_service_minimal():
    """
    Create minimal RetrieverService for MCP server.

    Lightweight service with vector-only fallback for fast startup.

    Returns:
        RetrieverService instance with minimal dependencies

    Raises:
        RuntimeError: If service creation fails
    """
    from codegraph_shared.infra.config.settings import Settings
    from codegraph_shared.infra.di import InfraContainer
    from codegraph_engine.multi_index.infrastructure.di import IndexContainer
    from codegraph_shared.infra.foundation_stub import FoundationContainer  # STUB: Legacy compatibility

    settings = Settings()
    infra = InfraContainer(settings)

    # Initialize PostgreSQL
    await infra.postgres.initialize()

    # Create Index and Foundation containers
    index = IndexContainer(settings, infra.postgres, infra.local_llm)
    foundation = FoundationContainer(settings, infra.postgres)

    # Factory for RepoMap store (lazy)
    def repomap_factory():
        try:
            return foundation.repomap_store
        except Exception:
            return None

    # Create RetrieverContainer
    retriever_container = RetrieverContainer(
        settings=settings,
        infra_container=infra,
        index_container=index,
        foundation_container=foundation,
        repomap_store_factory=repomap_factory,
    )

    # Return the service
    return retriever_container.service
