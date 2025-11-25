"""
Zoekt Search Adapter Tests

Tests HTTP-based Zoekt search operations:
- Adapter initialization
- Search with query parameters
- Repo filtering
- Response parsing (FileMatches, Matches, Fragments)
- Health checks
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.infra.search.zoekt import (
    ZoektAdapter,
    ZoektFileMatch,
    ZoektMatch,
    ZoektMatchFragment,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for testing."""
    mock_client = MagicMock()

    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock()

    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    return mock_client, mock_response


# ============================================================
# Initialization Tests
# ============================================================


class TestZoektAdapterBasics:
    """Test basic adapter creation and configuration."""

    def test_zoekt_adapter_creation(self):
        """Test creating Zoekt adapter with defaults."""
        adapter = ZoektAdapter(host="localhost", port=7205)

        assert adapter.host == "localhost"
        assert adapter.port == 7205
        assert adapter.base_url == "http://localhost:7205"
        assert adapter.client is not None

    def test_zoekt_adapter_custom_host(self):
        """Test creating Zoekt adapter with custom host."""
        adapter = ZoektAdapter(host="zoekt.example.com", port=8080)

        assert adapter.host == "zoekt.example.com"
        assert adapter.port == 8080
        assert adapter.base_url == "http://zoekt.example.com:8080"


# ============================================================
# Search Tests
# ============================================================


class TestSearch:
    """Test search operations."""

    @pytest.mark.asyncio
    async def test_search_basic(self, mock_httpx_client):
        """Test basic search."""
        mock_client, mock_response = mock_httpx_client

        # Mock search response
        mock_response.json.return_value = {
            "result": {
                "FileMatches": [
                    {
                        "FileName": "example.py",
                        "Repo": "test-repo",
                        "Language": "Python",
                        "Matches": [
                            {
                                "LineNum": 42,
                                "Fragments": [{"Pre": "def ", "Match": "hello", "Post": "():\n"}],
                                "FileName": "example.py",
                            }
                        ],
                    }
                ]
            }
        }

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        results = await adapter.search(query="hello", limit=200)

        assert len(results) == 1
        assert isinstance(results[0], ZoektFileMatch)
        assert results[0].FileName == "example.py"
        assert results[0].Repo == "test-repo"
        assert results[0].Language == "Python"
        assert len(results[0].Matches) == 1

        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == "http://localhost:7205/search"
        assert call_args[1]["params"]["q"] == "hello"
        assert call_args[1]["params"]["num"] == 200
        assert call_args[1]["params"]["format"] == "json"

    @pytest.mark.asyncio
    async def test_search_with_repo_filter(self, mock_httpx_client):
        """Test search with repo filter."""
        mock_client, mock_response = mock_httpx_client

        mock_response.json.return_value = {"result": {"FileMatches": []}}

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        await adapter.search(query="test", limit=100, repo_filter="my-repo")

        # Verify query includes repo filter
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["q"] == "repo:my-repo test"
        assert call_args[1]["params"]["num"] == 100

    @pytest.mark.asyncio
    async def test_search_empty_results(self, mock_httpx_client):
        """Test search with no results."""
        mock_client, mock_response = mock_httpx_client

        # No FileMatches
        mock_response.json.return_value = {"result": {}}

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        results = await adapter.search(query="nonexistent")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_multiple_file_matches(self, mock_httpx_client):
        """Test search with multiple file matches."""
        mock_client, mock_response = mock_httpx_client

        mock_response.json.return_value = {
            "result": {
                "FileMatches": [
                    {
                        "FileName": "file1.py",
                        "Repo": "repo1",
                        "Language": "Python",
                        "Matches": [],
                    },
                    {
                        "FileName": "file2.js",
                        "Repo": "repo2",
                        "Language": "JavaScript",
                        "Matches": [],
                    },
                ]
            }
        }

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        results = await adapter.search(query="test")

        assert len(results) == 2
        assert results[0].FileName == "file1.py"
        assert results[1].FileName == "file2.js"

    @pytest.mark.asyncio
    async def test_search_with_multiple_matches(self, mock_httpx_client):
        """Test search with multiple matches in a file."""
        mock_client, mock_response = mock_httpx_client

        mock_response.json.return_value = {
            "result": {
                "FileMatches": [
                    {
                        "FileName": "example.py",
                        "Repo": "test-repo",
                        "Matches": [
                            {
                                "LineNum": 10,
                                "Fragments": [{"Pre": "class ", "Match": "Test", "Post": ":\n"}],
                                "FileName": "example.py",
                            },
                            {
                                "LineNum": 20,
                                "Fragments": [{"Pre": "def ", "Match": "test", "Post": "():\n"}],
                                "FileName": "example.py",
                            },
                        ],
                    }
                ]
            }
        }

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        results = await adapter.search(query="test")

        assert len(results) == 1
        assert len(results[0].Matches) == 2
        assert results[0].Matches[0].LineNum == 10
        assert results[0].Matches[1].LineNum == 20


# ============================================================
# Health Check Tests
# ============================================================


class TestHealthCheck:
    """Test health check operations."""

    @pytest.mark.asyncio
    async def test_healthcheck_success(self, mock_httpx_client):
        """Test health check when Zoekt is available."""
        mock_client, mock_response = mock_httpx_client

        mock_response.status_code = 200

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        is_healthy = await adapter.healthcheck()

        assert is_healthy is True
        mock_client.get.assert_called_once_with("http://localhost:7205/")

    @pytest.mark.asyncio
    async def test_healthcheck_failure(self, mock_httpx_client):
        """Test health check when Zoekt is unavailable."""
        mock_client, _ = mock_httpx_client

        # Mock connection error
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        is_healthy = await adapter.healthcheck()

        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_healthcheck_non_200_status(self, mock_httpx_client):
        """Test health check with non-200 status."""
        mock_client, mock_response = mock_httpx_client

        mock_response.status_code = 500

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        is_healthy = await adapter.healthcheck()

        assert is_healthy is False


# ============================================================
# Cleanup Tests
# ============================================================


class TestCleanup:
    """Test cleanup operations."""

    @pytest.mark.asyncio
    async def test_close_client(self, mock_httpx_client):
        """Test closing HTTP client."""
        mock_client, _ = mock_httpx_client

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        await adapter.close()

        mock_client.aclose.assert_called_once()


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_search_http_error(self, mock_httpx_client):
        """Test search with HTTP error."""
        mock_client, _ = mock_httpx_client

        # Mock HTTP error
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=MagicMock()
        )

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        with pytest.raises(httpx.HTTPError):
            await adapter.search(query="test")

    @pytest.mark.asyncio
    async def test_search_network_error(self, mock_httpx_client):
        """Test search with network error."""
        mock_client, _ = mock_httpx_client

        # Mock network error
        mock_client.get.side_effect = httpx.ConnectError("Connection failed")

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        with pytest.raises(httpx.HTTPError):
            await adapter.search(query="test")

    @pytest.mark.asyncio
    async def test_search_timeout(self, mock_httpx_client):
        """Test search with timeout."""
        mock_client, _ = mock_httpx_client

        # Mock timeout
        mock_client.get.side_effect = httpx.TimeoutException("Request timeout")

        adapter = ZoektAdapter(host="localhost", port=7205)
        adapter.client = mock_client

        with pytest.raises(httpx.HTTPError):
            await adapter.search(query="test")


# ============================================================
# Pydantic Model Tests
# ============================================================


class TestPydanticModels:
    """Test Pydantic model creation and validation."""

    def test_zoekt_match_fragment_creation(self):
        """Test ZoektMatchFragment model."""
        fragment = ZoektMatchFragment(Pre="def ", Match="hello", Post="():\n")

        assert fragment.Pre == "def "
        assert fragment.Match == "hello"
        assert fragment.Post == "():\n"

    def test_zoekt_match_creation(self):
        """Test ZoektMatch model."""
        match = ZoektMatch(
            LineNum=42,
            Fragments=[ZoektMatchFragment(Pre="def ", Match="test", Post="():\n")],
            FileName="example.py",
        )

        assert match.LineNum == 42
        assert len(match.Fragments) == 1
        assert match.FileName == "example.py"

    def test_zoekt_file_match_creation(self):
        """Test ZoektFileMatch model."""
        file_match = ZoektFileMatch(
            FileName="example.py",
            Repo="test-repo",
            Language="Python",
            Matches=[ZoektMatch(LineNum=1, Fragments=[], FileName="example.py")],
        )

        assert file_match.FileName == "example.py"
        assert file_match.Repo == "test-repo"
        assert file_match.Language == "Python"
        assert len(file_match.Matches) == 1

    def test_zoekt_file_match_from_dict(self):
        """Test creating ZoektFileMatch from dict."""
        data = {
            "FileName": "test.py",
            "Repo": "my-repo",
            "Language": "Python",
            "Matches": [
                {
                    "LineNum": 10,
                    "Fragments": [{"Pre": "class ", "Match": "Test", "Post": ":\n"}],
                    "FileName": "test.py",
                }
            ],
        }

        file_match = ZoektFileMatch(**data)

        assert file_match.FileName == "test.py"
        assert file_match.Repo == "my-repo"
        assert len(file_match.Matches) == 1
        assert file_match.Matches[0].LineNum == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
