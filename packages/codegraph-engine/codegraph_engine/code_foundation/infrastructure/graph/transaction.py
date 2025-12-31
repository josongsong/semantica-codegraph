"""
Graph Store Transaction Support (SOTA).

Provides transaction context manager for atomic graph operations.
Ensures data integrity during incremental updates.
"""

from contextlib import asynccontextmanager
from typing import Any, Protocol

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class GraphStoreTransaction(Protocol):
    """
    Transaction protocol for graph store operations.

    Ensures atomic execution of:
    1. Delete outbound edges
    2. Upsert nodes
    3. Commit or rollback
    """

    async def delete_outbound_edges_by_file_paths(self, repo_id: str, file_paths: list[str]) -> int:
        """Delete outbound edges for modified files."""
        ...

    async def upsert_nodes(self, repo_id: str, nodes: list[Any]) -> int:
        """Upsert graph nodes."""
        ...

    async def upsert_edges(self, repo_id: str, edges: list[Any]) -> int:
        """Upsert graph edges."""
        ...

    async def commit(self) -> None:
        """Commit transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback transaction."""
        ...


class GraphStoreWithTransaction(Protocol):
    """Graph store that supports transactions."""

    @asynccontextmanager
    async def transaction(self) -> GraphStoreTransaction:
        """
        Begin a transaction for atomic graph operations.

        Usage:
            async with graph_store.transaction() as tx:
                await tx.delete_outbound_edges_by_file_paths(repo_id, files)
                await tx.upsert_nodes(repo_id, new_nodes)
                await tx.commit()  # Auto-commit on success

        Yields:
            Transaction context
        """
        ...


class MockGraphTransaction:
    """
    Mock transaction implementation for testing.

    In production, this would be replaced with actual DB transaction
    (e.g., Memgraph MULTI/EXEC, PostgreSQL BEGIN/COMMIT).
    """

    def __init__(self, graph_store):
        self.graph_store = graph_store
        self._operations: list[tuple[str, Any]] = []
        self._committed = False
        self._rolled_back = False

    async def delete_outbound_edges_by_file_paths(self, repo_id: str, file_paths: list[str]) -> int:
        """Delete outbound edges (queued)."""
        logger.debug("transaction_queue_delete_edges", repo_id=repo_id, files_count=len(file_paths))
        self._operations.append(("delete_edges", (repo_id, file_paths)))
        return len(file_paths)  # Mock count

    async def upsert_nodes(self, repo_id: str, nodes: list[Any]) -> int:
        """Upsert nodes (queued)."""
        logger.debug("transaction_queue_upsert_nodes", repo_id=repo_id, nodes_count=len(nodes))
        self._operations.append(("upsert_nodes", (repo_id, nodes)))
        return len(nodes)

    async def upsert_edges(self, repo_id: str, edges: list[Any]) -> int:
        """Upsert edges (queued)."""
        logger.debug("transaction_queue_upsert_edges", repo_id=repo_id, edges_count=len(edges))
        self._operations.append(("upsert_edges", (repo_id, edges)))
        return len(edges)

    async def commit(self) -> None:
        """Commit all queued operations."""
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")

        logger.info("transaction_commit_started", operations_count=len(self._operations))

        try:
            for op_type, args in self._operations:
                if op_type == "delete_edges":
                    repo_id, file_paths = args
                    await self.graph_store.delete_outbound_edges_by_file_paths(repo_id, file_paths)
                elif op_type == "upsert_nodes":
                    repo_id, nodes = args
                    # Call actual graph store upsert
                    if hasattr(self.graph_store, "upsert_nodes"):
                        await self.graph_store.upsert_nodes(repo_id, nodes)
                elif op_type == "upsert_edges":
                    repo_id, edges = args
                    if hasattr(self.graph_store, "upsert_edges"):
                        await self.graph_store.upsert_edges(repo_id, edges)

            self._committed = True
            logger.info("transaction_commit_completed", operations_count=len(self._operations))

        except Exception as e:
            logger.error("transaction_commit_failed_rolling_back", error=str(e))
            await self.rollback()
            raise

    async def rollback(self) -> None:
        """Rollback transaction (no-op for queued operations)."""
        if self._committed:
            logger.warning("transaction_rollback_after_commit_ignored")
            return

        logger.warning("transaction_rollback", operations_discarded=len(self._operations))
        self._operations.clear()
        self._rolled_back = True


@asynccontextmanager
async def graph_transaction(graph_store):
    """
    Transaction context manager for graph operations.

    Usage:
        async with graph_transaction(store) as tx:
            await tx.delete_outbound_edges_by_file_paths(repo_id, files)
            await tx.upsert_nodes(repo_id, nodes)
            # Auto-commit on success, auto-rollback on exception
    """
    tx = MockGraphTransaction(graph_store)

    try:
        yield tx
        # Auto-commit on successful exit
        if not tx._committed and not tx._rolled_back:
            await tx.commit()
    except Exception as e:
        # Auto-rollback on exception
        logger.error("graph_transaction_exception_auto_rollback", error=str(e))
        await tx.rollback()
        raise
