"""
Real Infrastructure Benchmark

Uses actual Kuzu, Qdrant, and Zoekt instead of mocks.

Steps:
1. Initialize real infrastructure (Kuzu, Qdrant, Zoekt)
2. Parse and index src/ directory
3. Run benchmark queries
4. Compare with mock baseline

Target: Achieve 70%+ precision on Symbol/Definition queries
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# Set environment for docker-compose ports
os.environ.setdefault("SEMANTICA_QDRANT_URL", "http://localhost:7203")
os.environ.setdefault("SEMANTICA_ZOEKT_HOST", "localhost")
os.environ.setdefault("SEMANTICA_ZOEKT_PORT", "7205")
os.environ.setdefault("SEMANTICA_DATABASE_URL", "postgresql://codegraph:codegraph_dev@localhost:7201/codegraph")
os.environ.setdefault("SEMANTICA_KUZU_DB_PATH", "./data/kuzu_benchmark")
os.environ.setdefault("SEMANTICA_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import benchmark queries
from real_retriever_benchmark import (
    BENCHMARK_QUERIES,
    BenchmarkResult,
    FusionV2,
    calculate_ndcg,
)

from src.container import Container
from src.foundation.chunk.builder import ChunkBuilder
from src.foundation.graph.builder import GraphBuilder
from src.foundation.parsing.parser_registry import ParserRegistry
from src.index.service import IndexingService

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class RealInfrastructureAdapter:
    """Adapter to make real indexes look like mock indexes."""

    def __init__(self, index_service: IndexingService, repo_id: str, snapshot_id: str):
        self.index_service = index_service
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.index_type = "unknown"

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search using real infrastructure."""
        # Use index service unified search
        weights = {
            "lexical": 1.0 if self.index_type == "lexical" else 0.0,
            "vector": 1.0 if self.index_type == "vector" else 0.0,
            "symbol": 1.0 if self.index_type == "symbol" else 0.0,
        }

        hits = await self.index_service.search(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            query=query,
            limit=limit,
            weights=weights,
        )

        # Convert SearchHit to mock format
        results = []
        for i, hit in enumerate(hits):
            results.append(
                {
                    "chunk_id": hit.chunk_id,
                    "file_path": hit.file_path,
                    "score": hit.score,
                    "rank": i,
                    "metadata": hit.metadata,
                }
            )

        return results


async def index_codebase(container: Container, src_dir: Path) -> tuple[str, str]:
    """
    Index the src/ directory using real infrastructure.

    Returns:
        (repo_id, snapshot_id) tuple
    """
    logger.info("=" * 80)
    logger.info("Step 1: Parsing and Building Chunks")
    logger.info("=" * 80)

    repo_id = "semantica-v2-codegraph"
    snapshot_id = f"benchmark-{int(time.time())}"

    # Step 1: List Python files
    files = list(src_dir.rglob("*.py"))
    # Convert to relative paths
    files = [f.relative_to(src_dir) for f in files]
    logger.info(f"  Found {len(files)} Python files")

    # Step 2: Parse files to AST
    parser_registry = ParserRegistry()
    parser = parser_registry.get_parser("python")
    parsed_files = []

    for file_path in files[:50]:  # Limit to 50 files for faster indexing
        full_path = src_dir / file_path
        try:
            with open(full_path, "rb") as f:  # Read as bytes
                content_bytes = f.read()
            content = content_bytes.decode("utf-8")
            tree = parser.parse(content_bytes)
            parsed_files.append((file_path, content, tree))
        except Exception as e:
            logger.warning(f"  Failed to parse {file_path}: {e}")

    logger.info(f"  Parsed {len(parsed_files)} files successfully")

    # Step 3: Build chunks
    logger.info("")
    logger.info("Step 2: Building Chunks")
    chunk_builder = ChunkBuilder()  # ChunkBuilder doesn't need chunk_store

    chunks = []
    for file_path, content, tree in parsed_files:
        try:
            file_chunks = chunk_builder.build_chunks(file_path=str(file_path), source_code=content, tree=tree)
            chunks.extend(file_chunks)
        except Exception as e:
            logger.warning(f"  Failed to chunk {file_path}: {e}")

    logger.info(f"  Built {len(chunks)} chunks")

    # Step 4: Build graph
    logger.info("")
    logger.info("Step 3: Building Symbol Graph")
    graph_builder = GraphBuilder()

    # Build IR documents first (needed for graph)
    from src.foundation.generators.python_generator import PythonIRGenerator

    ir_generator = PythonIRGenerator()
    ir_docs = []

    for file_path, content, tree in parsed_files:
        try:
            ir_doc = ir_generator.generate(file_path=str(file_path), tree=tree, source_code=content)
            ir_docs.append(ir_doc)
        except Exception as e:
            logger.warning(f"  Failed to generate IR for {file_path}: {e}")

    logger.info(f"  Generated {len(ir_docs)} IR documents")

    # Build graph from IR documents
    graph_doc = None
    try:
        graph_doc = graph_builder.build_graph(ir_documents=ir_docs)
        logger.info(f"  Built graph with {len(graph_doc.nodes)} nodes and {len(graph_doc.edges)} edges")
    except Exception as e:
        logger.error(f"  Failed to build graph: {e}")

    # Step 5: Index to real infrastructure
    logger.info("")
    logger.info("Step 4: Indexing to Real Infrastructure")
    logger.info("=" * 80)

    # Check if OpenAI API key is available for vector embeddings
    has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
    if not has_openai_key:
        logger.warning("  ⚠️  OPENAI_API_KEY not set - skipping vector index")
        vector_index = None
    else:
        vector_index = container.vector_index

    indexing_service = IndexingService(
        lexical_index=container.lexical_index,
        vector_index=vector_index,
        symbol_index=container.symbol_index,
    )

    # Prepare source codes dict
    source_codes = {chunk.chunk_id: chunk.content for chunk in chunks}

    try:
        await indexing_service.index_repo_full(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            chunks=chunks,
            graph_doc=graph_doc,
            source_codes=source_codes,
        )
        logger.info("  ✅ Indexing complete!")
        vector_status = "✅" if has_openai_key else "⚠️ skipped"
        logger.info(f"     Indexes: Lexical(Zoekt) ✅, Symbol(Kuzu) ✅, Vector(Qdrant) {vector_status}")
        logger.info(f"     Repo ID: {repo_id}")
        logger.info(f"     Snapshot ID: {snapshot_id}")
    except Exception as e:
        logger.error(f"  ❌ Indexing failed: {e}", exc_info=True)
        raise

    return repo_id, snapshot_id


async def run_real_benchmark(container: Container, repo_id: str, snapshot_id: str) -> list[BenchmarkResult]:
    """Run benchmark queries against real infrastructure."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("Step 5: Running Benchmark Queries")
    logger.info("=" * 80)

    # Create index service (skip vector if no API key)
    has_openai_key = bool(os.getenv("OPENAI_API_KEY"))

    indexing_service = IndexingService(
        lexical_index=container.lexical_index,
        vector_index=container.vector_index if has_openai_key else None,
        symbol_index=container.symbol_index,
    )

    # Create adapters for each index type
    lexical_adapter = RealInfrastructureAdapter(indexing_service, repo_id, snapshot_id)
    lexical_adapter.index_type = "lexical"

    if has_openai_key:
        vector_adapter = RealInfrastructureAdapter(indexing_service, repo_id, snapshot_id)
        vector_adapter.index_type = "vector"
    else:
        # Use empty adapter that returns no results
        class EmptyAdapter:
            async def search(self, query: str, limit: int = 50):
                return []

        vector_adapter = EmptyAdapter()

    symbol_adapter = RealInfrastructureAdapter(indexing_service, repo_id, snapshot_id)
    symbol_adapter.index_type = "symbol"

    # Run benchmark
    results = []
    fusion = FusionV2(rrf_k=60)

    for query_spec in BENCHMARK_QUERIES:
        logger.info(f"Query: {query_spec.query}")
        logger.info(f"  Intent: {query_spec.intent}, K={query_spec.k}")

        fusion.set_weights_for_intent(query_spec.intent)

        # Start timing
        start_time = time.perf_counter()

        # Search all indexes
        lexical_results = await lexical_adapter.search(query_spec.query, limit=50)
        vector_results = await vector_adapter.search(query_spec.query, limit=50)
        symbol_results = await symbol_adapter.search(query_spec.query, limit=50)

        # Fuse results
        strategy_results = {
            "lexical": lexical_results,
            "vector": vector_results,
            "symbol": symbol_results,
        }

        fused_results = fusion.fuse(strategy_results)

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

        result = BenchmarkResult(
            query=query_spec.query,
            version="Real Infrastructure",
            latency_ms=latency_ms,
            top_k_results=top_k,
            precision_at_k=precision_at_k,
            hit_rate=hit_rate,
            ndcg=ndcg,
        )

        results.append(result)

        logger.info(f"  P@{query_spec.k}={precision_at_k:.2f}, NDCG={ndcg:.3f}, Latency={latency_ms:.1f}ms")
        logger.info("")

    return results


async def main():
    """Main benchmark runner."""
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        logger.error(f"Source directory not found: {src_dir}")
        return

    logger.info("=" * 80)
    logger.info("REAL INFRASTRUCTURE BENCHMARK")
    logger.info("=" * 80)
    logger.info(f"Source directory: {src_dir}")
    logger.info(f"Total queries: {len(BENCHMARK_QUERIES)}")
    logger.info("")

    # Initialize container with real infrastructure
    container = Container()

    try:
        # Step 1-4: Index codebase
        repo_id, snapshot_id = await index_codebase(container, src_dir)

        # Step 5: Run benchmark
        real_results = await run_real_benchmark(container, repo_id, snapshot_id)

        # Summary
        logger.info("=" * 80)
        logger.info("REAL INFRASTRUCTURE RESULTS")
        logger.info("=" * 80)

        avg_precision = sum(r.precision_at_k for r in real_results) / len(real_results)
        avg_ndcg = sum(r.ndcg for r in real_results) / len(real_results)
        avg_latency = sum(r.latency_ms for r in real_results) / len(real_results)

        logger.info(f"Avg Precision: {avg_precision:.3f}")
        logger.info(f"Avg NDCG:      {avg_ndcg:.3f}")
        logger.info(f"Avg Latency:   {avg_latency:.1f}ms")
        logger.info("")

        # Category analysis
        symbol_nav_results = real_results[:3]
        symbol_nav_precision = sum(r.precision_at_k for r in symbol_nav_results) / len(symbol_nav_results)

        logger.info("Category Analysis:")
        logger.info(f"  Symbol Navigation (Queries 1-3): {symbol_nav_precision:.3f}")

        if symbol_nav_precision >= 0.70:
            logger.info(f"  ✅ Target achieved! ({symbol_nav_precision:.1%} ≥ 70%)")
        else:
            logger.info(f"  ⚠️ Target not met ({symbol_nav_precision:.1%} < 70%)")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)
        return


if __name__ == "__main__":
    asyncio.run(main())
