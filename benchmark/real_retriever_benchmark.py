"""
Real Retriever Benchmark on Actual Codebase

Tests v1 (score-based), v2 (Weighted RRF), and v3 (complete rewrite)
on the actual src/ directory of the codegraph project.

This benchmark:
1. Indexes the actual src/ directory
2. Runs realistic queries on real code
3. Compares precision, latency, and ranking quality
4. Shows real-world performance differences
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkQuery:
    """A single benchmark query with expected results."""

    query: str
    intent: str  # symbol_nav, flow_trace, concept_search, code_search
    expected_in_top_k: list[str]  # File paths or symbols expected in top-K
    k: int = 10


@dataclass
class BenchmarkResult:
    """Results for a single query."""

    query: str
    version: str
    latency_ms: float
    top_k_results: list[dict[str, Any]]
    precision_at_k: float
    hit_rate: float
    ndcg: float


# ============================================================
# Benchmark Queries (Real Queries on Our Codebase)
# ============================================================

BENCHMARK_QUERIES = [
    # Symbol Navigation
    BenchmarkQuery(
        query="Chunk class",
        intent="symbol_nav",
        expected_in_top_k=[
            "foundation/chunk/models.py",  # Chunk definition
        ],
        k=5,
    ),
    BenchmarkQuery(
        query="SmartInterleaver",
        intent="symbol_nav",
        expected_in_top_k=[
            "retriever/fusion/smart_interleaving.py",
            "retriever/fusion/smart_interleaving_v2.py",
        ],
        k=5,
    ),
    BenchmarkQuery(
        query="RetrieverConfig",
        intent="symbol_nav",
        expected_in_top_k=[
            "retriever/service_optimized.py",
            "retriever/v3/config.py",
        ],
        k=5,
    ),
    # Code Search (Semantic)
    BenchmarkQuery(
        query="how to build AST from python code",
        intent="code_search",
        expected_in_top_k=[
            "foundation/parsing/",
            "foundation/generators/python",
        ],
        k=10,
    ),
    BenchmarkQuery(
        query="vector embedding search implementation",
        intent="code_search",
        expected_in_top_k=[
            "infra/vector/qdrant.py",
            "index/vector/",
        ],
        k=10,
    ),
    BenchmarkQuery(
        query="weighted RRF fusion algorithm",
        intent="concept_search",
        expected_in_top_k=[
            "retriever/fusion/smart_interleaving_v2.py",
            "retriever/v3/rrf_normalizer.py",
        ],
        k=10,
    ),
    # Flow/Graph Queries
    BenchmarkQuery(
        query="chunk builder graph integration",
        intent="flow_trace",
        expected_in_top_k=[
            "foundation/chunk/builder.py",
            "foundation/graph/builder.py",
        ],
        k=10,
    ),
    BenchmarkQuery(
        query="indexing service search flow",
        intent="flow_trace",
        expected_in_top_k=[
            "index/service.py",
            "index/factory.py",
        ],
        k=10,
    ),
    # Concept Search
    BenchmarkQuery(
        query="intent classification for retrieval",
        intent="concept_search",
        expected_in_top_k=[
            "retriever/intent/",
            "retriever/v3/intent_classifier.py",
        ],
        k=10,
    ),
    BenchmarkQuery(
        query="consensus boosting in multi-strategy fusion",
        intent="concept_search",
        expected_in_top_k=[
            "retriever/v3/consensus_engine.py",
            "retriever/fusion/",
        ],
        k=10,
    ),
]


# ============================================================
# Mock Index Adapters (for quick testing without real infra)
# ============================================================


class MockLexicalIndex:
    """Mock BM25-style lexical index that searches file paths and content."""

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.files = list(src_dir.rglob("*.py"))

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search by keyword matching in file paths."""
        results = []
        query_lower = query.lower()

        for file_path in self.files:
            rel_path = file_path.relative_to(self.src_dir)
            score = 0.0

            # Score based on keyword matches in file path
            path_str = str(rel_path).lower()
            for word in query_lower.split():
                if word in path_str:
                    score += 10.0  # BM25-like large score

            # Read file content for keyword matching
            try:
                content = file_path.read_text()
                content_lower = content.lower()
                for word in query_lower.split():
                    # Count occurrences (simple BM25 approximation)
                    count = content_lower.count(word)
                    score += count * 5.0
            except Exception:
                pass

            if score > 0:
                results.append(
                    {
                        "chunk_id": f"chunk:{rel_path}",
                        "file_path": str(rel_path),
                        "score": score,
                        "rank": 0,  # Will be set later
                    }
                )

        # Sort by score and assign ranks
        results.sort(key=lambda x: x["score"], reverse=True)
        for rank, result in enumerate(results[:limit]):
            result["rank"] = rank

        return results[:limit]


class MockVectorIndex:
    """Mock vector similarity index using simple heuristics."""

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.files = list(src_dir.rglob("*.py"))

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search by semantic similarity (approximated)."""
        results = []
        query_lower = query.lower()

        for file_path in self.files:
            rel_path = file_path.relative_to(self.src_dir)
            score = 0.0

            # Read file content
            try:
                content = file_path.read_text()
                content_lower = content.lower()

                # Semantic similarity approximation:
                # - Check for query words in comments/docstrings (high signal)
                # - Check for class/function names matching query
                # - Contextual proximity of query words

                for word in query_lower.split():
                    # Docstrings (high value)
                    if f'"""' in content or "'''" in content:
                        if word in content_lower:
                            score += 0.15

                    # Class/function names (moderate value)
                    if f"class {word}" in content_lower or f"def {word}" in content_lower:
                        score += 0.20

                    # General occurrence (low value)
                    if word in content_lower:
                        score += 0.05

                # Normalize to [0.5, 0.95] range (typical vector scores)
                score = min(0.95, max(0.5, score))

            except Exception:
                pass

            if score >= 0.5:
                results.append(
                    {
                        "chunk_id": f"chunk:{rel_path}",
                        "file_path": str(rel_path),
                        "score": score,
                        "rank": 0,
                    }
                )

        # Sort by score and assign ranks
        results.sort(key=lambda x: x["score"], reverse=True)
        for rank, result in enumerate(results[:limit]):
            result["rank"] = rank

        return results[:limit]


class MockSymbolIndex:
    """Mock symbol index searching for class/function definitions."""

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.files = list(src_dir.rglob("*.py"))

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search for symbol definitions."""
        results = []
        query_lower = query.lower()

        for file_path in self.files:
            rel_path = file_path.relative_to(self.src_dir)
            score = 0.0

            try:
                content = file_path.read_text()
                lines = content.split("\n")

                # Look for class/function definitions
                for line_num, line in enumerate(lines):
                    line_lower = line.strip().lower()

                    # Check for class definition
                    if line_lower.startswith("class "):
                        class_name = line_lower.split("class ")[1].split("(")[0].split(":")[0].strip()
                        for word in query_lower.split():
                            if word in class_name:
                                score = 1.0  # Perfect match
                                break

                    # Check for function/method definition
                    if line_lower.startswith("def ") or "def " in line_lower:
                        func_name = ""
                        if "def " in line_lower:
                            func_name = line_lower.split("def ")[1].split("(")[0].strip()

                        for word in query_lower.split():
                            if word in func_name:
                                score = 0.95  # Near-perfect match
                                break

                    if score > 0:
                        break

            except Exception:
                pass

            if score > 0:
                results.append(
                    {
                        "chunk_id": f"chunk:{rel_path}",
                        "file_path": str(rel_path),
                        "score": score,
                        "rank": 0,
                    }
                )

        # Sort by score and assign ranks
        results.sort(key=lambda x: x["score"], reverse=True)
        for rank, result in enumerate(results[:limit]):
            result["rank"] = rank

        return results[:limit]


# ============================================================
# Fusion Implementations
# ============================================================


class FusionV1:
    """Score-based fusion (v1) from smart_interleaving.py."""

    def __init__(self):
        self.weights = {
            "vector": 0.5,
            "lexical": 0.2,
            "symbol": 0.2,
            "graph": 0.1,
        }

    def set_weights_for_intent(self, intent: str):
        """Set weights based on intent."""
        if intent == "symbol_nav":
            self.weights = {"vector": 0.2, "lexical": 0.2, "symbol": 0.5, "graph": 0.1}
        elif intent == "concept_search":
            self.weights = {"vector": 0.7, "lexical": 0.2, "symbol": 0.05, "graph": 0.05}
        elif intent == "flow_trace":
            self.weights = {"vector": 0.2, "lexical": 0.1, "symbol": 0.2, "graph": 0.5}
        else:  # code_search
            self.weights = {"vector": 0.5, "lexical": 0.3, "symbol": 0.1, "graph": 0.1}

    def fuse(self, strategy_results: dict[str, list[dict]]) -> list[dict[str, Any]]:
        """Fuse results using score-based method."""
        chunk_scores = {}

        # Aggregate scores
        for strategy, results in strategy_results.items():
            weight = self.weights.get(strategy, 0.0)

            for result in results:
                chunk_id = result["chunk_id"]
                score = result["score"]
                rank = result["rank"]

                # v1 formula: weight * score * rank_decay
                rank_decay = 1.0 / (1.0 + rank * 0.1)
                weighted_score = weight * score * rank_decay

                if chunk_id not in chunk_scores:
                    chunk_scores[chunk_id] = {
                        "chunk_id": chunk_id,
                        "file_path": result["file_path"],
                        "final_score": 0.0,
                        "strategies": [],
                    }

                chunk_scores[chunk_id]["final_score"] += weighted_score
                chunk_scores[chunk_id]["strategies"].append(strategy)

        # Consensus boost (v1: linear)
        for chunk_id, data in chunk_scores.items():
            num_strategies = len(set(data["strategies"]))
            if num_strategies > 1:
                consensus_factor = 1.0 + 0.2 * (num_strategies - 1)
                data["final_score"] *= consensus_factor

        # Sort and return
        results = list(chunk_scores.values())
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results


class FusionV2:
    """Weighted RRF fusion (v2) from smart_interleaving_v2.py."""

    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k
        self.weights = {
            "vector": 0.5,
            "lexical": 0.2,
            "symbol": 0.2,
            "graph": 0.1,
        }

    def set_weights_for_intent(self, intent: str):
        """Set weights based on intent."""
        if intent == "symbol_nav":
            self.weights = {"vector": 0.2, "lexical": 0.2, "symbol": 0.5, "graph": 0.1}
        elif intent == "concept_search":
            self.weights = {"vector": 0.7, "lexical": 0.2, "symbol": 0.05, "graph": 0.05}
        elif intent == "flow_trace":
            self.weights = {"vector": 0.2, "lexical": 0.1, "symbol": 0.2, "graph": 0.5}
        else:  # code_search
            self.weights = {"vector": 0.5, "lexical": 0.3, "symbol": 0.1, "graph": 0.1}

    def fuse(self, strategy_results: dict[str, list[dict]]) -> list[dict[str, Any]]:
        """Fuse results using Weighted RRF."""
        import math

        chunk_scores = {}

        # Aggregate RRF scores
        for strategy, results in strategy_results.items():
            weight = self.weights.get(strategy, 0.0)

            for result in results:
                chunk_id = result["chunk_id"]
                rank = result["rank"]

                # v2 formula: weight / (k + rank)
                rrf_component = weight / (self.rrf_k + rank)

                if chunk_id not in chunk_scores:
                    chunk_scores[chunk_id] = {
                        "chunk_id": chunk_id,
                        "file_path": result["file_path"],
                        "final_score": 0.0,
                        "strategies": [],
                        "rrf_components": [],
                        "max_rrf": 0.0,
                    }

                chunk_scores[chunk_id]["final_score"] += rrf_component
                chunk_scores[chunk_id]["strategies"].append(strategy)
                chunk_scores[chunk_id]["rrf_components"].append(rrf_component)
                chunk_scores[chunk_id]["max_rrf"] = max(
                    chunk_scores[chunk_id]["max_rrf"], rrf_component
                )

        # Quality-aware consensus boost (v2: sqrt growth)
        consensus_boost_base = 0.15
        strong_threshold = 0.01

        for chunk_id, data in chunk_scores.items():
            num_strategies = len(set(data["strategies"]))
            if num_strategies > 1:
                effective_strategies = min(num_strategies, 3)
                base_factor = 1.0 + consensus_boost_base * math.sqrt(effective_strategies - 1)

                # Quality check
                max_rrf = data["max_rrf"]
                if max_rrf >= strong_threshold:
                    consensus_factor = base_factor
                else:
                    consensus_factor = 1.0 + (base_factor - 1.0) * 0.5

                data["final_score"] *= consensus_factor

        # Sort and return
        results = list(chunk_scores.values())
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results


class FusionV3Simplified:
    """
    Simplified v3 fusion for benchmark (without full infrastructure).

    Uses same logic as v3 but adapted for benchmark environment.
    """

    def __init__(self):
        self.rrf_k = {"vector": 70, "lexical": 70, "symbol": 50, "graph": 50}
        self.weights = {
            "vector": 0.5,
            "lexical": 0.2,
            "symbol": 0.2,
            "graph": 0.1,
        }

    def set_weights_for_intent(self, intent: str):
        """Set weights based on intent (using v3 profiles)."""
        if intent == "symbol_nav":
            self.weights = {"vector": 0.2, "lexical": 0.2, "symbol": 0.5, "graph": 0.1}
        elif intent == "concept_search":
            self.weights = {"vector": 0.7, "lexical": 0.2, "symbol": 0.05, "graph": 0.05}
        elif intent == "flow_trace":
            self.weights = {"vector": 0.2, "lexical": 0.1, "symbol": 0.2, "graph": 0.5}
        else:  # code_search
            self.weights = {"vector": 0.5, "lexical": 0.3, "symbol": 0.1, "graph": 0.1}

    def fuse(self, strategy_results: dict[str, list[dict]]) -> list[dict[str, Any]]:
        """Fuse results using v3 logic (strategy-specific RRF + consensus)."""
        import math

        chunk_scores = {}

        # Aggregate RRF scores (strategy-specific k)
        for strategy, results in strategy_results.items():
            weight = self.weights.get(strategy, 0.0)
            k = self.rrf_k.get(strategy, 60)

            for result in results:
                chunk_id = result["chunk_id"]
                rank = result["rank"]

                # v3 formula: weight / (k_strategy + rank)
                rrf_component = weight / (k + rank)

                if chunk_id not in chunk_scores:
                    chunk_scores[chunk_id] = {
                        "chunk_id": chunk_id,
                        "file_path": result["file_path"],
                        "base_score": 0.0,
                        "final_score": 0.0,
                        "strategies": [],
                        "ranks": {},
                    }

                chunk_scores[chunk_id]["base_score"] += rrf_component
                chunk_scores[chunk_id]["strategies"].append(strategy)
                chunk_scores[chunk_id]["ranks"][strategy] = rank

        # v3 consensus boost (from consensus_engine.py)
        beta = 0.3
        q0 = 10.0

        for chunk_id, data in chunk_scores.items():
            num_strategies = len(set(data["strategies"]))
            avg_rank = sum(data["ranks"].values()) / max(num_strategies, 1)

            # Quality factor: q = 1 / (1 + avg_rank / q0)
            quality_factor = 1.0 / (1.0 + avg_rank / q0)

            # Consensus factor: f = 1 + beta * log2(k) * q
            consensus_factor = 1.0 + beta * math.log2(max(num_strategies, 1) + 1) * quality_factor
            consensus_factor = min(consensus_factor, 1.5)  # Cap at max_factor

            data["final_score"] = data["base_score"] * consensus_factor

        # Sort and return
        results = list(chunk_scores.values())
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results


# ============================================================
# Benchmark Runner
# ============================================================


async def run_single_query_benchmark(
    query_spec: BenchmarkQuery,
    fusion_impl: Any,
    lexical_idx: MockLexicalIndex,
    vector_idx: MockVectorIndex,
    symbol_idx: MockSymbolIndex,
    version: str,
    debug: bool = False,
) -> BenchmarkResult:
    """Run benchmark for a single query."""
    # Set weights for intent
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

    # Debug: Show actual results
    if debug and version == "v1 (Score-based)":  # Only show once per query
        logger.info(f"\n  DEBUG: Index results for '{query_spec.query}':")
        logger.info(f"    Lexical: {len(lexical_results)} results")
        if lexical_results:
            logger.info(f"      Top-3: {[r['file_path'][:50] for r in lexical_results[:3]]}")
        logger.info(f"    Vector: {len(vector_results)} results")
        if vector_results:
            logger.info(f"      Top-3: {[r['file_path'][:50] for r in vector_results[:3]]}")
        logger.info(f"    Symbol: {len(symbol_results)} results")
        if symbol_results:
            logger.info(f"      Top-3: {[r['file_path'][:50] for r in symbol_results[:3]]}")
        logger.info(f"    Fused top-{query_spec.k}:")
        for i, r in enumerate(top_k):
            logger.info(f"      {i+1}. {r['file_path']}")
        logger.info(f"    Expected: {query_spec.expected_in_top_k}")
        logger.info("")

    # Check how many expected files are in top-K
    hits = 0
    for expected in query_spec.expected_in_top_k:
        # Strip "src/" prefix from expected for matching
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


def calculate_ndcg(ranked_paths: list[str], expected: list[str], k: int) -> float:
    """Calculate NDCG@K."""
    import math

    # Create relevance scores
    relevance_scores = []
    for path in ranked_paths[:k]:
        score = 0
        for exp in expected:
            if exp in path:
                score = 1
                break
        relevance_scores.append(score)

    # DCG
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(relevance_scores))

    # Ideal DCG
    ideal_relevance = sorted(relevance_scores, reverse=True)
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_relevance))

    return dcg / idcg if idcg > 0 else 0.0


async def run_full_benchmark(src_dir: Path):
    """Run full benchmark across all queries and versions."""
    logger.info("=" * 80)
    logger.info("Real Retriever Benchmark on Actual Codebase")
    logger.info("=" * 80)
    logger.info(f"Source directory: {src_dir}")
    logger.info(f"Total queries: {len(BENCHMARK_QUERIES)}")
    logger.info("")

    # Initialize indexes
    logger.info("Initializing indexes...")
    lexical_idx = MockLexicalIndex(src_dir)
    vector_idx = MockVectorIndex(src_dir)
    symbol_idx = MockSymbolIndex(src_dir)
    logger.info(f"Indexed {len(lexical_idx.files)} Python files")
    logger.info("")

    # Initialize fusion implementations
    versions = {
        "v1 (Score-based)": FusionV1(),
        "v2 (Weighted RRF)": FusionV2(rrf_k=60),
        "v3 (Complete)": FusionV3Simplified(),
    }

    logger.info("Fusion versions:")
    logger.info("  v1: Score-based (weight * score * rank_decay)")
    logger.info("  v2: Weighted RRF (weight / (k + rank))")
    logger.info("  v3: Strategy-specific RRF k + quality-aware consensus")
    logger.info("")

    # Run benchmarks
    all_results = []

    for query_spec in BENCHMARK_QUERIES:
        logger.info(f"Query: {query_spec.query}")
        logger.info(f"Intent: {query_spec.intent}, K={query_spec.k}")

        for version_name, fusion_impl in versions.items():
            result = await run_single_query_benchmark(
                query_spec=query_spec,
                fusion_impl=fusion_impl,
                lexical_idx=lexical_idx,
                vector_idx=vector_idx,
                symbol_idx=symbol_idx,
                version=version_name,
                debug=True,  # Enable debug output
            )
            all_results.append(result)

            logger.info(
                f"  {version_name}: "
                f"P@{query_spec.k}={result.precision_at_k:.2f}, "
                f"NDCG={result.ndcg:.3f}, "
                f"latency={result.latency_ms:.1f}ms"
            )

        logger.info("")

    # Aggregate results
    logger.info("=" * 80)
    logger.info("Aggregate Results")
    logger.info("=" * 80)

    for version_name in versions.keys():
        version_results = [r for r in all_results if r.version == version_name]

        avg_precision = sum(r.precision_at_k for r in version_results) / len(version_results)
        avg_ndcg = sum(r.ndcg for r in version_results) / len(version_results)
        avg_latency = sum(r.latency_ms for r in version_results) / len(version_results)

        logger.info(f"{version_name}:")
        logger.info(f"  Avg Precision: {avg_precision:.3f}")
        logger.info(f"  Avg NDCG: {avg_ndcg:.3f}")
        logger.info(f"  Avg Latency: {avg_latency:.1f}ms")
        logger.info("")

    # Winner analysis
    logger.info("=" * 80)
    logger.info("Version Comparison")
    logger.info("=" * 80)

    # Group by query
    for query_spec in BENCHMARK_QUERIES:
        query_results = [r for r in all_results if r.query == query_spec.query]

        # Find best precision
        best_precision = max(r.precision_at_k for r in query_results)
        winners = [r for r in query_results if r.precision_at_k == best_precision]

        logger.info(f"Query: {query_spec.query}")
        logger.info(f"  Winner(s): {', '.join(r.version for r in winners)} (P@K={best_precision:.2f})")

    logger.info("")
    logger.info("=" * 80)
    logger.info("Benchmark Complete")
    logger.info("=" * 80)


# ============================================================
# Main Entry Point
# ============================================================


def main():
    """Main entry point."""
    # Get src directory
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        logger.error(f"Source directory not found: {src_dir}")
        return

    # Run benchmark
    asyncio.run(run_full_benchmark(src_dir))


if __name__ == "__main__":
    main()
