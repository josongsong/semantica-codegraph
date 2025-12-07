"""
Test Symbol Index with SymbolGraph Integration

Verifies that KuzuSymbolIndex can work with both:
1. GraphDocument (old way - backward compatibility)
2. SymbolGraph (new way - lightweight)
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from src.foundation.ir.models import Span
from src.foundation.symbol_graph.models import (
    Relation,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex


@pytest.fixture
def temp_kuzu_db():
    """Create temporary Kuzu database for testing"""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_kuzu.db"
    yield str(db_path)
    # Cleanup
    if Path(temp_dir).exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def sample_symbol_graph():
    """Create a simple SymbolGraph for testing"""
    # Create symbols
    file_symbol = Symbol(
        id="file:main.py",
        kind=SymbolKind.FILE,
        fqn="main.py",
        name="main.py",
        repo_id="test_repo",
        snapshot_id="snap_001",
        span=None,
    )

    module_symbol = Symbol(
        id="module:main",
        kind=SymbolKind.MODULE,
        fqn="main",
        name="main",
        repo_id="test_repo",
        snapshot_id="snap_001",
        span=Span(start_line=1, end_line=20, start_col=0, end_col=0),
        parent_id="file:main.py",
    )

    class_symbol = Symbol(
        id="class:main.Calculator",
        kind=SymbolKind.CLASS,
        fqn="main.Calculator",
        name="Calculator",
        repo_id="test_repo",
        snapshot_id="snap_001",
        span=Span(start_line=5, end_line=15, start_col=0, end_col=0),
        parent_id="module:main",
    )

    method_symbol = Symbol(
        id="method:main.Calculator.add",
        kind=SymbolKind.METHOD,
        fqn="main.Calculator.add",
        name="add",
        repo_id="test_repo",
        snapshot_id="snap_001",
        span=Span(start_line=6, end_line=8, start_col=4, end_col=0),
        parent_id="class:main.Calculator",
        signature_id="sig:main.Calculator.add",
    )

    function_symbol = Symbol(
        id="function:main.helper",
        kind=SymbolKind.FUNCTION,
        fqn="main.helper",
        name="helper",
        repo_id="test_repo",
        snapshot_id="snap_001",
        span=Span(start_line=17, end_line=19, start_col=0, end_col=0),
        parent_id="module:main",
        signature_id="sig:main.helper",
    )

    # Create relations
    contains_module = Relation(
        id="rel:file:main.py:contains:module:main",
        kind=RelationKind.CONTAINS,
        source_id="file:main.py",
        target_id="module:main",
    )

    contains_class = Relation(
        id="rel:module:main:contains:class:main.Calculator",
        kind=RelationKind.CONTAINS,
        source_id="module:main",
        target_id="class:main.Calculator",
    )

    contains_method = Relation(
        id="rel:class:main.Calculator:contains:method:main.Calculator.add",
        kind=RelationKind.CONTAINS,
        source_id="class:main.Calculator",
        target_id="method:main.Calculator.add",
    )

    calls_helper = Relation(
        id="rel:method:main.Calculator.add:calls:function:main.helper",
        kind=RelationKind.CALLS,
        source_id="method:main.Calculator.add",
        target_id="function:main.helper",
        span=Span(start_line=7, end_line=7, start_col=8, end_col=14),
    )

    # Build SymbolGraph
    symbol_graph = SymbolGraph(
        repo_id="test_repo",
        snapshot_id="snap_001",
        symbols={
            "file:main.py": file_symbol,
            "module:main": module_symbol,
            "class:main.Calculator": class_symbol,
            "method:main.Calculator.add": method_symbol,
            "function:main.helper": function_symbol,
        },
        relations=[contains_module, contains_class, contains_method, calls_helper],
    )

    return symbol_graph


@pytest.mark.asyncio
async def test_index_symbol_graph_basic(temp_kuzu_db, sample_symbol_graph):
    """Test basic indexing of SymbolGraph"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Index the symbol graph
    await index.index_symbol_graph(repo_id="test_repo", snapshot_id="snap_001", symbol_graph=sample_symbol_graph)

    # Verify we can search for symbols
    results = await index.search(repo_id="test_repo", snapshot_id="snap_001", query="Calculator")

    assert len(results) > 0
    calc_result = results[0]
    assert calc_result.metadata["name"] == "Calculator"
    assert calc_result.metadata["kind"] == "class"
    assert calc_result.metadata["fqn"] == "main.Calculator"

    index.close()


@pytest.mark.asyncio
async def test_index_symbol_graph_search_method(temp_kuzu_db, sample_symbol_graph):
    """Test searching for methods"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    await index.index_symbol_graph(repo_id="test_repo", snapshot_id="snap_001", symbol_graph=sample_symbol_graph)

    # Search for method
    results = await index.search(repo_id="test_repo", snapshot_id="snap_001", query="add")

    assert len(results) >= 1
    add_result = [r for r in results if r.metadata["name"] == "add"][0]
    assert add_result.metadata["kind"] == "method"
    assert add_result.metadata["fqn"] == "main.Calculator.add"
    assert add_result.metadata["start_line"] == 6
    assert add_result.metadata["end_line"] == 8

    index.close()


@pytest.mark.asyncio
async def test_get_callees_from_symbol_graph(temp_kuzu_db, sample_symbol_graph):
    """Test getting callees (functions called by a method)"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    await index.index_symbol_graph(repo_id="test_repo", snapshot_id="snap_001", symbol_graph=sample_symbol_graph)

    # Get callees of Calculator.add method
    callees = await index.get_callees(symbol_id="method:main.Calculator.add")

    assert len(callees) == 1
    assert callees[0]["name"] == "helper"
    assert callees[0]["kind"] == "function"

    index.close()


@pytest.mark.asyncio
async def test_get_callers_from_symbol_graph(temp_kuzu_db, sample_symbol_graph):
    """Test getting callers (who calls this function)"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    await index.index_symbol_graph(repo_id="test_repo", snapshot_id="snap_001", symbol_graph=sample_symbol_graph)

    # Get callers of helper function
    callers = await index.get_callers(symbol_id="function:main.helper")

    assert len(callers) == 1
    assert callers[0]["name"] == "add"
    assert callers[0]["kind"] == "method"

    index.close()


@pytest.mark.asyncio
async def test_symbol_graph_multiple_snapshots(temp_kuzu_db, sample_symbol_graph):
    """Test that different snapshots are isolated"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Index snapshot 1
    await index.index_symbol_graph(repo_id="test_repo", snapshot_id="snap_001", symbol_graph=sample_symbol_graph)

    # Create modified symbol graph for snapshot 2
    symbol_graph_v2 = SymbolGraph(
        repo_id="test_repo",
        snapshot_id="snap_002",
        symbols={
            "class:main.NewClass": Symbol(
                id="class:main.NewClass",
                kind=SymbolKind.CLASS,
                fqn="main.NewClass",
                name="NewClass",
                repo_id="test_repo",
                snapshot_id="snap_002",
            )
        },
        relations=[],
    )

    await index.index_symbol_graph(repo_id="test_repo", snapshot_id="snap_002", symbol_graph=symbol_graph_v2)

    # Search in snapshot 1 - should find Calculator
    results_v1 = await index.search(repo_id="test_repo", snapshot_id="snap_001", query="Calculator")
    assert len(results_v1) > 0
    assert results_v1[0].metadata["name"] == "Calculator"

    # Search in snapshot 2 - should find NewClass
    results_v2 = await index.search(repo_id="test_repo", snapshot_id="snap_002", query="NewClass")
    assert len(results_v2) > 0
    assert results_v2[0].metadata["name"] == "NewClass"

    # Search in snapshot 2 should NOT find Calculator
    results_v2_calc = await index.search(repo_id="test_repo", snapshot_id="snap_002", query="Calculator")
    assert len(results_v2_calc) == 0

    index.close()


@pytest.mark.asyncio
async def test_symbol_graph_empty_case(temp_kuzu_db):
    """Test indexing empty SymbolGraph"""
    index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    empty_graph = SymbolGraph(repo_id="test_repo", snapshot_id="snap_empty")

    # Should not raise error
    await index.index_symbol_graph(repo_id="test_repo", snapshot_id="snap_empty", symbol_graph=empty_graph)

    # Search should return empty
    results = await index.search(repo_id="test_repo", snapshot_id="snap_empty", query="anything")
    assert len(results) == 0

    index.close()


@pytest.mark.asyncio
async def test_symbol_graph_stats(sample_symbol_graph):
    """Test SymbolGraph.stats() for verification"""
    stats = sample_symbol_graph.stats()

    assert stats["total_symbols"] == 5
    assert stats["total_relations"] == 4

    assert stats["symbols_by_kind"]["file"] == 1
    assert stats["symbols_by_kind"]["module"] == 1
    assert stats["symbols_by_kind"]["class"] == 1
    assert stats["symbols_by_kind"]["method"] == 1
    assert stats["symbols_by_kind"]["function"] == 1

    assert stats["relations_by_kind"]["contains"] == 3
    assert stats["relations_by_kind"]["calls"] == 1
