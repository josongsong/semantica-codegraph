"""
Weighted RRF (Reciprocal Rank Fusion) Normalizer.

Implements rank-based normalization with strategy-specific k values (RFC section 6).
"""

from collections import defaultdict

from .config import RRFConfig, WeightProfile
from .models import RankedHit


class RRFNormalizer:
    """
    Weighted RRF normalizer.

    Converts ranked lists from multiple strategies into normalized RRF scores,
    then combines them using intent-based weights.
    """

    def __init__(self, config: RRFConfig):
        """
        Initialize RRF normalizer.

        Args:
            config: RRF configuration with k values
        """
        self.config = config

    def calculate_rrf_scores(
        self, hits_by_strategy: dict[str, list[RankedHit]]
    ) -> dict[str, float]:
        """
        Calculate per-strategy RRF scores for all chunks.

        Args:
            hits_by_strategy: Dict of strategy → list of RankedHit

        Returns:
            Dict of chunk_id → dict of strategy → rrf_score
        """
        chunk_scores: dict[str, dict[str, float]] = defaultdict(dict)

        for strategy, hits in hits_by_strategy.items():
            k = self._get_k_for_strategy(strategy)

            for hit in hits:
                # RRF formula: 1 / (k + rank)
                rrf_score = 1.0 / (k + hit.rank)
                chunk_scores[hit.chunk_id][strategy] = rrf_score

        return chunk_scores

    def calculate_weighted_scores(
        self, rrf_scores: dict[str, dict[str, float]], weights: WeightProfile
    ) -> dict[str, float]:
        """
        Calculate weighted RRF scores using intent weights.

        Args:
            rrf_scores: Dict of chunk_id → dict of strategy → rrf_score
            weights: Intent-based weight profile

        Returns:
            Dict of chunk_id → weighted_score
        """
        weighted_scores = {}
        weight_map = weights.to_dict()

        for chunk_id, strategy_scores in rrf_scores.items():
            weighted_score = 0.0

            for strategy, rrf_score in strategy_scores.items():
                weight = weight_map.get(strategy, 0.0)
                weighted_score += weight * rrf_score

            weighted_scores[chunk_id] = weighted_score

        return weighted_scores

    def normalize_and_weight(
        self, hits_by_strategy: dict[str, list[RankedHit]], weights: WeightProfile
    ) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        """
        Complete normalization and weighting pipeline.

        Args:
            hits_by_strategy: Dict of strategy → list of RankedHit
            weights: Intent-based weight profile

        Returns:
            Tuple of:
                - weighted_scores: Dict of chunk_id → final weighted score
                - rrf_scores: Dict of chunk_id → dict of strategy → rrf_score
        """
        # Step 1: Calculate RRF scores per strategy
        rrf_scores = self.calculate_rrf_scores(hits_by_strategy)

        # Step 2: Calculate weighted combination
        weighted_scores = self.calculate_weighted_scores(rrf_scores, weights)

        return weighted_scores, rrf_scores

    def _get_k_for_strategy(self, strategy: str) -> int:
        """
        Get k value for a specific strategy.

        Args:
            strategy: Strategy name

        Returns:
            k value for RRF formula
        """
        strategy_lower = strategy.lower()

        if "vector" in strategy_lower or "vec" in strategy_lower:
            return self.config.k_vec
        elif "lexical" in strategy_lower or "lex" in strategy_lower:
            return self.config.k_lex
        elif "symbol" in strategy_lower or "sym" in strategy_lower:
            return self.config.k_sym
        elif "graph" in strategy_lower:
            return self.config.k_graph
        else:
            # Default to lexical k
            return self.config.k_lex

    def get_strategy_rrf_score(
        self, chunk_id: str, strategy: str, rrf_scores: dict[str, dict[str, float]]
    ) -> float:
        """
        Get RRF score for a specific chunk and strategy.

        Args:
            chunk_id: Chunk identifier
            strategy: Strategy name
            rrf_scores: RRF scores dict

        Returns:
            RRF score (0.0 if not found)
        """
        if chunk_id not in rrf_scores:
            return 0.0
        return rrf_scores[chunk_id].get(strategy, 0.0)
