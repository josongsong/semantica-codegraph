"""
Kuzu Graph Store Adapter Tests

Tests the infrastructure layer Kuzu adapter which wraps the foundation layer.
Tests delegation to the foundation store and legacy interface deprecation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infra.graph.kuzu import KuzuGraphStore

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_foundation_store():
    """Mock foundation layer KuzuGraphStore."""
    mock_store = MagicMock()

    # Mock query methods
    mock_store.query_called_by.return_value = ["func1", "func2"]
    mock_store.query_imported_by.return_value = ["module1"]
    mock_store.query_contains_children.return_value = ["child1", "child2"]
    mock_store.query_reads_variable.return_value = ["block1"]
    mock_store.query_writes_variable.return_value = ["block2"]
    mock_store.query_cfg_successors.return_value = ["block3"]
    mock_store.query_node_by_id.return_value = {"id": "test", "kind": "function"}

    # Mock delete methods
    mock_store.delete_nodes.return_value = 5
    mock_store.delete_repo.return_value = {"nodes": 100, "edges": 200}
    mock_store.delete_snapshot.return_value = {"nodes": 10, "edges": 20}
    mock_store.delete_nodes_by_filter.return_value = 3

    # Mock save method
    mock_store.save_graph.return_value = None

    # Mock close
    mock_store.close.return_value = None

    return mock_store


# ============================================================
# Initialization Tests
# ============================================================


class TestKuzuAdapterBasics:
    """Test basic adapter creation and configuration."""

    def test_kuzu_adapter_creation(self, mock_foundation_store):
        """Test creating Kuzu adapter."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            assert adapter.db_path == Path("/tmp/test.db")
            assert adapter.buffer_pool_size == 1024  # default
            assert adapter._store is mock_foundation_store

    def test_kuzu_adapter_custom_config(self, mock_foundation_store):
        """Test creating Kuzu adapter with custom config."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(
                db_path="/custom/path.db",
                buffer_pool_size=2048,
                include_framework_rels=True,
            )

            assert adapter.db_path == Path("/custom/path.db")
            assert adapter.buffer_pool_size == 2048

            # Verify foundation store was created with correct args
            mock_class.assert_called_once_with(
                db_path="/custom/path.db", include_framework_rels=True
            )


# ============================================================
# Graph Save Tests
# ============================================================


class TestGraphSave:
    """Test graph save operations."""

    def test_save_graph_delegates_to_foundation(self, mock_foundation_store):
        """Test that save_graph delegates to foundation store."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            # Mock GraphDocument
            mock_graph_doc = MagicMock()

            adapter.save_graph(mock_graph_doc)

            # Should delegate to foundation store
            mock_foundation_store.save_graph.assert_called_once_with(mock_graph_doc)


# ============================================================
# Query Tests
# ============================================================


class TestQueries:
    """Test query operations."""

    def test_query_called_by(self, mock_foundation_store):
        """Test query_called_by delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.query_called_by("func:test")

            assert result == ["func1", "func2"]
            mock_foundation_store.query_called_by.assert_called_once_with("func:test")

    def test_query_imported_by(self, mock_foundation_store):
        """Test query_imported_by delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.query_imported_by("module:test")

            assert result == ["module1"]
            mock_foundation_store.query_imported_by.assert_called_once_with("module:test")

    def test_query_contains_children(self, mock_foundation_store):
        """Test query_contains_children delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.query_contains_children("parent:id")

            assert result == ["child1", "child2"]
            mock_foundation_store.query_contains_children.assert_called_once_with("parent:id")

    def test_query_reads_variable(self, mock_foundation_store):
        """Test query_reads_variable delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.query_reads_variable("var:x")

            assert result == ["block1"]
            mock_foundation_store.query_reads_variable.assert_called_once_with("var:x")

    def test_query_writes_variable(self, mock_foundation_store):
        """Test query_writes_variable delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.query_writes_variable("var:y")

            assert result == ["block2"]
            mock_foundation_store.query_writes_variable.assert_called_once_with("var:y")

    def test_query_cfg_successors(self, mock_foundation_store):
        """Test query_cfg_successors delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.query_cfg_successors("block:1")

            assert result == ["block3"]
            mock_foundation_store.query_cfg_successors.assert_called_once_with("block:1")

    def test_query_node_by_id(self, mock_foundation_store):
        """Test query_node_by_id delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.query_node_by_id("node:test")

            assert result == {"id": "test", "kind": "function"}
            mock_foundation_store.query_node_by_id.assert_called_once_with("node:test")


# ============================================================
# Delete Tests
# ============================================================


class TestDelete:
    """Test delete operations."""

    def test_delete_nodes(self, mock_foundation_store):
        """Test delete_nodes delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            count = adapter.delete_nodes(["node1", "node2", "node3"])

            assert count == 5
            mock_foundation_store.delete_nodes.assert_called_once_with(["node1", "node2", "node3"])

    def test_delete_repo(self, mock_foundation_store):
        """Test delete_repo delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.delete_repo("repo:test")

            assert result == {"nodes": 100, "edges": 200}
            mock_foundation_store.delete_repo.assert_called_once_with("repo:test")

    def test_delete_snapshot(self, mock_foundation_store):
        """Test delete_snapshot delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            result = adapter.delete_snapshot("repo:test", "snap:001")

            assert result == {"nodes": 10, "edges": 20}
            mock_foundation_store.delete_snapshot.assert_called_once_with("repo:test", "snap:001")

    def test_delete_nodes_by_filter(self, mock_foundation_store):
        """Test delete_nodes_by_filter delegates correctly."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            count = adapter.delete_nodes_by_filter(
                repo_id="repo:test", snapshot_id="snap:001", kind="function"
            )

            assert count == 3
            mock_foundation_store.delete_nodes_by_filter.assert_called_once_with(
                "repo:test", "snap:001", "function"
            )


# ============================================================
# Legacy Interface Tests
# ============================================================


class TestLegacyInterface:
    """Test deprecated legacy interface methods."""

    @pytest.mark.asyncio
    async def test_create_node_raises_not_implemented(self, mock_foundation_store):
        """Test that create_node raises NotImplementedError."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            with pytest.raises(NotImplementedError, match="create_node\\(\\) is deprecated"):
                await adapter.create_node({"id": "test"})

    @pytest.mark.asyncio
    async def test_create_relationship_raises_not_implemented(self, mock_foundation_store):
        """Test that create_relationship raises NotImplementedError."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            with pytest.raises(
                NotImplementedError, match="create_relationship\\(\\) is deprecated"
            ):
                await adapter.create_relationship("src", "tgt", "CALLS")

    @pytest.mark.asyncio
    async def test_get_neighbors_raises_not_implemented(self, mock_foundation_store):
        """Test that get_neighbors raises NotImplementedError."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            with pytest.raises(NotImplementedError, match="get_neighbors\\(\\) is not"):
                await adapter.get_neighbors("node:test")

    @pytest.mark.asyncio
    async def test_query_path_raises_not_implemented(self, mock_foundation_store):
        """Test that query_path raises NotImplementedError."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            with pytest.raises(NotImplementedError, match="query_path\\(\\) is not"):
                await adapter.query_path("node1", "node2")

    @pytest.mark.asyncio
    async def test_bulk_create_raises_not_implemented(self, mock_foundation_store):
        """Test that bulk_create raises NotImplementedError."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            with pytest.raises(NotImplementedError, match="bulk_create\\(\\) is deprecated"):
                await adapter.bulk_create([{"id": "test"}])


# ============================================================
# Cleanup Tests
# ============================================================


class TestCleanup:
    """Test cleanup operations."""

    def test_close(self, mock_foundation_store):
        """Test close delegates to foundation store."""
        with patch("src.infra.graph.kuzu.FoundationKuzuStore") as mock_class:
            mock_class.return_value = mock_foundation_store

            adapter = KuzuGraphStore(db_path="/tmp/test.db")

            adapter.close()

            mock_foundation_store.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
