"""
Chunk Data Models

Symbol-first hierarchical chunking for RAG.

Hierarchy:
    Repo → Project → Module → File → Class → Function
"""

from dataclasses import dataclass, field
from datetime import datetime
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
        # Documentation
        "document",  # Documentation file or section
        # GAP #5: Cross-file chunk types
        "module_api",  # Module-level public API (from __all__ exports)
        "interface",  # Cross-file interface/protocol definition
        "reexport",  # Re-exported symbol from another module
        # P2: Diff/PR analysis
        "diff",  # Git diff block (for PR/commit analysis)
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

    # P1: Test detection (M1)
    is_test: bool | None = None  # True if this is a test function/class

    # P2: Overlay support (IDE integration)
    is_overlay: bool = False  # True if this is an overlay chunk (unsaved IDE changes)
    overlay_session_id: str | None = None  # IDE session ID for overlay chunks
    base_chunk_id: str | None = None  # Original base chunk ID that this overlay shadows

    # Git History (P0-1: Layer 19)
    # Enriched during indexing via GitHistoryAnalyzer
    history: "ChunkHistory | None" = None


# Type aliases for mappings
ChunkId = str
GraphNodeId = str
IRNodeId = str

ChunkToGraph = dict[ChunkId, set[GraphNodeId]]
ChunkToIR = dict[ChunkId, set[IRNodeId]]
ChunkHierarchy = dict[ChunkId, list[ChunkId]]  # parent -> children


# ============================================================
# GAP #5: Cross-file Chunk Relationships
# ============================================================


class ModuleAPIChunk(BaseModel):
    """
    Module-level public API chunk (GAP #5).

    Represents the public API surface of a module, derived from:
    - __all__ exports (Python)
    - export statements (TypeScript/JavaScript)
    - Public declarations (Go, Rust)

    This chunk has no line range (cross-file) and references
    symbols from multiple files within the module.
    """

    chunk_id: str
    repo_id: str
    snapshot_id: str
    module_path: str

    # Exported symbols (symbol_id → source file)
    exported_symbols: dict[str, str] = {}  # symbol_id → file_path

    # Re-exports (symbol_id → original module)
    reexported_symbols: dict[str, str] = {}  # symbol_id → source_module_path

    # All exports (computed: exported + reexported)
    @property
    def all_exports(self) -> set[str]:
        return set(self.exported_symbols.keys()) | set(self.reexported_symbols.keys())


class CrossFileRelation(BaseModel):
    """
    Cross-file relationship between chunks (GAP #5).

    Represents dependencies/references that span file boundaries.
    """

    source_chunk_id: str
    target_chunk_id: str
    relation_type: Literal[
        "imports",  # Source imports target
        "extends",  # Source extends target (inheritance)
        "implements",  # Source implements target (interface)
        "uses",  # Source uses target (function call, type reference)
        "reexports",  # Source re-exports target
    ]
    # Optional: Symbol ID for the specific reference
    symbol_id: str | None = None


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


# ============================================================
# Git History Models (P0-1: Layer 19)
# ============================================================


class ChunkHistory(BaseModel):
    """
    Git history enrichment for chunks.

    Provides code ownership, evolution metrics, and co-change patterns
    for improved retrieval and context ranking.

    Enriched during indexing via GitHistoryAnalyzer.
    """

    # Primary ownership
    author: str | None  # Primary contributor (most lines authored)
    last_modified_by: str | None  # Most recent contributor
    last_modified_at: datetime | None  # Last modification timestamp
    commit_sha: str | None  # Last commit that modified this chunk

    # Evolution metrics
    churn_score: float | None  # Change frequency (higher = more volatile)
    stability_index: float | None  # Inverse of churn (higher = more stable)
    contributor_count: int | None  # Number of unique contributors

    # Co-change patterns (for context expansion)
    co_changed_files: list[str] = field(default_factory=list)  # Files frequently modified together
    co_change_strength: dict[str, float] = field(default_factory=dict)  # file_path -> confidence score

    # Age metrics
    first_commit_at: datetime | None = None  # When this chunk was first created
    days_since_last_change: int | None = None  # Staleness indicator
