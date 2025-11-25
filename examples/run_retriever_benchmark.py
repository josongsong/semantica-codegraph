"""
Retriever Benchmark Runner

Example script to run retriever benchmarks with mock data.
"""

import asyncio
import logging
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MockRetrievalFunction:
    """Mock retrieval function for testing."""

    def __init__(self, quality_level: str = "good"):
        """
        Initialize mock retrieval.

        Args:
            quality_level: Quality level (perfect, good, medium, poor)
        """
        self.quality_level = quality_level

    async def __call__(
        self, repo_id: str, snapshot_id: str, query: str
    ) -> list[dict[str, Any]]:
        """
        Mock retrieval function.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            query: User query

        Returns:
            Mock results
        """
        # Simulate retrieval latency
        await asyncio.sleep(0.05)  # 50ms

        # Generate mock results based on quality level
        results = []
        top_k = 50  # Default top-k

        if self.quality_level == "perfect":
            # Perfect retrieval: all relevant chunks ranked correctly
            for i in range(min(10, top_k)):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"This is a relevant chunk for query: {query}",
                        "score": 1.0 - (i * 0.05),
                        "file_path": f"src/module_{i}.py",
                        "is_relevant": True,
                    }
                )

            # Add some irrelevant chunks
            for i in range(10, top_k):
                results.append(
                    {
                        "chunk_id": f"irrelevant_{i}",
                        "content": f"This is not relevant to: {query}",
                        "score": 0.5 - (i * 0.01),
                        "file_path": f"src/other_{i}.py",
                        "is_relevant": False,
                    }
                )

        elif self.quality_level == "good":
            # Good retrieval: 80% relevant in top-10
            for i in range(min(8, top_k)):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Relevant: {query}",
                        "score": 0.9 - (i * 0.05),
                        "file_path": f"src/module_{i}.py",
                        "is_relevant": True,
                    }
                )

            for i in range(8, top_k):
                results.append(
                    {
                        "chunk_id": f"irrelevant_{i}",
                        "content": "Not relevant",
                        "score": 0.5 - (i * 0.01),
                        "file_path": f"src/other_{i}.py",
                        "is_relevant": False,
                    }
                )

        elif self.quality_level == "medium":
            # Medium retrieval: 50% relevant in top-10
            for i in range(0, top_k, 2):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Relevant: {query}",
                        "score": 0.8 - (i * 0.02),
                        "file_path": f"src/module_{i}.py",
                        "is_relevant": True,
                    }
                )
                if i + 1 < top_k:
                    results.append(
                        {
                            "chunk_id": f"irrelevant_{i+1}",
                            "content": "Not relevant",
                            "score": 0.8 - ((i + 1) * 0.02),
                            "file_path": f"src/other_{i+1}.py",
                            "is_relevant": False,
                        }
                    )

        else:  # poor
            # Poor retrieval: 20% relevant
            for i in range(0, top_k, 5):
                results.append(
                    {
                        "chunk_id": f"relevant_{i}",
                        "content": f"Relevant: {query}",
                        "score": 0.7 - (i * 0.01),
                        "file_path": f"src/module_{i}.py",
                        "is_relevant": True,
                    }
                )
            for i in range(top_k - len(results)):
                results.append(
                    {
                        "chunk_id": f"irrelevant_{i}",
                        "content": "Not relevant",
                        "score": 0.6 - (i * 0.01),
                        "file_path": f"src/other_{i}.py",
                        "is_relevant": False,
                    }
                )

        return results


async def run_benchmark():
    """Run retriever benchmark with mock retrieval."""
    from benchmark.retriever_benchmark import (
        BenchmarkConfig,
        QueryTestCase,
        RetrieverBenchmark,
    )

    logger.info("=" * 80)
    logger.info("Retriever Benchmark - Mock Run")
    logger.info("=" * 80)

    # Create test cases
    test_cases = [
        QueryTestCase(
            query="find authentication function",
            intent="code_search",
            expected_results=[f"relevant_{i}" for i in range(5)],
            category="simple",
        ),
        QueryTestCase(
            query="User class definition",
            intent="symbol_nav",
            expected_results=[f"relevant_{i}" for i in range(3)],
            category="simple",
        ),
        QueryTestCase(
            query="how does the login flow work",
            intent="flow_trace",
            expected_results=[f"relevant_{i}" for i in range(10)],
            category="multi_hop",
        ),
    ]

    # Create config
    config = BenchmarkConfig(
        repo_id="mock_repo",
        snapshot_id="main",
        test_cases=test_cases,
        token_budget=4000,
        top_k=20,
    )

    # Test different quality levels
    quality_levels = ["perfect", "good", "medium", "poor"]

    for quality_level in quality_levels:
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Testing Quality Level: {quality_level.upper()}")
        logger.info(f"{'=' * 80}\n")

        # Create mock retrieval function
        mock_retrieval = MockRetrievalFunction(quality_level=quality_level)

        # Create benchmark
        benchmark = RetrieverBenchmark(config)

        # Run benchmark
        result = await benchmark.run_benchmark(mock_retrieval)

        # Print results
        logger.info("\n" + "=" * 80)
        logger.info(f"BENCHMARK RESULTS - {quality_level.upper()}")
        logger.info("=" * 80)

        logger.info("\nOverall Metrics:")
        logger.info(f"  Top-3 Hit:   {result.top_3_hit_rate:.3f}")
        logger.info(f"  Symbol Nav:  {result.symbol_nav_hit_rate:.3f}")
        logger.info(f"  Multi-hop:   {result.multi_hop_success_rate:.3f}")
        logger.info(f"  Context Rel: {result.context_relevance_score:.3f}")
        logger.info(f"  Avg Latency: {result.avg_latency_ms:.1f}ms")
        logger.info(f"  P95 Latency: {result.e2e_latency_p95_ms:.1f}ms")

        logger.info("\nExit Criteria:")
        logger.info(f"  Phase 1: {'✅ PASS' if result.phase_1_passed else '❌ FAIL'}")
        logger.info(f"  Phase 2: {'✅ PASS' if result.phase_2_passed else '❌ FAIL'}")
        logger.info(f"  Phase 3: {'✅ PASS' if result.phase_3_passed else '❌ FAIL'}")

        logger.info("\nBy Intent:")
        for intent, metrics in result.by_intent_metrics.items():
            logger.info(f"  {intent}: {metrics}")

        logger.info("\nBy Category:")
        for category, metrics in result.by_category_metrics.items():
            logger.info(f"  {category}: {metrics}")

        logger.info(f"\n✅ Test Cases: {result.successful_queries}/{result.total_queries} passed")

        logger.info("\n")

    logger.info("=" * 80)
    logger.info("Benchmark Complete!")
    logger.info("=" * 80)


async def run_quick_benchmark():
    """Run a quick benchmark with just one quality level."""
    from benchmark.retriever_benchmark import (
        BenchmarkConfig,
        QueryTestCase,
        RetrieverBenchmark,
    )

    logger.info("\n" + "=" * 80)
    logger.info("Quick Retriever Benchmark")
    logger.info("=" * 80 + "\n")

    # Create test cases
    test_cases = [
        # Code search
        QueryTestCase(
            query="find authentication function",
            intent="code_search",
            expected_results=[f"relevant_{i}" for i in range(5)],
            category="simple",
        ),
        QueryTestCase(
            query="database connection pool",
            intent="code_search",
            expected_results=[f"relevant_{i}" for i in range(5)],
            category="simple",
        ),
        # Symbol navigation
        QueryTestCase(
            query="User class",
            intent="symbol_nav",
            expected_results=[f"relevant_{i}" for i in range(3)],
            category="simple",
        ),
        QueryTestCase(
            query="authenticate method",
            intent="symbol_nav",
            expected_results=[f"relevant_{i}" for i in range(2)],
            category="simple",
        ),
        # Flow trace
        QueryTestCase(
            query="how does login work",
            intent="flow_trace",
            expected_results=[f"relevant_{i}" for i in range(8)],
            category="multi_hop",
        ),
        # Concept search
        QueryTestCase(
            query="explain authentication system",
            intent="concept_search",
            expected_results=[f"relevant_{i}" for i in range(10)],
            category="complex",
        ),
    ]

    # Create config
    config = BenchmarkConfig(
        repo_id="mock_repo",
        snapshot_id="main",
        test_cases=test_cases,
        token_budget=4000,
        top_k=20,
    )

    # Create good quality mock retrieval
    mock_retrieval = MockRetrievalFunction(quality_level="good")

    # Create benchmark
    benchmark = RetrieverBenchmark(config)

    # Run benchmark
    logger.info("Running benchmark with 'good' quality mock retrieval...")
    result = await benchmark.run_benchmark(mock_retrieval)

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("BENCHMARK SUMMARY")
    logger.info("=" * 80)

    logger.info("\n📊 Overall Metrics:")
    logger.info(f"  • Top-3 Hit Rate:  {result.top_3_hit_rate:.1%}")
    logger.info(f"  • Symbol Nav Rate: {result.symbol_nav_hit_rate:.1%}")
    logger.info(f"  • Avg Latency:     {result.avg_latency_ms:.1f}ms")
    logger.info(f"  • P95 Latency:     {result.e2e_latency_p95_ms:.1f}ms")
    logger.info(f"  • Intent Latency:  {result.intent_latency_p95_ms:.1f}ms")
    logger.info(f"  • Context Score:   {result.context_relevance_score:.3f}")
    logger.info(f"  • Multi-hop Rate:  {result.multi_hop_success_rate:.1%}")

    logger.info("\n🎯 Exit Criteria:")
    logger.info(
        f"  • Phase 1 (MVP):      {'✅ PASS' if result.phase_1_passed else '❌ FAIL'}"
    )
    logger.info(
        f"  • Phase 2 (Enhanced): {'✅ PASS' if result.phase_2_passed else '❌ FAIL'}"
    )
    logger.info(
        f"  • Phase 3 (SOTA):     {'✅ PASS' if result.phase_3_passed else '❌ FAIL'}"
    )

    logger.info("\n📈 By Intent:")
    for intent, metrics in sorted(result.by_intent_metrics.items()):
        logger.info(f"  • {intent:20s}: {metrics}")

    logger.info("\n📁 By Category:")
    for category, metrics in sorted(result.by_category_metrics.items()):
        logger.info(f"  • {category:15s}: {metrics}")

    logger.info(
        f"\n✅ Test Cases: {result.successful_queries}/{result.total_queries} passed"
    )

    if not result.phase_3_passed:
        logger.info("\n⚠️  Recommendations:")
        if result.top_3_hit_rate < 0.7:
            logger.info(
                "  • Improve ranking: Consider using learned reranker or cross-encoder"
            )
        if result.avg_latency_ms > 500:
            logger.info(
                "  • Reduce latency: Enable embedding cache and adaptive top-k"
            )
        if result.symbol_nav_hit_rate < 0.85:
            logger.info("  • Improve symbol navigation: Check symbol index quality")

    logger.info("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        # Run full benchmark with all quality levels
        asyncio.run(run_benchmark())
    else:
        # Run quick benchmark (default)
        asyncio.run(run_quick_benchmark())
