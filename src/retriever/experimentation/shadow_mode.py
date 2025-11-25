"""
Shadow Mode Runner

Runs new retrieval strategies in "shadow mode" alongside production.
Collects metrics without affecting user experience.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShadowResult:
    """Result from shadow mode execution."""

    production_result: Any
    shadow_result: Any
    production_latency_ms: float
    shadow_latency_ms: float
    rank_correlation: float | None  # Spearman correlation of ranks
    hit_at_k: dict[int, bool]  # Whether top production hit is in shadow top-K
    query: str


class ShadowModeRunner:
    """
    Runs new strategies in shadow mode.

    Shadow mode:
    - Production strategy returns result to user (no impact)
    - New strategy runs in background
    - Metrics collected for both
    - Results compared for quality analysis
    """

    def __init__(self, shadow_timeout_seconds: float = 10.0):
        """
        Initialize shadow mode runner.

        Args:
            shadow_timeout_seconds: Timeout for shadow execution
        """
        self.shadow_timeout = shadow_timeout_seconds
        self.shadow_results: list[ShadowResult] = []

    async def run_shadow(
        self,
        query: str,
        production_func: Callable[[str], Any],
        shadow_func: Callable[[str], Any],
    ) -> ShadowResult:
        """
        Run production and shadow strategies in parallel.

        Args:
            query: User query
            production_func: Production retrieval function
            shadow_func: Shadow (experimental) retrieval function

        Returns:
            Shadow result with comparison
        """
        # Run both in parallel (shadow doesn't block production)
        start_prod = time.time()
        prod_result = await production_func(query)
        prod_latency = (time.time() - start_prod) * 1000

        # Shadow runs with timeout
        try:
            start_shadow = time.time()
            shadow_result = await asyncio.wait_for(
                shadow_func(query), timeout=self.shadow_timeout
            )
            shadow_latency = (time.time() - start_shadow) * 1000
        except asyncio.TimeoutError:
            logger.warning(
                f"Shadow execution timeout for query: {query[:50]}... "
                f"(>{self.shadow_timeout}s)"
            )
            shadow_result = None
            shadow_latency = self.shadow_timeout * 1000

        # Compare results
        rank_correlation = self._calculate_rank_correlation(prod_result, shadow_result)
        hit_at_k = self._calculate_hit_at_k(prod_result, shadow_result)

        result = ShadowResult(
            production_result=prod_result,
            shadow_result=shadow_result,
            production_latency_ms=prod_latency,
            shadow_latency_ms=shadow_latency,
            rank_correlation=rank_correlation,
            hit_at_k=hit_at_k,
            query=query,
        )

        self.shadow_results.append(result)

        # Log if significant difference
        if rank_correlation is not None and rank_correlation < 0.7:
            logger.info(
                f"Shadow mode: Low rank correlation ({rank_correlation:.3f}) "
                f"for query: {query[:50]}..."
            )

        return result

    def _calculate_rank_correlation(
        self, prod_result: Any, shadow_result: Any
    ) -> float | None:
        """
        Calculate Spearman rank correlation between production and shadow results.

        Args:
            prod_result: Production result
            shadow_result: Shadow result

        Returns:
            Spearman correlation or None if can't compute
        """
        if shadow_result is None:
            return None

        try:
            from scipy.stats import spearmanr

            # Extract ranked chunk IDs
            prod_ids = self._extract_result_ids(prod_result)
            shadow_ids = self._extract_result_ids(shadow_result)

            # Find common IDs
            common_ids = set(prod_ids) & set(shadow_ids)
            if len(common_ids) < 3:
                return None

            # Get ranks for common IDs
            prod_ranks = [prod_ids.index(id) for id in common_ids]
            shadow_ranks = [shadow_ids.index(id) for id in common_ids]

            correlation, _ = spearmanr(prod_ranks, shadow_ranks)
            return float(correlation)
        except Exception as e:
            logger.warning(f"Failed to calculate rank correlation: {e}")
            return None

    def _calculate_hit_at_k(
        self, prod_result: Any, shadow_result: Any
    ) -> dict[int, bool]:
        """
        Check if top production hit appears in shadow top-K.

        Args:
            prod_result: Production result
            shadow_result: Shadow result

        Returns:
            Hit@K metrics
        """
        if shadow_result is None:
            return {1: False, 3: False, 5: False, 10: False}

        prod_ids = self._extract_result_ids(prod_result)
        shadow_ids = self._extract_result_ids(shadow_result)

        if not prod_ids or not shadow_ids:
            return {1: False, 3: False, 5: False, 10: False}

        top_prod_id = prod_ids[0]

        return {
            1: top_prod_id in shadow_ids[:1],
            3: top_prod_id in shadow_ids[:3],
            5: top_prod_id in shadow_ids[:5],
            10: top_prod_id in shadow_ids[:10],
        }

    def _extract_result_ids(self, result: Any) -> list[str]:
        """Extract ordered chunk IDs from result."""
        if result is None:
            return []

        if hasattr(result, "context"):
            return [chunk.chunk_id for chunk in result.context.chunks]
        elif isinstance(result, list):
            return [r.get("chunk_id", "") for r in result]
        return []

    def get_summary_statistics(self) -> dict[str, Any]:
        """
        Get summary statistics for shadow mode runs.

        Returns:
            Summary stats
        """
        if not self.shadow_results:
            return {"error": "No shadow results yet"}

        prod_latencies = [r.production_latency_ms for r in self.shadow_results]
        shadow_latencies = [r.shadow_latency_ms for r in self.shadow_results]

        correlations = [
            r.rank_correlation
            for r in self.shadow_results
            if r.rank_correlation is not None
        ]

        hit_at_1 = [r.hit_at_k.get(1, False) for r in self.shadow_results]
        hit_at_3 = [r.hit_at_k.get(3, False) for r in self.shadow_results]
        hit_at_5 = [r.hit_at_k.get(5, False) for r in self.shadow_results]
        hit_at_10 = [r.hit_at_k.get(10, False) for r in self.shadow_results]

        return {
            "total_runs": len(self.shadow_results),
            "production_latency": {
                "avg_ms": sum(prod_latencies) / len(prod_latencies),
                "p50_ms": sorted(prod_latencies)[len(prod_latencies) // 2],
                "p95_ms": sorted(prod_latencies)[int(len(prod_latencies) * 0.95)],
            },
            "shadow_latency": {
                "avg_ms": sum(shadow_latencies) / len(shadow_latencies),
                "p50_ms": sorted(shadow_latencies)[len(shadow_latencies) // 2],
                "p95_ms": sorted(shadow_latencies)[int(len(shadow_latencies) * 0.95)],
            },
            "rank_correlation": {
                "avg": sum(correlations) / len(correlations) if correlations else 0.0,
                "count": len(correlations),
            },
            "hit_rate": {
                "hit@1": sum(hit_at_1) / len(hit_at_1) if hit_at_1 else 0.0,
                "hit@3": sum(hit_at_3) / len(hit_at_3) if hit_at_3 else 0.0,
                "hit@5": sum(hit_at_5) / len(hit_at_5) if hit_at_5 else 0.0,
                "hit@10": sum(hit_at_10) / len(hit_at_10) if hit_at_10 else 0.0,
            },
        }
