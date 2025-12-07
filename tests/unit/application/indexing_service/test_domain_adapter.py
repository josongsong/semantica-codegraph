"""
Domain Meta Index Adapter Integration Tests

Tests PostgreSQL full-text search for documentation:
- Schema creation with tsvector indexes
- Document type classification (README, ADR, API spec, etc.)
- Full-text search with ts_rank scoring
- Title extraction from markdown
- Incremental upsert and delete
"""

import os

import pytest

from src.index.common.documents import IndexDocument, SearchHit
from src.index.domain_meta.adapter_meta import DomainMetaIndex
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
async def domain_index(postgres_store):
    """Create DomainMetaIndex with initialized PostgresStore."""
    index = DomainMetaIndex(postgres_store=postgres_store)

    # Ensure schema is created
    await index._ensure_schema()

    # Clean up test data before each test
    async with postgres_store.pool.acquire() as conn:
        await conn.execute("DELETE FROM domain_documents WHERE repo_id = 'test_repo'")

    return index


@pytest.fixture
def sample_domain_documents():
    """Create sample domain IndexDocuments for testing."""
    return [
        # README document
        IndexDocument(
            chunk_id="chunk:readme",
            repo_id="test_repo",
            snapshot_id="snapshot:123",
            file_path="README.md",
            language="markdown",
            symbol_id=None,
            fqn="README",
            node_type="document",
            content="""# MyProject

A comprehensive code search engine with semantic understanding.

## Installation

Install via pip:
```bash
pip install myproject
```

## Usage

Import and use the SearchEngine class to index your codebase.
""",
            metadata={},
        ),
        # ADR document
        IndexDocument(
            chunk_id="chunk:adr",
            repo_id="test_repo",
            snapshot_id="snapshot:123",
            file_path="docs/adr/0001-use-postgresql.md",
            language="markdown",
            symbol_id=None,
            fqn="ADR-0001",
            node_type="document",
            content="""# ADR 0001: Use PostgreSQL for Fuzzy Search

## Status

Accepted

## Context

We need a database that supports trigram similarity for fuzzy identifier matching.

## Decision

We will use PostgreSQL with the pg_trgm extension.

## Consequences

This allows us to implement typo-tolerant search without additional dependencies.
""",
            metadata={},
        ),
        # API documentation
        IndexDocument(
            chunk_id="chunk:api",
            repo_id="test_repo",
            snapshot_id="snapshot:123",
            file_path="docs/api/search.md",
            language="markdown",
            symbol_id=None,
            fqn="API-Search",
            node_type="document",
            content="""# Search API

## Endpoint: POST /api/search

Search for code using natural language queries.

### Parameters

- `query` (string): The search query
- `limit` (integer): Maximum number of results (default: 50)

### Response

Returns a list of SearchHit objects with relevance scores.
""",
            metadata={},
        ),
        # CHANGELOG
        IndexDocument(
            chunk_id="chunk:changelog",
            repo_id="test_repo",
            snapshot_id="snapshot:123",
            file_path="CHANGELOG.md",
            language="markdown",
            symbol_id=None,
            fqn="CHANGELOG",
            node_type="document",
            content="""# Changelog

## [2.0.0] - 2025-01-01

### Added
- Fuzzy search with PostgreSQL pg_trgm
- Domain metadata indexing for documentation
- Improved relevance scoring

### Fixed
- Search timeout issues
""",
            metadata={},
        ),
    ]


# ============================================================
# Schema and Initialization Tests
# ============================================================


@pytest.mark.asyncio
async def test_schema_creation(domain_index, postgres_store):
    """Test that schema is created correctly."""
    # Schema should already be created by fixture

    # Verify table exists
    async with postgres_store.pool.acquire() as conn:
        result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'domain_documents'
            )
        """
        )

        assert result is True

        # Verify GIN index for full-text search exists
        idx_result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_indexes
                WHERE tablename = 'domain_documents'
                  AND indexname = 'idx_domain_content_fts'
            )
        """
        )

        assert idx_result is True


# ============================================================
# Document Type Classification Tests
# ============================================================


@pytest.mark.asyncio
async def test_document_type_inference(domain_index):
    """Test document type inference from file paths."""
    test_cases = [
        (
            IndexDocument(
                chunk_id="1",
                repo_id="r",
                snapshot_id="s",
                file_path="README.md",
                language="md",
                symbol_id=None,
                fqn="",
                node_type="doc",
                content="",
            ),
            "readme",
        ),
        (
            IndexDocument(
                chunk_id="2",
                repo_id="r",
                snapshot_id="s",
                file_path="CHANGELOG.md",
                language="md",
                symbol_id=None,
                fqn="",
                node_type="doc",
                content="",
            ),
            "changelog",
        ),
        (
            IndexDocument(
                chunk_id="3",
                repo_id="r",
                snapshot_id="s",
                file_path="LICENSE",
                language="txt",
                symbol_id=None,
                fqn="",
                node_type="doc",
                content="",
            ),
            "license",
        ),
        (
            IndexDocument(
                chunk_id="4",
                repo_id="r",
                snapshot_id="s",
                file_path="docs/adr/0001-decision.md",
                language="md",
                symbol_id=None,
                fqn="",
                node_type="doc",
                content="",
            ),
            "adr",
        ),
        (
            IndexDocument(
                chunk_id="5",
                repo_id="r",
                snapshot_id="s",
                file_path="api/openapi.yaml",
                language="yaml",
                symbol_id=None,
                fqn="",
                node_type="doc",
                content="",
            ),
            "api_spec",
        ),
        (
            IndexDocument(
                chunk_id="6",
                repo_id="r",
                snapshot_id="s",
                file_path="CONTRIBUTING.md",
                language="md",
                symbol_id=None,
                fqn="",
                node_type="doc",
                content="",
            ),
            "contributing",
        ),
        (
            IndexDocument(
                chunk_id="7",
                repo_id="r",
                snapshot_id="s",
                file_path="docs/guide.md",
                language="md",
                symbol_id=None,
                fqn="",
                node_type="doc",
                content="",
            ),
            "markdown_doc",
        ),
    ]

    for doc, expected_type in test_cases:
        inferred_type = domain_index._infer_doc_type(doc)
        assert inferred_type == expected_type, f"Expected {expected_type} for {doc.file_path}, got {inferred_type}"


@pytest.mark.asyncio
async def test_title_extraction_from_markdown(domain_index):
    """Test title extraction from markdown H1 headers."""
    # Markdown with H1
    doc_with_h1 = IndexDocument(
        chunk_id="1",
        repo_id="r",
        snapshot_id="s",
        file_path="test.md",
        language="md",
        symbol_id=None,
        fqn="",
        node_type="doc",
        content="# My Title\n\nSome content here.",
    )

    title = domain_index._extract_title(doc_with_h1)
    assert title == "My Title"

    # Markdown without H1 (uses first line)
    doc_without_h1 = IndexDocument(
        chunk_id="2",
        repo_id="r",
        snapshot_id="s",
        file_path="test.md",
        language="md",
        symbol_id=None,
        fqn="",
        node_type="doc",
        content="First line as title\n\nMore content.",
    )

    title2 = domain_index._extract_title(doc_without_h1)
    assert title2 == "First line as title"

    # Empty content (uses filename)
    doc_empty = IndexDocument(
        chunk_id="3",
        repo_id="r",
        snapshot_id="s",
        file_path="my_file.md",
        language="md",
        symbol_id=None,
        fqn="",
        node_type="doc",
        content="",
    )

    title3 = domain_index._extract_title(doc_empty)
    assert title3 == "my_file"


# ============================================================
# Indexing Tests
# ============================================================


@pytest.mark.asyncio
async def test_full_index_creation(domain_index, sample_domain_documents):
    """Test full index creation with domain documents."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Verify documents were indexed
    async with domain_index.postgres.pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM domain_documents
            WHERE repo_id = 'test_repo' AND snapshot_id = 'snapshot:123'
        """
        )

        assert count == len(sample_domain_documents)


@pytest.mark.asyncio
async def test_upsert_documents(domain_index, sample_domain_documents):
    """Test incremental upsert of domain documents."""
    # Initial index
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents[:2],  # Only first 2
    )

    # Upsert with modified README
    modified_readme = IndexDocument(
        chunk_id="chunk:readme",  # Same chunk_id
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        file_path="README.md",
        language="markdown",
        symbol_id=None,
        fqn="README",
        node_type="document",
        content="# MyProject v2\n\nUpdated documentation with new features.",
        metadata={},
    )

    await domain_index.upsert(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=[modified_readme],
    )

    # Search for updated content
    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="updated documentation",
        limit=10,
    )

    assert len(results) > 0


@pytest.mark.asyncio
async def test_delete_documents(domain_index, sample_domain_documents):
    """Test deletion of domain documents by chunk IDs."""
    # Index all documents
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Delete README
    await domain_index.delete(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        doc_ids=["chunk:readme"],
    )

    # Verify README is gone
    async with domain_index.postgres.pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM domain_documents
            WHERE chunk_id = 'chunk:readme'
        """
        )

        assert count == 0

        # Other documents should remain
        other_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM domain_documents
            WHERE repo_id = 'test_repo'
        """
        )

        assert other_count == len(sample_domain_documents) - 1


# ============================================================
# Full-Text Search Tests
# ============================================================


@pytest.mark.asyncio
async def test_full_text_search_readme(domain_index, sample_domain_documents):
    """Test full-text search matches README content."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Search for "installation"
    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="installation",
        limit=10,
    )

    assert len(results) > 0
    assert results[0].source == "domain"

    # Should match README (contains "Installation" section)
    assert any(hit.file_path == "README.md" for hit in results)


@pytest.mark.asyncio
async def test_full_text_search_adr(domain_index, sample_domain_documents):
    """Test full-text search matches ADR content."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Search for "PostgreSQL trigram"
    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="PostgreSQL trigram",
        limit=10,
    )

    assert len(results) > 0

    # Should match ADR document
    assert any("adr" in hit.file_path.lower() for hit in results)


@pytest.mark.asyncio
async def test_full_text_search_api_docs(domain_index, sample_domain_documents):
    """Test full-text search matches API documentation."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Search for "search endpoint"
    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="search endpoint",
        limit=10,
    )

    assert len(results) > 0

    # Should match API docs
    assert any("api" in hit.file_path.lower() for hit in results)


@pytest.mark.asyncio
async def test_relevance_ranking(domain_index, sample_domain_documents):
    """Test that results are ranked by relevance (ts_rank)."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="search",
        limit=10,
    )

    # Results should be sorted by score (descending)
    if len(results) > 1:
        scores = [hit.score for hit in results]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_empty_query_returns_empty(domain_index):
    """Test that empty query returns empty results."""
    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="",
        limit=10,
    )

    assert results == []


@pytest.mark.asyncio
async def test_limit_parameter(domain_index, sample_domain_documents):
    """Test that limit parameter works correctly."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Search with limit=2
    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="documentation",
        limit=2,
    )

    # Should return at most 2 results
    assert len(results) <= 2


# ============================================================
# SearchHit Metadata Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_hit_structure(domain_index, sample_domain_documents):
    """Test that SearchHit has correct structure and metadata."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="installation",
        limit=1,
    )

    assert len(results) > 0

    hit = results[0]
    assert isinstance(hit, SearchHit)
    assert hit.source == "domain"
    assert hit.chunk_id is not None
    assert hit.file_path is not None
    assert hit.score > 0.0

    # Check metadata
    assert "doc_type" in hit.metadata
    assert "title" in hit.metadata
    assert "preview" in hit.metadata
    assert "match_type" in hit.metadata
    assert hit.metadata["match_type"] == "full_text"

    # Preview should be truncated
    assert len(hit.metadata["preview"]) <= 203  # 200 + "..."


@pytest.mark.asyncio
async def test_document_type_in_metadata(domain_index, sample_domain_documents):
    """Test that document type is included in search results."""
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Search for README
    results = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="installation",
        limit=10,
    )

    # Find README result
    readme_hit = next((hit for hit in results if hit.file_path == "README.md"), None)
    assert readme_hit is not None
    assert readme_hit.metadata["doc_type"] == "readme"


# ============================================================
# Snapshot Isolation Tests
# ============================================================


@pytest.mark.asyncio
async def test_snapshot_isolation(domain_index, sample_domain_documents):
    """Test that different snapshots are isolated."""
    # Index to snapshot:123
    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        docs=sample_domain_documents,
    )

    # Index different data to snapshot:456
    other_doc = IndexDocument(
        chunk_id="chunk:other",
        repo_id="test_repo",
        snapshot_id="snapshot:456",
        file_path="OTHER.md",
        language="markdown",
        symbol_id=None,
        fqn="OTHER",
        node_type="document",
        content="# Other Document\n\nCompletely different content about widgets.",
        metadata={},
    )

    await domain_index.index(
        repo_id="test_repo",
        snapshot_id="snapshot:456",
        docs=[other_doc],
    )

    # Search in snapshot:123 should not find "widgets"
    results_123 = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        query="widgets",
        limit=10,
    )

    assert len(results_123) == 0

    # Search in snapshot:456 should find "widgets"
    results_456 = await domain_index.search(
        repo_id="test_repo",
        snapshot_id="snapshot:456",
        query="widgets",
        limit=10,
    )

    assert len(results_456) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
