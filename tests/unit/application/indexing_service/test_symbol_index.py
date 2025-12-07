"""
Symbol Index Tests

Tests for Kuzu-based symbol index functionality.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from src.foundation.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphIndex,
    GraphNode,
    GraphNodeKind,
)
from src.foundation.ir.models import Span
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex


@pytest.fixture
def temp_kuzu_db():
    """Create temporary Kuzu database directory"""
    # Get a temp directory path without creating it (Kuzu will create it)
    temp_base = tempfile.gettempdir()
    db_name = f"test_kuzu_{tempfile._get_candidate_names().__next__()}"
    db_path = Path(temp_base) / db_name
    yield str(db_path)
    # Cleanup
    if db_path.exists():
        shutil.rmtree(db_path, ignore_errors=True)


@pytest.fixture
def sample_graph_doc():
    """Create sample GraphDocument for testing"""
    # Create sample nodes
    file_node = GraphNode(
        id="file:test.py",
        kind=GraphNodeKind.FILE,
        repo_id="test_repo",
        snapshot_id="commit123",
        fqn="test.py",
        name="test.py",
        path="test.py",
        span=Span(start_line=1, end_line=100, start_col=0, end_col=0),
    )

    class_node = GraphNode(
        id="class:MyClass",
        kind=GraphNodeKind.CLASS,
        repo_id="test_repo",
        snapshot_id="commit123",
        fqn="test.MyClass",
        name="MyClass",
        path="test.py",
        span=Span(start_line=10, end_line=50, start_col=0, end_col=0),
    )

    func1_node = GraphNode(
        id="func:MyClass.method1",
        kind=GraphNodeKind.METHOD,
        repo_id="test_repo",
        snapshot_id="commit123",
        fqn="test.MyClass.method1",
        name="method1",
        path="test.py",
        span=Span(start_line=15, end_line=20, start_col=4, end_col=0),
    )

    func2_node = GraphNode(
        id="func:MyClass.method2",
        kind=GraphNodeKind.METHOD,
        repo_id="test_repo",
        snapshot_id="commit123",
        fqn="test.MyClass.method2",
        name="method2",
        path="test.py",
        span=Span(start_line=25, end_line=30, start_col=4, end_col=0),
    )

    # Create sample edges
    contains_edge1 = GraphEdge(
        id="edge:file_contains_class",
        kind=GraphEdgeKind.CONTAINS,
        source_id="file:test.py",
        target_id="class:MyClass",
    )

    contains_edge2 = GraphEdge(
        id="edge:class_contains_method1",
        kind=GraphEdgeKind.CONTAINS,
        source_id="class:MyClass",
        target_id="func:MyClass.method1",
    )

    contains_edge3 = GraphEdge(
        id="edge:class_contains_method2",
        kind=GraphEdgeKind.CONTAINS,
        source_id="class:MyClass",
        target_id="func:MyClass.method2",
    )

    # Call edge (method1 calls method2)
    call_edge = GraphEdge(
        id="edge:method1_calls_method2",
        kind=GraphEdgeKind.CALLS,
        source_id="func:MyClass.method1",
        target_id="func:MyClass.method2",
    )

    # Create graph document
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="commit123",
        graph_nodes={
            "file:test.py": file_node,
            "class:MyClass": class_node,
            "func:MyClass.method1": func1_node,
            "func:MyClass.method2": func2_node,
        },
        graph_edges=[contains_edge1, contains_edge2, contains_edge3, call_edge],
        indexes=GraphIndex(),
    )

    return graph_doc


@pytest.mark.asyncio
async def test_symbol_index_basic(temp_kuzu_db, sample_graph_doc):
    """Test basic symbol indexing and search"""
    # Create index
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Index the graph
    await index.index_graph("test_repo", "commit123", sample_graph_doc)

    # Search for class
    results = await index.search("test_repo", "commit123", "MyClass", limit=10)

    # Verify results
    assert len(results) > 0
    assert any(hit.metadata.get("name") == "MyClass" for hit in results)

    # Search for method
    results = await index.search("test_repo", "commit123", "method1", limit=10)
    assert len(results) > 0
    assert any(hit.metadata.get("name") == "method1" for hit in results)

    # Cleanup
    index.close()


@pytest.mark.asyncio
async def test_symbol_callers_callees(temp_kuzu_db, sample_graph_doc):
    """Test get_callers and get_callees"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Index the graph
    await index.index_graph("test_repo", "commit123", sample_graph_doc)

    # Get callers of method2 (should be method1)
    callers = await index.get_callers("func:MyClass.method2")
    assert len(callers) == 1
    assert callers[0]["id"] == "func:MyClass.method1"

    # Get callees of method1 (should be method2)
    callees = await index.get_callees("func:MyClass.method1")
    assert len(callees) == 1
    assert callees[0]["id"] == "func:MyClass.method2"

    # Cleanup
    index.close()


@pytest.mark.asyncio
async def test_symbol_partial_match(temp_kuzu_db, sample_graph_doc):
    """Test partial name matching"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Index the graph
    await index.index_graph("test_repo", "commit123", sample_graph_doc)

    # Search with partial match
    results = await index.search("test_repo", "commit123", "method", limit=10)

    # Should find both method1 and method2
    assert len(results) >= 2
    names = [hit.metadata.get("name") for hit in results]
    assert "method1" in names
    assert "method2" in names

    # Cleanup
    index.close()


@pytest.mark.asyncio
async def test_symbol_snapshot_isolation(temp_kuzu_db, sample_graph_doc):
    """Test snapshot isolation (different snapshots don't interfere)"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Index to snapshot1
    await index.index_graph("test_repo", "snapshot1", sample_graph_doc)

    # Index to snapshot2 (with modified doc)
    doc2 = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot2",
        graph_nodes={
            "class:OtherClass": GraphNode(
                id="class:OtherClass",
                kind=GraphNodeKind.CLASS,
                repo_id="test_repo",
                snapshot_id="snapshot2",
                fqn="test.OtherClass",
                name="OtherClass",
                path="test.py",
            )
        },
        graph_edges=[],
        indexes=GraphIndex(),
    )
    await index.index_graph("test_repo", "snapshot2", doc2)

    # Search in snapshot1 (should find MyClass)
    results1 = await index.search("test_repo", "snapshot1", "MyClass", limit=10)
    assert len(results1) > 0

    # Search in snapshot2 (should NOT find MyClass, but find OtherClass)
    results2_my = await index.search("test_repo", "snapshot2", "MyClass", limit=10)
    assert len(results2_my) == 0

    results2_other = await index.search("test_repo", "snapshot2", "OtherClass", limit=10)
    assert len(results2_other) > 0

    # Cleanup
    index.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
