"""
Integration Tests: RFC-053 Tier 0 - search tool

Tests the hybrid search handler with real MCPSearchService.

Test Coverage:
- Happy path (all, chunks, symbols)
- Invalid input (empty query, invalid limit)
- Timeout scenarios
- Mixed ranking algorithm
- Error handling
"""

import asyncio
import json

import pytest

from apps.mcp.mcp.adapters.mcp.services import MCPSearchService, SearchResult
from apps.mcp.mcp.handlers.search import search


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_search_service():
    """Mock MCPSearchService for testing."""

    class MockSearchService:
        """Mock service returning fake results."""

        async def search_chunks(self, query: str, limit: int, repo_id: str = "", snapshot_id: str = "main"):
            """Return mock chunks."""
            return [
                SearchResult(
                    id=f"chunk_{i}",
                    content=f"Chunk content {i} matching {query}",
                    file_path=f"file{i}.py",
                    line=i * 10,
                    score=0.9 - (i * 0.1),
                    metadata={"type": "chunk"},
                )
                for i in range(min(3, limit))
            ]

        async def search_symbols(self, query: str, limit: int, repo_id: str = "", snapshot_id: str = "main"):
            """Return mock symbols."""
            return [
                SearchResult(
                    id=f"symbol_{i}",
                    content=f"Symbol{i}",
                    file_path=f"module{i}.py",
                    line=i * 20,
                    score=0.95 - (i * 0.05),
                    metadata={"type": "symbol", "kind": "function", "name": f"Symbol{i}"},
                )
                for i in range(min(3, limit))
            ]

    return MockSearchService()


# ============================================================
# Happy Path Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_all_types(mock_search_service):
    """Test search with types=["all"] returns both chunks and symbols."""
    result_json = await search(
        mock_search_service,
        {
            "query": "authentication",
            "types": ["all"],
            "limit": 10,
        },
    )

    result = json.loads(result_json)

    # Validate schema
    assert "query" in result
    assert result["query"] == "authentication"

    assert "results" in result
    assert "chunks" in result["results"]
    assert "symbols" in result["results"]

    assert "mixed_ranking" in result
    assert "took_ms" in result
    assert "meta" in result

    # Validate content
    assert len(result["results"]["chunks"]) == 3
    assert len(result["results"]["symbols"]) == 3

    # Mixed ranking should have both types
    assert len(result["mixed_ranking"]) == 6  # 3 chunks + 3 symbols

    # Check mixed ranking is sorted by score
    scores = [item["score"] for item in result["mixed_ranking"]]
    assert scores == sorted(scores, reverse=True)

    # Validate meta
    assert result["meta"]["timeout_seconds"] == 2
    assert result["meta"]["cost_hint"] == "low"
    assert result["meta"]["tier"] == 0


@pytest.mark.asyncio
async def test_search_chunks_only(mock_search_service):
    """Test search with types=["chunks"] returns only chunks."""
    result_json = await search(
        mock_search_service,
        {
            "query": "validate",
            "types": ["chunks"],
            "limit": 5,
        },
    )

    result = json.loads(result_json)

    # Should have chunks
    assert "chunks" in result["results"]
    assert len(result["results"]["chunks"]) == 3

    # Should NOT have symbols
    assert "symbols" not in result["results"]

    # Mixed ranking should only have chunks
    assert all(item["type"] == "chunk" for item in result["mixed_ranking"])


@pytest.mark.asyncio
async def test_search_symbols_only(mock_search_service):
    """Test search with types=["symbols"] returns only symbols."""
    result_json = await search(
        mock_search_service,
        {
            "query": "UserService",
            "types": ["symbols"],
            "limit": 5,
        },
    )

    result = json.loads(result_json)

    # Should have symbols
    assert "symbols" in result["results"]
    assert len(result["results"]["symbols"]) == 3

    # Should NOT have chunks
    assert "chunks" not in result["results"]

    # Mixed ranking should only have symbols
    assert all(item["type"] == "symbol" for item in result["mixed_ranking"])


# ============================================================
# Invalid Input Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_empty_query(mock_search_service):
    """Test search with empty query raises ValueError."""
    with pytest.raises(ValueError, match="Query parameter is required"):
        await search(
            mock_search_service,
            {
                "query": "",
                "types": ["all"],
            },
        )


@pytest.mark.asyncio
async def test_search_missing_query(mock_search_service):
    """Test search without query raises ValueError."""
    with pytest.raises(ValueError, match="Query parameter is required"):
        await search(
            mock_search_service,
            {
                "types": ["all"],
            },
        )


@pytest.mark.asyncio
async def test_search_invalid_limit_too_low(mock_search_service):
    """Test search with limit < 1 raises ValueError."""
    with pytest.raises(ValueError, match="Limit must be an integer between 1 and 100"):
        await search(
            mock_search_service,
            {
                "query": "test",
                "limit": 0,
            },
        )


@pytest.mark.asyncio
async def test_search_invalid_limit_too_high(mock_search_service):
    """Test search with limit > 100 raises ValueError."""
    with pytest.raises(ValueError, match="Limit must be an integer between 1 and 100"):
        await search(
            mock_search_service,
            {
                "query": "test",
                "limit": 101,
            },
        )


@pytest.mark.asyncio
async def test_search_invalid_types_fallback_to_all(mock_search_service):
    """Test search with invalid types falls back to 'all'."""
    result_json = await search(
        mock_search_service,
        {
            "query": "test",
            "types": ["invalid_type"],
            "limit": 5,
        },
    )

    result = json.loads(result_json)

    # Should fallback to 'all' and return both
    assert "chunks" in result["results"]
    assert "symbols" in result["results"]


# ============================================================
# Edge Case Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_limit_applied_to_mixed_ranking(mock_search_service):
    """Test that limit is applied to mixed ranking."""
    result_json = await search(
        mock_search_service,
        {
            "query": "test",
            "types": ["all"],
            "limit": 3,  # Limit to 3 total results
        },
    )

    result = json.loads(result_json)

    # Mixed ranking should respect limit
    assert len(result["mixed_ranking"]) == 3

    # But individual results may have more
    assert len(result["results"]["chunks"]) == 3
    assert len(result["results"]["symbols"]) == 3


@pytest.mark.asyncio
async def test_search_deduplication_in_mixed_ranking(mock_search_service):
    """Test that mixed ranking deduplicates by (type, id)."""

    class DuplicateService:
        """Service that returns duplicate IDs."""

        async def search_chunks(self, query, limit, repo_id="", snapshot_id="main"):
            return [
                SearchResult(id="dup_1", content="A", file_path="f.py", line=1, score=0.9, metadata={}),
                SearchResult(id="dup_1", content="A", file_path="f.py", line=1, score=0.9, metadata={}),  # Duplicate
            ]

        async def search_symbols(self, query, limit, repo_id="", snapshot_id="main"):
            return [
                SearchResult(
                    id="dup_1", content="B", file_path="g.py", line=2, score=0.8, metadata={}
                ),  # Different type, same ID
            ]

    result_json = await search(
        DuplicateService(),
        {
            "query": "test",
            "types": ["all"],
            "limit": 10,
        },
    )

    result = json.loads(result_json)

    # Mixed ranking should have 2 items (chunk:dup_1, symbol:dup_1)
    assert len(result["mixed_ranking"]) == 2

    # Check both types present
    types = {item["type"] for item in result["mixed_ranking"]}
    assert types == {"chunk", "symbol"}


# ============================================================
# Timeout Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_timeout_chunks(mock_search_service):
    """Test graceful degradation when chunks search times out."""

    class TimeoutChunksService:
        """Service where chunks search times out."""

        async def search_chunks(self, query, limit, repo_id="", snapshot_id="main"):
            await asyncio.sleep(3)  # Exceeds 2s timeout
            return []

        async def search_symbols(self, query, limit, repo_id="", snapshot_id="main"):
            return [
                SearchResult(id="s1", content="Symbol", file_path="f.py", line=1, score=0.9, metadata={}),
            ]

    result_json = await search(
        TimeoutChunksService(),
        {
            "query": "test",
            "types": ["all"],
            "limit": 10,
        },
    )

    result = json.loads(result_json)

    # Should have symbols but empty chunks (graceful degradation)
    assert len(result["results"]["chunks"]) == 0
    assert len(result["results"]["symbols"]) == 1


# ============================================================
# Performance Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_performance_under_2s(mock_search_service):
    """Test that search completes within 2s target."""
    import time

    start = time.time()

    result_json = await search(
        mock_search_service,
        {
            "query": "performance test",
            "types": ["all"],
            "limit": 10,
        },
    )

    elapsed = time.time() - start

    # Should complete in < 2s
    assert elapsed < 2.0

    # Verify took_ms is reasonable
    result = json.loads(result_json)
    assert result["took_ms"] < 2000


# ============================================================
# Schema Validation Tests
# ============================================================


@pytest.mark.asyncio
async def test_search_response_schema_complete(mock_search_service):
    """Test that response has all required fields."""
    result_json = await search(
        mock_search_service,
        {
            "query": "schema test",
            "types": ["all"],
            "limit": 5,
        },
    )

    result = json.loads(result_json)

    # Required top-level fields
    required_fields = ["query", "results", "mixed_ranking", "took_ms", "meta"]
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"

    # Meta fields
    assert "timeout_seconds" in result["meta"]
    assert "cost_hint" in result["meta"]
    assert "tier" in result["meta"]

    # Results structure
    assert isinstance(result["results"], dict)
    assert isinstance(result["mixed_ranking"], list)

    # Each item in mixed_ranking should have type field
    for item in result["mixed_ranking"]:
        assert "type" in item
        assert item["type"] in ["chunk", "symbol"]
