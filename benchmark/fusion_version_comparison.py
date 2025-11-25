"""
Fusion Version Comparison Benchmark

Compares different fusion strategies:
- v1: Score-based fusion (original)
- v2: Weighted RRF fusion (improved)

Tests with agent scenario benchmark to measure real-world performance.
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class FusionBenchmarkResult:
    """Results from fusion version comparison."""

    fusion_version: str
    total_scenarios: int
    passed_scenarios: int
    pass_rate: float
    avg_latency_ms: float
    avg_precision: float
    avg_recall: float
    avg_mrr: float
    by_category: dict[str, Any]
    recommendations: list[str]


class MockMultiStrategyRetrieval:
    """
    Mock multi-strategy retrieval for testing fusion.

    Simulates different index behaviors:
    - Vector: High recall, 0.6-0.95 score range
    - Lexical (BM25): Variable recall, 0-30 score range
    - Symbol: Low recall, binary-like (0.9-1.0)
    - Graph: Medium recall, 0.5-0.9
    """

    def __init__(self, quality_level: str = "good"):
        """
        Initialize mock retrieval.

        Args:
            quality_level: Quality level (perfect, good, medium, poor)
        """
        self.quality_level = quality_level

    async def __call__(
        self, repo_id: str, snapshot_id: str, query: str
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Mock multi-strategy retrieval.

        Returns:
            Dict of strategy -> results
        """
        # Simulate latency
        await asyncio.sleep(0.05)

        # Generate results for each strategy
        vector_results = self._generate_vector_results(query)
        lexical_results = self._generate_lexical_results(query)
        symbol_results = self._generate_symbol_results(query)
        graph_results = self._generate_graph_results(query)

        return {
            "vector": vector_results,
            "lexical": lexical_results,
            "symbol": symbol_results,
            "graph": graph_results,
        }

    def _generate_vector_results(self, query: str) -> list[dict[str, Any]]:
        """Generate vector search results."""
        results = []

        if self.quality_level == "perfect":
            # Perfect: All relevant, tight score range
            for i in range(10):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Vector relevant chunk {i}",
                        "score": 0.95 - (i * 0.02),  # 0.95 → 0.77
                        "is_relevant": True,
                    }
                )
        elif self.quality_level == "good":
            # Good: 80% relevant
            for i in range(8):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Vector relevant chunk {i}",
                        "score": 0.90 - (i * 0.03),
                        "is_relevant": True,
                    }
                )
            for i in range(8, 10):
                results.append(
                    {
                        "chunk_id": f"irrelevant_v_{i}",
                        "content": "Vector noise",
                        "score": 0.65 - (i * 0.02),
                        "is_relevant": False,
                    }
                )
        elif self.quality_level == "medium":
            # Medium: 50% relevant
            for i in range(5):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Vector relevant chunk {i}",
                        "score": 0.85 - (i * 0.04),
                        "is_relevant": True,
                    }
                )
            for i in range(5, 10):
                results.append(
                    {
                        "chunk_id": f"irrelevant_v_{i}",
                        "content": "Vector noise",
                        "score": 0.70 - (i * 0.03),
                        "is_relevant": False,
                    }
                )
        else:  # poor
            # Poor: 20% relevant
            for i in range(2):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Vector relevant chunk {i}",
                        "score": 0.80 - (i * 0.05),
                        "is_relevant": True,
                    }
                )
            for i in range(2, 10):
                results.append(
                    {
                        "chunk_id": f"irrelevant_v_{i}",
                        "content": "Vector noise",
                        "score": 0.70 - (i * 0.04),
                        "is_relevant": False,
                    }
                )

        return results

    def _generate_lexical_results(self, query: str) -> list[dict[str, Any]]:
        """Generate lexical (BM25) search results with large score range."""
        results = []

        if self.quality_level == "perfect":
            for i in range(8):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Lexical relevant chunk {i}",
                        "score": 25.0 - (i * 2.0),  # BM25 scale: 25 → 11
                        "is_relevant": True,
                    }
                )
        elif self.quality_level == "good":
            for i in range(6):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Lexical relevant chunk {i}",
                        "score": 22.0 - (i * 2.5),
                        "is_relevant": True,
                    }
                )
            for i in range(6, 10):
                results.append(
                    {
                        "chunk_id": f"irrelevant_l_{i}",
                        "content": "Lexical noise",
                        "score": 10.0 - (i * 0.5),
                        "is_relevant": False,
                    }
                )
        elif self.quality_level == "medium":
            for i in range(4):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Lexical relevant chunk {i}",
                        "score": 20.0 - (i * 3.0),
                        "is_relevant": True,
                    }
                )
            for i in range(4, 10):
                results.append(
                    {
                        "chunk_id": f"irrelevant_l_{i}",
                        "content": "Lexical noise",
                        "score": 12.0 - (i * 1.0),
                        "is_relevant": False,
                    }
                )
        else:  # poor
            for i in range(2):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Lexical relevant chunk {i}",
                        "score": 18.0 - (i * 4.0),
                        "is_relevant": True,
                    }
                )
            for i in range(2, 10):
                results.append(
                    {
                        "chunk_id": f"irrelevant_l_{i}",
                        "content": "Lexical noise",
                        "score": 10.0 - (i * 0.8),
                        "is_relevant": False,
                    }
                )

        return results

    def _generate_symbol_results(self, query: str) -> list[dict[str, Any]]:
        """Generate symbol search results (binary-like, perfect matches)."""
        results = []

        if self.quality_level in ["perfect", "good"]:
            # Symbol index: very precise, low recall
            for i in range(3):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Symbol perfect match {i}",
                        "score": 1.0 - (i * 0.01),  # Binary-like: 1.0 → 0.98
                        "is_relevant": True,
                    }
                )
        elif self.quality_level == "medium":
            for i in range(2):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Symbol match {i}",
                        "score": 1.0 - (i * 0.02),
                        "is_relevant": True,
                    }
                )
        else:  # poor
            # Symbol miss
            results.append(
                {
                    "chunk_id": f"relevant_0",
                    "content": "Symbol match 0",
                    "score": 0.95,
                    "is_relevant": True,
                }
            )

        return results

    def _generate_graph_results(self, query: str) -> list[dict[str, Any]]:
        """Generate graph search results."""
        results = []

        if self.quality_level == "perfect":
            for i in range(5):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Graph relevant {i}",
                        "score": 0.85 - (i * 0.05),
                        "is_relevant": True,
                    }
                )
        elif self.quality_level == "good":
            for i in range(4):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Graph relevant {i}",
                        "score": 0.80 - (i * 0.06),
                        "is_relevant": True,
                    }
                )
        elif self.quality_level == "medium":
            for i in range(3):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Graph relevant {i}",
                        "score": 0.75 - (i * 0.07),
                        "is_relevant": True,
                    }
                )
        else:  # poor
            for i in range(2):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Graph relevant {i}",
                        "score": 0.70 - (i * 0.10),
                        "is_relevant": True,
                    }
                )

        return results


async def run_fusion_comparison(quality_level: str = "good"):
    """Run fusion version comparison."""
    logger.info("=" * 80)
    logger.info(f"Fusion Version Comparison - Quality: {quality_level.upper()}")
    logger.info("=" * 80)

    # Import fusion implementations
    from src.retriever.fusion.smart_interleaving import (
        SearchStrategy,
        SmartInterleaver,
        StrategyResult,
    )
    from src.retriever.fusion.smart_interleaving_v2 import SmartInterleaverV2

    # Create mock retrieval
    mock_retrieval = MockMultiStrategyRetrieval(quality_level=quality_level)

    # Test queries
    test_queries = [
        ("User class definition", "symbol_nav"),
        ("find authentication function", "code_search"),
        ("how does login work", "flow_trace"),
        ("explain authentication system", "concept_search"),
    ]

    results_by_version = {}

    for fusion_version, interleaver_cls in [
        ("v1", SmartInterleaver),
        ("v2", SmartInterleaverV2),
    ]:
        logger.info(f"\n{'='*80}")
        logger.info(f"Testing Fusion {fusion_version.upper()}")
        logger.info(f"{'='*80}\n")

        total_passed = 0
        total_queries = len(test_queries)
        all_precisions = []
        all_latencies = []

        for query, intent in test_queries:
            logger.info(f"Query: '{query}' (intent: {intent})")

            # Get multi-strategy results
            import time

            start_time = time.time()
            strategy_dict = await mock_retrieval("test_repo", "main", query)

            # Convert to StrategyResult format
            strategy_results = [
                StrategyResult(
                    strategy=SearchStrategy.VECTOR,
                    chunks=strategy_dict["vector"],
                    confidence=0.9,
                    metadata={},
                ),
                StrategyResult(
                    strategy=SearchStrategy.LEXICAL,
                    chunks=strategy_dict["lexical"],
                    confidence=0.85,
                    metadata={},
                ),
                StrategyResult(
                    strategy=SearchStrategy.SYMBOL,
                    chunks=strategy_dict["symbol"],
                    confidence=0.95,
                    metadata={},
                ),
                StrategyResult(
                    strategy=SearchStrategy.GRAPH,
                    chunks=strategy_dict["graph"],
                    confidence=0.8,
                    metadata={},
                ),
            ]

            # Create interleaver
            if fusion_version == "v2":
                interleaver = SmartInterleaverV2(
                    rrf_k=60, consensus_boost_base=0.15, consensus_max_strategies=3
                )
            else:
                interleaver = interleaver_cls()

            # Set intent
            interleaver.set_weights_for_intent(intent)

            # Interleave
            interleaved = interleaver.interleave(strategy_results, top_k=10)

            latency_ms = (time.time() - start_time) * 1000
            all_latencies.append(latency_ms)

            # Calculate precision
            relevant_in_top10 = sum(
                1 for chunk in interleaved[:10] if chunk.get("is_relevant", False)
            )
            precision = relevant_in_top10 / 10 if interleaved else 0.0
            all_precisions.append(precision)

            # Check pass
            passed = precision >= 0.6
            total_passed += passed

            logger.info(
                f"  Precision: {precision:.2f}, "
                f"Latency: {latency_ms:.1f}ms, "
                f"Status: {'✅ PASS' if passed else '❌ FAIL'}"
            )

            # Debug: Show top-3 with scores
            logger.info("  Top-3 Results:")
            for i, chunk in enumerate(interleaved[:3]):
                score = chunk.get("interleaving_score", chunk.get("final_score", 0))
                strategies = chunk.get("strategies", [])
                logger.info(
                    f"    {i+1}. {chunk['chunk_id']}: "
                    f"score={score:.4f}, "
                    f"strategies={strategies}, "
                    f"relevant={chunk.get('is_relevant', False)}"
                )

        # Summary
        pass_rate = total_passed / total_queries
        avg_precision = sum(all_precisions) / len(all_precisions)
        avg_latency = sum(all_latencies) / len(all_latencies)

        logger.info(f"\n{fusion_version.upper()} Summary:")
        logger.info(f"  Pass Rate: {pass_rate:.1%} ({total_passed}/{total_queries})")
        logger.info(f"  Avg Precision: {avg_precision:.2f}")
        logger.info(f"  Avg Latency: {avg_latency:.1f}ms")

        results_by_version[fusion_version] = {
            "pass_rate": pass_rate,
            "avg_precision": avg_precision,
            "avg_latency": avg_latency,
            "passed": total_passed,
            "total": total_queries,
        }

    # Compare
    logger.info(f"\n{'='*80}")
    logger.info("COMPARISON SUMMARY")
    logger.info(f"{'='*80}\n")

    v1_results = results_by_version["v1"]
    v2_results = results_by_version["v2"]

    logger.info(f"Pass Rate:")
    logger.info(f"  v1: {v1_results['pass_rate']:.1%}")
    logger.info(f"  v2: {v2_results['pass_rate']:.1%}")
    logger.info(
        f"  Δ:  {(v2_results['pass_rate'] - v1_results['pass_rate']):.1%} "
        f"({'✅ Better' if v2_results['pass_rate'] > v1_results['pass_rate'] else '⚠️ Worse'})"
    )

    logger.info(f"\nAvg Precision:")
    logger.info(f"  v1: {v1_results['avg_precision']:.3f}")
    logger.info(f"  v2: {v2_results['avg_precision']:.3f}")
    logger.info(
        f"  Δ:  {(v2_results['avg_precision'] - v1_results['avg_precision']):.3f} "
        f"({'✅ Better' if v2_results['avg_precision'] > v1_results['avg_precision'] else '⚠️ Worse'})"
    )

    logger.info(f"\nAvg Latency:")
    logger.info(f"  v1: {v1_results['avg_latency']:.1f}ms")
    logger.info(f"  v2: {v2_results['avg_latency']:.1f}ms")
    logger.info(
        f"  Δ:  {(v2_results['avg_latency'] - v1_results['avg_latency']):.1f}ms "
        f"({'✅ Faster' if v2_results['avg_latency'] < v1_results['avg_latency'] else '⚠️ Slower'})"
    )

    logger.info(f"\n{'='*80}\n")

    return results_by_version


async def run_all_quality_levels():
    """Run comparison across all quality levels."""
    logger.info("\n" + "=" * 80)
    logger.info("FUSION VERSION COMPARISON - ALL QUALITY LEVELS")
    logger.info("=" * 80 + "\n")

    quality_levels = ["perfect", "good", "medium", "poor"]
    all_results = {}

    for quality in quality_levels:
        results = await run_fusion_comparison(quality_level=quality)
        all_results[quality] = results

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("FINAL SUMMARY ACROSS ALL QUALITY LEVELS")
    logger.info("=" * 80 + "\n")

    for quality in quality_levels:
        v1 = all_results[quality]["v1"]
        v2 = all_results[quality]["v2"]

        logger.info(f"{quality.upper()}:")
        logger.info(
            f"  v1: {v1['pass_rate']:.0%} pass, {v1['avg_precision']:.2f} precision"
        )
        logger.info(
            f"  v2: {v2['pass_rate']:.0%} pass, {v2['avg_precision']:.2f} precision"
        )
        logger.info(
            f"  Winner: {'v2 ✅' if v2['avg_precision'] > v1['avg_precision'] else 'v1' if v1['avg_precision'] > v2['avg_precision'] else 'Tie'}\n"
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        # Run all quality levels
        asyncio.run(run_all_quality_levels())
    else:
        # Quick test with "good" quality
        asyncio.run(run_fusion_comparison(quality_level="good"))
