"""
Kùzu Graph Store Adapter

Provides the interface expected by the DI container.
Wraps the actual KuzuGraphStore implementation from foundation layer.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from src.foundation.graph.models import GraphDocument
from src.foundation.storage.kuzu.store import KuzuGraphStore as FoundationKuzuStore


class KuzuGraphStore:
    """
    Infrastructure layer adapter for Kuzu graph database.

    This adapter wraps the foundation layer's KuzuGraphStore and provides
    both the legacy interface (for backward compatibility) and direct access
    to the foundation store.
    """

    def __init__(
        self,
        db_path: str | Path,
        buffer_pool_size: int = 1024,
        include_framework_rels: bool = False,
    ) -> None:
        """
        Initialize Kuzu graph store.

        Args:
            db_path: Path to Kuzu database directory
            buffer_pool_size: Buffer pool size (currently unused, kept for compatibility)
            include_framework_rels: Whether to create framework-specific REL tables
        """
        self.db_path = Path(db_path)
        self.buffer_pool_size = buffer_pool_size

        # Initialize foundation layer Kuzu store
        self._store = FoundationKuzuStore(db_path=db_path, include_framework_rels=include_framework_rels)

    # ============================================================
    # Foundation Layer Direct Access
    # ============================================================

    def save_graph(self, graph_doc: GraphDocument) -> None:
        """
        Save GraphDocument to Kuzu.

        Args:
            graph_doc: Graph document to save
        """
        self._store.save_graph(graph_doc)

    def query_called_by(self, function_id: str) -> list[str]:
        """Find all functions that call this function."""
        return self._store.query_called_by(function_id)

    def query_imported_by(self, module_id: str) -> list[str]:
        """Find all modules that import this module."""
        return self._store.query_imported_by(module_id)

    def query_contains_children(self, parent_id: str) -> list[str]:
        """Find all direct children of a node."""
        return self._store.query_contains_children(parent_id)

    def query_reads_variable(self, variable_id: str) -> list[str]:
        """Find all CFG blocks that read this variable."""
        return self._store.query_reads_variable(variable_id)

    def query_writes_variable(self, variable_id: str) -> list[str]:
        """Find all CFG blocks that write this variable."""
        return self._store.query_writes_variable(variable_id)

    def query_cfg_successors(self, block_id: str) -> list[str]:
        """Find all CFG successor blocks."""
        return self._store.query_cfg_successors(block_id)

    def query_node_by_id(self, node_id: str) -> dict | None:
        """Get node by ID."""
        return self._store.query_node_by_id(node_id)

    # ============================================================
    # Delete Operations
    # ============================================================

    def delete_nodes(self, node_ids: list[str]) -> int:
        """
        Delete nodes by IDs.

        Args:
            node_ids: List of node IDs to delete

        Returns:
            Number of nodes deleted
        """
        return self._store.delete_nodes(node_ids)

    def delete_repo(self, repo_id: str) -> dict[str, int]:
        """
        Delete all data for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            Dict with deletion counts
        """
        return self._store.delete_repo(repo_id)

    def delete_snapshot(self, repo_id: str, snapshot_id: str) -> dict[str, int]:
        """
        Delete all data for a specific snapshot.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Dict with deletion counts
        """
        return self._store.delete_snapshot(repo_id, snapshot_id)

    def delete_nodes_by_filter(self, repo_id: str, snapshot_id: str | None = None, kind: str | None = None) -> int:
        """
        Delete nodes by filter criteria.

        Args:
            repo_id: Repository ID (required)
            snapshot_id: Optional snapshot ID filter
            kind: Optional node kind filter

        Returns:
            Number of nodes deleted
        """
        return self._store.delete_nodes_by_filter(repo_id, snapshot_id, kind)

    # ============================================================
    # Legacy Interface (for backward compatibility)
    # ============================================================

    async def create_node(self, node: dict[str, Any]) -> None:
        """
        Legacy interface for creating a node.

        Note: This is kept for backward compatibility.
        Prefer using save_graph() with GraphDocument for new code.
        """
        # Convert dict to GraphNode if needed
        # For now, raise NotImplementedError to encourage migration
        raise NotImplementedError("create_node() is deprecated. Use save_graph() with GraphDocument instead.")

    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Legacy interface for creating a relationship.

        Note: This is kept for backward compatibility.
        Prefer using save_graph() with GraphDocument for new code.
        """
        raise NotImplementedError("create_relationship() is deprecated. Use save_graph() with GraphDocument instead.")

    async def get_neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "outgoing",
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        """
        Get neighbors of a node.

        Args:
            node_id: Node ID
            rel_type: Relationship type filter (e.g., "CALLS", "CONTAINS")
            direction: "outgoing", "incoming", or "both"
            depth: Traversal depth

        Returns:
            List of neighbor nodes
        """
        # Implement basic neighbor query
        # For complex queries, use Cypher-like queries via foundation store
        raise NotImplementedError("get_neighbors() is not fully implemented yet")

    async def query_path(self, start_id: str, end_id: str, max_depth: int = 5) -> list[list[str]]:
        """
        Find paths between two nodes.

        Args:
            start_id: Start node ID
            end_id: End node ID
            max_depth: Maximum path depth

        Returns:
            List of paths (each path is a list of node IDs)
        """
        raise NotImplementedError("query_path() is not fully implemented yet")

    async def bulk_create(self, nodes: Iterable[dict[str, Any]]) -> None:
        """
        Bulk create nodes.

        Note: Prefer using save_graph() with GraphDocument for new code.
        """
        raise NotImplementedError("bulk_create() is deprecated. Use save_graph() with GraphDocument instead.")

    def close(self) -> None:
        """Close database connection."""
        self._store.close()
