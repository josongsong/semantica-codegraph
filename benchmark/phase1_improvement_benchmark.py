"""
Phase 1 Improvement Benchmark

Compare Basic Mock vs Enhanced Mock indexes to measure improvement.

Target: Symbol/Definition queries 40% → 70%+ precision
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Import enhanced indexes
sys.path.insert(0, str(Path(__file__).parent))

from enhanced_mock_indexes import (
    EnhancedMockLexicalIndex,
    EnhancedMockSymbolIndex,
    EnhancedMockVectorIndex,
)
from real_retriever_benchmark import (
    BENCHMARK_QUERIES,
    BenchmarkQuery,
    BenchmarkResult,
    FusionV2,
    MockLexicalIndex,
    MockSymbolIndex,
    MockVectorIndex,
    calculate_ndcg,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def run_single_benchmark(
    query_spec: BenchmarkQuery,
    fusion_impl: Any,
    lexical_idx: Any,
    vector_idx: Any,
    symbol_idx: Any,
    version: str,
) -> BenchmarkResult:
    """Run benchmark for a single query."""
    fusion_impl.set_weights_for_intent(query_spec.intent)

    # Start timing
    start_time = time.perf_counter()

    # Search all indexes
    lexical_results = await lexical_idx.search(query_spec.query, limit=50)
    vector_results = await vector_idx.search(query_spec.query, limit=50)
    symbol_results = await symbol_idx.search(query_spec.query, limit=50)

    # Fuse results
    strategy_results = {
        "lexical": lexical_results,
        "vector": vector_results,
        "symbol": symbol_results,
    }

    fused_results = fusion_impl.fuse(strategy_results)

    # End timing
    latency_ms = (time.perf_counter() - start_time) * 1000

    # Evaluate precision
    top_k = fused_results[: query_spec.k]
    top_k_paths = [r["file_path"] for r in top_k]

    # Check how many expected files are in top-K
    hits = 0
    for expected in query_spec.expected_in_top_k:
        expected_clean = expected.replace("src/", "").replace("src\\", "")
        for path in top_k_paths:
            if expected_clean in path or expected in path:
                hits += 1
                break

    precision_at_k = hits / len(query_spec.expected_in_top_k) if query_spec.expected_in_top_k else 0.0
    hit_rate = hits / query_spec.k if query_spec.k > 0 else 0.0

    # Simple NDCG calculation
    ndcg = calculate_ndcg(top_k_paths, query_spec.expected_in_top_k, query_spec.k)

    return BenchmarkResult(
        query=query_spec.query,
        version=version,
        latency_ms=latency_ms,
        top_k_results=top_k,
        precision_at_k=precision_at_k,
        hit_rate=hit_rate,
        ndcg=ndcg,
    )


async def run_phase1_comparison(src_dir: Path):
    """Compare Basic vs Enhanced mock indexes."""
    logger.info("=" * 80)
    logger.info("Phase 1 Improvement Benchmark: Basic vs Enhanced Mock")
    logger.info("=" * 80)
    logger.info(f"Source directory: {src_dir}")
    logger.info(f"Total queries: {len(BENCHMARK_QUERIES)}")
    logger.info("")

    # Initialize BASIC mock indexes
    logger.info("Initializing BASIC mock indexes...")
    basic_lexical = MockLexicalIndex(src_dir)
    basic_vector = MockVectorIndex(src_dir)
    basic_symbol = MockSymbolIndex(src_dir)
    logger.info(f"  Basic: Indexed {len(basic_lexical.files)} files")

    # Initialize ENHANCED mock indexes
    logger.info("Initializing ENHANCED mock indexes...")
    enhanced_lexical = EnhancedMockLexicalIndex(src_dir)
    enhanced_vector = EnhancedMockVectorIndex(src_dir)
    enhanced_symbol = EnhancedMockSymbolIndex(src_dir)
    logger.info(f"  Enhanced: Indexed {len(enhanced_lexical.files)} files")
    logger.info(f"  Enhanced: Built symbol table with {len(enhanced_symbol.symbols)} symbols")
    logger.info("")

    # Run benchmarks
    basic_results = []
    enhanced_results = []

    fusion = FusionV2(rrf_k=60)

    logger.info("Running benchmarks...")
    logger.info("")

    for query_spec in BENCHMARK_QUERIES:
        logger.info(f"Query: {query_spec.query}")
        logger.info(f"  Intent: {query_spec.intent}, K={query_spec.k}")

        # Basic
        basic_result = await run_single_benchmark(
            query_spec=query_spec,
            fusion_impl=fusion,
            lexical_idx=basic_lexical,
            vector_idx=basic_vector,
            symbol_idx=basic_symbol,
            version="Basic Mock",
        )
        basic_results.append(basic_result)

        # Enhanced
        enhanced_result = await run_single_benchmark(
            query_spec=query_spec,
            fusion_impl=fusion,
            lexical_idx=enhanced_lexical,
            vector_idx=enhanced_vector,
            symbol_idx=enhanced_symbol,
            version="Enhanced Mock",
        )
        enhanced_results.append(enhanced_result)

        # Compare
        precision_diff = enhanced_result.precision_at_k - basic_result.precision_at_k
        ndcg_diff = enhanced_result.ndcg - basic_result.ndcg

        basic_str = f"P@{query_spec.k}={basic_result.precision_at_k:.2f}, NDCG={basic_result.ndcg:.3f}"
        enhanced_str = f"P@{query_spec.k}={enhanced_result.precision_at_k:.2f}, NDCG={enhanced_result.ndcg:.3f}"

        if precision_diff > 0 or ndcg_diff > 0:
            winner = "✅ ENHANCED"
            improvement = f"(+{precision_diff:.2f} P, +{ndcg_diff:.3f} NDCG)"
        elif precision_diff < 0 or ndcg_diff < 0:
            winner = "❌ WORSE"
            improvement = f"({precision_diff:.2f} P, {ndcg_diff:.3f} NDCG)"
        else:
            winner = "TIE"
            improvement = ""

        logger.info(f"  Basic:    {basic_str}")
        logger.info(f"  Enhanced: {enhanced_str} {winner} {improvement}")
        logger.info("")

    # Aggregate results
    logger.info("=" * 80)
    logger.info("Aggregate Results")
    logger.info("=" * 80)

    basic_avg_precision = sum(r.precision_at_k for r in basic_results) / len(basic_results)
    basic_avg_ndcg = sum(r.ndcg for r in basic_results) / len(basic_results)
    basic_avg_latency = sum(r.latency_ms for r in basic_results) / len(basic_results)

    enhanced_avg_precision = sum(r.precision_at_k for r in enhanced_results) / len(enhanced_results)
    enhanced_avg_ndcg = sum(r.ndcg for r in enhanced_results) / len(enhanced_results)
    enhanced_avg_latency = sum(r.latency_ms for r in enhanced_results) / len(enhanced_results)

    logger.info("Basic Mock:")
    logger.info(f"  Avg Precision: {basic_avg_precision:.3f}")
    logger.info(f"  Avg NDCG: {basic_avg_ndcg:.3f}")
    logger.info(f"  Avg Latency: {basic_avg_latency:.1f}ms")
    logger.info("")

    logger.info("Enhanced Mock:")
    logger.info(f"  Avg Precision: {enhanced_avg_precision:.3f}")
    logger.info(f"  Avg NDCG: {enhanced_avg_ndcg:.3f}")
    logger.info(f"  Avg Latency: {enhanced_avg_latency:.1f}ms")
    logger.info("")

    # Improvement
    precision_improvement = enhanced_avg_precision - basic_avg_precision
    ndcg_improvement = enhanced_avg_ndcg - basic_avg_ndcg
    latency_change = enhanced_avg_latency - basic_avg_latency

    logger.info("=" * 80)
    logger.info("Improvement Summary")
    logger.info("=" * 80)

    logger.info(f"Precision: {basic_avg_precision:.3f} → {enhanced_avg_precision:.3f} "
                f"({precision_improvement:+.3f}, {precision_improvement/basic_avg_precision*100:+.1f}%)")
    logger.info(f"NDCG:      {basic_avg_ndcg:.3f} → {enhanced_avg_ndcg:.3f} "
                f"({ndcg_improvement:+.3f}, {ndcg_improvement/basic_avg_ndcg*100:+.1f}%)")
    logger.info(f"Latency:   {basic_avg_latency:.1f}ms → {enhanced_avg_latency:.1f}ms "
                f"({latency_change:+.1f}ms)")
    logger.info("")

    # Category-wise improvement
    logger.info("=" * 80)
    logger.info("Category-Wise Improvement")
    logger.info("=" * 80)

    # Symbol Navigation queries (first 3)
    symbol_nav_queries = BENCHMARK_QUERIES[:3]
    basic_symbol_precision = sum(
        r.precision_at_k for i, r in enumerate(basic_results) if i < 3
    ) / len(symbol_nav_queries)
    enhanced_symbol_precision = sum(
        r.precision_at_k for i, r in enumerate(enhanced_results) if i < 3
    ) / len(symbol_nav_queries)

    logger.info("Symbol Navigation (Queries 1-3):")
    logger.info(f"  Basic:    {basic_symbol_precision:.3f}")
    logger.info(f"  Enhanced: {enhanced_symbol_precision:.3f}")
    logger.info(f"  Improvement: {enhanced_symbol_precision - basic_symbol_precision:+.3f} "
                f"({(enhanced_symbol_precision - basic_symbol_precision)/basic_symbol_precision*100:+.1f}%)")
    logger.info("")

    # Code Search queries (queries 4-5)
    code_search_queries = BENCHMARK_QUERIES[3:5]
    basic_code_precision = sum(
        r.precision_at_k for i, r in enumerate(basic_results) if 3 <= i < 5
    ) / len(code_search_queries)
    enhanced_code_precision = sum(
        r.precision_at_k for i, r in enumerate(enhanced_results) if 3 <= i < 5
    ) / len(code_search_queries)

    logger.info("Code Search (Queries 4-5):")
    logger.info(f"  Basic:    {basic_code_precision:.3f}")
    logger.info(f"  Enhanced: {enhanced_code_precision:.3f}")
    logger.info(f"  Improvement: {enhanced_code_precision - basic_code_precision:+.3f}")
    logger.info("")

    # Winner count
    basic_wins = sum(1 for b, e in zip(basic_results, enhanced_results) if b.precision_at_k > e.precision_at_k)
    enhanced_wins = sum(1 for b, e in zip(basic_results, enhanced_results) if e.precision_at_k > b.precision_at_k)
    ties = len(basic_results) - basic_wins - enhanced_wins

    logger.info("=" * 80)
    logger.info("Winner Analysis")
    logger.info("=" * 80)
    logger.info(f"Enhanced Wins: {enhanced_wins}/{len(BENCHMARK_QUERIES)}")
    logger.info(f"Basic Wins:    {basic_wins}/{len(BENCHMARK_QUERIES)}")
    logger.info(f"Ties:          {ties}/{len(BENCHMARK_QUERIES)}")
    logger.info("")

    # Success
    if enhanced_avg_precision > basic_avg_precision:
        logger.info("✅ Phase 1 Improvement: SUCCESS!")
        logger.info(f"   Target: 40% → 70%+ precision on Symbol Navigation")
        if enhanced_symbol_precision >= 0.70:
            logger.info(f"   Achieved: {enhanced_symbol_precision:.1%} precision on Symbol Navigation ✅")
        else:
            logger.info(f"   Achieved: {enhanced_symbol_precision:.1%} precision on Symbol Navigation (partial)")
    else:
        logger.info("⚠️ Phase 1 Improvement: No significant improvement")

    logger.info("")
    logger.info("=" * 80)
    logger.info("Phase 1 Benchmark Complete")
    logger.info("=" * 80)


def main():
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        logger.error(f"Source directory not found: {src_dir}")
        return

    # Run phase 1 comparison
    asyncio.run(run_phase1_comparison(src_dir))


if __name__ == "__main__":
    main()
