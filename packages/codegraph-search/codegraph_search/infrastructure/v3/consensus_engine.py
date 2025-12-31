"""
Consensus Engine for multi-index agreement boosting.

Implements consensus-aware ranking based on multi-strategy co-occurrence (RFC section 7).
"""

import math

from codegraph_search.infrastructure.v3.config import ConsensusConfig
from codegraph_search.infrastructure.v3.models import ConsensusStats, RankedHit


class ConsensusEngine:
    """
    Consensus engine for boosting chunks that appear in multiple strategies.

    Implements the consensus factor calculation from RFC section 7.
    """

    def __init__(self, config: ConsensusConfig):
        """
        Initialize consensus engine.

        Args:
            config: Consensus configuration
        """
        self.config = config

    def calculate_consensus_stats(self, chunk_id: str, hits_by_strategy: dict[str, list[RankedHit]]) -> ConsensusStats:
        """
        Calculate consensus statistics for a chunk.

        Args:
            chunk_id: Chunk identifier
            hits_by_strategy: Dict of strategy → list of RankedHit

        Returns:
            ConsensusStats with all consensus metrics
        """
        # Find all strategies that returned this chunk
        ranks = {}

        for strategy, hits in hits_by_strategy.items():
            for hit in hits:
                if hit.chunk_id == chunk_id:
                    ranks[strategy] = hit.rank
                    break

        if not ranks:
            # Chunk not found in any strategy (shouldn't happen)
            return ConsensusStats(
                num_strategies=0,
                ranks={},
                best_rank=999999,
                avg_rank=999999.0,
                quality_factor=0.0,
                consensus_factor=1.0,
            )

        # Calculate statistics
        num_strategies = len(ranks)
        best_rank = min(ranks.values())
        avg_rank = sum(ranks.values()) / len(ranks)

        # Quality factor based on average rank
        quality_factor = 1.0 / (1.0 + avg_rank / self.config.quality_q0)

        # Consensus factor calculation (RFC 7-3)
        consensus_raw = 1.0 + self.config.beta * (math.sqrt(num_strategies) - 1.0)
        consensus_capped = min(self.config.max_factor, consensus_raw)
        consensus_factor = consensus_capped * (0.5 + 0.5 * quality_factor)

        return ConsensusStats(
            num_strategies=num_strategies,
            ranks=ranks,
            best_rank=best_rank,
            avg_rank=avg_rank,
            quality_factor=quality_factor,
            consensus_factor=consensus_factor,
        )

    def apply_consensus_boost(
        self, base_scores: dict[str, float], hits_by_strategy: dict[str, list[RankedHit]]
    ) -> tuple[dict[str, float], dict[str, ConsensusStats]]:
        """
        Apply consensus boost to base scores.

        Args:
            base_scores: Dict of chunk_id → base_score (from weighted RRF)
            hits_by_strategy: Dict of strategy → list of RankedHit

        Returns:
            Tuple of:
                - boosted_scores: Dict of chunk_id → boosted_score
                - consensus_stats: Dict of chunk_id → ConsensusStats
        """
        boosted_scores = {}
        consensus_stats_map = {}

        for chunk_id, base_score in base_scores.items():
            # Calculate consensus statistics
            stats = self.calculate_consensus_stats(chunk_id, hits_by_strategy)

            # Apply boost
            boosted_score = base_score * stats.consensus_factor

            boosted_scores[chunk_id] = boosted_score
            consensus_stats_map[chunk_id] = stats

        return boosted_scores, consensus_stats_map

    def get_chunks_by_consensus(self, consensus_stats: dict[str, ConsensusStats], min_strategies: int = 2) -> list[str]:
        """
        Get chunks that appear in at least N strategies.

        Args:
            consensus_stats: Dict of chunk_id → ConsensusStats
            min_strategies: Minimum number of strategies

        Returns:
            List of chunk_ids sorted by consensus_factor (descending)
        """
        filtered = [
            (chunk_id, stats) for chunk_id, stats in consensus_stats.items() if stats.num_strategies >= min_strategies
        ]

        # Sort by consensus factor
        filtered.sort(key=lambda x: x[1].consensus_factor, reverse=True)

        return [chunk_id for chunk_id, _ in filtered]

    def explain_consensus(self, stats: ConsensusStats) -> str:
        """
        Generate human-readable explanation of consensus boost.

        Args:
            stats: Consensus statistics

        Returns:
            Explanation string
        """
        strategies_str = ", ".join(stats.ranks.keys())

        explanation = (
            f"Found in {stats.num_strategies} strategies ({strategies_str}). "
            f"Best rank: {stats.best_rank}, Avg rank: {stats.avg_rank:.1f}. "
            f"Quality factor: {stats.quality_factor:.3f}, "
            f"Consensus boost: {stats.consensus_factor:.3f}x."
        )

        return explanation
