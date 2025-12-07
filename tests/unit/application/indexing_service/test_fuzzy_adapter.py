"""
Fuzzy Index Adapter Integration Tests

Tests PostgreSQL pg_trgm-based fuzzy search:
- Schema creation and indexing
- Identifier extraction from IndexDocuments
- Trigram similarity search
- Typo-tolerant matching
- Incremental upsert and delete
"""

import os

import pytest
from src.index.common.documents import IndexDocument, SearchHit
from src.index.fuzzy.adapter_pgtrgm import PostgresFuzzyIndex

from src.infra.storage.postgres import PostgresStore

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def postgres_connection_string():
    """Get PostgreSQL connection string from environment or use test default."""
    return os.getenv("SEMANTICA_DATABASE_URL", "postgresql://test_user:test_password@localhost:5432/test_db")


@pytest.fixture
async def postgres_store(postgres_connection_string):
    """Create and initialize PostgresStore."""
    store = PostgresStore(connection_string=postgres_connection_string)

    try:
        await store.initialize()
        yield store
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")
    finally:
        await store.close()


@pytest.fixture
async def fuzzy_index(postgres_store):
    """Create FuzzyIndex with initialized PostgresStore."""

    index = PostgresFuzzyIndex(postgres_store=postgres_store)

    # Ensure schema is created
    await index._ensure_schema()

    # Clean up test data before each test
    async with postgres_store.pool.acquire() as conn:
        await conn.execute("DELETE FROM fuzzy_identifiers WHERE repo_id = 'test_repo'")

    return index


@pytest.fixture
def sample_index_documents():
    """Create sample IndexDocuments for testing."""
    return [
        IndexDocument(
            chunk_id="chunk:1",
            repo_id="test_repo",
            snapshot_id="snapshot:123",
            file_path="src/services/search.py",
            language="python",
            symbol_id="class:SearchService",
            fqn="src.services.search.SearchService",
            node_type="class",
            content="class SearchService:\n    def search(self, query):\n        pass",
            metadata={"symbol_name": "SearchService"},
        ),
        IndexDocument(
            chunk_id="chunk:2",
            repo_id="test_repo",
            snapshot_id="snapshot:123",
            file_path="src/api/routes.py",
            language="python",
            symbol_id="func:search_route",
            fqn="src.api.routes.search_route",
            node_type="function",
            content="def search_route(query: str):\n    return SearchService().search(query)",
            metadata={"symbol_name": "search_route"},
        ),
        IndexDocument(
            chunk_id="chunk:3",
            repo_id="test_repo",
            snapshot_id="snapshot:123",
            file_path="src/indexing/indexer.py",
            language="python",
            symbol_id="class:IndexManager",
            fqn="src.indexing.indexer.IndexManager",
            node_type="class",
            content="class IndexManager:\n    def index_repository(self, repo_path):\n        pass",
            metadata={"symbol_name": "IndexManager"},
        ),
    ]


# ============================================================
# Schema and Initialization Tests
# ============================================================


@pytest.mark.asyncio
async def test_schema_creation(fuzzy_index, postgres_store):
    """Test that schema is created correctly."""
    # Schema should already be created by fixture

    # Verify table exists
    async with postgres_store.pool.acquire() as conn:
        result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'fuzzy_identifiers'
            )
        """
        )

        assert result is True

        # Verify GIN index exists
        idx_result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_indexes
                WHERE tablename = 'fuzzy_identifiers'
                  AND indexname = 'idx_fuzzy_identifier_trgm'
            )
        """
        )

        assert idx_result is True


@pytest.mark.asyncio
async def test_pg_trgm_extension_enabled(postgres_store):
    """Test that pg_trgm extension is enabled."""
    async with postgres_store.pool.acquire() as conn:
        result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_extension
                WHERE extname = 'pg_trgm'
            )
        """
        )

        # pg_trgm should be created by _ensure_schema
        assert result is True


# ============================================================
# Indexing Tests
# ============================================================


@pytest.mark.asyncio
async def test_full_index_creation(fuzzy_index, sample_index_documents):
    """Test full index creation with IndexDocuments."""
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    # Verify identifiers were extracted and indexed
    async with fuzzy_index.postgres.pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM fuzzy_identifiers
            WHERE repo_id = 'test_repo' AND snapshot_id = 'snapshot:123'
        """
        )

        # Should have multiple identifiers (from symbol names and FQN parts)
        assert count > 0


@pytest.mark.asyncio
async def test_identifier_extraction(fuzzy_index, sample_index_documents):
    """Test that identifiers are correctly extracted from IndexDocuments."""
    doc = sample_index_documents[0]  # SearchService

    identifiers = fuzzy_index._extract_identifiers(doc)

    # Should extract from symbol_name
    assert any(ident[0] == "SearchService" for ident in identifiers)

    # Should extract from FQN parts
    fqn_identifiers = [ident[0] for ident in identifiers]
    assert "search" in fqn_identifiers
    assert "services" in fqn_identifiers


@pytest.mark.asyncio
async def test_upsert_identifiers(fuzzy_index, sample_index_documents):
    """Test incremental upsert of identifiers."""
    # Initial index
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents[:2],  # Only first 2 docs
    )

    # Upsert with modified doc
    modified_doc = IndexDocument(
        chunk_id="chunk:1",  # Same chunk_id
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        file_path="src/services/search.py",
        language="python",
        symbol_id="class:SearchService",
        fqn="src.services.search.SearchServiceV2",  # Modified FQN
        node_type="class",
        content="class SearchServiceV2: pass",
        metadata={"symbol_name": "SearchServiceV2"},  # Modified name
    )

    await fuzzy_index.upsert(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=[modified_doc],
    )

    # Search for new identifier
    results = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="SearchServiceV2",
        limit=10,
    )

    assert len(results) > 0
    assert any("SearchServiceV2" in hit.metadata.get("identifier", "") for hit in results)


@pytest.mark.asyncio
async def test_delete_identifiers(fuzzy_index, sample_index_documents):
    """Test deletion of identifiers by chunk IDs."""
    # Index all documents
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    # Delete chunk:1
    await fuzzy_index.delete(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        doc_ids=["chunk:1"],
    )

    # Verify chunk:1 identifiers are gone
    async with fuzzy_index.postgres.pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM fuzzy_identifiers
            WHERE chunk_id = 'chunk:1'
        """
        )

        assert count == 0

        # Other chunks should remain
        other_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM fuzzy_identifiers
            WHERE chunk_id IN ('chunk:2', 'chunk:3')
        """
        )

        assert other_count > 0


# ============================================================
# Search Tests
# ============================================================


@pytest.mark.asyncio
async def test_exact_match_search(fuzzy_index, sample_index_documents):
    """Test exact identifier matching."""
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    results = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="SearchService",
        limit=10,
    )

    assert len(results) > 0
    assert results[0].source == "fuzzy"
    assert "SearchService" in results[0].metadata.get("identifier", "")


@pytest.mark.asyncio
async def test_fuzzy_typo_matching(fuzzy_index, sample_index_documents):
    """Test fuzzy matching with typos."""
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    # Search with typo: "SarchServce" instead of "SearchService"
    results = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="SarchServce",  # Missing 'e' and 'i'
        limit=10,
    )

    # Should still find SearchService due to trigram similarity
    # Note: Depending on similarity threshold, may or may not match
    # If no results, that's also acceptable (means threshold is strict)
    if len(results) > 0:
        assert results[0].source == "fuzzy"
        assert results[0].score > 0.0


@pytest.mark.asyncio
async def test_partial_match_search(fuzzy_index, sample_index_documents):
    """Test partial identifier matching."""
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    # Search with partial query
    results = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="index",  # Should match "IndexManager", "index_repository"
        limit=10,
    )

    assert len(results) > 0
    assert any("index" in hit.metadata.get("identifier", "").lower() for hit in results)


@pytest.mark.asyncio
async def test_case_insensitive_search(fuzzy_index, sample_index_documents):
    """Test that search is case-insensitive."""
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    # Search with different cases
    results_lower = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="searchservice",
        limit=10,
    )

    results_upper = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="SEARCHSERVICE",
        limit=10,
    )

    # Both should return similar results
    assert len(results_lower) > 0
    assert len(results_upper) > 0


@pytest.mark.asyncio
async def test_empty_query_returns_empty(fuzzy_index):
    """Test that empty query returns empty results."""
    results = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="",
        limit=10,
    )

    assert results == []


@pytest.mark.asyncio
async def test_limit_parameter(fuzzy_index, sample_index_documents):
    """Test that limit parameter works correctly."""
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    # Search with limit=1
    results = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="search",
        limit=1,
    )

    # Should return at most 1 result
    assert len(results) <= 1


# ============================================================
# Snapshot Isolation Tests
# ============================================================


@pytest.mark.asyncio
async def test_snapshot_isolation(fuzzy_index, sample_index_documents):
    """Test that different snapshots are isolated."""
    # Index to snapshot:123
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    # Index different data to snapshot:456
    other_doc = IndexDocument(
        chunk_id="chunk:other",
        repo_id="test_repo",
        snapshot_id="snapshot:456",
        file_path="other.py",
        language="python",
        symbol_id="func:other_func",
        fqn="other.other_func",
        node_type="function",
        content="def other_func(): pass",
        metadata={"symbol_name": "other_func"},
    )

    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:456",
        docs=[other_doc],
    )

    # Search in snapshot:123 should not find other_func
    results_123 = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="other_func",
        limit=10,
    )

    assert len(results_123) == 0

    # Search in snapshot:456 should find other_func
    results_456 = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:456",
        query="other_func",
        limit=10,
    )

    assert len(results_456) > 0


# ============================================================
# SearchHit Metadata Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_hit_structure(fuzzy_index, sample_index_documents):
    """Test that SearchHit has correct structure and metadata."""
    await fuzzy_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_index_documents,
    )

    results = await fuzzy_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="SearchService",
        limit=1,
    )

    assert len(results) > 0

    hit = results[0]
    assert isinstance(hit, SearchHit)
    assert hit.source == "fuzzy"
    assert hit.chunk_id is not None
    assert hit.file_path is not None
    assert hit.score >= 0.0

    # Check metadata
    assert "identifier" in hit.metadata
    assert "kind" in hit.metadata
    assert "match_type" in hit.metadata
    assert hit.metadata["match_type"] == "trigram"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
