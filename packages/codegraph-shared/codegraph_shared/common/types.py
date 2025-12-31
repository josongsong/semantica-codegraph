"""
Common Type Definitions

Provides type aliases and protocols for dependency injection.
"""

from collections.abc import Callable
from typing import Protocol, TypeVar

# Type variable for generic types
T = TypeVar("T")


# ============================================================
# Factory Type Aliases
# ============================================================


class GraphStoreProtocol(Protocol):
    """Protocol for GraphStore interface."""

    def add_node(self, node_id: str, **kwargs) -> None: ...

    def add_edge(self, source: str, target: str, **kwargs) -> None: ...

    def close(self) -> None: ...


class RepoMapStoreProtocol(Protocol):
    """Protocol for RepoMapStore interface."""

    def get(self, repo_id: str) -> dict | None: ...

    def save(self, repo_id: str, data: dict) -> None: ...


class PyrightDaemonProtocol(Protocol):
    """Protocol for PyrightDaemon interface."""

    def analyze(self, file_path: str) -> dict: ...

    def shutdown(self) -> None: ...


# Factory function type aliases
GraphStoreFactory = Callable[[], GraphStoreProtocol]
RepoMapStoreFactory = Callable[[], RepoMapStoreProtocol]
PyrightDaemonFactory = Callable[[str], PyrightDaemonProtocol]


# Generic factory type
Factory = Callable[[], T]


# ============================================================
# Container Type Protocols
# ============================================================


class IndexingContainerProtocol(Protocol):
    """Protocol for IndexingContainer interface."""

    @property
    def orchestrator(self): ...

    @property
    def job_orchestrator(self): ...


# Container factory type aliases
IndexingContainerFactory = Callable[[], IndexingContainerProtocol]


# ============================================================
# Utility Types
# ============================================================


# Optional factory (can be None)
OptionalFactory = Callable[[], T] | None
