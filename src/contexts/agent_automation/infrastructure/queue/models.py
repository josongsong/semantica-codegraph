"""Patch Queue Models."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class PatchStatus(str, Enum):
    """Patch proposal status."""

    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    CONFLICT = "conflict"
    SUPERSEDED = "superseded"


@dataclass
class PatchProposal:
    """A proposed code patch waiting to be applied.

    Tracks version information to detect conflicts and ensure
    patches are applied to the correct base.
    """

    patch_id: str
    repo_id: str
    file_path: str
    patch_content: str  # Unified diff format
    base_content: str | None = None  # Original file content
    base_version_id: int | None = None  # File version when created
    index_version_id: int | None = None  # Index version used by agent
    description: str | None = None
    status: PatchStatus = PatchStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    applied_at: datetime | None = None
    agent_mode: str | None = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        repo_id: str,
        file_path: str,
        patch_content: str,
        base_content: str | None = None,
        base_version_id: int | None = None,
        index_version_id: int | None = None,
        description: str | None = None,
        agent_mode: str | None = None,
        metadata: dict | None = None,
    ) -> "PatchProposal":
        """Create a new patch proposal.

        Args:
            repo_id: Repository ID
            file_path: Target file path
            patch_content: Unified diff
            base_content: Original file content
            base_version_id: File version when patch created
            index_version_id: Index version used by agent
            description: Patch description
            agent_mode: Which agent mode created this
            metadata: Additional metadata

        Returns:
            New PatchProposal
        """
        return cls(
            patch_id=str(uuid.uuid4()),
            repo_id=repo_id,
            file_path=file_path,
            patch_content=patch_content,
            base_content=base_content,
            base_version_id=base_version_id,
            index_version_id=index_version_id,
            description=description,
            agent_mode=agent_mode,
            metadata=metadata or {},
        )

    def is_pending(self) -> bool:
        """Check if patch is pending."""
        return self.status == PatchStatus.PENDING

    def is_applied(self) -> bool:
        """Check if patch was applied."""
        return self.status == PatchStatus.APPLIED

    def has_conflict(self) -> bool:
        """Check if patch has conflict."""
        return self.status == PatchStatus.CONFLICT

    def mark_applied(self) -> None:
        """Mark patch as successfully applied."""
        self.status = PatchStatus.APPLIED
        self.applied_at = datetime.now()

    def mark_failed(self, reason: str) -> None:
        """Mark patch as failed."""
        self.status = PatchStatus.FAILED
        self.metadata["failure_reason"] = reason

    def mark_conflict(self, conflict_details: dict) -> None:
        """Mark patch as having conflict."""
        self.status = PatchStatus.CONFLICT
        self.metadata["conflict_details"] = conflict_details

    def mark_superseded(self, superseded_by: str) -> None:
        """Mark patch as superseded by newer patch."""
        self.status = PatchStatus.SUPERSEDED
        self.metadata["superseded_by"] = superseded_by

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "patch_id": self.patch_id,
            "repo_id": self.repo_id,
            "file_path": self.file_path,
            "patch_content": self.patch_content,
            "base_content": self.base_content,
            "base_version_id": self.base_version_id,
            "index_version_id": self.index_version_id,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "agent_mode": self.agent_mode,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatchProposal":
        """Create from dictionary."""
        return cls(
            patch_id=data["patch_id"],
            repo_id=data["repo_id"],
            file_path=data["file_path"],
            patch_content=data["patch_content"],
            base_content=data.get("base_content"),
            base_version_id=data.get("base_version_id"),
            index_version_id=data.get("index_version_id"),
            description=data.get("description"),
            status=PatchStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            applied_at=(datetime.fromisoformat(data["applied_at"]) if data.get("applied_at") else None),
            agent_mode=data.get("agent_mode"),
            metadata=data.get("metadata", {}),
        )
