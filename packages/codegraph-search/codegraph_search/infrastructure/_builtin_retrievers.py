"""
Built-in Retriever Implementations

This module contains all built-in retriever implementations.
Each retriever self-registers with the global registry on import.

To add a new retriever:
1. Create a wrapper class implementing retrieve()
2. Use @retriever_registry.register("name") decorator
3. Import will auto-register
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

from codegraph_search.infrastructure.registry import retriever_registry
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_search.infrastructure.factory import RetrieverConfig
    from codegraph_search.infrastructure.models import RetrievalResult

logger = get_logger(__name__)


# ============================================================
# Unified Result Format
# ============================================================


@dataclass
class UnifiedRetrievalResult:
    """Unified result format across all retriever types."""

    query: str
    chunks: list[dict[str, Any]]
    total_results: int
    intent: str | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    _raw_result: Any = None

    @property
    def context_text(self) -> str:
        """Get concatenated context text."""
        return "\n\n".join(c.get("content", "") for c in self.chunks)

    @property
    def file_paths(self) -> list[str]:
        """Get unique file paths from chunks."""
        paths = set()
        for c in self.chunks:
            if path := c.get("file_path"):
                paths.add(path)
        return sorted(paths)


# ============================================================
# Basic Retriever
# ============================================================


@retriever_registry.register(
    "basic",
    description="Basic multi-index fusion retriever",
    features=["intent_analysis", "scope_selection", "multi_index", "fusion"],
)
class BasicRetrieverWrapper:
    """Wrapper for RetrieverService to match protocol."""

    def __init__(self, container: Any, config: "RetrieverConfig"):
        self._container = container
        self._config = config
        self._service = self._create_service()

    def _create_service(self) -> Any:
        from codegraph_search.infrastructure.context_builder import ContextBuilder
        from codegraph_search.infrastructure.fusion import FusionEngine
        from codegraph_search.infrastructure.intent import IntentAnalyzer
        from codegraph_search.infrastructure.multi_index import MultiIndexOrchestrator
        from codegraph_search.infrastructure.scope import ScopeSelector
        from codegraph_search.infrastructure.service import RetrieverService

        intent_analyzer = IntentAnalyzer(llm_client=self._container.llm_port)
        scope_selector = ScopeSelector(repomap_port=self._container.repomap_port)

        graph_client = getattr(self._container, "graph_client", None)
        if graph_client is None:
            graph_client = MagicMock()
            graph_client.expand = AsyncMock(return_value=[])

        orchestrator = MultiIndexOrchestrator(
            vector_client=self._container.vector_index,
            lexical_client=self._container.lexical_index,
            symbol_client=self._container.symbol_index,
            graph_client=graph_client,
        )
        fusion_engine = FusionEngine()
        context_builder = ContextBuilder()

        return RetrieverService(
            intent_analyzer=intent_analyzer,
            scope_selector=scope_selector,
            orchestrator=orchestrator,
            fusion_engine=fusion_engine,
            context_builder=context_builder,
            repomap_port=self._container.repomap_port,
        )

    async def retrieve(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        **kwargs: Any,
    ) -> UnifiedRetrievalResult:
        token_budget = kwargs.get("token_budget", self._config.token_budget)
        timeout = kwargs.get("timeout_seconds", self._config.timeout_seconds)

        result = await self._service.retrieve(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            token_budget=token_budget,
            timeout_seconds=timeout,
        )

        return self._to_unified(result, query)

    def _to_unified(self, result: "RetrievalResult", query: str) -> UnifiedRetrievalResult:
        chunks = []
        for hit in result.fused_hits:
            chunks.append(
                {
                    "chunk_id": hit.chunk_id,
                    "content": getattr(hit, "content", ""),
                    "file_path": getattr(hit, "file_path", ""),
                    "score": hit.priority_score,
                }
            )

        return UnifiedRetrievalResult(
            query=query,
            chunks=chunks,
            total_results=len(result.fused_hits),
            intent=result.intent_kind,
            confidence=result.intent_result.intent.confidence,
            metadata=result.metadata,
            _raw_result=result,
        )


# ============================================================
# V3 Retriever (Orchestrator-based)
# ============================================================


@retriever_registry.register(
    "v3",
    description="Latest retriever with intent-aware fusion",
    features=[
        "intent_classification",
        "query_expansion",
        "consensus_scoring",
        "rrf_normalization",
        "l1_l2_caching",
        "cross_encoder_reranking",
    ],
)
class V3OrchestratorWrapper:
    """Wrapper for RetrieverV3Orchestrator with full integration."""

    def __init__(self, container: Any, config: "RetrieverConfig"):
        self._container = container
        self._config = config
        self._orchestrator = self._create_orchestrator()
        self._scope_selector = self._create_scope_selector()

    def _create_orchestrator(self) -> Any:
        from codegraph_search.infrastructure.v3.config import CrossEncoderConfig, RetrieverV3Config
        from codegraph_search.infrastructure.v3.orchestrator import RetrieverV3Orchestrator

        v3_config = RetrieverV3Config(
            enable_cache=self._config.enable_cache,
            cache_ttl=self._config.cache_ttl,
            enable_query_expansion=self._config.enable_query_expansion,
            cross_encoder=CrossEncoderConfig(
                enabled=True,
                final_k=15,
                min_query_length=20,
            ),
        )

        cross_encoder = self._create_cross_encoder()
        weight_learner = self._create_weight_learner()
        strategy_router = self._create_strategy_router()

        return RetrieverV3Orchestrator(
            symbol_index=getattr(self._container, "symbol_index", None),
            vector_index=getattr(self._container, "vector_index", None),
            lexical_index=getattr(self._container, "lexical_index", None),
            graph_index=getattr(self._container, "graph_index", None),
            v3_config=v3_config,
            enable_async=True,
            cross_encoder=cross_encoder,
            strategy_router=strategy_router,
            weight_learner=weight_learner,
            enable_routing=True,
        )

    def _create_cross_encoder(self) -> Any:
        try:
            from codegraph_search.infrastructure.hybrid.cross_encoder_reranker import CrossEncoderReranker

            return CrossEncoderReranker(
                model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
                device="cpu",
                batch_size=10,
            )
        except ImportError:
            logger.warning("Cross-encoder dependencies not available")
            return None

    def _create_scope_selector(self) -> Any:
        try:
            from codegraph_search.infrastructure.scope.selector import ScopeSelector

            repomap_port = getattr(self._container, "repomap_port", None)
            if repomap_port:
                return ScopeSelector(repomap_port=repomap_port)
        except Exception as e:
            logger.warning(f"Scope selector creation failed: {e}")
        return None

    def _create_weight_learner(self) -> Any:
        try:
            from codegraph_search.infrastructure.adaptive.weight_learner import AdaptiveWeightLearner

            return AdaptiveWeightLearner()
        except Exception as e:
            logger.warning(f"Weight learner creation failed: {e}")
        return None

    def _create_strategy_router(self) -> Any:
        try:
            from codegraph_search.infrastructure.routing.strategy_router import StrategyRouter

            return StrategyRouter()
        except Exception as e:
            logger.warning(f"Strategy router creation failed: {e}")
        return None

    async def retrieve(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        **kwargs: Any,
    ) -> UnifiedRetrievalResult:
        # Scope selection
        scope = None
        if self._scope_selector:
            try:
                from codegraph_search.infrastructure.intent.models import QueryIntent

                intent = QueryIntent(query=query, intent_kind="symbol")
                scope = self._scope_selector.select_scope(repo_id, snapshot_id, intent)
                logger.debug("scope_selected", scope_type=scope.scope_type)
            except Exception as e:
                logger.warning(f"Scope selection failed: {e}")

        result = await self._orchestrator.retrieve(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=self._config.max_results,
            scope=scope,
        )

        return self._to_unified(result, query)

    def _to_unified(self, result: Any, query: str) -> UnifiedRetrievalResult:
        chunks = []

        fused_results = result.get("fused_results", [])
        intent_prob = result.get("intent_prob")

        for fused_result in fused_results:
            chunks.append(
                {
                    "chunk_id": fused_result.chunk_id,
                    "content": getattr(fused_result, "content", ""),
                    "file_path": getattr(fused_result, "file_path", ""),
                    "score": fused_result.final_score,
                    "consensus_strategies": fused_result.consensus_stats.num_strategies,
                    "metadata": fused_result.metadata,
                }
            )

        dominant_intent = intent_prob.dominant_intent() if intent_prob else "balanced"
        confidence = max(intent_prob.to_dict().values()) if intent_prob else 0.5

        return UnifiedRetrievalResult(
            query=query,
            chunks=chunks,
            total_results=len(chunks),
            intent=dominant_intent,
            confidence=confidence,
            metadata={
                "type": "v3_orchestrator",
                "cross_encoder_used": result.get("metadata", {}).get("cross_encoder_used", False),
                "routing_used": result.get("metadata", {}).get("routing_used", False),
            },
            _raw_result=result,
        )

    def record_feedback(self, feedback: Any) -> None:
        """Record user feedback for adaptive weight learning."""
        if hasattr(self._orchestrator, "record_feedback"):
            self._orchestrator.record_feedback(feedback)


# ============================================================
# Multi-Hop Retriever
# ============================================================


@retriever_registry.register(
    "multi_hop",
    description="Multi-hop retriever following code relationships",
    features=["hop_traversal", "relationship_following", "context_accumulation"],
)
class MultiHopRetrieverWrapper:
    """Wrapper for MultiHopRetriever with query decomposition."""

    def __init__(self, container: Any, config: "RetrieverConfig"):
        self._container = container
        self._config = config
        self._base_retriever = BasicRetrieverWrapper(container, config)
        self._multi_hop_retriever, self._decomposer = self._create_components()

    def _create_components(self) -> tuple[Any, Any]:
        from codegraph_search.infrastructure.query.decomposer import QueryDecomposer
        from codegraph_search.infrastructure.query.multi_hop import MultiHopRetriever

        decomposer = QueryDecomposer(llm_client=self._container.llm_port)
        multi_hop_retriever = MultiHopRetriever(retriever_service=self._base_retriever)

        return multi_hop_retriever, decomposer

    async def retrieve(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        **kwargs: Any,
    ) -> UnifiedRetrievalResult:
        decomposed = await self._decomposer.decompose(query)

        if decomposed.is_multi_hop() and len(decomposed.steps) > 1:
            token_budget_per_step = kwargs.get(
                "token_budget_per_step",
                self._config.token_budget // len(decomposed.steps),
            )

            result = await self._multi_hop_retriever.retrieve_multi_hop(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                decomposed=decomposed,
                token_budget_per_step=token_budget_per_step,
            )

            return self._to_unified_multi_hop(result, query)
        else:
            result = await self._base_retriever.retrieve(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query=query,
                token_budget=kwargs.get("token_budget", self._config.token_budget),
            )
            return result

    def _to_unified_multi_hop(self, result: Any, query: str) -> UnifiedRetrievalResult:
        chunks = []

        for chunk_dict in result.final_chunks:
            chunks.append(
                {
                    "chunk_id": chunk_dict.get("chunk_id", ""),
                    "content": chunk_dict.get("content", ""),
                    "file_path": chunk_dict.get("file_path", ""),
                    "score": chunk_dict.get("score", 0.0),
                    "metadata": chunk_dict.get("metadata", {}),
                }
            )

        return UnifiedRetrievalResult(
            query=query,
            chunks=chunks,
            total_results=len(chunks),
            intent=result.decomposed_query.query_type.value,
            confidence=1.0,
            metadata={
                "type": "multi_hop",
                "num_steps": len(result.step_results),
                "reasoning": result.reasoning_chain,
                "query_type": result.decomposed_query.query_type.value,
            },
            _raw_result=result,
        )


# ============================================================
# Reasoning Retriever
# ============================================================


@retriever_registry.register(
    "reasoning",
    description="Reasoning retriever with test-time compute",
    features=["self_verification", "iterative_refinement", "confidence_estimation"],
)
class ReasoningRetrieverWrapper:
    """Wrapper for ReasoningRetriever."""

    def __init__(self, container: Any, config: "RetrieverConfig"):
        self._container = container
        self._config = config
        self._retriever = self._create_retriever()

    def _create_retriever(self) -> Any:
        from codegraph_search.infrastructure.reasoning.test_time_compute import ReasoningRetriever

        return ReasoningRetriever()

    async def retrieve(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        **kwargs: Any,
    ) -> UnifiedRetrievalResult:
        reasoning_budget = kwargs.get("reasoning_budget", self._config.reasoning_budget)

        result = await self._retriever.retrieve(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            reasoning_budget=reasoning_budget,
        )

        return self._to_unified(result, query)

    def _to_unified(self, result: Any, query: str) -> UnifiedRetrievalResult:
        chunks = []
        if hasattr(result, "chunks"):
            for chunk in result.chunks:
                chunks.append(
                    {
                        "chunk_id": getattr(chunk, "chunk_id", ""),
                        "content": getattr(chunk, "content", ""),
                        "file_path": getattr(chunk, "file_path", ""),
                        "verified": getattr(chunk, "verified", False),
                    }
                )

        return UnifiedRetrievalResult(
            query=query,
            chunks=chunks,
            total_results=len(chunks),
            confidence=getattr(result, "confidence", 0.0),
            metadata={
                "type": "reasoning",
                "iterations": getattr(result, "iterations", 0),
                "reasoning_trace": getattr(result, "reasoning_trace", []),
            },
            _raw_result=result,
        )
