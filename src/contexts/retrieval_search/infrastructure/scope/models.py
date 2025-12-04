"""
Scope Selection Models

Models for search scope selection based on RepoMap and intent.
"""

from dataclasses import dataclass, field
from typing import Literal

from src.contexts.repo_structure.infrastructure.models import RepoMapNode


@dataclass
class ScopeResult:
    """
    Result of scope selection.

    Attributes:
        scope_type: Type of scope ("full_repo", "focused", "symbol_only")
        reason: Reason for scope selection
        focus_nodes: RepoMap nodes selected as focus points
        chunk_ids: Chunk IDs within scope (for filtering)
        metadata: Additional metadata
    """

    scope_type: Literal["full_repo", "focused", "symbol_only"]
    reason: str
    focus_nodes: list[RepoMapNode] = field(default_factory=list)
    chunk_ids: set[str] = field(default_factory=set)
    metadata: dict = field(default_factory=dict)

    @property
    def is_full_repo(self) -> bool:
        """Whether scope is full repository."""
        return self.scope_type == "full_repo"

    @property
    def is_focused(self) -> bool:
        """Whether scope is focused on specific nodes."""
        return self.scope_type == "focused"

    @property
    def node_count(self) -> int:
        """Number of focus nodes."""
        return len(self.focus_nodes)

    @property
    def chunk_count(self) -> int:
        """Number of chunks in scope."""
        return len(self.chunk_ids)
