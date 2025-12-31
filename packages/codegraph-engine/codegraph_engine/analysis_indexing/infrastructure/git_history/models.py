"""
Git History Data Models

Models for git blame, code churn, and evolution tracking.

Phase: P0-1 Git History Analysis (Layer 19)
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============================================================
# Enums
# ============================================================


class ChangeType(str, Enum):
    """File change types in git history."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"


class HotspotReason(str, Enum):
    """Reasons for marking a chunk as a hotspot."""

    HIGH_CHURN = "high_churn"  # Frequently changed
    MANY_AUTHORS = "many_authors"  # Many contributors
    RECENT_ACTIVITY = "recent_activity"  # Recently very active


# ============================================================
# Git Commit Model
# ============================================================


class GitCommit(BaseModel):
    """
    Git commit metadata.

    Represents a single git commit with full metadata.
    """

    commit_hash: str = Field(..., description="Git SHA-1 commit hash (40 chars)")
    repo_id: str = Field(..., description="Repository identifier")

    # Author information
    author_name: str
    author_email: str
    author_date: datetime

    # Committer information (may differ from author for rebases/merges)
    committer_name: str | None = None
    committer_email: str | None = None
    commit_date: datetime

    # Commit message
    message: str
    message_summary: str | None = Field(None, description="First line of commit message")

    # Parents
    parent_hashes: list[str] = Field(default_factory=list, description="Parent commit hashes")
    is_merge: bool = Field(default=False, description="True if merge commit (>1 parent)")

    # Statistics
    files_changed: int = Field(default=0, description="Number of files changed")
    insertions: int = Field(default=0, description="Lines inserted")
    deletions: int = Field(default=0, description="Lines deleted")

    # Tags and references
    tags: list[str] = Field(default_factory=list, description="Git tags at this commit")
    branches: list[str] = Field(default_factory=list, description="Branches containing commit")

    # Metadata
    indexed_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "commit_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
                "repo_id": "codegraph",
                "author_name": "Alice Developer",
                "author_email": "alice@example.com",
                "author_date": "2025-11-26T10:30:00Z",
                "commit_date": "2025-11-26T10:30:00Z",
                "message": "feat: Add git history tracking\n\nImplement git blame and churn metrics",
                "message_summary": "feat: Add git history tracking",
                "files_changed": 5,
                "insertions": 150,
                "deletions": 20,
            }
        }
    )


# ============================================================
# File History Model
# ============================================================


class FileHistory(BaseModel):
    """
    File-level change record.

    Tracks changes to a specific file in a commit.
    """

    id: UUID | None = None
    repo_id: str
    file_path: str
    commit_hash: str

    # Change information
    change_type: ChangeType
    old_file_path: str | None = Field(None, description="Previous path for renames/copies")

    # Statistics
    lines_added: int = Field(default=0)
    lines_deleted: int = Field(default=0)

    # File metadata
    file_size_bytes: int | None = None
    language: str | None = None

    # Metadata
    indexed_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "repo_id": "codegraph",
                "file_path": "src/git_history/models.py",
                "commit_hash": "a1b2c3d4...",
                "change_type": "modified",
                "lines_added": 50,
                "lines_deleted": 10,
                "language": "python",
            }
        }
    )


# ============================================================
# Chunk History Model
# ============================================================


class ChunkHistory(BaseModel):
    """
    Chunk-level change record.

    Tracks changes to a specific chunk (function, class, etc) across commits.
    """

    id: UUID | None = None
    chunk_id: str
    repo_id: str
    commit_hash: str

    # Existence tracking
    existed: bool = Field(default=True, description="False if chunk was deleted in this commit")

    # Change metrics
    lines_added: int = Field(default=0)
    lines_deleted: int = Field(default=0)
    lines_modified: int = Field(default=0)

    # Churn score
    churn_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Volatility score 0-1 (higher = more changes)",
    )

    # Author information
    primary_author: str | None = Field(None, description="Author with most lines")
    author_count: int = Field(default=1, description="Number of distinct authors")

    # Metadata
    indexed_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# Git Blame Model
# ============================================================


class GitBlame(BaseModel):
    """
    Line-level attribution (git blame).

    Represents attribution for a range of lines in the current snapshot.
    """

    id: UUID | None = None
    repo_id: str
    snapshot_id: str = Field(..., description="Current snapshot (commit hash or timestamp)")
    file_path: str

    # Line range
    start_line: int
    end_line: int

    # Attribution
    commit_hash: str
    author_name: str
    author_email: str
    commit_date: datetime

    # Chunk association
    chunk_id: str | None = Field(None, description="Associated chunk (for aggregation)")

    # Metadata
    indexed_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "repo_id": "codegraph",
                "snapshot_id": "HEAD",
                "file_path": "src/git_history/models.py",
                "start_line": 10,
                "end_line": 50,
                "commit_hash": "a1b2c3d4...",
                "author_name": "Alice Developer",
                "author_email": "alice@example.com",
                "commit_date": "2025-11-26T10:30:00Z",
            }
        }
    )


# ============================================================
# Chunk Churn Metrics Model
# ============================================================


class AuthorContribution(BaseModel):
    """Author contribution to a chunk."""

    name: str
    email: str
    commit_count: int
    lines_contributed: int | None = None


class ChunkChurnMetrics(BaseModel):
    """
    Aggregated churn metrics for a chunk.

    Provides fast access to churn statistics without scanning history.
    """

    chunk_id: str
    repo_id: str

    # Aggregate statistics
    total_commits: int = Field(default=0, description="Total commits affecting this chunk")
    total_lines_added: int = Field(default=0)
    total_lines_deleted: int = Field(default=0)
    total_lines_modified: int = Field(default=0)

    # Churn score
    churn_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Normalized volatility score (0-1)",
    )

    # Author statistics
    primary_author: str | None = Field(None, description="Most frequent contributor")
    author_count: int = Field(default=0, description="Distinct authors")
    authors: list[AuthorContribution] = Field(default_factory=list, description="All contributors")

    # Temporal metrics
    first_commit_hash: str | None = None
    first_commit_date: datetime | None = None
    last_commit_hash: str | None = None
    last_commit_date: datetime | None = None

    # Age metrics
    age_days: int | None = Field(None, description="Days since first commit")
    days_since_last_change: int | None = Field(None, description="Days since last modification")

    # Hotspot detection
    is_hotspot: bool = Field(default=False, description="Frequently changed (high churn)")
    hotspot_reason: HotspotReason | None = Field(None, description="Why marked as hotspot")

    # Metadata
    last_updated: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_id": "chunk:codegraph:function:Builder.build_full",
                "repo_id": "codegraph",
                "total_commits": 15,
                "total_lines_added": 120,
                "total_lines_deleted": 50,
                "churn_score": 0.75,
                "primary_author": "alice@example.com",
                "author_count": 3,
                "age_days": 90,
                "days_since_last_change": 2,
                "is_hotspot": True,
                "hotspot_reason": "high_churn",
            }
        }
    )


# ============================================================
# Evolution Snapshot Model
# ============================================================


class ChunkEvolutionSnapshot(BaseModel):
    """
    Point-in-time snapshot of a chunk's evolution.

    Used for building evolution graphs over time.
    """

    chunk_id: str
    commit_hash: str
    commit_date: datetime

    # Metrics at this point in time
    size_lines: int
    complexity_score: float | None = None

    # Cumulative metrics up to this point
    cumulative_commits: int
    cumulative_authors: int
    cumulative_churn: float

    # Change from previous snapshot
    delta_lines: int = Field(default=0, description="Change in lines since previous snapshot")
    delta_complexity: float | None = None


# ============================================================
# Hotspot Analysis Result
# ============================================================


class HotspotAnalysis(BaseModel):
    """
    Hotspot analysis result for a repository.

    Identifies code areas with high churn, complexity, or defect correlation.
    """

    repo_id: str
    snapshot_id: str
    analysis_date: datetime = Field(default_factory=datetime.now)

    # Top hotspots
    hotspots: list[ChunkChurnMetrics] = Field(..., description="Chunks ranked by hotspot score")

    # Summary statistics
    total_chunks_analyzed: int
    hotspot_count: int
    high_churn_count: int
    many_authors_count: int

    # Distribution
    churn_score_p50: float
    churn_score_p95: float
    churn_score_p99: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "repo_id": "codegraph",
                "snapshot_id": "HEAD",
                "total_chunks_analyzed": 500,
                "hotspot_count": 25,
                "high_churn_count": 20,
                "many_authors_count": 10,
                "churn_score_p50": 0.3,
                "churn_score_p95": 0.8,
                "churn_score_p99": 0.95,
            }
        }
    )
