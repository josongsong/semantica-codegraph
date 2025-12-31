"""Index Version Models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class IndexVersionStatus(str, Enum):
    """Index version status."""

    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IndexVersion:
    """Represents an indexed version of a repository.

    Each indexing run gets a unique version_id to track consistency.
    """

    repo_id: str
    version_id: int
    git_commit: str
    indexed_at: datetime
    file_count: int = 0
    status: IndexVersionStatus = IndexVersionStatus.INDEXING
    duration_ms: float = 0.0
    error_message: str | None = None
    metadata: dict | None = None

    def is_completed(self) -> bool:
        """Check if indexing completed successfully."""
        return self.status == IndexVersionStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if indexing failed."""
        return self.status == IndexVersionStatus.FAILED

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "repo_id": self.repo_id,
            "version_id": self.version_id,
            "git_commit": self.git_commit,
            "indexed_at": self.indexed_at.isoformat(),
            "file_count": self.file_count,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IndexVersion":
        """Create from dictionary."""
        return cls(
            repo_id=data["repo_id"],
            version_id=data["version_id"],
            git_commit=data["git_commit"],
            indexed_at=datetime.fromisoformat(data["indexed_at"]),
            file_count=data.get("file_count", 0),
            status=IndexVersionStatus(data.get("status", "indexing")),
            duration_ms=data.get("duration_ms", 0.0),
            error_message=data.get("error_message"),
            metadata=data.get("metadata"),
        )
