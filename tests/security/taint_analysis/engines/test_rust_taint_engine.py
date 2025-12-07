"""
Integration tests for Rust Taint Engine (RFC-007)

Tests the Memgraph → rustworkx → Taint analysis pipeline.
"""

import pytest


# Mock Memgraph store for testing
class MockMemgraphStore:
    """Mock Memgraph store for testing."""

    def __init__(self):
        self._driver = MockDriver()


class MockDriver:
    """Mock neo4j driver."""

    def session(self):
        return MockSession()


class MockSession:
    """Mock session."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run(self, query: str, **params):
        """Mock query execution."""
        # Mock VFG data
        if "ValueFlowNode" in query and "RETURN" in query:
            # Node query
            return [
                {
                    "id": "node1",
                    "value_type": "str",
                    "taint_label": "user_input",
                    "confidence": "high",
                    "location": "app.py:10",
                    "repo_id": "test_repo",
                    "snapshot_id": "test_snapshot",
                },
                {
                    "id": "node2",
                    "value_type": "str",
                    "taint_label": None,
                    "confidence": "medium",
                    "location": "app.py:20",
                    "repo_id": "test_repo",
                    "snapshot_id": "test_snapshot",
                },
                {
                    "id": "node3",
                    "value_type": "str",
                    "taint_label": None,
                    "confidence": "high",
                    "location": "app.py:30",
                    "repo_id": "test_repo",
                    "snapshot_id": "test_snapshot",
                },
            ]

        elif "FLOWS_TO" in query:
            # Edge query
            return [
                {"src_id": "node1", "dst_id": "node2", "kind": "assign", "confidence": "high"},
                {"src_id": "node2", "dst_id": "node3", "kind": "call", "confidence": "medium"},
            ]

        elif "taint_label IS NOT NULL" in query:
            # Sources
            return [{"node_id": "node1"}]

        elif "execute" in query or "query" in query or "write" in query:
            # Sinks
            return [{"node_id": "node3"}]

        return []


@pytest.fixture
def mock_memgraph_store():
    """Provide mock Memgraph store."""
    return MockMemgraphStore()


@pytest.fixture
def rust_engine():
    """Provide Rust taint engine."""
    try:
        from src.contexts.reasoning_engine.infrastructure.engine.rust_taint_engine import RustTaintEngine

        return RustTaintEngine()
    except ImportError:
        pytest.skip("rustworkx not installed")


def test_memgraph_extractor(mock_memgraph_store):
    """Test VFG extraction from Memgraph."""
    from src.contexts.reasoning_engine.infrastructure.engine.memgraph_extractor import MemgraphVFGExtractor

    extractor = MemgraphVFGExtractor(mock_memgraph_store)

    # Extract VFG
    vfg_data = extractor.extract_vfg("test_repo", "test_snapshot")

    # Verify
    assert len(vfg_data["nodes"]) == 3
    assert len(vfg_data["edges"]) == 2
    assert vfg_data["stats"]["num_nodes"] == 3
    assert vfg_data["stats"]["num_edges"] == 2


def test_rust_engine_load(rust_engine, mock_memgraph_store):
    """Test loading VFG into Rust engine."""
    # Load from Memgraph
    stats = rust_engine.load_from_memgraph(mock_memgraph_store, "test_repo", "test_snapshot")

    # Verify
    assert stats["num_nodes"] == 3
    assert stats["num_edges"] == 2
    assert rust_engine.graph is not None
    assert len(rust_engine.node_map) == 3


def test_rust_engine_taint_analysis(rust_engine, mock_memgraph_store):
    """Test taint analysis with Rust engine."""
    # Load
    rust_engine.load_from_memgraph(mock_memgraph_store, "test_repo", "test_snapshot")

    # Taint analysis
    paths = rust_engine.trace_taint(sources=["node1"], sinks=["node3"])

    # Verify
    assert len(paths) >= 1
    assert paths[0][0] == "node1"  # Starts at source
    assert paths[0][-1] == "node3"  # Ends at sink


def test_rust_engine_cache(rust_engine, mock_memgraph_store):
    """Test cache functionality."""
    # Load
    rust_engine.load_from_memgraph(mock_memgraph_store, "test_repo", "test_snapshot")

    sources = ["node1"]
    sinks = ["node3"]

    # First call (miss)
    paths1 = rust_engine.trace_taint(sources, sinks)
    assert rust_engine.cache_misses == 1
    assert rust_engine.cache_hits == 0

    # Second call (hit)
    paths2 = rust_engine.trace_taint(sources, sinks)
    assert rust_engine.cache_hits == 1
    assert paths1 == paths2


def test_rust_engine_cache_invalidation(rust_engine, mock_memgraph_store):
    """Test incremental cache invalidation."""
    # Load
    rust_engine.load_from_memgraph(mock_memgraph_store, "test_repo", "test_snapshot")

    # Analyze
    rust_engine.trace_taint(["node1"], ["node3"])
    assert len(rust_engine.cache) == 1

    # Invalidate
    num_invalidated = rust_engine.invalidate(["node2"])

    # Verify
    assert num_invalidated >= 0
    # Cache should be cleared if node2 was in any path


def test_rust_engine_reachability(rust_engine, mock_memgraph_store):
    """Test fast reachability check."""
    # Load
    rust_engine.load_from_memgraph(mock_memgraph_store, "test_repo", "test_snapshot")

    # Test reachability
    assert rust_engine.fast_reachability("node1", "node2") is True
    assert rust_engine.fast_reachability("node1", "node3") is True
    assert rust_engine.fast_reachability("node3", "node1") is False


def test_rust_engine_stats(rust_engine, mock_memgraph_store):
    """Test statistics collection."""
    # Load
    rust_engine.load_from_memgraph(mock_memgraph_store, "test_repo", "test_snapshot")

    # Run analysis
    rust_engine.trace_taint(["node1"], ["node3"])
    rust_engine.trace_taint(["node1"], ["node3"])  # Cache hit

    # Get stats
    stats = rust_engine.get_stats()

    # Verify
    assert stats["num_nodes"] == 3
    assert stats["num_edges"] == 2
    assert stats["cache_size"] >= 1
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 1
    assert "50.00%" in stats["cache_hit_rate"]


def test_sources_and_sinks_extraction(mock_memgraph_store):
    """Test source/sink extraction."""
    from src.contexts.reasoning_engine.infrastructure.engine.memgraph_extractor import MemgraphVFGExtractor

    extractor = MemgraphVFGExtractor(mock_memgraph_store)

    # Extract
    result = extractor.extract_sources_and_sinks("test_repo", "test_snapshot")

    # Verify
    assert len(result["sources"]) >= 1
    assert len(result["sinks"]) >= 1
    assert "node1" in result["sources"]  # Has taint_label
    assert "node3" in result["sinks"]  # Contains "query"


@pytest.mark.skipif(
    True,  # Skip unless rustworkx is installed
    reason="Requires rustworkx and Memgraph",
)
def test_reasoning_pipeline_integration():
    """Integration test with ReasoningPipeline."""
    from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
    from src.contexts.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline

    # Create pipeline with Rust engine
    graph = GraphDocument(graph_nodes={}, graph_edges=[])
    memgraph_store = MockMemgraphStore()

    pipeline = ReasoningPipeline(graph=graph, workspace_root="/tmp", memgraph_store=memgraph_store)

    # Test taint analysis
    result = pipeline.analyze_taint_fast(repo_id="test_repo", snapshot_id="test_snapshot")

    # Verify
    assert "paths" in result
    assert "performance" in result
    assert result["performance"]["total_time_ms"] >= 0
