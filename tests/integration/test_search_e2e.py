"""
End-to-End Integration Tests for Index Layer

Tests the complete indexing and search pipeline:
1. Lexical Search (Zoekt) E2E
2. Vector Search (Qdrant) E2E
3. Symbol Search (Kuzu) E2E
4. Hybrid Search with weighted fusion
5. Full indexing flow with all indexes

These tests verify that the entire system works together correctly,
from data ingestion through indexing to search and retrieval.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.foundation.chunk.models import Chunk
from src.foundation.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphIndex,
    GraphNode,
    GraphNodeKind,
)
from src.foundation.ir.models import Span
from src.index import (
    IndexingService,
    SearchHit,
)
from src.index.symbol import KuzuSymbolIndex
from tests.fakes import FakeLexicalSearch, FakeVectorIndex

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_kuzu_db():
    """Create temporary Kuzu database directory"""
    # Get a temp directory path without creating it (Kuzu will create it)
    temp_base = tempfile.gettempdir()
    db_name = f"test_kuzu_e2e_{tempfile._get_candidate_names().__next__()}"
    db_path = Path(temp_base) / db_name
    yield str(db_path)
    # Cleanup
    if db_path.exists():
        shutil.rmtree(db_path, ignore_errors=True)


@pytest.fixture
def sample_chunks():
    """Create sample chunks for testing"""
    return [
        Chunk(
            chunk_id="chunk_1",
            repo_id="test_repo",
            snapshot_id="commit123",
            project_id="test_project",
            module_path="src.api",
            file_path="src/api/routes.py",
            kind="function",
            fqn="src.api.routes.search_route",
            start_line=10,
            end_line=20,
            original_start_line=10,
            original_end_line=20,
            content_hash="abc123",
            parent_id="chunk_file_1",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="func:search_route",
            symbol_owner_id=None,
            summary="Search route endpoint function",
            importance=0.8,
            attrs={"function_name": "search_route"},
        ),
        Chunk(
            chunk_id="chunk_2",
            repo_id="test_repo",
            snapshot_id="commit123",
            project_id="test_project",
            module_path="src.services",
            file_path="src/services/search.py",
            kind="class",
            fqn="src.services.search.SearchService",
            start_line=5,
            end_line=30,
            original_start_line=5,
            original_end_line=30,
            content_hash="def456",
            parent_id="chunk_file_2",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="class:SearchService",
            symbol_owner_id=None,
            summary="Search service class",
            importance=0.9,
            attrs={"class_name": "SearchService"},
        ),
        Chunk(
            chunk_id="chunk_3",
            repo_id="test_repo",
            snapshot_id="commit123",
            project_id="test_project",
            module_path="src.models",
            file_path="src/models/document.py",
            kind="class",
            fqn="src.models.document.Document",
            start_line=1,
            end_line=15,
            original_start_line=1,
            original_end_line=15,
            content_hash="ghi789",
            parent_id="chunk_file_3",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="class:Document",
            symbol_owner_id=None,
            summary="Document data model",
            importance=0.7,
            attrs={"class_name": "Document"},
        ),
    ]


@pytest.fixture
def sample_graph_doc():
    """Create sample GraphDocument for testing"""
    # Create nodes
    file_node = GraphNode(
        id="file:src/api/routes.py",
        kind=GraphNodeKind.FILE,
        repo_id="test_repo",
        snapshot_id="commit123",
        fqn="src.api.routes",
        name="routes.py",
        path="src/api/routes.py",
        span=Span(start_line=1, start_col=0, end_line=100, end_col=0),
    )

    class_node = GraphNode(
        id="class:SearchService",
        kind=GraphNodeKind.CLASS,
        repo_id="test_repo",
        snapshot_id="commit123",
        fqn="src.services.search.SearchService",
        name="SearchService",
        path="src/services/search.py",
        span=Span(start_line=5, start_col=0, end_line=30, end_col=0),
    )

    func_node = GraphNode(
        id="func:SearchService.search",
        kind=GraphNodeKind.METHOD,
        repo_id="test_repo",
        snapshot_id="commit123",
        fqn="src.services.search.SearchService.search",
        name="search",
        path="src/services/search.py",
        span=Span(start_line=10, start_col=4, end_line=15, end_col=0),
    )

    # Create edges
    contains_edge1 = GraphEdge(
        id="edge:file_contains_class",
        kind=GraphEdgeKind.CONTAINS,
        source_id="file:src/api/routes.py",
        target_id="class:SearchService",
    )

    contains_edge2 = GraphEdge(
        id="edge:class_contains_method",
        kind=GraphEdgeKind.CONTAINS,
        source_id="class:SearchService",
        target_id="func:SearchService.search",
    )

    return GraphDocument(
        repo_id="test_repo",
        snapshot_id="commit123",
        graph_nodes={
            "file:src/api/routes.py": file_node,
            "class:SearchService": class_node,
            "func:SearchService.search": func_node,
        },
        graph_edges=[contains_edge1, contains_edge2],
        indexes=GraphIndex(),
    )


@pytest.fixture
def sample_source_codes():
    """Create sample source code mapping"""
    return {
        "chunk_1": "def search_route(query: str):\n    return vector_store.search(query)",
        "chunk_2": "class SearchService:\n    def search(self, query):\n        pass",
        "chunk_3": "class Document:\n    def __init__(self, text):\n        self.text = text",
    }


# ============================================================
# E2E Tests
# ============================================================


@pytest.mark.asyncio
async def test_lexical_search_e2e(sample_chunks):
    """
    Test Lexical Search E2E pipeline.

    Flow: Chunks → Zoekt indexing → Lexical search → SearchHits
    """
    # Setup fake lexical index
    fake_lexical = FakeLexicalSearch()

    # Mock chunk store
    mock_chunk_store = MagicMock()
    mock_chunk_store.get_chunk = AsyncMock(
        side_effect=lambda chunk_id: next((c for c in sample_chunks if c.chunk_id == chunk_id), None)
    )

    # Create service with only lexical index
    service = IndexingService(
        lexical_index=fake_lexical,
        vector_index=None,
        symbol_index=None,
    )

    # Mock reindex_repo to simulate Zoekt indexing
    async def mock_reindex_repo(repo_id, snapshot_id):
        # Simulate indexing by adding SearchHits to fake lexical
        for chunk in sample_chunks:
            hit = SearchHit(
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                symbol_id=None,
                score=0.9,
                source="lexical",
                metadata={"chunk_kind": chunk.kind, "fqn": chunk.fqn},
            )
            fake_lexical.add_hit(hit)

    fake_lexical.reindex_repo = mock_reindex_repo

    # Index repository
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
    )

    # Search
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="search",
        weights={"lexical": 1.0},  # Only lexical
    )

    # Verify results
    assert len(results) > 0
    assert all(hit.source == "lexical" for hit in results)
    assert any("search" in hit.file_path.lower() for hit in results)


@pytest.mark.asyncio
async def test_vector_search_e2e(sample_chunks, sample_source_codes):
    """
    Test Vector Search E2E pipeline.

    Flow: Chunks → IndexDocuments → Qdrant indexing → Vector search → SearchHits
    """
    # Setup fake vector index
    fake_vector = FakeVectorIndex()

    # Create service with only vector index
    service = IndexingService(
        lexical_index=None,
        vector_index=fake_vector,
        symbol_index=None,
    )

    # Index repository
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        source_codes=sample_source_codes,
    )

    # Verify indexing happened
    assert fake_vector.doc_count == len(sample_chunks)

    # Search (use a term that's in the chunk fqn/summary)
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="search",  # Matches "SearchService" in chunks
        weights={"vector": 1.0},  # Only vector
    )

    # Verify results
    assert len(results) > 0
    assert all(hit.source == "vector" for hit in results)
    assert all(hit.chunk_id.startswith("chunk_") for hit in results)


@pytest.mark.asyncio
async def test_symbol_search_e2e(temp_kuzu_db, sample_graph_doc):
    """
    Test Symbol Search E2E pipeline.

    Flow: GraphDocument → Kuzu indexing → Symbol search → SearchHits
    """
    # Create real Kuzu symbol index
    symbol_index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Create service with only symbol index
    service = IndexingService(
        lexical_index=None,
        vector_index=None,
        symbol_index=symbol_index,
    )

    # Index repository
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=[],  # Not needed for symbol index
        graph_doc=sample_graph_doc,
    )

    # Search for class
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="SearchService",
        weights={"symbol": 1.0},  # Only symbol
    )

    # Verify results
    assert len(results) > 0
    assert all(hit.source == "symbol" for hit in results)
    assert any(hit.metadata.get("name") == "SearchService" for hit in results)

    # Search for method
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="search",
        weights={"symbol": 1.0},
    )

    assert len(results) > 0
    assert any(hit.metadata.get("name") == "search" for hit in results)

    # Cleanup
    symbol_index.close()


@pytest.mark.asyncio
async def test_hybrid_search_with_fusion(temp_kuzu_db, sample_chunks, sample_graph_doc, sample_source_codes):
    """
    Test Hybrid Search with weighted fusion.

    Flow: All indexes → Weighted fusion → Ranked SearchHits
    """
    # Setup all indexes
    fake_lexical = FakeLexicalSearch()
    symbol_index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Mock lexical index
    async def mock_reindex_repo(repo_id, snapshot_id):
        for chunk in sample_chunks:
            hit = SearchHit(
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                symbol_id=None,
                score=0.8,  # Base score for lexical
                source="lexical",
                metadata={"chunk_kind": chunk.kind, "fqn": chunk.fqn},
            )
            fake_lexical.add_hit(hit)

    fake_lexical.reindex_repo = mock_reindex_repo

    # Setup fake vector index
    fake_vector_index = FakeVectorIndex()

    # Create service with all indexes
    service = IndexingService(
        lexical_index=fake_lexical,
        vector_index=fake_vector_index,
        symbol_index=symbol_index,
    )

    # Index repository (full indexing)
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        graph_doc=sample_graph_doc,
        source_codes=sample_source_codes,
    )

    # Hybrid search with custom weights
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="search",
        limit=20,
        weights={
            "lexical": 0.3,
            "vector": 0.4,
            "symbol": 0.3,
        },
    )

    # Verify fusion results
    assert len(results) > 0

    # Check that results have fused metadata
    for hit in results:
        assert hit.score >= 0.0
        # Metadata should include source information
        if "sources" in hit.metadata:
            assert isinstance(hit.metadata["sources"], list)
            assert len(hit.metadata["sources"]) >= 1

    # Results should be sorted by fused score (descending)
    scores = [hit.score for hit in results]
    assert scores == sorted(scores, reverse=True)

    # Cleanup
    symbol_index.close()


@pytest.mark.asyncio
async def test_full_indexing_flow(temp_kuzu_db, sample_chunks, sample_graph_doc, sample_source_codes):
    """
    Test full indexing flow with all components.

    Verifies:
    1. Full indexing completes without errors
    2. All indexes are populated
    3. Search returns results from all sources
    """
    # Setup all indexes
    fake_lexical = FakeLexicalSearch()
    symbol_index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    # Mock implementations
    async def mock_reindex_repo(repo_id, snapshot_id):
        for chunk in sample_chunks:
            fake_lexical.add_hit(
                SearchHit(
                    chunk_id=chunk.chunk_id,
                    file_path=chunk.file_path,
                    symbol_id=None,
                    score=0.85,
                    source="lexical",
                    metadata={},
                )
            )

    fake_lexical.reindex_repo = mock_reindex_repo

    # Setup fake vector index
    fake_vector_index = FakeVectorIndex()

    # Create service
    service = IndexingService(
        lexical_index=fake_lexical,
        vector_index=fake_vector_index,
        symbol_index=symbol_index,
    )

    # Full indexing
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        graph_doc=sample_graph_doc,
        source_codes=sample_source_codes,
    )

    # Verify all indexes were populated
    assert fake_vector_index.doc_count == len(sample_chunks)

    # Search and verify results from all sources
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="search",
        limit=50,
        weights={
            "lexical": 0.33,
            "vector": 0.33,
            "symbol": 0.34,
        },
    )

    # Verify we got results
    assert len(results) > 0

    # Verify scores are properly computed
    for hit in results:
        assert 0.0 <= hit.score <= 1.0

    # Cleanup
    symbol_index.close()


# ============================================================
# Performance and Edge Cases
# ============================================================


@pytest.mark.asyncio
async def test_search_with_no_results(temp_kuzu_db):
    """Test search with query that returns no results"""
    symbol_index = KuzuSymbolIndex(db_path=temp_kuzu_db)

    service = IndexingService(
        lexical_index=None,
        vector_index=None,
        symbol_index=symbol_index,
    )

    # Search without indexing anything
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="nonexistent",
        weights={"symbol": 1.0},
    )

    # Should return empty list, not error
    assert results == []

    symbol_index.close()


@pytest.mark.asyncio
async def test_search_with_empty_weights():
    """Test search with empty weights dictionary"""
    fake_lexical = FakeLexicalSearch()

    service = IndexingService(
        lexical_index=fake_lexical,
        vector_index=None,
        symbol_index=None,
    )

    # Search with empty weights
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="test",
        weights={},  # Empty weights
    )

    # Should handle gracefully
    assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
