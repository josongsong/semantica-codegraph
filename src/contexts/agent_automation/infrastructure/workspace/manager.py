"""Workspace Manager - Pool management for workspace sessions."""

import asyncio
from pathlib import Path

from src.contexts.agent_automation.infrastructure.exceptions import WorkspaceCreationError, WorkspacePoolExhaustedError
from src.infra.observability import get_logger

from .session import WorkspaceSession
from .worktree import GitWorktreeAdapter

logger = get_logger(__name__)


class WorkspaceManager:
    """Manages a pool of workspace sessions with automatic cleanup.

    Provides:
    - Workspace allocation/deallocation
    - TTL-based automatic cleanup
    - Pool size management
    - Session reuse
    """

    def __init__(
        self,
        repo_path: Path,
        worktree_base_dir: Path | None = None,
        max_workspaces: int = 10,
        session_ttl_minutes: int = 60,
    ):
        """Initialize workspace manager.

        Args:
            repo_path: Main repository path
            worktree_base_dir: Base directory for worktrees (default: {repo}/.worktrees)
            max_workspaces: Maximum concurrent workspaces
            session_ttl_minutes: Session TTL in minutes
        """
        self.repo_path = Path(repo_path)
        self.worktree_base_dir = worktree_base_dir or (self.repo_path / ".worktrees")
        self.worktree_base_dir.mkdir(parents=True, exist_ok=True)

        self.max_workspaces = max_workspaces
        self.session_ttl_minutes = session_ttl_minutes

        self.git_adapter = GitWorktreeAdapter(repo_path)
        self.sessions: dict[str, WorkspaceSession] = {}
        self._lock = asyncio.Lock()

        self._cleanup_task: asyncio.Task | None = None

    async def allocate(
        self,
        repo_id: str,
        session_name: str | None = None,
        branch: str | None = None,
    ) -> WorkspaceSession:
        """Allocate a workspace session.

        Args:
            repo_id: Repository ID
            session_name: Optional session name (default: auto-generated)
            branch: Optional branch to create

        Returns:
            WorkspaceSession

        Raises:
            RuntimeError: If pool is full
        """
        async with self._lock:
            # Try to reuse an available session
            for session in self.sessions.values():
                if not session.in_use and session.repo_id == repo_id:
                    session.acquire()
                    logger.info(
                        "workspace_reused",
                        session_id=session.session_id,
                        repo_id=repo_id,
                    )
                    return session

            # Check pool limit
            if len(self.sessions) >= self.max_workspaces:
                # Try to cleanup expired sessions
                await self._cleanup_expired()

                if len(self.sessions) >= self.max_workspaces:
                    raise WorkspacePoolExhaustedError(
                        max_workspaces=self.max_workspaces,
                        current_size=len(self.sessions),
                    )

            # Create new session
            session_name = session_name or f"session-{len(self.sessions)}"
            worktree_path = self.worktree_base_dir / session_name

            # Create git worktree
            success = self.git_adapter.create_worktree(
                worktree_path=worktree_path,
                branch=branch,
                detach=not branch,  # Detach if no branch specified
            )

            if not success:
                raise WorkspaceCreationError(f"Failed to create worktree at {worktree_path}")

            # Create session
            session = WorkspaceSession.create(
                repo_id=repo_id,
                worktree_path=worktree_path,
                branch_name=branch,
            )

            session.acquire()
            self.sessions[session.session_id] = session

            logger.info(
                "workspace_allocated",
                session_id=session.session_id,
                worktree_path=str(worktree_path),
                pool_size=len(self.sessions),
            )

            return session

    async def deallocate(self, session_id: str, keep_worktree: bool = False) -> None:
        """Deallocate a workspace session.

        Args:
            session_id: Session ID
            keep_worktree: Keep worktree directory (for inspection)
        """
        async with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                logger.warning("session_not_found", session_id=session_id)
                return

            session.release()

            if not keep_worktree:
                # Remove worktree
                success = self.git_adapter.remove_worktree(
                    session.worktree_path,
                    force=True,
                )

                if success:
                    del self.sessions[session_id]
                    logger.info(
                        "workspace_deallocated",
                        session_id=session_id,
                        pool_size=len(self.sessions),
                    )
                else:
                    logger.error(
                        "worktree_removal_failed",
                        session_id=session_id,
                    )

    async def release(self, session_id: str) -> None:
        """Release session without removing worktree (for reuse).

        Args:
            session_id: Session ID
        """
        async with self._lock:
            session = self.sessions.get(session_id)
            if session:
                session.release()
                logger.debug("workspace_released", session_id=session_id)

    async def cleanup_all(self, force: bool = True) -> int:
        """Clean up all workspaces.

        Args:
            force: Force cleanup even if in use

        Returns:
            Number of workspaces cleaned
        """
        async with self._lock:
            count = 0
            session_ids = list(self.sessions.keys())

            for session_id in session_ids:
                session = self.sessions[session_id]

                if force or not session.in_use:
                    success = self.git_adapter.remove_worktree(
                        session.worktree_path,
                        force=True,
                    )

                    if success:
                        del self.sessions[session_id]
                        count += 1

            # Prune stale worktree admin files
            self.git_adapter.prune_worktrees()

            logger.info("workspaces_cleaned_up", count=count)
            return count

    async def _cleanup_expired(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions cleaned
        """
        count = 0
        session_ids = list(self.sessions.keys())

        for session_id in session_ids:
            session = self.sessions[session_id]

            if session.is_expired(self.session_ttl_minutes):
                success = self.git_adapter.remove_worktree(
                    session.worktree_path,
                    force=True,
                )

                if success:
                    del self.sessions[session_id]
                    count += 1
                    logger.info(
                        "expired_workspace_cleaned",
                        session_id=session_id,
                        age_minutes=session.get_age_minutes(),
                    )

        return count

    async def start_background_cleanup(self, interval_seconds: int = 300) -> None:
        """Start background cleanup task.

        Args:
            interval_seconds: Cleanup interval (default: 5 minutes)
        """
        if self._cleanup_task and not self._cleanup_task.done():
            logger.warning("cleanup_task_already_running")
            return

        self._cleanup_task = asyncio.create_task(self._cleanup_loop(interval_seconds))

        logger.info(
            "background_cleanup_started",
            interval_seconds=interval_seconds,
        )

    async def stop_background_cleanup(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

            logger.info("background_cleanup_stopped")

    async def _cleanup_loop(self, interval_seconds: int) -> None:
        """Background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                count = await self._cleanup_expired()

                if count > 0:
                    logger.info(
                        "background_cleanup_completed",
                        cleaned_count=count,
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("background_cleanup_error", error=str(e))

    def get_pool_stats(self) -> dict:
        """Get workspace pool statistics.

        Returns:
            Statistics dict
        """
        total = len(self.sessions)
        in_use = sum(1 for s in self.sessions.values() if s.in_use)
        available = total - in_use

        return {
            "total": total,
            "in_use": in_use,
            "available": available,
            "max_capacity": self.max_workspaces,
            "utilization_pct": (in_use / self.max_workspaces * 100) if self.max_workspaces > 0 else 0,
        }
