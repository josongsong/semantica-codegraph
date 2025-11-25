"""
IndexingService Error Handling Tests

Tests error handling and partial failure resilience:
- Individual index failures don't break entire operation
- Error collection and reporting
- Graceful degradation with missing indexes
- Weighted search with partial index availability
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.foundation.chunk.models import Chunk
from src.foundation.graph.models import GraphDocument, GraphIndex
from src.index.common.documents import SearchHit
from src.index.service import IndexingService

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def sample_chunks():
    """Create sample chunks for testing."""
    return [
        Chunk(
            chunk_id="chunk:1",
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
            parent_id="chunk:file:1",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="func:search_route",
            symbol_owner_id=None,
            summary="Search route endpoint",
            importance=0.8,
            attrs={},
        ),
    ]


@pytest.fixture
def sample_source_codes():
    """Create sample source code mapping."""
    return {
        "chunk:1": "def search_route(query: str):\n    return search(query)",
    }


@pytest.fixture
def sample_graph_doc():
    """Create minimal GraphDocument for testing."""
    return GraphDocument(
        repo_id="test_repo",
        snapshot_id="commit123",
        graph_nodes={},
        graph_edges=[],
        indexes=GraphIndex(),
    )


# ============================================================
# Error Handling Tests - Full Indexing
# ============================================================


@pytest.mark.asyncio
async def test_lexical_index_failure_doesnt_break_others(sample_chunks, sample_source_codes):
    """Test that lexical index failure doesn't prevent other indexes from completing."""
    # Setup indexes
    failing_lexical = MagicMock()
    failing_lexical.reindex_repo = AsyncMock(side_effect=Exception("Zoekt connection failed"))

    working_vector = MagicMock()
    working_vector.index = AsyncMock()

    working_symbol = MagicMock()
    working_symbol.index_graph = AsyncMock()

    # Create service
    service = IndexingService(
        lexical_index=failing_lexical,
        vector_index=working_vector,
        symbol_index=working_symbol,
    )

    # Index should complete despite lexical failure
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        source_codes=sample_source_codes,
        graph_doc=sample_graph_doc,
    )

    # Verify vector and symbol indexes were still called
    working_vector.index.assert_called_once()
    working_symbol.index_graph.assert_called_once()


@pytest.mark.asyncio
async def test_vector_index_failure_doesnt_break_others(sample_chunks, sample_source_codes):
    """Test that vector index failure doesn't prevent other indexes from completing."""
    # Setup indexes
    working_lexical = MagicMock()
    working_lexical.reindex_repo = AsyncMock()

    failing_vector = MagicMock()
    failing_vector.index = AsyncMock(side_effect=Exception("Qdrant connection timeout"))

    working_symbol = MagicMock()
    working_symbol.index_graph = AsyncMock()

    # Create service
    service = IndexingService(
        lexical_index=working_lexical,
        vector_index=failing_vector,
        symbol_index=working_symbol,
    )

    # Index should complete despite vector failure
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        source_codes=sample_source_codes,
        graph_doc=sample_graph_doc,
    )

    # Verify other indexes were still called
    working_lexical.reindex_repo.assert_called_once()
    working_symbol.index_graph.assert_called_once()


@pytest.mark.asyncio
async def test_symbol_index_failure_doesnt_break_others(sample_chunks, sample_source_codes):
    """Test that symbol index failure doesn't prevent other indexes from completing."""
    # Setup indexes
    working_lexical = MagicMock()
    working_lexical.reindex_repo = AsyncMock()

    working_vector = MagicMock()
    working_vector.index = AsyncMock()

    failing_symbol = MagicMock()
    failing_symbol.index_graph = AsyncMock(side_effect=Exception("Kuzu database locked"))

    # Create service
    service = IndexingService(
        lexical_index=working_lexical,
        vector_index=working_vector,
        symbol_index=failing_symbol,
    )

    # Index should complete despite symbol failure
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        source_codes=sample_source_codes,
        graph_doc=sample_graph_doc,
    )

    # Verify other indexes were still called
    working_lexical.reindex_repo.assert_called_once()
    working_vector.index.assert_called_once()


@pytest.mark.asyncio
async def test_fuzzy_index_failure_doesnt_break_others(sample_chunks, sample_source_codes):
    """Test that fuzzy index failure doesn't prevent other indexes from completing."""
    # Setup indexes
    working_vector = MagicMock()
    working_vector.index = AsyncMock()

    failing_fuzzy = MagicMock()
    failing_fuzzy.index = AsyncMock(side_effect=Exception("PostgreSQL pg_trgm not installed"))

    # Create service
    service = IndexingService(
        lexical_index=None,
        vector_index=working_vector,
        symbol_index=None,
        fuzzy_index=failing_fuzzy,
    )

    # Index should complete despite fuzzy failure
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        source_codes=sample_source_codes,
    )

    # Verify vector index was still called
    working_vector.index.assert_called_once()


@pytest.mark.asyncio
async def test_domain_index_failure_doesnt_break_others(sample_chunks, sample_source_codes):
    """Test that domain index failure doesn't prevent other indexes from completing."""
    # Setup indexes
    working_vector = MagicMock()
    working_vector.index = AsyncMock()

    failing_domain = MagicMock()
    failing_domain.index = AsyncMock(side_effect=Exception("Full-text search not configured"))

    # Create service
    service = IndexingService(
        lexical_index=None,
        vector_index=working_vector,
        symbol_index=None,
        domain_index=failing_domain,
    )

    # Index should complete despite domain failure
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        source_codes=sample_source_codes,
    )

    # Verify vector index was still called
    working_vector.index.assert_called_once()


@pytest.mark.asyncio
async def test_multiple_index_failures(sample_chunks, sample_source_codes):
    """Test that multiple index failures are handled gracefully."""
    # Setup indexes - all failing except vector
    failing_lexical = MagicMock()
    failing_lexical.reindex_repo = AsyncMock(side_effect=Exception("Lexical failed"))

    working_vector = MagicMock()
    working_vector.index = AsyncMock()

    failing_symbol = MagicMock()
    failing_symbol.index_graph = AsyncMock(side_effect=Exception("Symbol failed"))

    failing_fuzzy = MagicMock()
    failing_fuzzy.index = AsyncMock(side_effect=Exception("Fuzzy failed"))

    # Create service
    service = IndexingService(
        lexical_index=failing_lexical,
        vector_index=working_vector,
        symbol_index=failing_symbol,
        fuzzy_index=failing_fuzzy,
    )

    # Should complete with only vector index succeeding
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=sample_chunks,
        source_codes=sample_source_codes,
        graph_doc=sample_graph_doc,
    )

    # Verify vector index was called
    working_vector.index.assert_called_once()


# ============================================================
# Error Handling Tests - Incremental Indexing
# ============================================================


@pytest.mark.asyncio
async def test_incremental_upsert_failure_handling(sample_chunks, sample_source_codes):
    """Test error handling in incremental indexing (upsert)."""
    # Setup indexes
    working_vector = MagicMock()
    working_vector.upsert = AsyncMock()

    failing_fuzzy = MagicMock()
    failing_fuzzy.upsert = AsyncMock(side_effect=Exception("Fuzzy upsert failed"))

    # Create service
    service = IndexingService(
        lexical_index=None,
        vector_index=working_vector,
        symbol_index=None,
        fuzzy_index=failing_fuzzy,
    )

    # Incremental index should handle failure
    await service.index_repo_incremental(
        repo_id="test_repo",
        snapshot_id="commit123",
        changed_chunks=sample_chunks,
        deleted_chunk_ids=[],
        source_codes=sample_source_codes,
    )

    # Verify vector index was still called
    working_vector.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_incremental_delete_failure_handling(sample_chunks):
    """Test error handling in incremental delete operations."""
    # Setup indexes
    working_vector = MagicMock()
    working_vector.delete = AsyncMock()

    failing_fuzzy = MagicMock()
    failing_fuzzy.delete = AsyncMock(side_effect=Exception("Fuzzy delete failed"))

    # Create service
    service = IndexingService(
        lexical_index=None,
        vector_index=working_vector,
        symbol_index=None,
        fuzzy_index=failing_fuzzy,
    )

    # Incremental delete should handle failure
    await service.index_repo_incremental(
        repo_id="test_repo",
        snapshot_id="commit123",
        changed_chunks=[],
        deleted_chunk_ids=["chunk:1", "chunk:2"],
        source_codes={},
    )

    # Verify vector index was still called
    working_vector.delete.assert_called_once()


# ============================================================
# Search with Partial Index Availability
# ============================================================


@pytest.mark.asyncio
async def test_search_with_failing_lexical_index():
    """Test search works when lexical index fails."""
    # Setup indexes
    failing_lexical = MagicMock()
    failing_lexical.search = AsyncMock(side_effect=Exception("Lexical search failed"))

    working_vector = MagicMock()
    working_vector.search = AsyncMock(
        return_value=[
            SearchHit(
                chunk_id="chunk:1",
                file_path="test.py",
                symbol_id="sym:1",
                score=0.85,
                source="vector",
                metadata={},
            )
        ]
    )

    # Create service
    service = IndexingService(
        lexical_index=failing_lexical,
        vector_index=working_vector,
        symbol_index=None,
    )

    # Search should return vector results despite lexical failure
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="test query",
        weights={"lexical": 0.5, "vector": 0.5},
    )

    # Should have results from vector
    assert len(results) > 0
    assert all(hit.source == "vector" for hit in results)


@pytest.mark.asyncio
async def test_search_with_failing_vector_index():
    """Test search works when vector index fails."""
    # Setup indexes
    working_lexical = MagicMock()
    working_lexical.search = AsyncMock(
        return_value=[
            SearchHit(
                chunk_id="chunk:1",
                file_path="test.py",
                symbol_id=None,
                score=0.75,
                source="lexical",
                metadata={},
            )
        ]
    )

    failing_vector = MagicMock()
    failing_vector.search = AsyncMock(side_effect=Exception("Vector search timeout"))

    # Create service
    service = IndexingService(
        lexical_index=working_lexical,
        vector_index=failing_vector,
        symbol_index=None,
    )

    # Search should return lexical results despite vector failure
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="test query",
        weights={"lexical": 0.5, "vector": 0.5},
    )

    # Should have results from lexical
    assert len(results) > 0
    assert all(hit.source == "lexical" for hit in results)


@pytest.mark.asyncio
async def test_search_with_multiple_index_failures():
    """Test search works when multiple indexes fail but at least one succeeds."""
    # Setup indexes
    failing_lexical = MagicMock()
    failing_lexical.search = AsyncMock(side_effect=Exception("Lexical failed"))

    failing_vector = MagicMock()
    failing_vector.search = AsyncMock(side_effect=Exception("Vector failed"))

    working_symbol = MagicMock()
    working_symbol.search = AsyncMock(
        return_value=[
            SearchHit(
                chunk_id="chunk:1",
                file_path="test.py",
                symbol_id="sym:1",
                score=0.9,
                source="symbol",
                metadata={"name": "test_func"},
            )
        ]
    )

    # Create service
    service = IndexingService(
        lexical_index=failing_lexical,
        vector_index=failing_vector,
        symbol_index=working_symbol,
    )

    # Search should return symbol results
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="test_func",
        weights={"lexical": 0.33, "vector": 0.33, "symbol": 0.34},
    )

    # Should have results from symbol
    assert len(results) > 0
    assert all(hit.source == "symbol" for hit in results)


@pytest.mark.asyncio
async def test_search_with_all_indexes_failing():
    """Test search returns empty list when all indexes fail."""
    # Setup indexes - all failing
    failing_lexical = MagicMock()
    failing_lexical.search = AsyncMock(side_effect=Exception("Lexical failed"))

    failing_vector = MagicMock()
    failing_vector.search = AsyncMock(side_effect=Exception("Vector failed"))

    failing_symbol = MagicMock()
    failing_symbol.search = AsyncMock(side_effect=Exception("Symbol failed"))

    # Create service
    service = IndexingService(
        lexical_index=failing_lexical,
        vector_index=failing_vector,
        symbol_index=failing_symbol,
    )

    # Search should return empty list
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="test query",
        weights={"lexical": 0.33, "vector": 0.33, "symbol": 0.34},
    )

    assert results == []


# ============================================================
# Graceful Degradation Tests
# ============================================================


@pytest.mark.asyncio
async def test_indexing_with_no_indexes():
    """Test that indexing with no indexes configured doesn't raise errors."""
    # Create service with all indexes as None
    service = IndexingService(
        lexical_index=None,
        vector_index=None,
        symbol_index=None,
        fuzzy_index=None,
        domain_index=None,
    )

    # Should complete without errors
    await service.index_repo_full(
        repo_id="test_repo",
        snapshot_id="commit123",
        chunks=[],
    )

    # No assertions needed - just verifying no exception


@pytest.mark.asyncio
async def test_search_with_no_indexes():
    """Test that search with no indexes returns empty list."""
    # Create service with all indexes as None
    service = IndexingService(
        lexical_index=None,
        vector_index=None,
        symbol_index=None,
    )

    # Search should return empty list
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="test query",
        weights={},
    )

    assert results == []


@pytest.mark.asyncio
async def test_search_with_empty_weights():
    """Test search with empty weights dictionary."""
    working_vector = MagicMock()
    working_vector.search = AsyncMock(
        return_value=[
            SearchHit(
                chunk_id="chunk:1",
                file_path="test.py",
                symbol_id="sym:1",
                score=0.85,
                source="vector",
                metadata={},
            )
        ]
    )

    service = IndexingService(
        lexical_index=None,
        vector_index=working_vector,
        symbol_index=None,
    )

    # Search with empty weights should handle gracefully
    results = await service.search(
        repo_id="test_repo",
        snapshot_id="commit123",
        query="test",
        weights={},  # Empty weights
    )

    # Should return results (implementation may vary)
    assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
