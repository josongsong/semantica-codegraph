"""
Retriever Service V3.

Main service orchestrating the complete retrieval pipeline (RFC section 10).
"""

import hashlib
import json
import time
from typing import Any

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.v3.cache import RetrieverV3Cache
from codegraph_search.infrastructure.v3.config import RetrieverV3Config
from codegraph_search.infrastructure.v3.fusion_engine import FusionEngineV3
from codegraph_search.infrastructure.v3.intent_classifier import IntentClassifierV3
from codegraph_search.infrastructure.v3.models import (
    ConsensusStats,
    FeatureVector,
    FusedResultV3,
    IntentProbability,
    RankedHit,
)
from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

logger = get_logger(__name__)


class RetrieverV3Service:
    """
    Main retriever service for v3.

    Orchestrates:
    1. Query preprocessing and intent classification
    2. Multi-strategy retrieval (delegated to caller)
    3. Fusion and ranking
    4. Optional caching
    """

    def __init__(
        self,
        config: RetrieverV3Config | None = None,
        cache_client: Any | None = None,
    ):
        """
        Initialize retriever service.

        Args:
            config: V3 configuration (uses default if None)
            cache_client: Optional cache client (Redis, etc. for L2 cache)
        """
        self.config = config or RetrieverV3Config()
        self.classifier = IntentClassifierV3()
        self.fusion_engine = FusionEngineV3(self.config)
        self.cache_client = cache_client  # L2 cache (Redis, optional)

        # L1 in-memory cache (configurable via settings)
        self.l1_cache = RetrieverV3Cache(
            query_cache_size=self.config.l1_cache_size,
            intent_cache_size=self.config.intent_cache_size,
            rrf_cache_size=self.config.intent_cache_size // 2,  # RRF cache is half of intent
            ttl=self.config.cache_ttl,
        )
        logger.info(
            "l1_cache_initialized",
            query_cache_size=self.config.l1_cache_size,
            intent_cache_size=self.config.intent_cache_size,
            ttl_seconds=self.config.cache_ttl,
            enabled=self.config.enable_cache,
        )

    def retrieve(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        hits_by_strategy: dict[str, list[SearchHit]],
        metadata_map: dict[str, dict[str, Any]] | None = None,
        enable_cache: bool = True,
    ) -> tuple[list[FusedResultV3], IntentProbability]:
        """
        Execute complete retrieval pipeline with 3-tier caching.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            query: User query string
            hits_by_strategy: Dict of strategy → list of SearchHit
                              Each SearchHit should have chunk_id, score, file_path, etc.
            metadata_map: Optional dict of chunk_id → metadata
            enable_cache: Enable cache lookup/store

        Returns:
            Tuple of (fused_results, intent_probability)

        Cache Strategy:
            Tier 1 (L1 query cache): Full results (repo + query + hits → results)
            Tier 2 (L1 intent cache): Intent classification (repo + query → intent)
            Tier 3 (L1 rrf cache): RRF scores (repo + hits → rrf_scores)
            Tier 4 (L2 Redis): Optional distributed cache
        """
        # ============================================================
        # Tier 1: Check L1 full query cache
        # ============================================================
        retrieval_start_time = time.time()

        if enable_cache and self.config.enable_cache:
            query_key = self.l1_cache.make_query_key(repo_id, snapshot_id, query)
            cached_result = self.l1_cache.query_results.get(query_key)
            if cached_result:
                logger.info("l1_cache_hit", tier="query", repo_id=repo_id, query_preview=query[:50])
                record_counter("retriever_cache_hits_total", labels={"tier": "l1_query", "repo_id": repo_id})
                retrieval_duration = time.time() - retrieval_start_time
                record_histogram("retriever_query_duration_seconds", retrieval_duration)
                return cached_result

        # ============================================================
        # Tier 2: Check L1 intent cache
        # ============================================================
        intent_prob = None
        expansions = None

        if enable_cache and self.config.enable_cache:
            intent_key = self.l1_cache.make_intent_key(repo_id, snapshot_id, query)
            cached_intent = self.l1_cache.intent_probs.get(intent_key)
            if cached_intent:
                intent_prob, expansions = cached_intent
                logger.debug("l1_cache_hit", tier="intent", repo_id=repo_id, query_preview=query[:50])
                record_counter("retriever_cache_hits_total", labels={"tier": "l1_intent", "repo_id": repo_id})

        # Compute intent if not cached
        if intent_prob is None:
            if self.config.enable_query_expansion:
                intent_prob, expansions = self.classifier.classify_with_expansion(query)
                logger.debug("query_expansions_generated", expansions=expansions)
            else:
                intent_prob = self.classifier.classify(query)

            # Store intent in L1 cache
            if enable_cache and self.config.enable_cache:
                intent_key = self.l1_cache.make_intent_key(repo_id, snapshot_id, query)
                self.l1_cache.intent_probs.set(intent_key, (intent_prob, expansions))
                record_counter("retriever_cache_misses_total", labels={"tier": "l1_intent", "repo_id": repo_id})

        dominant_intent = intent_prob.dominant_intent()
        logger.info(
            "intent_classified",
            dominant_intent=dominant_intent,
            intent_probs=intent_prob.to_dict(),
        )
        record_counter("retriever_intent_classifications_total", labels={"intent": dominant_intent, "repo_id": repo_id})

        # ============================================================
        # Step 2: Convert SearchHit to RankedHit
        # ============================================================
        ranked_hits = self._convert_to_ranked_hits(hits_by_strategy)

        # ============================================================
        # Step 3: Fusion (with expansions if enabled)
        # ============================================================
        fusion_start_time = time.time()
        fused_results = self.fusion_engine.fuse(
            hits_by_strategy=ranked_hits,
            intent_prob=intent_prob,
            metadata_map=metadata_map,
            query_expansions=expansions,  # Pass expansions for boosting
        )
        fusion_duration = time.time() - fusion_start_time
        record_histogram("retriever_fusion_duration_seconds", fusion_duration)

        # ============================================================
        # Step 4: Apply intent-based cutoff
        # ============================================================
        fused_results = self.fusion_engine.apply_cutoff(fused_results, intent_prob)

        # Calculate metrics
        avg_score = sum(r.final_score for r in fused_results) / len(fused_results) if fused_results else 0.0
        retrieval_duration = time.time() - retrieval_start_time

        logger.info(
            "retrieval_complete",
            results_count=len(fused_results),
            avg_score=avg_score,
            duration_seconds=retrieval_duration,
            repo_id=repo_id,
        )

        # Record metrics
        record_histogram("retriever_query_duration_seconds", retrieval_duration)
        record_histogram("retriever_results_count", len(fused_results))
        record_histogram("retriever_avg_score", avg_score)

        # ============================================================
        # Cache results in L1
        # ============================================================
        if enable_cache and self.config.enable_cache:
            query_key = self.l1_cache.make_query_key(repo_id, snapshot_id, query)
            self.l1_cache.query_results.set(query_key, (fused_results, intent_prob))
            logger.debug("l1_cache_stored", tier="query", repo_id=repo_id, cache_key=query_key)
            record_counter("retriever_cache_stores_total", labels={"tier": "l1_query", "repo_id": repo_id})

        # ============================================================
        # Optional: Cache in L2 (Redis)
        # ============================================================
        if enable_cache and self.config.enable_cache and self.cache_client:
            self._store_to_cache(repo_id, snapshot_id, query, hits_by_strategy, (fused_results, intent_prob))

        return fused_results, intent_prob

    def _convert_to_ranked_hits(self, hits_by_strategy: dict[str, list[SearchHit]]) -> dict[str, list[RankedHit]]:
        """
        Convert SearchHit objects to RankedHit with rank assignments.

        Args:
            hits_by_strategy: Dict of strategy → list of SearchHit

        Returns:
            Dict of strategy → list of RankedHit
        """
        ranked_hits = {}

        for strategy, hits in hits_by_strategy.items():
            ranked = []

            for rank, hit in enumerate(hits):
                ranked_hit = RankedHit(
                    chunk_id=hit.chunk_id,
                    strategy=strategy,
                    rank=rank,
                    raw_score=hit.score,
                    file_path=hit.file_path,
                    symbol_id=hit.symbol_id,
                    metadata=hit.metadata,
                )
                ranked.append(ranked_hit)

            ranked_hits[strategy] = ranked

        return ranked_hits

    def _get_cache_key(
        self, repo_id: str, snapshot_id: str, query: str, hits_by_strategy: dict[str, list[SearchHit]]
    ) -> str:
        """
        Generate cache key for query and hits.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            query: Query string
            hits_by_strategy: Dict of strategy → list of SearchHit

        Returns:
            Cache key string
        """
        # Create deterministic representation of hits
        hits_repr = {}
        for strategy, hits in hits_by_strategy.items():
            hits_repr[strategy] = [hit.chunk_id for hit in hits[:50]]  # Top 50 per strategy

        cache_input = {
            "repo_id": repo_id,
            "snapshot_id": snapshot_id,
            "query": query,
            "hits": hits_repr,
            "config_version": "v3",
        }

        cache_str = json.dumps(cache_input, sort_keys=True)
        cache_hash = hashlib.sha256(cache_str.encode()).hexdigest()

        return f"retriever:v3:{repo_id}:{cache_hash[:16]}"

    def _get_from_cache(
        self, repo_id: str, snapshot_id: str, query: str, hits_by_strategy: dict[str, list[SearchHit]]
    ) -> tuple[list[FusedResultV3], IntentProbability] | None:
        """
        Get cached result if available.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            query: Query string
            hits_by_strategy: Dict of strategy → list of SearchHit

        Returns:
            Cached result tuple or None
        """
        if not self.cache_client:
            return None

        try:
            cache_key = self._get_cache_key(repo_id, snapshot_id, query, hits_by_strategy)
            cached_data = self.cache_client.get(cache_key)

            if cached_data:
                # Deserialize from JSON
                data = json.loads(cached_data)
                results = [self._deserialize_fused_result(r) for r in data.get("results", [])]
                intent = IntentProbability(**data.get("intent", {}))
                logger.debug("l2_cache_hit", repo_id=repo_id, cache_key=cache_key)
                record_counter("retriever_cache_hits_total", labels={"tier": "l2", "repo_id": repo_id})
                return results, intent

            return None

        except Exception as e:
            logger.warning("cache_get_error", error=str(e), exc_info=True)
            record_counter("retriever_cache_errors_total", labels={"operation": "get", "tier": "l2"})
            return None

    def _store_to_cache(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        hits_by_strategy: dict[str, list[SearchHit]],
        result: tuple[list[FusedResultV3], IntentProbability],
    ):
        """
        Store result to cache.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            query: Query string
            hits_by_strategy: Dict of strategy → list of SearchHit
            result: Result tuple to cache
        """
        if not self.cache_client:
            return

        try:
            cache_key = self._get_cache_key(repo_id, snapshot_id, query, hits_by_strategy)
            fused_results, intent_prob = result

            # Serialize to JSON
            cache_data = {
                "results": [r.to_dict() for r in fused_results],
                "intent": intent_prob.to_dict(),
            }
            serialized = json.dumps(cache_data)

            self.cache_client.setex(
                cache_key,
                self.config.cache_ttl,
                serialized,
            )
            logger.debug("l2_cache_stored", repo_id=repo_id, cache_key=cache_key)
            record_counter("retriever_cache_stores_total", labels={"tier": "l2", "repo_id": repo_id})

        except Exception as e:
            logger.warning("cache_store_error", error=str(e), exc_info=True)
            record_counter("retriever_cache_errors_total", labels={"operation": "store", "tier": "l2"})

    def _deserialize_fused_result(self, data: dict[str, Any]) -> FusedResultV3:
        """Deserialize a FusedResultV3 from dict."""
        # Reconstruct FeatureVector
        fv_data = data.get("feature_vector", {})
        ranks = fv_data.get("ranks", {})
        rrf = fv_data.get("rrf_scores", {})
        weights = fv_data.get("weights", {})
        consensus = fv_data.get("consensus", {})
        metadata_fv = fv_data.get("metadata", {})

        feature_vector = FeatureVector(
            chunk_id=data["chunk_id"],
            rank_vec=ranks.get("vector"),
            rank_lex=ranks.get("lexical"),
            rank_sym=ranks.get("symbol"),
            rank_graph=ranks.get("graph"),
            rrf_vec=rrf.get("vector", 0.0),
            rrf_lex=rrf.get("lexical", 0.0),
            rrf_sym=rrf.get("symbol", 0.0),
            rrf_graph=rrf.get("graph", 0.0),
            weight_vec=weights.get("vector", 0.0),
            weight_lex=weights.get("lexical", 0.0),
            weight_sym=weights.get("symbol", 0.0),
            weight_graph=weights.get("graph", 0.0),
            num_strategies=consensus.get("num_strategies", 0),
            best_rank=consensus.get("best_rank", 999999),
            avg_rank=consensus.get("avg_rank", 999999.0),
            consensus_factor=consensus.get("consensus_factor", 1.0),
            chunk_size=metadata_fv.get("chunk_size", 0),
            file_depth=metadata_fv.get("file_depth", 0),
            symbol_type=metadata_fv.get("symbol_type", ""),
        )

        # Reconstruct ConsensusStats
        cs_data = data.get("consensus_stats", {})
        consensus_stats = ConsensusStats(
            num_strategies=cs_data.get("num_strategies", 0),
            ranks=cs_data.get("ranks", {}),
            best_rank=cs_data.get("best_rank", 999999),
            avg_rank=cs_data.get("avg_rank", 999999.0),
            quality_factor=cs_data.get("quality_factor", 0.0),
            consensus_factor=cs_data.get("consensus_factor", 1.0),
        )

        return FusedResultV3(
            chunk_id=data["chunk_id"],
            file_path=data.get("file_path"),
            symbol_id=data.get("symbol_id"),
            final_score=data.get("final_score", 0.0),
            feature_vector=feature_vector,
            consensus_stats=consensus_stats,
            metadata=data.get("metadata", {}),
            explanation=data.get("explanation", ""),
        )

    def explain_result(self, result: FusedResultV3) -> str:
        """
        Get detailed explanation for a result.

        Args:
            result: FusedResultV3 to explain

        Returns:
            Detailed explanation string
        """
        if result.explanation:
            return result.explanation

        # Generate explanation on-demand
        return (
            f"Chunk {result.chunk_id}: "
            f"final_score={result.final_score:.4f}, "
            f"consensus={result.consensus_stats.num_strategies} strategies, "
            f"best_rank={result.consensus_stats.best_rank}"
        )

    def get_feature_vectors(self, results: list[FusedResultV3]) -> tuple[list[str], list[list[float]]]:
        """
        Extract feature vectors for LTR training.

        Args:
            results: List of FusedResultV3

        Returns:
            Tuple of (chunk_ids, feature_arrays)
        """
        chunk_ids = []
        feature_arrays = []

        for result in results:
            chunk_ids.append(result.chunk_id)
            feature_arrays.append(result.feature_vector.to_array())

        return chunk_ids, feature_arrays

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get L1 cache statistics.

        Returns:
            Dictionary with cache stats for all tiers
        """
        return self.l1_cache.stats()

    def clear_cache(self) -> None:
        """Clear all L1 cache tiers."""
        self.l1_cache.clear_all()
        logger.info("l1_cache_cleared")
        record_counter("retriever_cache_clears_total", labels={"tier": "l1"})
