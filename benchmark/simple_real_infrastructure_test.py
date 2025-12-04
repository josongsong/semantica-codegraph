"""
Simple Real Infrastructure Test

Quick test to verify real infrastructure (Kuzu, Qdrant, Zoekt) is working.
Simplified approach: Just test Symbol Index (Kuzu) since it doesn't require embeddings.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Set environment for docker-compose ports
os.environ.setdefault("SEMANTICA_QDRANT_URL", "http://localhost:7203")
os.environ.setdefault("SEMANTICA_ZOEKT_HOST", "localhost")
os.environ.setdefault("SEMANTICA_ZOEKT_PORT", "7205")
os.environ.setdefault("SEMANTICA_DATABASE_URL", "postgresql://codegraph:codegraph_dev@localhost:7201/codegraph")
os.environ.setdefault("SEMANTICA_KUZU_DB_PATH", "./data/kuzu_test")
os.environ.setdefault("SEMANTICA_REDIS_HOST", "localhost")
os.environ.setdefault("SEMANTICA_REDIS_PORT", "7202")
os.environ.setdefault("SEMANTICA_REDIS_PASSWORD", "codegraph_redis")

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.foundation.graph.models import GraphDocument, GraphEdge, GraphEdgeKind, GraphNode, GraphNodeKind
from src.foundation.ir.models import Span
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def test_kuzu_symbol_index():
    """Test Kuzu Symbol Index with simple graph."""
    logger.info("=" * 80)
    logger.info("Testing Kuzu Symbol Index")
    logger.info("=" * 80)

    # Create symbol index
    kuzu_path = "./data/kuzu_test"
    logger.info(f"Kuzu DB path: {kuzu_path}")

    symbol_index = KuzuSymbolIndex(db_path=kuzu_path)

    # Create a simple graph document
    repo_id = "test-repo"
    snapshot_id = "snapshot-1"

    nodes = {
        "node:chunk": GraphNode(
            id="node:chunk",
            kind=GraphNodeKind.CLASS,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            fqn="foundation.chunk.models.Chunk",
            name="Chunk",
            path="foundation/chunk/models.py",
            span=Span(start_line=10, end_line=50, start_col=0, end_col=0),
            attrs={"docstring": "Represents a code chunk"},
        ),
        "node:graph_node": GraphNode(
            id="node:graph_node",
            kind=GraphNodeKind.CLASS,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            fqn="foundation.graph.models.GraphNode",
            name="GraphNode",
            path="foundation/graph/models.py",
            span=Span(start_line=20, end_line=60, start_col=0, end_col=0),
            attrs={"docstring": "Represents a graph node"},
        ),
        "node:builder": GraphNode(
            id="node:builder",
            kind=GraphNodeKind.FUNCTION,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            fqn="foundation.chunk.builder.build_chunks",
            name="build_chunks",
            path="foundation/chunk/builder.py",
            span=Span(start_line=100, end_line=150, start_col=0, end_col=0),
            attrs={"docstring": "Build chunks from source"},
        ),
    }

    edges = [
        GraphEdge(
            id="edge:1",
            source_id="node:builder",
            target_id="node:chunk",
            kind=GraphEdgeKind.CALLS,
            attrs={},
        )
    ]

    graph_doc = GraphDocument(
        repo_id=repo_id,
        snapshot_id=snapshot_id,
        graph_nodes=nodes,
        graph_edges=edges,
    )

    logger.info("")
    logger.info(f"Created test graph with {len(graph_doc.graph_nodes)} nodes and {len(graph_doc.graph_edges)} edges")

    # Index the graph
    logger.info("")
    logger.info("Indexing graph to Kuzu...")

    try:
        await symbol_index.index_graph(repo_id, snapshot_id, graph_doc)
        logger.info("✅ Indexing successful!")
    except Exception as e:
        logger.error(f"❌ Indexing failed: {e}", exc_info=True)
        return

    # Test search queries
    logger.info("")
    logger.info("=" * 80)
    logger.info("Running Search Queries")
    logger.info("=" * 80)

    test_queries = [
        ("Chunk class", "foundation/chunk/models.py"),
        ("GraphNode", "foundation/graph/models.py"),
        ("build chunks", "foundation/chunk/builder.py"),
        ("code chunk", "foundation/chunk/models.py"),  # Semantic match via docstring
    ]

    for query, expected_file in test_queries:
        logger.info("")
        logger.info(f'Query: "{query}"')
        logger.info(f"  Expected: {expected_file}")

        try:
            results = await symbol_index.search(repo_id, snapshot_id, query, limit=5)

            if results:
                logger.info(f"  Results: {len(results)} hits")
                for i, hit in enumerate(results[:3]):
                    logger.info(f"    {i + 1}. {hit.file_path} (score: {hit.score:.3f})")

                # Check if expected file is in results
                found = any(expected_file in hit.file_path for hit in results)
                if found:
                    logger.info(f"  ✅ Found expected file!")
                else:
                    logger.info(f"  ❌ Expected file not in results")
            else:
                logger.info(f"  ⚠️  No results")
        except Exception as e:
            logger.error(f"  ❌ Search failed: {e}")

    logger.info("")
    logger.info("=" * 80)
    logger.info("Test Complete")
    logger.info("=" * 80)


async def main():
    """Main entry point."""
    await test_kuzu_symbol_index()


if __name__ == "__main__":
    asyncio.run(main())
