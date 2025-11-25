"""
Retriever Service V3.

Main service orchestrating the complete retrieval pipeline (RFC section 10).
"""

import hashlib
import json
import logging
from typing import Any

from src.index.common.documents import SearchHit

from .config import RetrieverV3Config
from .fusion_engine import FusionEngineV3
from .intent_classifier import IntentClassifierV3
from .models import FusedResultV3, IntentProbability, RankedHit

logger = logging.getLogger(__name__)


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
            cache_client: Optional cache client (Redis, etc.)
        """
        self.config = config or RetrieverV3Config()
        self.classifier = IntentClassifierV3()
        self.fusion_engine = FusionEngineV3(self.config)
        self.cache_client = cache_client

    def retrieve(
        self,
        query: str,
        hits_by_strategy: dict[str, list[SearchHit]],
        metadata_map: dict[str, dict[str, Any]] | None = None,
        enable_cache: bool = True,
    ) -> tuple[list[FusedResultV3], IntentProbability]:
        """
        Execute complete retrieval pipeline.

        Args:
            query: User query string
            hits_by_strategy: Dict of strategy → list of SearchHit
                              Each SearchHit should have chunk_id, score, file_path, etc.
            metadata_map: Optional dict of chunk_id → metadata
            enable_cache: Enable cache lookup/store

        Returns:
            Tuple of (fused_results, intent_probability)
        """
        # Check cache first
        if enable_cache and self.config.enable_cache and self.cache_client:
            cached = self._get_from_cache(query, hits_by_strategy)
            if cached:
                logger.info(f"Cache hit for query: {query[:50]}")
                return cached

        # Step 1: Classify intent
        expansions = None
        if self.config.enable_query_expansion:
            intent_prob, expansions = self.classifier.classify_with_expansion(query)
            logger.debug(f"Query expansions: {expansions}")
        else:
            intent_prob = self.classifier.classify(query)

        logger.info(
            f"Intent classification: {intent_prob.to_dict()}, "
            f"dominant={intent_prob.dominant_intent()}"
        )

        # Step 2: Convert SearchHit to RankedHit
        ranked_hits = self._convert_to_ranked_hits(hits_by_strategy)

        # Step 3: Fusion (with expansions if enabled)
        fused_results = self.fusion_engine.fuse(
            hits_by_strategy=ranked_hits,
            intent_prob=intent_prob,
            metadata_map=metadata_map,
            query_expansions=expansions,  # Pass expansions for boosting
        )

        # Step 4: Apply intent-based cutoff
        fused_results = self.fusion_engine.apply_cutoff(fused_results, intent_prob)

        logger.info(
            f"Retrieval complete: {len(fused_results)} results after cutoff, "
            f"avg_score={sum(r.final_score for r in fused_results) / len(fused_results):.4f}"
        )

        # Cache result
        if enable_cache and self.config.enable_cache and self.cache_client:
            self._store_to_cache(query, hits_by_strategy, (fused_results, intent_prob))

        return fused_results, intent_prob

    def _convert_to_ranked_hits(
        self, hits_by_strategy: dict[str, list[SearchHit]]
    ) -> dict[str, list[RankedHit]]:
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

    def _get_cache_key(self, query: str, hits_by_strategy: dict[str, list[SearchHit]]) -> str:
        """
        Generate cache key for query and hits.

        Args:
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
            "query": query,
            "hits": hits_repr,
            "config_version": "v3",
        }

        cache_str = json.dumps(cache_input, sort_keys=True)
        cache_hash = hashlib.sha256(cache_str.encode()).hexdigest()

        return f"retriever:v3:{cache_hash[:16]}"

    def _get_from_cache(
        self, query: str, hits_by_strategy: dict[str, list[SearchHit]]
    ) -> tuple[list[FusedResultV3], IntentProbability] | None:
        """
        Get cached result if available.

        Args:
            query: Query string
            hits_by_strategy: Dict of strategy → list of SearchHit

        Returns:
            Cached result tuple or None
        """
        if not self.cache_client:
            return None

        try:
            cache_key = self._get_cache_key(query, hits_by_strategy)
            cached_data = self.cache_client.get(cache_key)

            if cached_data:
                # Deserialize
                # In practice, you'd implement proper serialization
                return None  # Placeholder

            return None

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    def _store_to_cache(
        self,
        query: str,
        hits_by_strategy: dict[str, list[SearchHit]],
        result: tuple[list[FusedResultV3], IntentProbability],
    ):
        """
        Store result to cache.

        Args:
            query: Query string
            hits_by_strategy: Dict of strategy → list of SearchHit
            result: Result tuple to cache
        """
        if not self.cache_client:
            return

        try:
            cache_key = self._get_cache_key(query, hits_by_strategy)

            # Serialize result
            # In practice, you'd implement proper serialization
            # For now, just store a flag
            self.cache_client.setex(
                cache_key,
                self.config.cache_ttl,
                "cached",  # Placeholder
            )

        except Exception as e:
            logger.warning(f"Cache store error: {e}")

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

    def get_feature_vectors(
        self, results: list[FusedResultV3]
    ) -> tuple[list[str], list[list[float]]]:
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
