"""
Retriever Service

End-to-end retrieval pipeline coordinating all retriever components.
"""

import asyncio
import time
from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.context_builder import ContextBuilder
from src.contexts.retrieval_search.infrastructure.exceptions import QueryValidationError, RetrievalTimeoutError
from src.contexts.retrieval_search.infrastructure.fusion import FusionEngine
from src.contexts.retrieval_search.infrastructure.intent import IntentAnalyzer
from src.contexts.retrieval_search.infrastructure.models import RetrievalResult
from src.contexts.retrieval_search.infrastructure.multi_index import MultiIndexOrchestrator
from src.contexts.retrieval_search.infrastructure.scope import ScopeSelector
from src.infra.observability import record_counter, record_histogram

if TYPE_CHECKING:
    from src.ports import RepoMapPort
from src.common.observability import get_logger

logger = get_logger(__name__)


class RetrieverService:
    """
    Retriever service coordinating the complete retrieval pipeline.

    Pipeline:
    1. Intent Analysis (LLM → Rule fallback)
    2. Scope Selection (RepoMap-based)
    3. Multi-index Search (parallel)
    4. Fusion (weighted scoring + dedup)
    5. Context Building (token packing + trimming)
    """

    def __init__(
        self,
        # Intent
        intent_analyzer: IntentAnalyzer,
        # Scope
        scope_selector: ScopeSelector,
        # Multi-index
        orchestrator: MultiIndexOrchestrator,
        # Fusion
        fusion_engine: FusionEngine,
        # Context
        context_builder: ContextBuilder,
        # RepoMap
        repomap_port: "RepoMapPort",
    ):
        """
        Initialize retriever service.

        Args:
            intent_analyzer: Intent analysis service
            scope_selector: Scope selection service
            orchestrator: Multi-index orchestrator
            fusion_engine: Fusion engine
            context_builder: Context builder
            repomap_port: RepoMap query port
        """
        self.intent_analyzer = intent_analyzer
        self.scope_selector = scope_selector
        self.orchestrator = orchestrator
        self.fusion_engine = fusion_engine
        self.context_builder = context_builder
        self.repomap_port = repomap_port

    async def retrieve(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        token_budget: int = 4000,
        llm_requested_indices: list[str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> RetrievalResult:
        """
        Execute end-to-end retrieval pipeline with validation and timeout.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: User query
            token_budget: Token budget for context
            llm_requested_indices: Explicitly requested indexes by LLM
            timeout_seconds: Maximum time for retrieval (default: 30s)

        Returns:
            RetrievalResult with complete retrieval data

        Raises:
            QueryValidationError: If input validation fails
            RetrievalTimeoutError: If retrieval exceeds timeout
        """
        # Input validation
        self._validate_inputs(repo_id, snapshot_id, query, token_budget)

        # Execute with timeout
        try:
            return await asyncio.wait_for(
                self._retrieve_internal(repo_id, snapshot_id, query, token_budget, llm_requested_indices),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as e:
            logger.error(f"Retrieval timeout after {timeout_seconds}s for query: {query[:50]}")
            raise RetrievalTimeoutError(query, timeout_seconds) from e

    def _validate_inputs(self, repo_id: str, snapshot_id: str, query: str, token_budget: int):
        """
        Validate retrieval inputs.

        Raises:
            QueryValidationError: If validation fails
        """
        # Validate query
        if not query or not query.strip():
            raise QueryValidationError("Query cannot be empty", query)

        if len(query) > 1000:
            raise QueryValidationError(f"Query too long: {len(query)} chars (max: 1000)", query)

        # Validate repo_id
        if not repo_id or not repo_id.strip():
            raise QueryValidationError("repo_id cannot be empty")

        # Validate snapshot_id
        if not snapshot_id or not snapshot_id.strip():
            raise QueryValidationError("snapshot_id cannot be empty")

        # Validate token_budget
        if token_budget < 100:
            raise QueryValidationError(f"token_budget too small: {token_budget} (min: 100)")

        if token_budget > 100000:
            raise QueryValidationError(f"token_budget too large: {token_budget} (max: 100000)")

    async def _retrieve_internal(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        token_budget: int,
        llm_requested_indices: list[str] | None,
    ) -> RetrievalResult:
        """Internal retrieval implementation (called with timeout wrapper)."""
        start_time = time.time()

        logger.info(f"Starting retrieval: repo={repo_id}, snapshot={snapshot_id}, query='{query}'")

        # Metrics: Total retrievals
        record_counter("retrieval_started_total", labels={"repo_id": repo_id})

        # Step 0: Snapshot validation (optional - can be disabled for performance)
        # Note: Validation is minimal to avoid extra latency
        # Full validation (checking all indexes) can be added if needed
        logger.debug("Step 0: Snapshot validation")
        try:
            # Validate RepoMap snapshot exists (lightweight check)
            repomap_snapshot = self.repomap_port.get_snapshot(repo_id, snapshot_id)
            if repomap_snapshot is None:
                logger.warning(f"RepoMap not found for {repo_id}:{snapshot_id}, will use full-repo scope")
        except Exception as e:
            logger.warning(f"RepoMap validation warning: {e}")
            # Continue without RepoMap (graceful degradation)

        # Step 1: Intent Analysis (LLM → Rule fallback)
        logger.debug("Step 1: Intent analysis")
        intent_result = await self.intent_analyzer.analyze_intent(query)
        intent = intent_result.intent

        logger.info(f"Intent: {intent.kind.value} (method={intent_result.method}, confidence={intent.confidence:.2f})")

        # Metrics: Intent
        record_counter(
            "retrieval_intent_total",
            labels={"intent": intent.kind.value, "method": intent_result.method},
        )
        record_histogram("retrieval_intent_confidence", intent.confidence)

        # Step 2: Scope Selection (RepoMap + freshness check)
        logger.debug("Step 2: Scope selection")
        scope = self.scope_selector.select_scope(repo_id, snapshot_id, intent)

        logger.info(f"Scope: {scope.scope_type} (nodes={scope.node_count}, chunks={scope.chunk_count})")

        # Metrics: Scope
        record_counter("retrieval_scope_total", labels={"scope_type": scope.scope_type})
        record_histogram("retrieval_scope_nodes", scope.node_count)
        record_histogram("retrieval_scope_chunks", scope.chunk_count)

        # Step 3: Multi-index Search (parallel)
        logger.debug("Step 3: Multi-index search")
        multi_result = await self.orchestrator.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            intent=intent,
            scope=scope,
            llm_requested_indices=llm_requested_indices,
            limit=50,
        )

        logger.info(
            f"Multi-index results: "
            f"lexical={len(multi_result.lexical_hits)}, "
            f"vector={len(multi_result.vector_hits)}, "
            f"symbol={len(multi_result.symbol_hits)}, "
            f"graph={len(multi_result.graph_hits)}"
        )

        # Step 4: Fusion + PriorityScore + Dedup
        logger.debug("Step 4: Fusion")

        # Get RepoMap importance scores for fusion
        repomap_importance = self._get_repomap_importance(repo_id, snapshot_id, scope)

        fused_hits = self.fusion_engine.fuse(
            multi_result=multi_result,
            intent=intent,
            repomap_importance=repomap_importance,
        )

        logger.info(f"Fusion: {len(fused_hits)} unique chunks (after dedup)")

        # Metrics: Fusion
        record_histogram("retrieval_fusion_results", len(fused_hits))

        # Step 5: Context Building
        logger.debug("Step 5: Context building")
        context = await self.context_builder.build(
            fused_hits=fused_hits,
            token_budget=token_budget,
        )

        logger.info(
            f"Context: {context.chunk_count} chunks, "
            f"{context.total_tokens}/{token_budget} tokens "
            f"({context.token_utilization:.1%})"
        )

        # Metrics: Context
        record_histogram("retrieval_context_chunks", context.chunk_count)
        record_histogram("retrieval_context_tokens", context.total_tokens)
        record_histogram("retrieval_token_utilization", context.token_utilization)

        # Build result
        elapsed_ms = (time.time() - start_time) * 1000

        # Metrics: Latency
        record_histogram("retrieval_latency_ms", elapsed_ms)
        record_counter("retrieval_completed_total", labels={"repo_id": repo_id})

        result = RetrievalResult(
            query=query,
            intent_result=intent_result,
            scope_result=scope,
            fused_hits=fused_hits,
            context=context,
            metadata={
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
                "latency_ms": elapsed_ms,
                "multi_index_hits": multi_result.total_hits,
                "fused_hits": len(fused_hits),
                "context_chunks": context.chunk_count,
                "token_budget": token_budget,
                "token_utilization": context.token_utilization,
            },
        )

        logger.info(
            f"Retrieval complete: {elapsed_ms:.0f}ms, {context.chunk_count} chunks, {context.total_tokens} tokens"
        )

        return result

    def _get_repomap_importance(self, repo_id: str, snapshot_id: str, scope) -> dict[str, float]:
        """
        Get RepoMap importance scores for chunks.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            scope: Scope result

        Returns:
            Dict mapping chunk_id → importance (0-1)
        """
        importance_map = {}

        # If no focused scope, return empty
        if not scope or not scope.is_focused:
            return importance_map

        # Get importance from focus nodes
        for node in scope.focus_nodes:
            importance = node.metrics.importance

            # Map to all associated chunks
            for chunk_id in node.chunk_ids:
                # Use max importance if chunk appears in multiple nodes
                if chunk_id in importance_map:
                    importance_map[chunk_id] = max(importance_map[chunk_id], importance)
                else:
                    importance_map[chunk_id] = importance

        return importance_map
