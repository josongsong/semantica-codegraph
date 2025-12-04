"""Workspace Session - Isolated workspace for agent execution."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class WorkspaceSession:
    """Isolated workspace session for agent execution.

    Each session gets its own git worktree, allowing parallel
    agents to work without interfering with each other.
    """

    session_id: str
    repo_id: str
    worktree_path: Path
    branch_name: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    in_use: bool = False
    metadata: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        repo_id: str,
        worktree_path: Path,
        branch_name: str | None = None,
    ) -> "WorkspaceSession":
        """Create a new workspace session.

        Args:
            repo_id: Repository ID
            worktree_path: Worktree directory path
            branch_name: Optional branch name

        Returns:
            New WorkspaceSession
        """
        return cls(
            session_id=str(uuid.uuid4()),
            repo_id=repo_id,
            worktree_path=worktree_path,
            branch_name=branch_name,
        )

    def acquire(self) -> None:
        """Mark session as in use."""
        self.in_use = True
        self.last_accessed = datetime.now()
        logger.debug("workspace_acquired", session_id=self.session_id)

    def release(self) -> None:
        """Mark session as available."""
        self.in_use = False
        self.last_accessed = datetime.now()
        logger.debug("workspace_released", session_id=self.session_id)

    def is_expired(self, ttl_minutes: int = 60) -> bool:
        """Check if session is expired.

        Args:
            ttl_minutes: Time to live in minutes

        Returns:
            True if expired
        """
        if self.in_use:
            return False

        age = datetime.now() - self.last_accessed
        return age > timedelta(minutes=ttl_minutes)

    def get_age_minutes(self) -> float:
        """Get session age in minutes.

        Returns:
            Age in minutes
        """
        age = datetime.now() - self.last_accessed
        return age.total_seconds() / 60

    def exists(self) -> bool:
        """Check if worktree directory exists.

        Returns:
            True if exists
        """
        return self.worktree_path.exists()

    def cleanup(self) -> None:
        """Clean up workspace files (not the worktree itself)."""
        if not self.exists():
            return

        # Clean up temporary files
        temp_patterns = ["*.pyc", "__pycache__", "*.tmp", ".pytest_cache"]

        for pattern in temp_patterns:
            for file in self.worktree_path.rglob(pattern):
                try:
                    if file.is_file():
                        file.unlink()
                    elif file.is_dir():
                        import shutil

                        shutil.rmtree(file)
                except Exception as e:
                    logger.warning(
                        "workspace_cleanup_failed",
                        session_id=self.session_id,
                        file=str(file),
                        error=str(e),
                    )
