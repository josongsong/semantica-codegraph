"""
Unit Tests: server.mcp_server.adapters.mcp.services

Tests MCPSearchService in isolation.

Test Coverage:
- MCPSearchService: search_chunks, search_symbols, get_chunk, get_symbol
- Input validation
- Error handling
- Edge cases
"""

import pytest
from unittest.mock import AsyncMock, Mock

from apps.mcp.mcp.adapters.mcp.services import MCPSearchService, SearchResult


# ============================================================
# MCPSearchService Tests
# ============================================================


class TestMCPSearchService:
    """Unit tests for MCPSearchService."""

    @pytest.fixture
    def mock_chunk_retriever(self):
        """Mock chunk retriever."""
        retriever = Mock()
        retriever.search_chunks = AsyncMock()
        return retriever

    @pytest.fixture
    def mock_symbol_retriever(self):
        """Mock symbol retriever."""
        retriever = Mock()
        retriever.search_symbols = AsyncMock()
        return retriever

    @pytest.fixture
    def mock_node_store(self):
        """Mock node store."""
        store = Mock()
        store.get_by_id = AsyncMock()
        return store

    @pytest.fixture
    def service(self, mock_chunk_retriever, mock_symbol_retriever, mock_node_store):
        """Create service instance."""
        return MCPSearchService(
            mock_chunk_retriever,
            mock_symbol_retriever,
            mock_node_store,
        )

    # ========================================
    # search_chunks Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_search_chunks_happy_path(self, service, mock_chunk_retriever):
        """Test search_chunks with valid input returns results."""
        # Arrange
        mock_chunk_retriever.search_chunks.return_value = [
            {"id": "c1", "content": "test", "file_path": "f.py", "line": 1, "score": 0.9},
        ]

        # Act
        results = await service.search_chunks("test query", limit=10)

        # Assert
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].id == "c1"
        assert results[0].content == "test"
        assert results[0].score == 0.9

        # Verify retriever called with correct params
        mock_chunk_retriever.search_chunks.assert_called_once()
        call_args = mock_chunk_retriever.search_chunks.call_args
        assert call_args[1]["query"] == "test query"
        assert call_args[1]["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_chunks_empty_query_raises_valueerror(self, service):
        """Test search_chunks with empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await service.search_chunks("")

    @pytest.mark.asyncio
    async def test_search_chunks_whitespace_query_raises_valueerror(self, service):
        """Test search_chunks with whitespace-only query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await service.search_chunks("   ")

    @pytest.mark.asyncio
    async def test_search_chunks_retriever_error_raises_runtimeerror(self, service, mock_chunk_retriever):
        """Test search_chunks handles retriever errors."""
        # Arrange
        mock_chunk_retriever.search_chunks.side_effect = Exception("Retriever failed")

        # Act & Assert
        with pytest.raises(RuntimeError, match="Chunk search failed"):
            await service.search_chunks("test")

    # ========================================
    # search_symbols Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_search_symbols_happy_path(self, service, mock_symbol_retriever):
        """Test search_symbols with valid input returns results."""
        # Arrange
        mock_symbol_retriever.search_symbols.return_value = [
            {"id": "s1", "name": "TestClass", "kind": "class", "file_path": "f.py", "line": 10, "score": 0.95},
        ]

        # Act
        results = await service.search_symbols("TestClass", limit=5)

        # Assert
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].id == "s1"
        assert results[0].content == "TestClass"  # Symbol name as content
        assert results[0].metadata["kind"] == "class"
        assert results[0].metadata["type"] == "symbol"

    @pytest.mark.asyncio
    async def test_search_symbols_empty_query_raises_valueerror(self, service):
        """Test search_symbols with empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await service.search_symbols("")

    # ========================================
    # get_chunk Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_get_chunk_found(self, service, mock_node_store):
        """Test get_chunk returns result when chunk exists."""
        # Arrange
        mock_chunk = Mock()
        mock_chunk.id = "chunk_123"
        mock_chunk.content = "chunk content"
        mock_chunk.file_path = "file.py"
        mock_chunk.start_line = 42
        mock_node_store.get_by_id.return_value = mock_chunk

        # Act
        result = await service.get_chunk("chunk_123")

        # Assert
        assert result is not None
        assert result.id == "chunk_123"
        assert result.content == "chunk content"
        assert result.line == 42
        assert result.score == 1.0  # Direct lookup

    @pytest.mark.asyncio
    async def test_get_chunk_not_found_returns_none(self, service, mock_node_store):
        """Test get_chunk returns None when chunk doesn't exist."""
        # Arrange
        mock_node_store.get_by_id.return_value = None

        # Act
        result = await service.get_chunk("nonexistent")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_chunk_empty_id_raises_valueerror(self, service):
        """Test get_chunk with empty ID raises ValueError."""
        with pytest.raises(ValueError, match="chunk_id cannot be empty"):
            await service.get_chunk("")

    @pytest.mark.asyncio
    async def test_get_chunk_error_returns_none(self, service, mock_node_store):
        """Test get_chunk returns None on error (graceful degradation)."""
        # Arrange
        mock_node_store.get_by_id.side_effect = Exception("Database error")

        # Act
        result = await service.get_chunk("chunk_123")

        # Assert
        assert result is None  # Graceful degradation

    # ========================================
    # get_symbol Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_get_symbol_found(self, service, mock_symbol_retriever):
        """Test get_symbol returns result when symbol exists."""
        # Arrange
        mock_symbol_retriever.search_symbols.return_value = [
            {"id": "s1", "name": "Symbol1", "kind": "function", "file_path": "f.py", "line": 1, "score": 0.9},
        ]

        # Act
        result = await service.get_symbol("s1")

        # Assert
        assert result is not None
        assert result.id == "s1"

    @pytest.mark.asyncio
    async def test_get_symbol_not_found_returns_none(self, service, mock_symbol_retriever):
        """Test get_symbol returns None when not found."""
        # Arrange
        mock_symbol_retriever.search_symbols.return_value = []

        # Act
        result = await service.get_symbol("nonexistent")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_symbol_empty_id_raises_valueerror(self, service):
        """Test get_symbol with empty ID raises ValueError."""
        with pytest.raises(ValueError, match="symbol_id cannot be empty"):
            await service.get_symbol("")


# ============================================================
# SearchResult Tests
# ============================================================


class TestSearchResult:
    """Unit tests for SearchResult DTO."""

    def test_searchresult_to_dict(self):
        """Test SearchResult.to_dict() returns correct dict."""
        # Arrange
        result = SearchResult(
            id="test_id",
            content="test content",
            file_path="test.py",
            line=42,
            score=0.95,
            metadata={"type": "chunk", "extra": "data"},
        )

        # Act
        result_dict = result.to_dict()

        # Assert
        assert result_dict["id"] == "test_id"
        assert result_dict["content"] == "test content"
        assert result_dict["file_path"] == "test.py"
        assert result_dict["line"] == 42
        assert result_dict["score"] == 0.95
        assert result_dict["type"] == "chunk"  # From metadata
        assert result_dict["extra"] == "data"  # From metadata

    def test_searchresult_to_dict_empty_metadata(self):
        """Test SearchResult.to_dict() with empty metadata."""
        # Arrange
        result = SearchResult(
            id="id",
            content="content",
            file_path="file.py",
            line=1,
            score=0.5,
        )

        # Act
        result_dict = result.to_dict()

        # Assert
        assert "id" in result_dict
        assert "content" in result_dict
        assert result_dict["score"] == 0.5
