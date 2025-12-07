"""
Tests for SearchIndex models and builder
"""

from src.foundation.search_index import SearchableSymbol, SearchIndexBuilder
from src.foundation.symbol_graph import (
    Relation,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)


def test_searchable_symbol_creation():
    """Test SearchableSymbol creation with ranking signals"""
    symbol = SearchableSymbol(
        id="function:repo:path:my_func",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule.my_func",
        name="my_func",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
        call_count=10,
        import_count=5,
        reference_count=2,
        is_public=True,
        is_exported=True,
        complexity=3,
        loc=25,
        docstring="Test function",
        signature="def my_func(x: int) -> str",
    )

    assert symbol.id == "function:repo:path:my_func"
    assert symbol.call_count == 10
    assert symbol.import_count == 5
    assert symbol.is_public is True
    assert symbol.docstring == "Test function"


def test_searchable_symbol_relevance_score():
    """Test relevance score calculation"""
    # High-quality symbol (public, documented, frequently called)
    good_symbol = SearchableSymbol(
        id="function:repo:path:good",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule.good",
        name="good",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
        call_count=100,
        import_count=10,
        reference_count=5,
        is_public=True,
        is_exported=True,
        docstring="Well documented",
        complexity=2,
    )

    # Low-quality symbol (private, undocumented, complex)
    bad_symbol = SearchableSymbol(
        id="function:repo:path:_bad",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule._bad",
        name="_bad",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
        call_count=1,
        import_count=0,
        reference_count=0,
        is_public=False,
        is_exported=False,
        docstring=None,
        complexity=25,
    )

    assert good_symbol.relevance_score() > bad_symbol.relevance_score()


def test_search_index_builder():
    """Test SearchIndexBuilder converts SymbolGraph to SearchIndex"""
    # Create SymbolGraph
    symbol_graph = SymbolGraph(
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

    symbol_graph.symbols[caller.id] = caller
    symbol_graph.symbols[callee.id] = callee

    # Add CALLS relation
    call_relation = Relation(
        id="edge:calls:0",
        kind=RelationKind.CALLS,
        source_id=caller.id,
        target_id=callee.id,
    )
    symbol_graph.relations.append(call_relation)

    # Build SearchIndex
    builder = SearchIndexBuilder()
    search_index = builder.build_from_symbol_graph(symbol_graph)

    # Verify conversion
    assert search_index.repo_id == "test-repo"
    assert search_index.snapshot_id == "snapshot-1"
    assert search_index.symbol_count == 2
    assert search_index.relation_count == 1

    # Check ranking signals
    callee_symbol = search_index.get_symbol(callee.id)
    assert callee_symbol is not None
    assert callee_symbol.call_count == 1  # Called once by caller
    assert callee_symbol.is_public is True  # No underscore prefix


def test_search_index_builder_ranking_signals():
    """Test ranking signal calculation"""
    # Create SymbolGraph with multiple callers
    symbol_graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add target symbol
    target = Symbol(
        id="function:repo:path:target",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule.target",
        name="target",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )
    symbol_graph.symbols[target.id] = target

    # Add 10 callers
    for i in range(10):
        caller = Symbol(
            id=f"function:repo:path:caller{i}",
            kind=SymbolKind.FUNCTION,
            fqn=f"mymodule.caller{i}",
            name=f"caller{i}",
            repo_id="test-repo",
            snapshot_id="snapshot-1",
        )
        symbol_graph.symbols[caller.id] = caller

        # Add call relation
        relation = Relation(
            id=f"edge:calls:{i}",
            kind=RelationKind.CALLS,
            source_id=caller.id,
            target_id=target.id,
        )
        symbol_graph.relations.append(relation)

    # Build SearchIndex
    builder = SearchIndexBuilder()
    search_index = builder.build_from_symbol_graph(symbol_graph)

    # Check target has call_count = 10
    target_symbol = search_index.get_symbol(target.id)
    assert target_symbol is not None
    assert target_symbol.call_count == 10


def test_search_index_query_indexes():
    """Test query index building"""
    # Create SymbolGraph
    symbol_graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add symbols
    for i, name in enumerate(["foo", "foobar", "bar", "baz"]):
        symbol = Symbol(
            id=f"function:repo:path:{name}",
            kind=SymbolKind.FUNCTION,
            fqn=f"mymodule.{name}",
            name=name,
            repo_id="test-repo",
            snapshot_id="snapshot-1",
        )
        symbol_graph.symbols[symbol.id] = symbol

    # Build SearchIndex
    builder = SearchIndexBuilder()
    search_index = builder.build_from_symbol_graph(symbol_graph)

    # Check fuzzy index
    assert "foo" in search_index.indexes.fuzzy_index
    assert "foobar" in search_index.indexes.fuzzy_index

    # Check prefix index
    assert "f" in search_index.indexes.prefix_index
    assert "fo" in search_index.indexes.prefix_index
    assert "foo" in search_index.indexes.prefix_index

    # Check domain index
    assert "function" in search_index.indexes.domain_index
    assert len(search_index.indexes.domain_index["function"]) == 4


def test_search_index_search_by_name():
    """Test in-memory name search"""
    # Create SymbolGraph
    symbol_graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add symbols
    for name in ["foo", "foobar", "food", "bar"]:
        symbol = Symbol(
            id=f"function:repo:path:{name}",
            kind=SymbolKind.FUNCTION,
            fqn=f"mymodule.{name}",
            name=name,
            repo_id="test-repo",
            snapshot_id="snapshot-1",
        )
        symbol_graph.symbols[symbol.id] = symbol

    # Build SearchIndex
    builder = SearchIndexBuilder()
    search_index = builder.build_from_symbol_graph(symbol_graph)

    # Search by name (prefix match)
    results = search_index.search_by_name("foo", limit=10)
    assert len(results) == 3
    assert all(r.name.startswith("foo") for r in results)

    # No matches
    results = search_index.search_by_name("xyz", limit=10)
    assert len(results) == 0


def test_search_index_get_top_symbols():
    """Test getting top symbols by relevance"""
    # Create SymbolGraph
    symbol_graph = SymbolGraph(
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )

    # Add popular symbol
    popular = Symbol(
        id="function:repo:path:popular",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule.popular",
        name="popular",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )
    symbol_graph.symbols[popular.id] = popular

    # Add unpopular symbol
    unpopular = Symbol(
        id="function:repo:path:_unpopular",
        kind=SymbolKind.FUNCTION,
        fqn="mymodule._unpopular",
        name="_unpopular",
        repo_id="test-repo",
        snapshot_id="snapshot-1",
    )
    symbol_graph.symbols[unpopular.id] = unpopular

    # Add 10 calls to popular
    for i in range(10):
        caller = Symbol(
            id=f"function:repo:path:caller{i}",
            kind=SymbolKind.FUNCTION,
            fqn=f"mymodule.caller{i}",
            name=f"caller{i}",
            repo_id="test-repo",
            snapshot_id="snapshot-1",
        )
        symbol_graph.symbols[caller.id] = caller

        relation = Relation(
            id=f"edge:calls:{i}",
            kind=RelationKind.CALLS,
            source_id=caller.id,
            target_id=popular.id,
        )
        symbol_graph.relations.append(relation)

    # Build SearchIndex
    builder = SearchIndexBuilder()
    search_index = builder.build_from_symbol_graph(symbol_graph)

    # Get top symbols
    top_symbols = search_index.get_top_symbols(limit=5)

    # Popular should be first
    assert top_symbols[0].id == popular.id
    assert top_symbols[0].call_count == 10
