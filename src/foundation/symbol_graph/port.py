"""
Symbol Graph Storage Port

Interface for persisting SymbolGraph to external storage.
Follows Port-Adapter (Hexagonal) architecture pattern.
"""

from typing import Protocol

from .models import SymbolGraph


class SymbolGraphPort(Protocol):
    """
    Port (Interface) for SymbolGraph persistence.

    Implementations (Adapters):
    - PostgreSQLSymbolGraphAdapter: Stores in PostgreSQL tables
    - MemgraphSymbolGraphAdapter: Stores in Memgraph (future)
    - FileSystemSymbolGraphAdapter: Stores as JSON files (future)
    """

    def save(self, graph: SymbolGraph) -> None:
        """
        Save SymbolGraph to persistent storage.

        Args:
            graph: SymbolGraph to save

        Raises:
            StorageError: If save operation fails
        """
        ...

    def load(self, repo_id: str, snapshot_id: str) -> SymbolGraph:
        """
        Load SymbolGraph from persistent storage.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            SymbolGraph instance

        Raises:
            NotFoundError: If graph not found
            StorageError: If load operation fails
        """
        ...

    def delete(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete SymbolGraph from persistent storage.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Raises:
            StorageError: If delete operation fails
        """
        ...

    def exists(self, repo_id: str, snapshot_id: str) -> bool:
        """
        Check if SymbolGraph exists in storage.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            True if graph exists, False otherwise
        """
        ...
