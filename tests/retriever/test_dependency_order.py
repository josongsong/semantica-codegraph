"""
Tests for Dependency-aware Ordering

Verifies:
1. Basic dependency ordering (definitions before usages)
2. Transitive dependencies
3. Cycle handling (SCC detection)
4. Multiple dependency levels
5. Integration with GraphDocument/SymbolGraph
"""

from src.foundation.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from src.retriever.context_builder.dependency_order import (
    DependencyAwareOrdering,
    DependencyGraphExtractor,
)


def test_simple_dependency_ordering():
    """Test basic dependency ordering: A depends on B → B comes first."""
    # Create simple graph: FunctionA calls FunctionB
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "func:A": GraphNode(
                id="func:A",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.FunctionA",
                name="FunctionA",
            ),
            "func:B": GraphNode(
                id="func:B",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.FunctionB",
                name="FunctionB",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.CALLS,
                source_id="func:A",
                target_id="func:B",
            )
        ],
    )

    # Create chunks
    chunks = [
        {
            "chunk_id": "chunk:A",
            "content": "def FunctionA(): FunctionB()",
            "metadata": {"symbol_id": "func:A", "fqn": "module.FunctionA"},
        },
        {
            "chunk_id": "chunk:B",
            "content": "def FunctionB(): pass",
            "metadata": {"symbol_id": "func:B", "fqn": "module.FunctionB"},
        },
    ]

    # Order by dependency
    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered = ordering.order_chunks(chunks)

    # FunctionB should come before FunctionA (definition before usage)
    assert len(ordered) == 2
    assert ordered[0]["chunk_id"] == "chunk:B"
    assert ordered[1]["chunk_id"] == "chunk:A"


def test_transitive_dependencies():
    """Test transitive dependencies: A → B → C should be ordered C, B, A."""
    # Create chain: A calls B, B calls C
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "func:A": GraphNode(
                id="func:A",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.A",
                name="A",
            ),
            "func:B": GraphNode(
                id="func:B",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.B",
                name="B",
            ),
            "func:C": GraphNode(
                id="func:C",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.C",
                name="C",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.CALLS,
                source_id="func:A",
                target_id="func:B",
            ),
            GraphEdge(
                id="edge:2",
                kind=GraphEdgeKind.CALLS,
                source_id="func:B",
                target_id="func:C",
            ),
        ],
    )

    chunks = [
        {"chunk_id": "chunk:A", "metadata": {"symbol_id": "func:A"}},
        {"chunk_id": "chunk:B", "metadata": {"symbol_id": "func:B"}},
        {"chunk_id": "chunk:C", "metadata": {"symbol_id": "func:C"}},
    ]

    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered = ordering.order_chunks(chunks)

    # Should be ordered: C, B, A (definitions first)
    assert len(ordered) == 3
    assert ordered[0]["chunk_id"] == "chunk:C"
    assert ordered[1]["chunk_id"] == "chunk:B"
    assert ordered[2]["chunk_id"] == "chunk:A"


def test_class_inheritance_ordering():
    """Test class inheritance: Child should come after Parent."""
    # Create inheritance: Child inherits from Parent
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "class:Parent": GraphNode(
                id="class:Parent",
                kind=GraphNodeKind.CLASS,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.Parent",
                name="Parent",
            ),
            "class:Child": GraphNode(
                id="class:Child",
                kind=GraphNodeKind.CLASS,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.Child",
                name="Child",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.INHERITS,
                source_id="class:Child",
                target_id="class:Parent",
            )
        ],
    )

    chunks = [
        {"chunk_id": "chunk:Child", "metadata": {"symbol_id": "class:Child"}},
        {"chunk_id": "chunk:Parent", "metadata": {"symbol_id": "class:Parent"}},
    ]

    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered = ordering.order_chunks(chunks)

    # Parent should come before Child
    assert len(ordered) == 2
    assert ordered[0]["chunk_id"] == "chunk:Parent"
    assert ordered[1]["chunk_id"] == "chunk:Child"


def test_cycle_handling():
    """Test cycle handling with SCC detection."""
    # Create cycle: A calls B, B calls A
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "func:A": GraphNode(
                id="func:A",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.A",
                name="A",
            ),
            "func:B": GraphNode(
                id="func:B",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.B",
                name="B",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.CALLS,
                source_id="func:A",
                target_id="func:B",
            ),
            GraphEdge(
                id="edge:2",
                kind=GraphEdgeKind.CALLS,
                source_id="func:B",
                target_id="func:A",
            ),
        ],
    )

    chunks = [
        {"chunk_id": "chunk:A", "metadata": {"symbol_id": "func:A"}},
        {"chunk_id": "chunk:B", "metadata": {"symbol_id": "func:B"}},
    ]

    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered = ordering.order_chunks(chunks)

    # Should handle cycle gracefully (both chunks returned)
    assert len(ordered) == 2
    # Order within cycle is not strictly defined, but both should be present
    chunk_ids = {c["chunk_id"] for c in ordered}
    assert chunk_ids == {"chunk:A", "chunk:B"}


def test_multiple_dependency_levels():
    """Test chunks with multiple dependency levels."""
    # Create diamond dependency:
    #     A
    #    / \
    #   B   C
    #    \ /
    #     D
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "func:A": GraphNode(
                id="func:A",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.A",
                name="A",
            ),
            "func:B": GraphNode(
                id="func:B",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.B",
                name="B",
            ),
            "func:C": GraphNode(
                id="func:C",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.C",
                name="C",
            ),
            "func:D": GraphNode(
                id="func:D",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.D",
                name="D",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.CALLS,
                source_id="func:A",
                target_id="func:B",
            ),
            GraphEdge(
                id="edge:2",
                kind=GraphEdgeKind.CALLS,
                source_id="func:A",
                target_id="func:C",
            ),
            GraphEdge(
                id="edge:3",
                kind=GraphEdgeKind.CALLS,
                source_id="func:B",
                target_id="func:D",
            ),
            GraphEdge(
                id="edge:4",
                kind=GraphEdgeKind.CALLS,
                source_id="func:C",
                target_id="func:D",
            ),
        ],
    )

    chunks = [
        {"chunk_id": "chunk:A", "metadata": {"symbol_id": "func:A"}},
        {"chunk_id": "chunk:B", "metadata": {"symbol_id": "func:B"}},
        {"chunk_id": "chunk:C", "metadata": {"symbol_id": "func:C"}},
        {"chunk_id": "chunk:D", "metadata": {"symbol_id": "func:D"}},
    ]

    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered = ordering.order_chunks(chunks)

    # D should come first (no dependencies)
    # B and C should come next (depend only on D)
    # A should come last (depends on B and C)
    assert len(ordered) == 4
    assert ordered[0]["chunk_id"] == "chunk:D"
    assert ordered[-1]["chunk_id"] == "chunk:A"

    # B and C can be in any order (same level)
    middle_chunks = {ordered[1]["chunk_id"], ordered[2]["chunk_id"]}
    assert middle_chunks == {"chunk:B", "chunk:C"}


def test_chunks_without_dependencies():
    """Test ordering with chunks that have no dependencies."""
    # No graph provided
    chunks = [
        {"chunk_id": "chunk:A", "content": "def A(): pass"},
        {"chunk_id": "chunk:B", "content": "def B(): pass"},
        {"chunk_id": "chunk:C", "content": "def C(): pass"},
    ]

    ordering = DependencyAwareOrdering()  # No graph
    ordered = ordering.order_chunks(chunks)

    # Should return chunks in original order
    assert len(ordered) == 3
    assert [c["chunk_id"] for c in ordered] == ["chunk:A", "chunk:B", "chunk:C"]


def test_dependency_info_extraction():
    """Test DependencyInfo extraction."""
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "func:A": GraphNode(
                id="func:A",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.A",
                name="A",
            ),
            "func:B": GraphNode(
                id="func:B",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.B",
                name="B",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.CALLS,
                source_id="func:A",
                target_id="func:B",
            )
        ],
    )

    chunks = [
        {"chunk_id": "chunk:A", "metadata": {"symbol_id": "func:A"}},
        {"chunk_id": "chunk:B", "metadata": {"symbol_id": "func:B"}},
    ]

    extractor = DependencyGraphExtractor(graph_doc=graph_doc)
    dependencies = extractor.extract_dependencies(chunks)

    # Check DependencyInfo
    assert len(dependencies) == 2

    # Chunk A depends on chunk B
    assert "chunk:A" in dependencies
    assert dependencies["chunk:A"].depends_on == ["chunk:B"]
    assert dependencies["chunk:A"].level == 1  # Depends on level 0

    # Chunk B has no dependencies
    assert "chunk:B" in dependencies
    assert dependencies["chunk:B"].depends_on == []
    assert dependencies["chunk:B"].depended_by == ["chunk:A"]
    assert dependencies["chunk:B"].level == 0  # No dependencies


def test_ordering_stats():
    """Test ordering statistics."""
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "func:A": GraphNode(
                id="func:A",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.A",
                name="A",
            ),
            "func:B": GraphNode(
                id="func:B",
                kind=GraphNodeKind.FUNCTION,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.B",
                name="B",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.CALLS,
                source_id="func:A",
                target_id="func:B",
            )
        ],
    )

    original_chunks = [
        {"chunk_id": "chunk:A", "metadata": {"symbol_id": "func:A"}},
        {"chunk_id": "chunk:B", "metadata": {"symbol_id": "func:B"}},
    ]

    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered_chunks = ordering.order_chunks(original_chunks)

    stats = ordering.get_ordering_stats(original_chunks, ordered_chunks)

    assert stats["total_chunks"] == 2
    assert stats["chunks_with_dependencies"] == 1  # Only A has dependencies
    assert stats["total_dependencies"] == 1  # A depends on B
    assert stats["avg_dependencies_per_chunk"] == 0.5
    assert stats["reordering_distance"] == 2  # Both chunks swapped positions
    assert stats["reordering_percentage"] == 100.0


def test_type_reference_dependency():
    """Test type reference creates dependency."""
    # Class A references Type B
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "class:A": GraphNode(
                id="class:A",
                kind=GraphNodeKind.CLASS,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.A",
                name="A",
            ),
            "type:B": GraphNode(
                id="type:B",
                kind=GraphNodeKind.TYPE,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="module.B",
                name="B",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.REFERENCES_TYPE,
                source_id="class:A",
                target_id="type:B",
            )
        ],
    )

    chunks = [
        {"chunk_id": "chunk:A", "metadata": {"symbol_id": "class:A"}},
        {"chunk_id": "chunk:B", "metadata": {"symbol_id": "type:B"}},
    ]

    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered = ordering.order_chunks(chunks)

    # Type B should come before Class A (type definition before usage)
    assert len(ordered) == 2
    assert ordered[0]["chunk_id"] == "chunk:B"
    assert ordered[1]["chunk_id"] == "chunk:A"


def test_import_dependency():
    """Test import relationship creates dependency."""
    # Module A imports Module B
    graph_doc = GraphDocument(
        repo_id="test_repo",
        snapshot_id="snapshot1",
        graph_nodes={
            "module:A": GraphNode(
                id="module:A",
                kind=GraphNodeKind.MODULE,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="A",
                name="A",
            ),
            "module:B": GraphNode(
                id="module:B",
                kind=GraphNodeKind.MODULE,
                repo_id="test_repo",
                snapshot_id="snapshot1",
                fqn="B",
                name="B",
            ),
        },
        graph_edges=[
            GraphEdge(
                id="edge:1",
                kind=GraphEdgeKind.IMPORTS,
                source_id="module:A",
                target_id="module:B",
            )
        ],
    )

    chunks = [
        {"chunk_id": "chunk:A", "metadata": {"symbol_id": "module:A"}},
        {"chunk_id": "chunk:B", "metadata": {"symbol_id": "module:B"}},
    ]

    ordering = DependencyAwareOrdering(graph_doc=graph_doc)
    ordered = ordering.order_chunks(chunks)

    # Module B should come before Module A (imported module first)
    assert len(ordered) == 2
    assert ordered[0]["chunk_id"] == "chunk:B"
    assert ordered[1]["chunk_id"] == "chunk:A"
