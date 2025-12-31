"""
Memgraph Graph Store Adapter

Infrastructure layer adapter for Memgraph graph database.

Performance Features:
- UNWIND-based batch operations (10-100x faster than individual queries)
- Configurable batch sizes for memory/performance tradeoff
- CREATE mode for fastest fresh data inserts
- Bulk query methods for efficient retrieval
- Async interface with sync driver wrapped via asyncio.to_thread()
- 🔥 SOTA: Real transaction support with ACID guarantees

Note:
    The neo4j driver used by Memgraph is synchronous. This adapter provides
    an async interface by wrapping sync calls with asyncio.to_thread().
    This allows the adapter to be used in async contexts without blocking
    the event loop.
"""

import asyncio
from typing import Any, Literal

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
from codegraph_engine.code_foundation.infrastructure.storage.memgraph.store import (
    DEFAULT_DELETE_BATCH_SIZE,
    DEFAULT_EDGE_BATCH_SIZE,
    DEFAULT_NODE_BATCH_SIZE,
    InsertMode,
)
from codegraph_engine.code_foundation.infrastructure.storage.memgraph.store import (
    MemgraphGraphStore as FoundationMemgraphStore,
)


class MemgraphGraphStore:
    """
    Infrastructure layer adapter for Memgraph graph database.

    Uses UNWIND-based batch operations for optimal performance.
    All public methods are async for consistency with other adapters.
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "",
        password: str = "",
        include_framework_rels: bool = False,
        node_batch_size: int = DEFAULT_NODE_BATCH_SIZE,
        edge_batch_size: int = DEFAULT_EDGE_BATCH_SIZE,
        delete_batch_size: int = DEFAULT_DELETE_BATCH_SIZE,
    ) -> None:
        """
        Initialize Memgraph graph store.

        Args:
            uri: Bolt URI
            username: Username
            password: Password
            include_framework_rels: Whether to create framework-specific indexes
            node_batch_size: Batch size for node insertions (default: 2000)
            edge_batch_size: Batch size for edge insertions (default: 2000)
            delete_batch_size: Batch size for delete operations (default: 3000)
        """
        self.uri = uri
        self._store = FoundationMemgraphStore(
            uri=uri,
            username=username,
            password=password,
            node_batch_size=node_batch_size,
            edge_batch_size=edge_batch_size,
            delete_batch_size=delete_batch_size,
        )

    async def save_graph(
        self,
        graph_doc: GraphDocument,
        mode: InsertMode = "upsert",
        parallel_edges: bool = True,
    ) -> dict[str, Any]:
        """
        Save GraphDocument to Memgraph.

        Args:
            graph_doc: Graph document to save
            mode: Insert mode - "create" (fastest), "merge", or "upsert" (default)
            parallel_edges: Execute edge batches in parallel (default: True)

        Returns:
            Dict with save statistics
        """
        return await asyncio.to_thread(self._store.save_graph, graph_doc, mode=mode, parallel_edges=parallel_edges)

    async def query_called_by(self, function_id: str) -> list[str]:
        """Find all functions that call this function."""
        return await asyncio.to_thread(self._store.query_called_by, function_id)

    async def query_imported_by(self, module_id: str) -> list[str]:
        """Find all modules that import this module."""
        return await asyncio.to_thread(self._store.query_imported_by, module_id)

    async def query_contains_children(self, parent_id: str) -> list[str]:
        """Find all direct children of a node."""
        return await asyncio.to_thread(self._store.query_contains_children, parent_id)

    async def query_node_by_id(self, node_id: str) -> dict | None:
        """Get node by ID."""
        return await asyncio.to_thread(self._store.query_node_by_id, node_id)

    async def delete_repo(self, repo_id: str) -> dict[str, int]:
        """Delete all data for a repository."""
        return await asyncio.to_thread(self._store.delete_repo, repo_id)

    async def delete_snapshot(self, repo_id: str, snapshot_id: str) -> dict[str, int]:
        """Delete all data for a specific snapshot."""
        return await asyncio.to_thread(self._store.delete_snapshot, repo_id, snapshot_id)

    async def delete_nodes_for_deleted_files(self, repo_id: str, file_paths: list[str]) -> int:
        """Delete nodes for files that have been deleted."""
        return await asyncio.to_thread(self._store.delete_nodes_for_deleted_files, repo_id, file_paths)

    async def delete_outbound_edges_by_file_paths(self, repo_id: str, file_paths: list[str]) -> int:
        """Delete only outbound edges from nodes belonging to specific file paths."""
        return await asyncio.to_thread(self._store.delete_outbound_edges_by_file_paths, repo_id, file_paths)

    async def delete_orphan_module_nodes(self, repo_id: str) -> int:
        """Delete orphan module nodes that have no child nodes."""
        return await asyncio.to_thread(self._store.delete_orphan_module_nodes, repo_id)

    # ==================== File-based Relationship Queries ====================

    async def get_imports(self, repo_id: str, file_path: str) -> set[str]:
        """Get file paths that this file imports."""
        return await asyncio.to_thread(self._store.get_imports, repo_id, file_path)

    async def get_imported_by(self, repo_id: str, file_path: str) -> set[str]:
        """Get file paths that import this file."""
        return await asyncio.to_thread(self._store.get_imported_by, repo_id, file_path)

    async def get_callers_by_file(self, repo_id: str, file_path: str) -> set[str]:
        """Get file paths containing functions that call functions in this file."""
        return await asyncio.to_thread(self._store.get_callers_by_file, repo_id, file_path)

    async def get_subclasses_by_file(self, repo_id: str, file_path: str) -> set[str]:
        """Get file paths containing subclasses of classes in this file."""
        return await asyncio.to_thread(self._store.get_subclasses_by_file, repo_id, file_path)

    async def get_superclasses_by_file(self, repo_id: str, file_path: str) -> set[str]:
        """Get file paths containing parent classes of classes in this file."""
        return await asyncio.to_thread(self._store.get_superclasses_by_file, repo_id, file_path)

    # ==================== Bulk Query Methods ====================

    async def query_nodes_by_ids(self, node_ids: list[str]) -> list[dict]:
        """Get multiple nodes by IDs in a single query."""
        return await asyncio.to_thread(self._store.query_nodes_by_ids, node_ids)

    async def query_nodes_by_fqns(self, fqns: list[str], repo_id: str | None = None) -> list[dict]:
        """Get multiple nodes by FQNs in a single query."""
        return await asyncio.to_thread(self._store.query_nodes_by_fqns, fqns, repo_id)

    async def query_neighbors_bulk(
        self,
        node_ids: list[str],
        rel_types: list[str] | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "both",
    ) -> dict[str, list[str]]:
        """Get neighbors for multiple nodes in a single query."""
        return await asyncio.to_thread(self._store.query_neighbors_bulk, node_ids, rel_types, direction)

    async def query_paths_between(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        rel_types: list[str] | None = None,
    ) -> list[list[str]]:
        """Find paths between two nodes."""
        return await asyncio.to_thread(self._store.query_paths_between, source_id, target_id, max_depth, rel_types)

    async def close(self) -> None:
        """Close database connection."""
        await asyncio.to_thread(self._store.close)

    # ==================== Sync Methods (for backward compatibility) ====================
    # These will be deprecated in future versions

    def save_graph_sync(
        self,
        graph_doc: GraphDocument,
        mode: InsertMode = "upsert",
        parallel_edges: bool = True,
    ) -> dict[str, Any]:
        """
        Sync version of save_graph for backward compatibility.

        DEPRECATED: Use async save_graph() instead.
        """
        return self._store.save_graph(graph_doc, mode=mode, parallel_edges=parallel_edges)

    def close_sync(self) -> None:
        """
        Sync version of close for backward compatibility.

        DEPRECATED: Use async close() instead.
        """
        self._store.close()
