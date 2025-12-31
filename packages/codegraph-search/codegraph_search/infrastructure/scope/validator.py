"""
RepoMap and Snapshot Validators

Validates snapshot consistency and RepoMap freshness for the Retriever Layer.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from codegraph_search.infrastructure.exceptions import IndexNotReadyError, SnapshotNotFoundError

if TYPE_CHECKING:
    from codegraph_engine.repo_structure.infrastructure.models import RepoMapSnapshot
    from codegraph_shared.ports import RepoMapPort
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class RepoMapStatus(str, Enum):
    """RepoMap freshness status."""

    FRESH = "fresh"  # Matches snapshot and recent
    STALE = "stale"  # Doesn't match snapshot
    OUTDATED = "outdated"  # Matches snapshot but old
    MISSING = "missing"  # No RepoMap exists


class SnapshotValidator:
    """
    Validates snapshot existence and readiness across indexes.

    Ensures all indexes (lexical, vector, symbol, graph, repomap) have
    the requested snapshot before retrieval.
    """

    def __init__(self):
        """Initialize snapshot validator."""
        pass

    def validate_snapshot_exists(
        self,
        repo_id: str,
        snapshot_id: str,
        index_name: str,
        check_fn: callable,
    ) -> bool:
        """
        Validate that a snapshot exists in an index.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            index_name: Name of the index (for error messages)
            check_fn: Function that returns True if snapshot exists

        Returns:
            True if snapshot exists

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
        """
        exists = check_fn(repo_id, snapshot_id)

        if not exists:
            raise SnapshotNotFoundError(repo_id, snapshot_id, index_name)

        return True

    def validate_index_ready(
        self,
        repo_id: str,
        snapshot_id: str,
        index_name: str,
        is_ready_fn: callable,
    ) -> bool:
        """
        Validate that an index is ready for querying.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            index_name: Name of the index
            is_ready_fn: Function that returns (is_ready, reason)

        Returns:
            True if index is ready

        Raises:
            IndexNotReadyError: If index is not ready
        """
        is_ready, reason = is_ready_fn(repo_id, snapshot_id)

        if not is_ready:
            raise IndexNotReadyError(repo_id, snapshot_id, index_name, reason)

        return True


class RepoMapValidator:
    """
    Validates RepoMap freshness and consistency.

    Checks whether RepoMap snapshot matches the requested snapshot
    and whether it's recent enough for use.
    """

    def __init__(
        self,
        repomap_port: "RepoMapPort",
        stale_threshold_hours: float = 1.0,
        outdated_threshold_hours: float = 24.0,
    ):
        """
        Initialize RepoMap validator.

        Args:
            repomap_port: RepoMap query port
            stale_threshold_hours: Hours before RepoMap is considered stale
            outdated_threshold_hours: Hours before RepoMap is considered outdated
        """
        self.repomap_port = repomap_port
        self.stale_threshold = timedelta(hours=stale_threshold_hours)
        self.outdated_threshold = timedelta(hours=outdated_threshold_hours)

    def validate_freshness(self, repo_id: str, snapshot_id: str) -> RepoMapStatus:
        """
        Validate RepoMap freshness.

        Args:
            repo_id: Repository identifier
            snapshot_id: Requested snapshot identifier

        Returns:
            RepoMapStatus indicating freshness level
        """
        # Get RepoMap snapshot
        repomap_snapshot = self.repomap_port.get_snapshot(repo_id, snapshot_id)

        if repomap_snapshot is None:
            logger.warning(f"RepoMap not found for repo={repo_id}, snapshot={snapshot_id}")
            return RepoMapStatus.MISSING

        # Check snapshot ID match
        if repomap_snapshot.snapshot_id != snapshot_id:
            logger.warning(f"RepoMap snapshot mismatch: requested={snapshot_id}, found={repomap_snapshot.snapshot_id}")
            return RepoMapStatus.STALE

        # Check age
        if repomap_snapshot.created_at:
            created_time = datetime.fromisoformat(repomap_snapshot.created_at.replace("Z", "+00:00"))
            age = datetime.now(created_time.tzinfo) - created_time

            if age > self.outdated_threshold:
                logger.info(
                    f"RepoMap is outdated: age={age.total_seconds() / 3600:.1f}h, "
                    f"threshold={self.outdated_threshold.total_seconds() / 3600:.1f}h"
                )
                return RepoMapStatus.OUTDATED

        logger.debug(f"RepoMap is fresh for repo={repo_id}, snapshot={snapshot_id}")
        return RepoMapStatus.FRESH

    def validate_or_warn(self, repo_id: str, snapshot_id: str) -> tuple[RepoMapStatus, bool]:
        """
        Validate RepoMap and return status + usability.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            Tuple of (status, can_use)
            - status: RepoMapStatus
            - can_use: Whether RepoMap can be used (True even if outdated)
        """
        status = self.validate_freshness(repo_id, snapshot_id)

        if status == RepoMapStatus.MISSING:
            logger.warning("RepoMap missing - will use full-repo search")
            return status, False

        if status == RepoMapStatus.STALE:
            logger.warning("RepoMap stale - will use full-repo search")
            return status, False

        if status == RepoMapStatus.OUTDATED:
            logger.info("RepoMap outdated but usable - scope selection may be suboptimal")
            return status, True

        # FRESH
        return status, True

    def get_snapshot(self, repo_id: str, snapshot_id: str) -> "RepoMapSnapshot | None":
        """
        Get RepoMap snapshot if available.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            RepoMapSnapshot or None if not available
        """
        return self.repomap_port.get_snapshot(repo_id, snapshot_id)
