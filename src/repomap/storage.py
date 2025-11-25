"""
RepoMap Storage Layer

Protocol and implementations for persisting RepoMap snapshots.

Implementations:
- InMemoryRepoMapStore: For testing and development
- PostgresRepoMapStore: For production (in storage_postgres.py)
"""

from abc import abstractmethod
from typing import Protocol

from src.repomap.models import RepoMapNode, RepoMapSnapshot


class RepoMapStore(Protocol):
    """
    Storage protocol for RepoMap snapshots.

    Implementations must support:
    - Save/load snapshots
    - Query nodes by ID, path, FQN
    - Get subtrees
    """

    @abstractmethod
    def save_snapshot(self, snapshot: RepoMapSnapshot) -> None:
        """Save a complete RepoMap snapshot."""
        ...

    @abstractmethod
    def get_snapshot(self, repo_id: str, snapshot_id: str) -> RepoMapSnapshot | None:
        """Get a snapshot by repo_id and snapshot_id."""
        ...

    @abstractmethod
    def list_snapshots(self, repo_id: str) -> list[str]:
        """List all snapshot IDs for a repo."""
        ...

    @abstractmethod
    def delete_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """Delete a snapshot."""
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> RepoMapNode | None:
        """Get a single node by ID."""
        ...

    @abstractmethod
    def get_nodes_by_path(self, repo_id: str, snapshot_id: str, path: str) -> list[RepoMapNode]:
        """Get all nodes matching a path."""
        ...

    @abstractmethod
    def get_nodes_by_fqn(self, repo_id: str, snapshot_id: str, fqn: str) -> list[RepoMapNode]:
        """Get all nodes matching an FQN."""
        ...

    @abstractmethod
    def get_subtree(self, node_id: str) -> list[RepoMapNode]:
        """Get node and all descendants."""
        ...


class InMemoryRepoMapStore:
    """
    In-memory RepoMapStore implementation.

    For testing and development. Does not persist across restarts.
    """

    def __init__(self):
        # snapshots: {(repo_id, snapshot_id): RepoMapSnapshot}
        self.snapshots: dict[tuple[str, str], RepoMapSnapshot] = {}

        # nodes: {node_id: RepoMapNode}
        self.nodes: dict[str, RepoMapNode] = {}

    def save_snapshot(self, snapshot: RepoMapSnapshot) -> None:
        """Save a complete RepoMap snapshot."""
        key = (snapshot.repo_id, snapshot.snapshot_id)
        self.snapshots[key] = snapshot

        # Index all nodes
        for node in snapshot.nodes:
            self.nodes[node.id] = node

    def get_snapshot(self, repo_id: str, snapshot_id: str) -> RepoMapSnapshot | None:
        """Get a snapshot by repo_id and snapshot_id."""
        key = (repo_id, snapshot_id)
        return self.snapshots.get(key)

    def list_snapshots(self, repo_id: str) -> list[str]:
        """List all snapshot IDs for a repo."""
        return [sid for rid, sid in self.snapshots.keys() if rid == repo_id]

    def delete_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """Delete a snapshot."""
        key = (repo_id, snapshot_id)
        snapshot = self.snapshots.pop(key, None)

        if snapshot:
            # Remove nodes from index
            for node in snapshot.nodes:
                self.nodes.pop(node.id, None)

    def get_node(self, node_id: str) -> RepoMapNode | None:
        """Get a single node by ID."""
        return self.nodes.get(node_id)

    def get_nodes_by_path(self, repo_id: str, snapshot_id: str, path: str) -> list[RepoMapNode]:
        """Get all nodes matching a path."""
        snapshot = self.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        return [node for node in snapshot.nodes if node.path == path]

    def get_nodes_by_fqn(self, repo_id: str, snapshot_id: str, fqn: str) -> list[RepoMapNode]:
        """Get all nodes matching an FQN."""
        snapshot = self.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        return [node for node in snapshot.nodes if node.fqn == fqn]

    def get_subtree(self, node_id: str) -> list[RepoMapNode]:
        """Get node and all descendants."""
        node = self.get_node(node_id)
        if not node:
            return []

        # Find snapshot containing this node
        snapshot = None
        for s in self.snapshots.values():
            if any(n.id == node_id for n in s.nodes):
                snapshot = s
                break

        if not snapshot:
            return [node]

        return snapshot.get_subtree(node_id)


# PostgresRepoMapStore is in storage_postgres.py
# Import here for convenience
try:
    from .storage_postgres import PostgresRepoMapStore
except ImportError:
    # asyncpg not installed, define stub
    class PostgresRepoMapStore:  # type: ignore
        """Stub class when asyncpg is not available."""

        def __init__(self, connection_string: str):
            raise ImportError("asyncpg is required for PostgresRepoMapStore. " "Install with: pip install asyncpg")
