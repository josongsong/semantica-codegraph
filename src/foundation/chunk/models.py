"""
Chunk Data Models

Symbol-first hierarchical chunking for RAG.

Hierarchy:
    Repo → Project → Module → File → Class → Function
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class Chunk(BaseModel):
    """
    A chunk represents a hierarchical unit of code for RAG.

    Hierarchy levels:
    - repo: Top-level repository
    - project: Sub-project within a monorepo
    - module: Directory/package structure
    - file: Source file
    - class: Class/interface/struct
    - function: Function/method (leaf chunks)

    ID format: chunk:{repo_id}:{kind}:{fqn}
    """

    chunk_id: str
    repo_id: str
    snapshot_id: str  # Git commit hash or timestamp
    project_id: str | None
    module_path: str | None
    file_path: str | None

    kind: Literal[
        # Core hierarchy (Phase 2)
        "repo",
        "project",
        "module",
        "file",
        "class",
        "function",
        # Extended types (Phase 3: Framework/Architecture)
        "route",  # API route endpoint
        "service",  # Service layer
        "repository",  # Data access layer
        "config",  # Configuration
        "job",  # Background job/task
        "middleware",  # Middleware component
    ]

    fqn: str  # Fully qualified dotted name

    # Line range (current snapshot)
    start_line: int | None
    end_line: int | None

    # Original line range (for span drift detection)
    original_start_line: int | None
    original_end_line: int | None

    content_hash: str | None  # Hash of code text

    parent_id: str | None
    children: list[str]

    language: str | None  # "python", "typescript", etc.
    symbol_visibility: str | None  # "public" | "internal" | "private"

    symbol_id: str | None  # Symbol this chunk represents
    symbol_owner_id: str | None  # Actual definition symbol (for re-exports/wrappers)

    summary: str | None
    importance: float | None
    attrs: dict[str, Any] = {}

    # Versioning (for incremental updates)
    version: int = 1
    last_indexed_commit: str | None = None
    is_deleted: bool = False


# Type aliases for mappings
ChunkId = str
GraphNodeId = str
IRNodeId = str

ChunkToGraph = dict[ChunkId, set[GraphNodeId]]
ChunkToIR = dict[ChunkId, set[IRNodeId]]
ChunkHierarchy = dict[ChunkId, list[ChunkId]]  # parent -> children


# ============================================================
# Incremental Update Models
# ============================================================


class ChunkDiffType(str, Enum):
    """Types of chunk differences"""

    UNCHANGED = "unchanged"  # No changes
    MOVED = "moved"  # Position changed, content unchanged (span drift)
    MODIFIED = "modified"  # Content changed
    ADDED = "added"  # New chunk
    DELETED = "deleted"  # Removed chunk


@dataclass
class ChunkRefreshResult:
    """
    Result of incremental chunk refresh.

    Tracks all changes to chunks after processing file modifications.
    """

    added_chunks: list[Chunk] = field(default_factory=list)
    updated_chunks: list[Chunk] = field(default_factory=list)
    deleted_chunks: list[str] = field(default_factory=list)  # chunk_id only
    renamed_chunks: dict[str, str] = field(default_factory=dict)  # old_id → new_id (Phase B)
    drifted_chunks: list[str] = field(default_factory=list)  # chunk_id (Phase B)

    def total_changes(self) -> int:
        """Get total number of changes"""
        return (
            len(self.added_chunks)
            + len(self.updated_chunks)
            + len(self.deleted_chunks)
            + len(self.renamed_chunks)
            + len(self.drifted_chunks)
        )

    def has_changes(self) -> bool:
        """Check if any changes occurred"""
        return self.total_changes() > 0
