"""
MCP Server Tests

Simple unit tests for MCP server handler functions.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.index.common.documents import SearchHit

import server.mcp_server.main as mcp_main


@pytest.fixture
def mock_service():
    """Create a mock IndexingService."""
    service = MagicMock()

    # Mock all search methods
    service.search = AsyncMock(return_value=[])
    service.lexical_index = MagicMock()
    service.lexical_index.search = AsyncMock(return_value=[])
    service.vector_index = MagicMock()
    service.vector_index.search = AsyncMock(return_value=[])
    service.symbol_index = MagicMock()
    service.symbol_index.search = AsyncMock(return_value=[])
    service.fuzzy_index = MagicMock()
    service.fuzzy_index.search = AsyncMock(return_value=[])
    service.domain_index = MagicMock()
    service.domain_index.search = AsyncMock(return_value=[])

    return service


# ==============================================================================
# Tool Handler Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_handle_search_empty_results(mock_service):
    """Test unified search handler with empty results."""
    args = {
        "query": "test",
        "repo_id": "test_repo",
        "snapshot_id": "HEAD",
    }

    result = await mcp_main.handle_search(mock_service, args)

    # Result should be JSON string
    data = json.loads(result)
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) == 0


@pytest.mark.asyncio
async def test_handle_search_with_results(mock_service):
    """Test unified search handler with results."""
    mock_hit = SearchHit(
        chunk_id="chunk:1",
        score=0.95,
        source="fuzzy",
        file_path="test.py",
        start_line=1,
        end_line=10,
        metadata={"identifier": "TestClass"},
    )
    mock_service.search = AsyncMock(return_value=[mock_hit])

    args = {
        "query": "test",
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search(mock_service, args)

    data = json.loads(result)
    assert len(data["results"]) == 1
    assert data["results"][0]["chunk_id"] == "chunk:1"
    assert data["results"][0]["score"] == 0.95


@pytest.mark.asyncio
async def test_handle_search_lexical(mock_service):
    """Test lexical search handler."""
    args = {
        "query": "test",
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search_lexical(mock_service, args)

    data = json.loads(result)
    assert "results" in data
    assert isinstance(data["results"], list)
    mock_service.lexical_index.search.assert_called_once()


@pytest.mark.asyncio
async def test_handle_search_fuzzy(mock_service):
    """Test fuzzy search handler with typo tolerance."""
    mock_hit = SearchHit(
        chunk_id="chunk:1",
        score=0.85,
        source="fuzzy",
        file_path="service.py",
        start_line=10,
        end_line=20,
        metadata={
            "identifier": "SearchService",
            "kind": "class",
        },
    )
    mock_service.fuzzy_index.search = AsyncMock(return_value=[mock_hit])

    args = {
        "query": "SarchServce",  # Typo
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search_fuzzy(mock_service, args)

    data = json.loads(result)
    assert len(data["results"]) == 1
    assert data["results"][0]["identifier"] == "SearchService"
    assert data["results"][0]["kind"] == "class"
    assert data["results"][0]["score"] == 0.85


@pytest.mark.asyncio
async def test_handle_search_domain(mock_service):
    """Test domain documentation search handler."""
    mock_hit = SearchHit(
        chunk_id="doc:readme",
        score=0.75,
        source="domain",
        file_path="README.md",
        start_line=1,
        end_line=100,
        metadata={
            "doc_type": "readme",
            "title": "Project Documentation",
        },
    )
    mock_service.domain_index.search = AsyncMock(return_value=[mock_hit])

    args = {
        "query": "authentication",
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search_domain(mock_service, args)

    data = json.loads(result)
    assert len(data["results"]) == 1
    assert data["results"][0]["doc_type"] == "readme"
    assert data["results"][0]["title"] == "Project Documentation"


@pytest.mark.asyncio
async def test_handle_get_callers(mock_service):
    """Test get_callers graph navigation handler."""
    mock_service.symbol_index.get_callers = AsyncMock(return_value=[])

    args = {
        "symbol_id": "sym:authenticate:123",
    }

    result = await mcp_main.handle_get_callers(mock_service, args)

    data = json.loads(result)
    assert "callers" in data
    assert isinstance(data["callers"], list)


@pytest.mark.asyncio
async def test_handle_get_callees(mock_service):
    """Test get_callees graph navigation handler."""
    mock_service.symbol_index.get_callees = AsyncMock(return_value=[])

    args = {
        "symbol_id": "sym:main:456",
    }

    result = await mcp_main.handle_get_callees(mock_service, args)

    data = json.loads(result)
    assert "callees" in data
    assert isinstance(data["callees"], list)


# ==============================================================================
# Error Handling Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_handle_search_error(mock_service):
    """Test search handler error handling."""
    mock_service.search = AsyncMock(side_effect=Exception("Database error"))

    args = {
        "query": "test",
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search(mock_service, args)

    # Should return error in JSON format
    data = json.loads(result)
    assert "error" in data
    assert "Database error" in data["error"]


@pytest.mark.asyncio
async def test_handle_fuzzy_search_error(mock_service):
    """Test fuzzy search handler error handling."""
    mock_service.fuzzy_index.search = AsyncMock(side_effect=Exception("Index unavailable"))

    args = {
        "query": "test",
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search_fuzzy(mock_service, args)

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_handle_domain_search_error(mock_service):
    """Test domain search handler error handling."""
    mock_service.domain_index.search = AsyncMock(side_effect=Exception("Connection failed"))

    args = {
        "query": "documentation",
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search_domain(mock_service, args)

    data = json.loads(result)
    assert "error" in data


# ==============================================================================
# Parameter Handling Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_handle_search_with_optional_params(mock_service):
    """Test search handler with optional parameters."""
    args = {
        "query": "test",
        "repo_id": "test_repo",
        "snapshot_id": "commit123",
        "limit": 20,
    }

    result = await mcp_main.handle_search(mock_service, args)

    data = json.loads(result)
    assert "results" in data
    # Verify service was called with correct params
    mock_service.search.assert_called_once()


@pytest.mark.asyncio
async def test_handle_fuzzy_search_default_params(mock_service):
    """Test fuzzy search with default parameters."""
    args = {
        "query": "TestClass",
        "repo_id": "test_repo",
        # No snapshot_id, should use default
    }

    result = await mcp_main.handle_search_fuzzy(mock_service, args)

    data = json.loads(result)
    assert "results" in data
    mock_service.fuzzy_index.search.assert_called_once()


@pytest.mark.asyncio
async def test_handle_domain_search_with_metadata(mock_service):
    """Test domain search preserves metadata."""
    mock_hit = SearchHit(
        chunk_id="doc:adr",
        score=0.9,
        source="domain",
        file_path="docs/adr/001.md",
        start_line=1,
        end_line=50,
        metadata={
            "doc_type": "adr",
            "title": "ADR 001: Database Choice",
            "tags": ["architecture", "database"],
        },
    )
    mock_service.domain_index.search = AsyncMock(return_value=[mock_hit])

    args = {
        "query": "database",
        "repo_id": "test_repo",
    }

    result = await mcp_main.handle_search_domain(mock_service, args)

    data = json.loads(result)
    assert data["results"][0]["doc_type"] == "adr"
    assert data["results"][0]["title"] == "ADR 001: Database Choice"
    # Metadata fields are preserved in the result
