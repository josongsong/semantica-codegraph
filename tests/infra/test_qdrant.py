"""
Qdrant Vector Store Tests

Tests Qdrant vector operations:
- Client initialization and lazy loading
- Collection creation and management
- Vector upsert operations
- Similarity search with filtering
- Point retrieval and deletion
- Health checks
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.vector.qdrant import QdrantAdapter

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_qdrant_client():
    """Mock AsyncQdrantClient for testing."""
    mock_client = MagicMock()

    # Mock get_collections
    mock_collections_response = MagicMock()
    mock_collections_response.collections = []
    mock_client.get_collections = AsyncMock(return_value=mock_collections_response)

    # Mock create_collection
    mock_client.create_collection = AsyncMock()

    # Mock upsert
    mock_client.upsert = AsyncMock()

    # Mock search
    mock_client.search = AsyncMock(return_value=[])

    # Mock retrieve
    mock_client.retrieve = AsyncMock(return_value=[])

    # Mock delete
    mock_client.delete = AsyncMock()

    # Mock delete_collection
    mock_client.delete_collection = AsyncMock()

    # Mock count
    mock_count_response = MagicMock()
    mock_count_response.count = 0
    mock_client.count = AsyncMock(return_value=mock_count_response)

    # Mock close
    mock_client.close = AsyncMock()

    return mock_client


# ============================================================
# Initialization Tests
# ============================================================


class TestQdrantAdapterBasics:
    """Test basic adapter creation and configuration."""

    def test_qdrant_adapter_creation(self):
        """Test creating Qdrant adapter with defaults."""
        adapter = QdrantAdapter()

        assert adapter.host == "localhost"
        assert adapter.port == 6333
        assert adapter.collection == "codegraph"
        assert adapter._client is None

    def test_qdrant_adapter_custom_config(self):
        """Test creating Qdrant adapter with custom config."""
        adapter = QdrantAdapter(
            host="qdrant.example.com", port=6334, collection="custom-collection"
        )

        assert adapter.host == "qdrant.example.com"
        assert adapter.port == 6334
        assert adapter.collection == "custom-collection"


# ============================================================
# Client Management Tests
# ============================================================


class TestClientManagement:
    """Test client initialization and management."""

    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, mock_qdrant_client):
        """Test that _get_client creates client on first call."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            client = await adapter._get_client()

            assert client is mock_qdrant_client
            mock_class.assert_called_once_with(host="localhost", port=6333)

    @pytest.mark.asyncio
    async def test_get_client_caches_client(self, mock_qdrant_client):
        """Test that _get_client returns same client on subsequent calls."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            client1 = await adapter._get_client()
            client2 = await adapter._get_client()

            assert client1 is client2
            mock_class.assert_called_once()  # Only called once


# ============================================================
# Collection Management Tests
# ============================================================


class TestCollectionManagement:
    """Test collection creation and management."""

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_if_not_exists(self, mock_qdrant_client):
        """Test that _ensure_collection creates collection if it doesn't exist."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Collection doesn't exist yet
            mock_collections_response = MagicMock()
            mock_collections_response.collections = []
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            await adapter._ensure_collection(vector_size=1536)

            # Should have created the collection
            mock_qdrant_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_if_exists(self, mock_qdrant_client):
        """Test that _ensure_collection skips creation if collection exists."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Collection already exists
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            await adapter._ensure_collection(vector_size=1536)

            # Should NOT have created the collection
            mock_qdrant_client.create_collection.assert_not_called()


# ============================================================
# Upsert Tests
# ============================================================


class TestUpsert:
    """Test vector upsert operations."""

    @pytest.mark.asyncio
    async def test_upsert_single_vector(self, mock_qdrant_client):
        """Test upserting a single vector."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            vectors = [{"id": "test-1", "vector": [0.1, 0.2, 0.3], "payload": {"text": "test"}}]

            await adapter.upsert_vectors(vectors)

            mock_qdrant_client.upsert.assert_called_once()
            call_args = mock_qdrant_client.upsert.call_args
            assert call_args[1]["collection_name"] == "codegraph"
            assert len(call_args[1]["points"]) == 1

    @pytest.mark.asyncio
    async def test_upsert_multiple_vectors(self, mock_qdrant_client):
        """Test upserting multiple vectors."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            vectors = [
                {"id": "test-1", "vector": [0.1, 0.2], "payload": {"text": "A"}},
                {"id": "test-2", "vector": [0.3, 0.4], "payload": {"text": "B"}},
            ]

            await adapter.upsert_vectors(vectors)

            mock_qdrant_client.upsert.assert_called_once()
            call_args = mock_qdrant_client.upsert.call_args
            assert len(call_args[1]["points"]) == 2

    @pytest.mark.asyncio
    async def test_upsert_generates_id_if_missing(self, mock_qdrant_client):
        """Test that upsert generates UUID if ID not provided."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            vectors = [{"vector": [0.1, 0.2]}]  # No ID provided

            await adapter.upsert_vectors(vectors)

            # Should have generated an ID
            call_args = mock_qdrant_client.upsert.call_args
            point_id = call_args[1]["points"][0].id
            assert point_id is not None

    @pytest.mark.asyncio
    async def test_upsert_raises_on_missing_vector(self, mock_qdrant_client):
        """Test that upsert raises error if vector data is missing."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            vectors = [{"id": "test-1", "payload": {"text": "test"}}]  # No vector

            with pytest.raises(RuntimeError, match="Failed to upsert vectors"):
                await adapter.upsert_vectors(vectors)


# ============================================================
# Search Tests
# ============================================================


class TestSearch:
    """Test vector similarity search."""

    @pytest.mark.asyncio
    async def test_search_basic(self, mock_qdrant_client):
        """Test basic similarity search."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            # Mock search results
            mock_hit1 = MagicMock()
            mock_hit1.id = "result-1"
            mock_hit1.score = 0.95
            mock_hit1.payload = {"text": "test result"}

            mock_qdrant_client.search.return_value = [mock_hit1]

            results = await adapter.search(query_vector=[0.1, 0.2, 0.3], limit=10)

            assert len(results) == 1
            assert results[0]["id"] == "result-1"
            assert results[0]["score"] == 0.95
            assert results[0]["payload"]["text"] == "test result"

    @pytest.mark.asyncio
    async def test_search_with_threshold(self, mock_qdrant_client):
        """Test search with score threshold."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            await adapter.search(query_vector=[0.1, 0.2], limit=5, score_threshold=0.8)

            # Verify threshold was passed
            call_args = mock_qdrant_client.search.call_args
            assert call_args[1]["score_threshold"] == 0.8

    @pytest.mark.asyncio
    async def test_search_with_filter(self, mock_qdrant_client):
        """Test search with metadata filter."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            filter_dict = {"kind": "function"}

            await adapter.search(query_vector=[0.1, 0.2], limit=5, filter_dict=filter_dict)

            # Verify filter was passed
            call_args = mock_qdrant_client.search.call_args
            assert call_args[1]["query_filter"] == filter_dict


# ============================================================
# Retrieval Tests
# ============================================================


class TestRetrieval:
    """Test point retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_qdrant_client):
        """Test getting point by ID when it exists."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock retrieved point
            mock_point = MagicMock()
            mock_point.id = "test-id"
            mock_point.vector = [0.1, 0.2, 0.3]
            mock_point.payload = {"text": "test"}

            mock_qdrant_client.retrieve.return_value = [mock_point]

            result = await adapter.get_by_id("test-id")

            assert result is not None
            assert result["id"] == "test-id"
            assert result["vector"] == [0.1, 0.2, 0.3]
            assert result["payload"]["text"] == "test"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_qdrant_client):
        """Test getting point by ID when it doesn't exist."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # No points returned
            mock_qdrant_client.retrieve.return_value = []

            result = await adapter.get_by_id("nonexistent")

            assert result is None


# ============================================================
# Deletion Tests
# ============================================================


class TestDeletion:
    """Test deletion operations."""

    @pytest.mark.asyncio
    async def test_delete_by_id(self, mock_qdrant_client):
        """Test deleting points by ID."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            point_ids = ["id-1", "id-2", "id-3"]

            await adapter.delete_by_id(point_ids)

            mock_qdrant_client.delete.assert_called_once()
            call_args = mock_qdrant_client.delete.call_args
            assert call_args[1]["collection_name"] == "codegraph"
            assert call_args[1]["points_selector"] == point_ids

    @pytest.mark.asyncio
    async def test_delete_collection(self, mock_qdrant_client):
        """Test deleting entire collection."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            await adapter.delete_collection()

            mock_qdrant_client.delete_collection.assert_called_once_with(
                collection_name="codegraph"
            )


# ============================================================
# Count Tests
# ============================================================


class TestCount:
    """Test count operations."""

    @pytest.mark.asyncio
    async def test_count_vectors(self, mock_qdrant_client):
        """Test counting vectors in collection."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock count response
            mock_count_response = MagicMock()
            mock_count_response.count = 42
            mock_qdrant_client.count.return_value = mock_count_response

            count = await adapter.count()

            assert count == 42

    @pytest.mark.asyncio
    async def test_count_empty_collection(self, mock_qdrant_client):
        """Test counting empty collection."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock count response
            mock_count_response = MagicMock()
            mock_count_response.count = 0
            mock_qdrant_client.count.return_value = mock_count_response

            count = await adapter.count()

            assert count == 0


# ============================================================
# Health Check Tests
# ============================================================


class TestHealthCheck:
    """Test health check operations."""

    @pytest.mark.asyncio
    async def test_healthcheck_success(self, mock_qdrant_client):
        """Test health check when Qdrant is available."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock successful get_collections
            mock_collections_response = MagicMock()
            mock_collections_response.collections = []
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            is_healthy = await adapter.healthcheck()

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_healthcheck_failure(self, mock_qdrant_client):
        """Test health check when Qdrant is unavailable."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock failed get_collections
            mock_qdrant_client.get_collections.side_effect = Exception("Connection error")

            is_healthy = await adapter.healthcheck()

            assert is_healthy is False


# ============================================================
# Cleanup Tests
# ============================================================


class TestCleanup:
    """Test cleanup operations."""

    @pytest.mark.asyncio
    async def test_close_client(self, mock_qdrant_client):
        """Test closing Qdrant client."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Create client first
            await adapter._get_client()

            # Close it
            await adapter.close()

            mock_qdrant_client.close.assert_called_once()
            assert adapter._client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        """Test close when no client exists."""
        adapter = QdrantAdapter()

        # Should not raise
        await adapter.close()

        assert adapter._client is None


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_upsert_error_handling(self, mock_qdrant_client):
        """Test upsert error handling."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock error
            mock_qdrant_client.upsert.side_effect = Exception("Upsert failed")

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            vectors = [{"id": "test", "vector": [0.1, 0.2]}]

            with pytest.raises(RuntimeError, match="Failed to upsert vectors"):
                await adapter.upsert_vectors(vectors)

    @pytest.mark.asyncio
    async def test_search_error_handling(self, mock_qdrant_client):
        """Test search error handling."""
        adapter = QdrantAdapter()

        with patch("src.infra.vector.qdrant.AsyncQdrantClient") as mock_class:
            mock_class.return_value = mock_qdrant_client

            # Mock error
            mock_qdrant_client.search.side_effect = Exception("Search failed")

            # Mock existing collection
            mock_collection = MagicMock()
            mock_collection.name = "codegraph"
            mock_collections_response = MagicMock()
            mock_collections_response.collections = [mock_collection]
            mock_qdrant_client.get_collections.return_value = mock_collections_response

            with pytest.raises(RuntimeError, match="Failed to search vectors"):
                await adapter.search(query_vector=[0.1, 0.2])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
