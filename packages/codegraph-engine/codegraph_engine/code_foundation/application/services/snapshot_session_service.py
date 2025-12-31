"""
Snapshot Session Service

RFC-052: MCP Service Layer Architecture
Application Service for Snapshot Stickiness.

Responsibilities:
- Manage session → snapshot binding
- Auto-lock to latest stable snapshot
- Validate snapshot consistency
- Handle snapshot mismatch errors

Design Principles:
- Session starts → auto-lock to latest stable
- All queries in session use same snapshot
- Explicit upgrade is allowed
- Temporal consistency for agent reasoning
"""

from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.application.dto import AnalysisError, ErrorCode

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.snapshot_store import (
        SemanticSnapshotStore,
    )
    from codegraph_engine.code_foundation.infrastructure.session import SnapshotSessionStore

logger = get_logger(__name__)


class SnapshotSessionService:
    """
    Application Service for Snapshot Stickiness.

    Manages session-to-snapshot binding for temporal consistency.

    Clean Architecture:
    - No Infrastructure imports (except TYPE_CHECKING)
    - Dependencies injected via constructor
    - Type hints use string literals or TYPE_CHECKING
    """

    def __init__(
        self,
        session_store: "SnapshotSessionStore",
        snapshot_store: "SemanticSnapshotStore",
    ):
        """
        Initialize service.

        Args:
            session_store: Session → snapshot mapping store
            snapshot_store: Semantic snapshot store
        """
        self.session_store = session_store
        self.snapshot_store = snapshot_store

    async def get_or_lock_snapshot(
        self,
        session_id: str,
        repo_id: str,
        requested_snapshot_id: str | None = None,
    ) -> str:
        """
        Get snapshot for session, or lock to latest stable.

        Contract:
        - If session already locked → return locked snapshot
        - If session not locked + no request → lock to latest stable
        - If session not locked + request → lock to requested

        Args:
            session_id: Session ID
            repo_id: Repository ID
            requested_snapshot_id: Optional explicit snapshot request

        Returns:
            Snapshot ID for this session

        Raises:
            ValueError: If requested snapshot not found
        """
        # Check existing lock
        existing_snapshot = await self.session_store.get_snapshot(session_id)
        if existing_snapshot:
            logger.debug(
                "snapshot_already_locked",
                session_id=session_id,
                snapshot_id=existing_snapshot,
            )
            return existing_snapshot

        # Determine snapshot to lock
        if requested_snapshot_id:
            # Validate requested snapshot exists
            snapshot = await self.snapshot_store.load_snapshot_by_id(requested_snapshot_id)
            if not snapshot:
                raise ValueError(f"Snapshot {requested_snapshot_id} not found")
            snapshot_id = requested_snapshot_id
        else:
            # Auto-lock to latest stable
            snapshot = await self.snapshot_store.load_latest_snapshot(repo_id)
            if not snapshot:
                raise ValueError(f"No snapshots found for repo {repo_id}")
            snapshot_id = snapshot.snapshot_id

        # Lock session to snapshot
        await self.session_store.lock_snapshot(
            session_id=session_id,
            snapshot_id=snapshot_id,
            repo_id=repo_id,
        )

        logger.info(
            "snapshot_locked",
            session_id=session_id,
            snapshot_id=snapshot_id,
            repo_id=repo_id,
            auto_locked=requested_snapshot_id is None,
        )

        return snapshot_id

    async def validate_snapshot_consistency(
        self,
        session_id: str,
        evidence_snapshot_id: str,
    ) -> tuple[bool, AnalysisError | None]:
        """
        Validate that evidence is from the same snapshot.

        Args:
            session_id: Session ID
            evidence_snapshot_id: Snapshot ID from evidence

        Returns:
            (is_consistent, error_if_not)
        """
        session_snapshot = await self.session_store.get_snapshot(session_id)
        if not session_snapshot:
            # Session not locked yet - can't validate
            return True, None

        if session_snapshot != evidence_snapshot_id:
            error = AnalysisError.snapshot_mismatch(
                expected_snapshot=session_snapshot,
                actual_snapshot=evidence_snapshot_id,
                evidence_id="unknown",
            )
            return False, error

        return True, None

    async def upgrade_snapshot(
        self,
        session_id: str,
        new_snapshot_id: str,
    ) -> None:
        """
        Explicitly upgrade session to newer snapshot.

        Args:
            session_id: Session ID
            new_snapshot_id: New snapshot ID

        Raises:
            ValueError: If new snapshot not found or session not found
        """
        # Validate new snapshot exists
        snapshot = await self.snapshot_store.load_snapshot_by_id(new_snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot {new_snapshot_id} not found")

        # Update session
        await self.session_store.update_snapshot(session_id, new_snapshot_id)

        logger.info(
            "snapshot_upgraded",
            session_id=session_id,
            new_snapshot=new_snapshot_id,
        )

    async def release_session(self, session_id: str) -> bool:
        """
        Release session lock (cleanup).

        Args:
            session_id: Session ID

        Returns:
            True if session was released, False if not found
        """
        released = await self.session_store.release_session(session_id)
        if released:
            logger.info("session_released", session_id=session_id)
        return released

    async def get_snapshot_info(self, session_id: str) -> dict | None:
        """
        Get snapshot info for session.

        Args:
            session_id: Session ID

        Returns:
            Dict with snapshot_id, repo_id, locked_at or None
        """
        return await self.session_store.get_session_info(session_id)

    async def cleanup_old_sessions(self, days: int = 7) -> int:
        """
        Cleanup sessions older than N days.

        Args:
            days: Age threshold

        Returns:
            Number of sessions cleaned up
        """
        deleted = await self.session_store.cleanup_old_sessions(days)
        logger.info("sessions_cleaned_up", deleted=deleted, threshold_days=days)
        return deleted
