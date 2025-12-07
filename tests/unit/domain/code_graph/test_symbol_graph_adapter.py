"""
Tests for SymbolGraph PostgreSQL Adapter

Note: These tests require a PostgreSQL database.
Run with: PYTHONPATH=. pytest tests/foundation/test_symbol_graph_adapter.py
"""

import pytest

from src.foundation.ir.models import Span
from src.foundation.symbol_graph import (
    PostgreSQLSymbolGraphAdapter,
    Relation,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)


@pytest.fixture
def mock_postgres():
    """
    Mock PostgreSQL store for testing.

    In a real test, you would use a test database.
    """
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    return mock


def test_adapter_save(mock_postgres):
    """Test saving SymbolGraph to PostgreSQL"""
    adapter = PostgreSQLSymbolGraphAdapter(mock_postgres)

    # Create test graph
    graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    symbol = Symbol(
        id="function:repo:path:test",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule.test",
        name="test",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
        span=Span(start_line=10, end_line=20, start_col=0, end_col=4),
    )
    graph.symbols[symbol.id] = symbol

    relation = Relation(
        id="edge:calls:0",
        kind=RelationKind.CALLS,
        source_id=symbol.id,
        target_id="function:repo:path:other",
    )
    graph.relations.append(relation)

    # Save (should call executemany)
    adapter.save(graph)

    # Verify mock was called
    mock_cursor = mock_postgres.get_connection().cursor()
    assert mock_cursor.execute.called
    assert mock_cursor.executemany.called
    assert mock_postgres.get_connection().commit.called


def test_adapter_exists(mock_postgres):
    """Test checking if SymbolGraph exists"""
    adapter = PostgreSQLSymbolGraphAdapter(mock_postgres)

    # Mock return value
    mock_cursor = mock_postgres.get_connection().cursor()
    mock_cursor.fetchone.return_value = (1,)

    result = adapter.exists("test-repo", "snapshot-1")

    assert result is True
    assert mock_cursor.execute.called


def test_adapter_delete(mock_postgres):
    """Test deleting SymbolGraph"""
    adapter = PostgreSQLSymbolGraphAdapter(mock_postgres)

    adapter.delete("test-repo", "snapshot-1")

    # Verify DELETE queries were executed
    mock_cursor = mock_postgres.get_connection().cursor()
    assert mock_cursor.execute.call_count >= 2  # 2 DELETE queries
    assert mock_postgres.get_connection().commit.called


@pytest.mark.skip(reason="Requires real PostgreSQL database")
def test_adapter_roundtrip_integration():
    """
    Integration test: Save and load SymbolGraph.

    This test requires a real PostgreSQL database with the schema.
    Run migration 004_create_symbol_graph_tables.sql first.
    """
    from src.infra.storage.postgres import PostgresStore

    # Setup (requires real DB connection)
    postgres = PostgresStore(
        host="localhost",
        port=5432,
        database="codegraph_test",
        user="postgres",
        password="postgres",
    )
    adapter = PostgreSQLSymbolGraphAdapter(postgres)

    # Create test graph
    graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-roundtrip",
    )

    # Add symbols
    symbol1 = Symbol(
        id="class:test:MyClass",
        kind=SymbolKind.CLASS,
        fqn="test.MyClass",
        name="MyClass",
        repo_id="test-repo",
        snapshot_id="snapshot-roundtrip",
        span=Span(start_line=1, end_line=10, start_col=0, end_col=4),
    )
    symbol2 = Symbol(
        id="function:test:MyClass.method",
        kind=SymbolKind.METHOD,
        fqn="test.MyClass.method",
        name="method",
        repo_id="test-repo",
        snapshot_id="snapshot-roundtrip",
        span=Span(start_line=5, end_line=8, start_col=4, end_col=8),
        parent_id=symbol1.id,
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

    # Save
    adapter.save(graph)

    # Load
    loaded_graph = adapter.load("test-repo", "snapshot-roundtrip")

    # Verify
    assert loaded_graph.repo_id == "test-repo"
    assert loaded_graph.snapshot_id == "snapshot-roundtrip"
    assert loaded_graph.symbol_count == 2
    assert loaded_graph.relation_count == 1

    # Check symbol
    loaded_symbol = loaded_graph.get_symbol(symbol1.id)
    assert loaded_symbol is not None
    assert loaded_symbol.kind == SymbolKind.CLASS
    assert loaded_symbol.fqn == "test.MyClass"
    assert loaded_symbol.span.start_line == 1

    # Check relation
    loaded_relations = loaded_graph.get_relations_by_kind(RelationKind.CONTAINS)
    assert len(loaded_relations) == 1
    assert loaded_relations[0].source_id == symbol1.id

    # Check indexes were rebuilt
    children = loaded_graph.indexes.get_children(symbol1.id)
    assert symbol2.id in children

    # Cleanup
    adapter.delete("test-repo", "snapshot-roundtrip")
