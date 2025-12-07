"""
V3 Async Orchestrator

Orchestrates async parallel strategy searches and V3 fusion.

Performance:
    - Sequential: ~9ms (symbol 2ms + vector 3ms + lexical 2ms + graph 2ms)
    - Async parallel: ~3ms (max of all)
    - Savings: ~6ms (-67%)

Integration (P1):
    - Strategy Router: Intent-based path selection with early stopping
    - Cost-Aware Graph Expander: Dijkstra-based flow expansion
    - Adaptive Weight Learner: Feedback-based weight optimization
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any, Literal

from src.contexts.multi_index.infrastructure.common.documents import SearchHit
from src.infra.observability import get_logger, record_counter, record_histogram

from .config import RetrieverV3Config
from .models import FusedResultV3, IntentProbability, RankedHit
from .service import RetrieverV3Service

if TYPE_CHECKING:
    # SOTA 2024
    from src.contexts.retrieval_search.infrastructure.adaptive.self_rag import SelfRAGRetriever
    from src.contexts.retrieval_search.infrastructure.adaptive.weight_learner import AdaptiveWeightLearner
    from src.contexts.retrieval_search.infrastructure.context_builder.compressor import BatchCompressor
    from src.contexts.retrieval_search.infrastructure.context_builder.position_bias import PositionBiasReorderer
    from src.contexts.retrieval_search.infrastructure.graph.cost_aware_expander import CostAwareGraphExpander
    from src.contexts.retrieval_search.infrastructure.query.hyde import HyDEQueryProcessor
    from src.contexts.retrieval_search.infrastructure.query.multi_query import MultiQueryRetriever
    from src.contexts.retrieval_search.infrastructure.routing.strategy_router import StrategyRouter

# Valid source types for SearchHit
SourceType = Literal["lexical", "vector", "symbol", "fuzzy", "domain", "runtime"]

logger = get_logger(__name__)


class RetrieverV3Orchestrator:
    """
    Orchestrator for async strategy search + V3 fusion.

    Responsibilities:
    1. Execute 4 strategy searches in parallel (async)
    2. Call V3 fusion engine
    3. Return ranked results

    Enhanced with (P1 Integration):
    - Strategy Router: Intent-based path selection
    - Graph Expander: Cost-aware flow expansion
    - Weight Learner: Adaptive weight optimization

    NOT responsible for:
    - Index implementation (delegated to adapters)
    - Fusion logic (delegated to V3)
    - Context building (handled by caller)
    """

    def __init__(
        self,
        symbol_index: Any | None = None,
        vector_index: Any | None = None,
        lexical_index: Any | None = None,
        graph_index: Any | None = None,
        v3_config: RetrieverV3Config | None = None,
        enable_async: bool = True,
        # P1 Integration: New optional components
        strategy_router: "StrategyRouter | None" = None,
        graph_expander: "CostAwareGraphExpander | None" = None,
        weight_learner: "AdaptiveWeightLearner | None" = None,
        enable_routing: bool = True,
        # P2: Cross-encoder reranker (optional)
        cross_encoder: Any | None = None,
        # ML Logging (optional)
        search_logger: Any | None = None,
        # SOTA 2024: Pre/Post-retrieval enhancements
        hyde_processor: "HyDEQueryProcessor | None" = None,
        self_rag_retriever: "SelfRAGRetriever | None" = None,
        multi_query_retriever: "MultiQueryRetriever | None" = None,
        batch_compressor: "BatchCompressor | None" = None,
        position_reorderer: "PositionBiasReorderer | None" = None,
    ):
        """
        Initialize V3 orchestrator.

        Args:
            symbol_index: Symbol search adapter (must have async search() method)
            vector_index: Vector search adapter (must have async search() method)
            lexical_index: Lexical search adapter (must have async search() method)
            graph_index: Graph search adapter (optional, rarely used for text queries)
            v3_config: V3 configuration
            enable_async: Enable async parallel search (default: True for performance)
            strategy_router: Optional StrategyRouter for intent-based routing
            graph_expander: Optional CostAwareGraphExpander for flow queries
            weight_learner: Optional AdaptiveWeightLearner for feedback-based optimization
            enable_routing: Enable strategy routing (default: True)
        """
        self.symbol_index = symbol_index
        self.vector_index = vector_index
        self.lexical_index = lexical_index
        self.graph_index = graph_index

        # V3 fusion service
        self.v3_service = RetrieverV3Service(config=v3_config)

        # Performance optimization flag
        self.enable_async = enable_async

        # P1 Integration: New components
        self.strategy_router = strategy_router
        self.graph_expander = graph_expander
        self.weight_learner = weight_learner
        self.enable_routing = enable_routing and strategy_router is not None

        # P2: Cross-encoder reranker
        self.cross_encoder = cross_encoder

        # ML Logging
        self.search_logger = search_logger

        # SOTA 2024: Pre/Post-retrieval enhancements
        self.hyde_processor = hyde_processor
        self.self_rag = self_rag_retriever
        self.multi_query = multi_query_retriever
        self.compressor = batch_compressor
        self.position_reorderer = position_reorderer

        logger.info(
            "orchestrator_initialized",
            async_enabled=enable_async,
            has_symbol_index=symbol_index is not None,
            has_vector_index=vector_index is not None,
            has_lexical_index=lexical_index is not None,
            has_graph_index=graph_index is not None,
            has_strategy_router=strategy_router is not None,
            has_graph_expander=graph_expander is not None,
            has_weight_learner=weight_learner is not None,
            routing_enabled=self.enable_routing,
            has_search_logger=search_logger is not None,
        )

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 40,
        symbol_limit: int = 20,
        enable_cache: bool = True,
    ) -> tuple[list[FusedResultV3], IntentProbability, dict[str, float], dict[str, list[SearchHit]]]:
        """
        Execute async search + V3 fusion.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            query: Search query string
            limit: Max results to return (after fusion)
            symbol_limit: Max results from symbol index (typically smaller, as symbols are precise)
            enable_cache: Enable V3 L1 cache

        Returns:
            Tuple of:
                - fused_results: List of FusedResultV3 (ranked)
                - intent: IntentProbability (detected query intent)
                - metrics: Performance metrics dict

        Performance:
            - With async (enable_async=True): ~3-4ms search + ~1ms fusion = ~4-5ms total
            - Without async (enable_async=False): ~9ms search + ~1ms fusion = ~10ms total
            - With routing: -30% for symbol/concept queries (early stopping)
            - Savings: ~5-6ms (-60%)
        """
        start_time = time.perf_counter()

        # ============================================================
        # SOTA Step 0.1: Self-RAG - 검색 필요성 판단
        # ============================================================
        if self.self_rag:
            should_retrieve = await self.self_rag.should_retrieve_for_query(query)
            if not should_retrieve:
                # Skip retrieval, return empty results
                logger.info("self_rag_skipped_retrieval", query=query[:50])
                return [], IntentProbability({}, "general"), {"self_rag_skipped": True}, {}

        # ============================================================
        # SOTA Step 0.2: Query Enhancement (HyDE, RAG-Fusion)
        # ============================================================
        query_variations = [query]  # Start with original
        hyde_used = False
        rag_fusion_used = False

        # HyDE: Hypothetical document generation
        if self.hyde_processor:
            hyde_result = await self.hyde_processor.process_query(
                query,
                query_complexity=0.7,  # TODO: Get from intent classifier
            )
            if hyde_result["use_hyde"]:
                hyde_used = True
                logger.info("hyde_applied", num_embeddings=len(hyde_result["embeddings"]))

        # RAG-Fusion: Multi-query generation
        if self.multi_query:
            expanded = await self.multi_query.expand_query(query)
            if len(expanded["queries"]) > 1:
                query_variations = expanded["queries"]
                rag_fusion_used = True
                logger.info("rag_fusion_applied", num_queries=len(query_variations))

        # ============================================================
        # Step 0: Early intent classification for routing
        # ============================================================
        intent_prob = self.v3_service.classifier.classify(query)
        dominant_intent = intent_prob.dominant_intent()

        # ============================================================
        # Step 1: Strategy searches (with optional routing)
        # ============================================================
        if self.enable_routing and self.strategy_router:
            hits_by_strategy, search_metrics = await self._search_with_routing(
                repo_id, snapshot_id, query, intent_prob, limit=limit, symbol_limit=symbol_limit
            )
        elif self.enable_async:
            hits_by_strategy, search_metrics = await self._search_parallel(
                repo_id, snapshot_id, query, limit=limit, symbol_limit=symbol_limit
            )
        else:
            hits_by_strategy, search_metrics = await self._search_sequential(
                repo_id, snapshot_id, query, limit=limit, symbol_limit=symbol_limit
            )

        # ============================================================
        # Step 1.5: Graph expansion for flow queries
        # ============================================================
        if dominant_intent == "flow" and self.graph_expander:
            graph_hits = await self._expand_graph_for_flow(repo_id, snapshot_id, query, hits_by_strategy, intent_prob)
            if graph_hits:
                hits_by_strategy["graph"] = graph_hits
                search_metrics["graph_expansion_count"] = len(graph_hits)

        # ============================================================
        # Step 2: V3 Fusion
        # ============================================================
        fusion_start = time.perf_counter()
        fused_results, intent = self.v3_service.retrieve(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            hits_by_strategy=hits_by_strategy,
            enable_cache=enable_cache,
        )
        fusion_time = (time.perf_counter() - fusion_start) * 1000  # ms

        # ============================================================
        # Step 2.5: Conditional Cross-Encoder Reranking (optional)
        # ============================================================
        cross_encoder_time = 0.0
        cross_encoder_used = False

        if self._should_use_cross_encoder(query, intent_prob):
            cross_encoder_start = time.perf_counter()
            fused_results = await self._apply_cross_encoder_reranking(query, fused_results, intent_prob)
            cross_encoder_time = (time.perf_counter() - cross_encoder_start) * 1000
            cross_encoder_used = True
            logger.info(
                "cross_encoder_applied",
                results_before=len(fused_results),
                target_k=self.v3_service.config.cross_encoder.final_k,
                latency_ms=cross_encoder_time,
            )

        # ============================================================
        # Step 3: Apply top-K limit
        # ============================================================
        fused_results = fused_results[:limit]

        # ============================================================
        # SOTA Step 3.5: Post-Retrieval Enhancements
        # ============================================================
        # Position Bias Mitigation (Lost-in-Middle)
        if self.position_reorderer and len(fused_results) >= 5:
            from src.contexts.retrieval_search.infrastructure.context_builder.position_bias import RankedChunk

            # Convert to RankedChunk
            chunks = [
                RankedChunk(
                    chunk_id=str(i),
                    content=result.chunk.content,
                    score=result.score,
                    original_rank=i,
                    metadata={"result": result},
                )
                for i, result in enumerate(fused_results)
            ]

            # Reorder
            reordered_chunks = self.position_reorderer.reorder(chunks)

            # Convert back
            fused_results = [chunk.metadata["result"] for chunk in reordered_chunks]

            logger.info("position_bias_mitigated", num_chunks=len(fused_results))

        # ============================================================
        # Step 4: Collect metrics
        # ============================================================
        total_time = (time.perf_counter() - start_time) * 1000  # ms

        metrics = {
            "total_ms": total_time,
            "search_ms": search_metrics["total_ms"],
            "fusion_ms": fusion_time,
            "cross_encoder_ms": cross_encoder_time,
            "cross_encoder_used": cross_encoder_used,
            "async_enabled": self.enable_async,
            "routing_enabled": self.enable_routing,
            "result_count": len(fused_results),
            "intent": dominant_intent,
            "early_stopped": search_metrics.get("early_stopped", False),
            # SOTA 2024 metrics
            "hyde_used": hyde_used,
            "rag_fusion_used": rag_fusion_used,
            "num_query_variations": len(query_variations),
            "position_bias_mitigated": self.position_reorderer is not None and len(fused_results) >= 5,
            **search_metrics,  # Include per-strategy timings
        }

        logger.info(
            "search_complete",
            query_preview=query[:50],
            results_count=len(fused_results),
            total_ms=total_time,
            search_ms=search_metrics["total_ms"],
            fusion_ms=fusion_time,
            async_enabled=self.enable_async,
            routing_enabled=self.enable_routing,
            intent=dominant_intent,
            early_stopped=search_metrics.get("early_stopped", False),
        )

        # Record metrics
        record_histogram("retriever_orchestrator_total_duration_ms", total_time)
        record_histogram("retriever_orchestrator_search_duration_ms", search_metrics["total_ms"])
        record_histogram("retriever_orchestrator_fusion_duration_ms", fusion_time)
        record_histogram("retriever_orchestrator_results_count", len(fused_results))

        # ML Logging (non-blocking)
        if self.search_logger:
            try:
                # Prepare results for logging
                results_for_logging = [
                    {
                        "chunk_id": result.chunk_id,
                        "score": result.score,
                        "rank": idx + 1,
                    }
                    for idx, result in enumerate(fused_results[:20])  # Top 20만 로깅
                ]

                # Get total candidates from hits_by_strategy
                total_candidates = sum(len(hits) for hits in hits_by_strategy.values())

                # Log search (non-blocking)
                await self.search_logger.log_search(
                    query=query,
                    repo_id=repo_id,
                    intent=dominant_intent,
                    results=results_for_logging,
                    candidates=None,  # 너무 많아서 생략
                    late_interaction_scores=None,  # TODO: Late Interaction 적용 시 추가
                    fusion_strategy="rrf_v3",
                    user_id=None,  # TODO: 사용자 정보 전달 방법 결정
                    session_id=None,
                    candidate_count=total_candidates,
                    async_enabled=self.enable_async,
                    routing_enabled=self.enable_routing,
                    early_stopped=search_metrics.get("early_stopped", False),
                    cross_encoder_used=cross_encoder_used,
                )
            except Exception as e:
                # 로깅 실패해도 검색은 성공
                logger.warning(f"Failed to log search: {e}")

        return fused_results, intent, metrics, hits_by_strategy

    def _should_use_cross_encoder(
        self,
        query: str,
        intent_prob: IntentProbability,
    ) -> bool:
        """
        Determine if cross-encoder reranking should be applied.

        Criteria:
        1. Cross-encoder enabled in config
        2. Cross-encoder component available
        3. Query complexity triggers it:
           - Query length > threshold
           - Intent in trigger list (flow, concept)
           - Complex query patterns (why/how/explain)

        Args:
            query: User query
            intent_prob: Intent probabilities

        Returns:
            True if cross-encoder should be applied
        """
        config = self.v3_service.config.cross_encoder

        # Must be enabled and available
        if not config.enabled or not self.cross_encoder:
            return False

        # Check query length
        if len(query) < config.min_query_length:
            return False

        # Check intent triggers
        dominant_intent = intent_prob.dominant_intent()
        if dominant_intent in config.intent_triggers:
            logger.debug("cross_encoder_triggered_by_intent", intent=dominant_intent)
            return True

        # Check for complex query patterns
        complex_keywords = ["why", "how", "explain", "debug", "refactor", "trace"]
        query_lower = query.lower()
        if any(keyword in query_lower for keyword in complex_keywords):
            logger.debug("cross_encoder_triggered_by_keyword", query=query[:50])
            return True

        return False

    async def _apply_cross_encoder_reranking(
        self,
        query: str,
        fused_results: list[FusedResultV3],
        intent_prob: IntentProbability,
    ) -> list[FusedResultV3]:
        """
        Apply cross-encoder reranking to fused results.

        Reduces top ~40 results to final 12-20 using cross-encoder.

        Args:
            query: User query
            fused_results: Fused results from V3 fusion
            intent_prob: Intent probabilities

        Returns:
            Reranked and filtered results (12-20 items)
        """
        target_k = self.v3_service.config.cross_encoder.final_k

        # Convert to format expected by cross-encoder
        candidates = []
        for result in fused_results:
            candidates.append(
                {
                    "chunk_id": result.chunk_id,
                    "file_path": result.file_path,
                    "content": result.metadata.get("content", ""),
                    "score": result.final_score,
                    "metadata": result.metadata,
                }
            )

        # Apply cross-encoder reranking
        if self.cross_encoder is None:
            return fused_results[:target_k]

        try:
            reranked_candidates = await self.cross_encoder.rerank(
                query=query,
                candidates=candidates,
                top_k=target_k,
            )

            # Convert back to FusedResultV3
            reranked_results = []
            for candidate in reranked_candidates:
                # Find original result
                for result in fused_results:
                    if result.chunk_id == candidate["chunk_id"]:
                        # Update with cross-encoder score
                        ce_score = candidate.get("cross_encoder_score", result.final_score)
                        result.metadata["cross_encoder_score"] = ce_score
                        reranked_results.append(result)
                        break

            logger.info(
                "cross_encoder_rerank_complete",
                before_count=len(fused_results),
                after_count=len(reranked_results),
                target_k=target_k,
            )

            return reranked_results

        except Exception as e:
            logger.error(f"Cross-encoder reranking failed: {e}", exc_info=True)
            # Fallback: return original top-k
            return fused_results[:target_k]

    async def _search_with_routing(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        intent_prob: IntentProbability,
        limit: int,
        symbol_limit: int,
    ) -> tuple[dict[str, list[SearchHit]], dict[str, float]]:
        """
        Execute searches using StrategyRouter for intent-based path selection.

        Benefits:
        - Early stopping: Skip fallback strategies if primary has enough results
        - Intent-aware: Different strategies for different query types
        - Latency savings: ~30% for symbol/concept queries
        """
        from src.contexts.retrieval_search.infrastructure.routing.strategy_router import StrategyType

        start = time.perf_counter()

        # Build strategy executors
        async def vector_executor(q: str, **kwargs) -> list[RankedHit]:
            hits = await self._search_vector(repo_id, snapshot_id, q, limit)
            return self._to_ranked_hits(hits, "vector")

        async def lexical_executor(q: str, **kwargs) -> list[RankedHit]:
            hits = await self._search_lexical(repo_id, snapshot_id, q, limit)
            return self._to_ranked_hits(hits, "lexical")

        async def symbol_executor(q: str, **kwargs) -> list[RankedHit]:
            hits = await self._search_symbol(repo_id, snapshot_id, q, symbol_limit)
            return self._to_ranked_hits(hits, "symbol")

        async def graph_executor(q: str, **kwargs) -> list[RankedHit]:
            hits = await self._search_graph(repo_id, snapshot_id, q, limit)
            return self._to_ranked_hits(hits, "graph")

        # Create temporary router with our executors
        executors = {
            StrategyType.VECTOR: vector_executor,
            StrategyType.LEXICAL: lexical_executor,
            StrategyType.SYMBOL: symbol_executor,
            StrategyType.GRAPH: graph_executor,
        }

        # Use the provided router's paths but with our executors
        from src.contexts.retrieval_search.infrastructure.routing.strategy_router import StrategyRouter

        router = StrategyRouter(
            strategy_executors=executors,
            intent_paths=self.strategy_router.intent_paths if self.strategy_router else None,
        )

        # Execute with routing
        routing_result = await router.route(query, intent_prob)

        # Convert RankedHit back to SearchHit for compatibility
        hits_by_strategy: dict[str, list[SearchHit]] = {}
        for strategy_name, ranked_hits in routing_result.hits_by_strategy.items():
            hits_by_strategy[strategy_name] = [
                SearchHit(
                    chunk_id=rh.chunk_id,
                    score=rh.raw_score,
                    file_path=rh.file_path,
                    symbol_id=rh.symbol_id,
                    source=strategy_name,
                    metadata=rh.metadata,
                )
                for rh in ranked_hits
            ]

        total_ms = (time.perf_counter() - start) * 1000

        metrics = {
            "total_ms": total_ms,
            "mode": "routed",
            "strategies_executed": routing_result.strategies_executed,
            "early_stopped": routing_result.early_stopped,
        }

        logger.debug(
            "routed_search_complete",
            strategies_executed=routing_result.strategies_executed,
            early_stopped=routing_result.early_stopped,
            total_ms=total_ms,
        )

        return hits_by_strategy, metrics

    def _to_ranked_hits(self, hits: list[SearchHit], strategy: str) -> list[RankedHit]:
        """Convert SearchHit list to RankedHit list."""
        return [
            RankedHit(
                chunk_id=hit.chunk_id,
                strategy=strategy,
                rank=rank,
                raw_score=hit.score,
                file_path=hit.file_path,
                symbol_id=hit.symbol_id,
                metadata=hit.metadata,
            )
            for rank, hit in enumerate(hits)
        ]

    async def _expand_graph_for_flow(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        hits_by_strategy: dict[str, list[SearchHit]],
        intent_prob: IntentProbability,
    ) -> list[SearchHit]:
        """
        Expand graph from symbol results for flow queries.

        Uses CostAwareGraphExpander with Dijkstra's algorithm.
        """
        if not self.graph_expander:
            return []

        try:
            # Get seed symbols from symbol/lexical results
            seed_symbol_ids = []
            for strategy in ["symbol", "lexical"]:
                for hit in hits_by_strategy.get(strategy, [])[:5]:  # Top 5 per strategy
                    if hit.symbol_id:
                        seed_symbol_ids.append(hit.symbol_id)

            if not seed_symbol_ids:
                return []

            # Expand using cost-aware algorithm
            graph_hits = await self.graph_expander.expand_flow(
                start_symbol_ids=seed_symbol_ids[:10],  # Max 10 seeds
                direction="forward",  # Callees
                intent="flow",
            )

            # Also expand backward for hub discovery
            backward_hits = await self.graph_expander.expand_flow(
                start_symbol_ids=seed_symbol_ids[:5],  # Fewer for backward
                direction="backward",  # Callers
                intent="flow",
            )

            # Combine and deduplicate
            seen = set()
            combined = []
            for hit in graph_hits + backward_hits:
                if hit.chunk_id not in seen:
                    seen.add(hit.chunk_id)
                    combined.append(hit)

            logger.debug(
                "graph_expansion_complete",
                seeds=len(seed_symbol_ids),
                forward_hits=len(graph_hits),
                backward_hits=len(backward_hits),
                combined=len(combined),
            )

            return combined[:40]  # Limit to 40

        except Exception as e:
            logger.warning("graph_expansion_error", error=str(e), exc_info=True)
            return []

    # ============================================================
    # Feedback Loop for Adaptive Weight Learning
    # ============================================================

    def record_feedback(
        self,
        query: str,
        intent: str,
        selected_chunk_ids: list[str],
        hits_by_strategy: dict[str, list[SearchHit]],
        is_positive: bool = True,
    ) -> None:
        """
        Record user feedback for adaptive weight learning.

        Call this when a user selects/clicks on results to improve future queries.

        Args:
            query: Original query string
            intent: Detected intent (symbol, flow, concept, code, balanced)
            selected_chunk_ids: Chunk IDs that user found useful
            hits_by_strategy: Original hits from each strategy
            is_positive: True if user found results helpful
        """
        if not self.weight_learner:
            return

        try:
            from src.contexts.retrieval_search.infrastructure.adaptive.weight_learner import FeedbackSignal

            # Build strategy contributions
            strategy_contributions = {}
            for strategy, hits in hits_by_strategy.items():
                strategy_contributions[strategy] = [h.chunk_id for h in hits]

            feedback = FeedbackSignal(
                query=query,
                intent=intent,
                selected_chunk_ids=selected_chunk_ids,
                strategy_contributions=strategy_contributions,
                is_positive=is_positive,
            )

            self.weight_learner.record_feedback(feedback)

            logger.debug(
                "feedback_recorded",
                query_preview=query[:30],
                intent=intent,
                selected_count=len(selected_chunk_ids),
                is_positive=is_positive,
            )

        except Exception as e:
            logger.warning("feedback_recording_error", error=str(e))

    async def _search_parallel(
        self, repo_id: str, snapshot_id: str, query: str, limit: int, symbol_limit: int
    ) -> tuple[dict[str, list[SearchHit]], dict[str, float]]:
        """
        Execute all strategy searches in parallel (async).

        This is the optimized path: ~3ms total (max of all strategies).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query
            limit: Max results per strategy
            symbol_limit: Max results for symbol strategy

        Returns:
            Tuple of (hits_by_strategy, metrics)
        """
        start = time.perf_counter()

        # Create async tasks for all available indexes
        tasks = []
        strategy_names = []

        if self.symbol_index:
            tasks.append(self._search_symbol(repo_id, snapshot_id, query, symbol_limit))
            strategy_names.append("symbol")

        if self.vector_index:
            tasks.append(self._search_vector(repo_id, snapshot_id, query, limit))
            strategy_names.append("vector")

        if self.lexical_index:
            tasks.append(self._search_lexical(repo_id, snapshot_id, query, limit))
            strategy_names.append("lexical")

        if self.graph_index:
            tasks.append(self._search_graph(repo_id, snapshot_id, query, limit))
            strategy_names.append("graph")

        # Execute all in parallel with asyncio.gather
        # return_exceptions=True: Don't fail entire search if one strategy fails
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build hits_by_strategy dict, handling exceptions
        hits_by_strategy = {}
        for strategy_name, result in zip(strategy_names, results, strict=False):
            if isinstance(result, Exception):
                logger.warning(
                    "strategy_search_failed",
                    strategy=strategy_name,
                    error=str(result),
                    exc_info=result,
                )
                record_counter(
                    "retriever_strategy_errors_total", labels={"strategy": strategy_name, "mode": "parallel"}
                )
                hits_by_strategy[strategy_name] = []
            else:
                hits_by_strategy[strategy_name] = result
                record_histogram("retriever_strategy_results_count", len(result))

        total_ms = (time.perf_counter() - start) * 1000

        metrics = {
            "total_ms": total_ms,
            "mode": "parallel",
        }

        return hits_by_strategy, metrics

    async def _search_sequential(
        self, repo_id: str, snapshot_id: str, query: str, limit: int, symbol_limit: int
    ) -> tuple[dict[str, list[SearchHit]], dict[str, float]]:
        """
        Execute strategy searches sequentially (for comparison/fallback).

        This is the slower path: ~9ms total (sum of all strategies).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query
            limit: Max results per strategy
            symbol_limit: Max results for symbol strategy

        Returns:
            Tuple of (hits_by_strategy, metrics)
        """
        start = time.perf_counter()
        hits_by_strategy = {}
        timings = {}

        # Execute sequentially, timing each
        if self.symbol_index:
            t = time.perf_counter()
            hits_by_strategy["symbol"] = await self._search_symbol(repo_id, snapshot_id, query, symbol_limit)
            duration_ms = (time.perf_counter() - t) * 1000
            timings["symbol_ms"] = duration_ms
            record_histogram("retriever_strategy_duration_ms", duration_ms)
            record_histogram("retriever_strategy_results_count", len(hits_by_strategy["symbol"]))

        if self.vector_index:
            t = time.perf_counter()
            hits_by_strategy["vector"] = await self._search_vector(repo_id, snapshot_id, query, limit)
            duration_ms = (time.perf_counter() - t) * 1000
            timings["vector_ms"] = duration_ms
            record_histogram("retriever_strategy_duration_ms", duration_ms)
            record_histogram("retriever_strategy_results_count", len(hits_by_strategy["vector"]))

        if self.lexical_index:
            t = time.perf_counter()
            hits_by_strategy["lexical"] = await self._search_lexical(repo_id, snapshot_id, query, limit)
            duration_ms = (time.perf_counter() - t) * 1000
            timings["lexical_ms"] = duration_ms
            record_histogram("retriever_strategy_duration_ms", duration_ms)
            record_histogram("retriever_strategy_results_count", len(hits_by_strategy["lexical"]))

        if self.graph_index:
            t = time.perf_counter()
            hits_by_strategy["graph"] = await self._search_graph(repo_id, snapshot_id, query, limit)
            duration_ms = (time.perf_counter() - t) * 1000
            timings["graph_ms"] = duration_ms
            record_histogram("retriever_strategy_duration_ms", duration_ms)
            record_histogram("retriever_strategy_results_count", len(hits_by_strategy["graph"]))

        total_ms = (time.perf_counter() - start) * 1000

        metrics = {
            "total_ms": total_ms,
            "mode": "sequential",
            **timings,
        }

        return hits_by_strategy, metrics

    # ============================================================
    # Individual Strategy Search Methods
    # ============================================================

    async def _search_symbol(self, repo_id: str, snapshot_id: str, query: str, limit: int) -> list[SearchHit]:
        """
        Search symbol index.

        Expected latency: ~2ms
        """
        if not self.symbol_index:
            return []

        try:
            results = await self.symbol_index.search(repo_id, snapshot_id, query, limit=limit)
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.error("symbol_search_error", error=str(e), exc_info=True)
            record_counter("retriever_strategy_errors_total", labels={"strategy": "symbol", "mode": "individual"})
            return []

    async def _search_vector(self, repo_id: str, snapshot_id: str, query: str, limit: int) -> list[SearchHit]:
        """
        Search vector index.

        Expected latency: ~3ms (slowest strategy)
        """
        if not self.vector_index:
            return []

        try:
            results = await self.vector_index.search(repo_id, snapshot_id, query, limit=limit)
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.error("vector_search_error", error=str(e), exc_info=True)
            record_counter("retriever_strategy_errors_total", labels={"strategy": "vector", "mode": "individual"})
            return []

    async def _search_lexical(self, repo_id: str, snapshot_id: str, query: str, limit: int) -> list[SearchHit]:
        """
        Search lexical index (Zoekt).

        Expected latency: ~2ms
        """
        if not self.lexical_index:
            return []

        try:
            results = await self.lexical_index.search(repo_id, snapshot_id, query, limit=limit)
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.error("lexical_search_error", error=str(e), exc_info=True)
            record_counter("retriever_strategy_errors_total", labels={"strategy": "lexical", "mode": "individual"})
            return []

    async def _search_graph(self, repo_id: str, snapshot_id: str, query: str, limit: int) -> list[SearchHit]:
        """
        Search graph index.

        Note: Graph index typically doesn't support direct text queries.
        This is a placeholder for future graph-based query expansion.

        Expected latency: ~2ms (if implemented)
        """
        if not self.graph_index:
            return []

        try:
            # Graph queries are usually triggered by symbol results, not text queries
            # This is a placeholder for potential text-to-graph query translation
            return []
        except Exception as e:
            logger.error("graph_search_error", error=str(e), exc_info=True)
            record_counter("retriever_strategy_errors_total", labels={"strategy": "graph", "mode": "individual"})
            return []

    # ============================================================
    # Utility Methods
    # ============================================================

    def get_cache_stats(self) -> dict[str, Any]:
        """Get V3 L1 cache statistics."""
        return self.v3_service.get_cache_stats()

    def clear_cache(self) -> None:
        """Clear V3 L1 cache."""
        self.v3_service.clear_cache()
