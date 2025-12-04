"""
Tests for SymbolGraph models and builder
"""

from src.foundation.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from src.foundation.ir.models import Span
from src.foundation.symbol_graph import (
    Relation,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolGraphBuilder,
    SymbolKind,
)


def test_symbol_creation():
    """Test Symbol creation with minimal fields"""
    symbol = Symbol(
        id="function:repo:path:MyClass.method",
        kind=SymbolKind.METHOD,
        fqn="mymodule.MyClass.method",
        name="method",
        repo_id="test-repo",
        snapshot_id="abc123",
        span=Span(start_line=10, end_line=20, start_col=4, end_col=8),
    )

    assert symbol.id == "function:repo:path:MyClass.method"
    assert symbol.kind == SymbolKind.METHOD
    assert symbol.fqn == "mymodule.MyClass.method"
    assert symbol.name == "method"
    assert symbol.is_callable() is True
    assert symbol.is_external() is False


def test_relation_creation():
    """Test Relation creation"""
    relation = Relation(
        id="edge:calls:0",
        kind=RelationKind.CALLS,
        source_id="function:repo:path:caller",
        target_id="function:repo:path:callee",
        span=Span(start_line=15, end_line=15, start_col=8, end_col=20),
    )

    assert relation.kind == RelationKind.CALLS
    assert relation.source_id == "function:repo:path:caller"
    assert relation.target_id == "function:repo:path:callee"


def test_symbol_graph_creation():
    """Test SymbolGraph creation and basic operations"""
    graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add symbols
    symbol1 = Symbol(
        id="class:repo:path:MyClass",
        kind=SymbolKind.CLASS,
        fqn="mymodule.MyClass",
        name="MyClass",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )
    symbol2 = Symbol(
        id="function:repo:path:MyClass.method",
        kind=SymbolKind.METHOD,
        fqn="mymodule.MyClass.method",
        name="method",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
        parent_id="class:repo:path:MyClass",
    )

    graph.symbols[symbol1.id] = symbol1
    graph.symbols[symbol2.id] = symbol2

    # Add relation
    relation = Relation(
        id="edge:contains:0",
        kind=RelationKind.CONTAINS,
        source_id=symbol1.id,
        target_id=symbol2.id,
    )
    graph.relations.append(relation)

    # Test queries
    assert graph.symbol_count == 2
    assert graph.relation_count == 1
    assert graph.get_symbol(symbol1.id) == symbol1
    assert len(graph.get_symbols_by_kind(SymbolKind.CLASS)) == 1
    assert len(graph.get_relations_by_kind(RelationKind.CONTAINS)) == 1


def test_symbol_graph_builder():
    """Test SymbolGraphBuilder converts GraphDocument to SymbolGraph"""
    # Create GraphDocument
    graph_doc = GraphDocument(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add nodes
    node1 = GraphNode(
        id="class:repo:path:MyClass",
        kind=GraphNodeKind.CLASS,
        repo_id="test-repo",
        snapshot_id="snapshot-1",
        fqn="mymodule.MyClass",
        name="MyClass",
        span=Span(start_line=5, end_line=25, start_col=0, end_col=4),
        attrs={"language": "python", "docstring": "Test class"},
    )
    node2 = GraphNode(
        id="function:repo:path:MyClass.method",
        kind=GraphNodeKind.METHOD,
        repo_id="test-repo",
        snapshot_id="snapshot-1",
        fqn="mymodule.MyClass.method",
        name="method",
        span=Span(start_line=10, end_line=20, start_col=4, end_col=8),
        attrs={
            "language": "python",
            "docstring": "Test method",
            "parent_id": "class:repo:path:MyClass",
        },
    )

    graph_doc.graph_nodes[node1.id] = node1
    graph_doc.graph_nodes[node2.id] = node2

    # Add edge
    edge = GraphEdge(
        id="edge:contains:0",
        kind=GraphEdgeKind.CONTAINS,
        source_id=node1.id,
        target_id=node2.id,
        attrs={"span": Span(start_line=10, end_line=10, start_col=4, end_col=4)},
    )
    graph_doc.graph_edges.append(edge)

    # Build SymbolGraph
    builder = SymbolGraphBuilder()
    symbol_graph = builder.build_from_graph(graph_doc)

    # Verify conversion
    assert symbol_graph.repo_id == "test-repo"
    assert symbol_graph.snapshot_id == "snapshot-1"
    assert symbol_graph.symbol_count == 2
    assert symbol_graph.relation_count == 1

    # Check symbol conversion (attrs removed)
    symbol1 = symbol_graph.get_symbol("class:repo:path:MyClass")
    assert symbol1 is not None
    assert symbol1.kind == SymbolKind.CLASS
    assert symbol1.fqn == "mymodule.MyClass"
    assert symbol1.name == "MyClass"
    assert symbol1.span == Span(start_line=5, end_line=25, start_col=0, end_col=4)
    # attrs should not exist in Symbol (lightweight)
    assert not hasattr(symbol1, "attrs") or symbol1.__dict__.get("attrs") is None

    # Check relation conversion
    relations = symbol_graph.get_relations_by_kind(RelationKind.CONTAINS)
    assert len(relations) == 1
    assert relations[0].source_id == node1.id
    assert relations[0].target_id == node2.id


def test_symbol_graph_indexes():
    """Test RelationIndex building"""
    graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add symbols
    caller = Symbol(
        id="function:repo:path:caller",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule.caller",
        name="caller",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )
    callee = Symbol(
        id="function:repo:path:callee",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule.callee",
        name="callee",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    graph.symbols[caller.id] = caller
    graph.symbols[callee.id] = callee

    # Add CALLS relation
    call_relation = Relation(
        id="edge:calls:0",
        kind=RelationKind.CALLS,
        source_id=caller.id,
        target_id=callee.id,
    )
    graph.relations.append(call_relation)

    # Build indexes using builder
    builder = SymbolGraphBuilder()
    builder._build_indexes(graph)

    # Test reverse index
    callers = graph.indexes.get_callers(callee.id)
    assert caller.id in callers

    # Test adjacency index
    outgoing = graph.indexes.get_outgoing_edges(caller.id)
    assert call_relation.id in outgoing

    incoming = graph.indexes.get_incoming_edges(callee.id)
    assert call_relation.id in incoming


def test_symbol_graph_stats():
    """Test SymbolGraph statistics"""
    graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add multiple symbols
    for i in range(5):
        symbol = Symbol(
            id=f"function:repo:path:func{i}",
            kind=SymbolKind.FUNCTION,
            fqn=f"mymodule.func{i}",
            name=f"func{i}",
            repo_id="test-repo",
            snapshot_id="snapshot-1",
        )
        graph.symbols[symbol.id] = symbol

    # Add class
    class_symbol = Symbol(
        id="class:repo:path:MyClass",
        kind=SymbolKind.CLASS,
        fqn="mymodule.MyClass",
        name="MyClass",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )
    graph.symbols[class_symbol.id] = class_symbol

    stats = graph.stats()
    assert stats["total_symbols"] == 6
    assert stats["symbols_by_kind"]["function"] == 5
    assert stats["symbols_by_kind"]["class"] == 1
