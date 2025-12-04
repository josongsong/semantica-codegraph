"""Index Version Middleware for API requests."""

from dataclasses import dataclass

from src.infra.observability import get_logger, record_counter, record_histogram

from .checker import IndexVersionChecker
from .store import IndexVersionStore

logger = get_logger(__name__)


@dataclass
class VersionCheckResult:
    """Result of version check."""

    is_valid: bool
    version_id: int | None
    staleness_seconds: float
    reason: str
    auto_reindex_triggered: bool = False


class VersionCheckMiddleware:
    """Middleware for checking index version before agent requests.

    Ensures agents always work with fresh index data by:
    - Checking version staleness
    - Optionally triggering auto-reindex
    - Recording metrics
    """

    def __init__(
        self,
        version_store: IndexVersionStore,
        version_checker: IndexVersionChecker,
        auto_reindex: bool = False,
        alert_on_stale: bool = True,
    ):
        """Initialize middleware.

        Args:
            version_store: Index version store
            version_checker: Version checker
            auto_reindex: Automatically trigger reindex if stale
            alert_on_stale: Send alert if index is stale
        """
        self.version_store = version_store
        self.version_checker = version_checker
        self.auto_reindex = auto_reindex
        self.alert_on_stale = alert_on_stale

    async def check_before_request(
        self,
        repo_id: str,
        current_commit: str,
    ) -> VersionCheckResult:
        """Check index version before processing agent request.

        Args:
            repo_id: Repository ID
            current_commit: Current git commit hash

        Returns:
            VersionCheckResult
        """
        is_valid, reason, version = await self.version_checker.check_version(repo_id, current_commit)

        if not version:
            # No version found
            record_counter(
                "index_version_check_total",
                labels={"status": "no_version", "repo_id": repo_id},
            )

            return VersionCheckResult(
                is_valid=False,
                version_id=None,
                staleness_seconds=float("inf"),
                reason=reason,
            )

        # Calculate staleness
        from datetime import datetime

        staleness = (datetime.now(version.indexed_at.tzinfo) - version.indexed_at).total_seconds()

        # Record metrics
        record_histogram("index_staleness_seconds", staleness)

        if not is_valid:
            record_counter(
                "index_version_check_total",
                labels={"status": "stale", "repo_id": repo_id},
            )

            logger.warning(
                "stale_index_detected",
                repo_id=repo_id,
                version_id=version.version_id,
                staleness_seconds=staleness,
                reason=reason,
            )

            # Alert if enabled
            if self.alert_on_stale:
                await self._send_alert(repo_id, version.version_id, staleness, reason)

            # Auto-reindex if enabled
            auto_reindex_triggered = False
            if self.auto_reindex:
                auto_reindex_triggered = await self._trigger_reindex(repo_id, current_commit)

            return VersionCheckResult(
                is_valid=False,
                version_id=version.version_id,
                staleness_seconds=staleness,
                reason=reason,
                auto_reindex_triggered=auto_reindex_triggered,
            )

        # Valid version
        record_counter(
            "index_version_check_total",
            labels={"status": "valid", "repo_id": repo_id},
        )

        logger.debug(
            "index_version_valid",
            repo_id=repo_id,
            version_id=version.version_id,
            staleness_seconds=staleness,
        )

        return VersionCheckResult(
            is_valid=True,
            version_id=version.version_id,
            staleness_seconds=staleness,
            reason="OK",
        )

    async def _send_alert(
        self,
        repo_id: str,
        version_id: int,
        staleness_seconds: float,
        reason: str,
    ) -> None:
        """Send alert about stale index.

        Args:
            repo_id: Repository ID
            version_id: Stale version ID
            staleness_seconds: Staleness in seconds
            reason: Staleness reason
        """
        # TODO: Integrate with Redis Pub/Sub or alerting system
        logger.warning(
            "stale_index_alert",
            repo_id=repo_id,
            version_id=version_id,
            staleness_minutes=staleness_seconds / 60,
            reason=reason,
        )

    async def _trigger_reindex(self, repo_id: str, current_commit: str) -> bool:
        """Trigger automatic reindexing.

        Args:
            repo_id: Repository ID
            current_commit: Current commit hash

        Returns:
            True if reindex was triggered
        """
        # TODO: Integrate with IndexJobOrchestrator
        logger.info(
            "auto_reindex_triggered",
            repo_id=repo_id,
            commit=current_commit[:8],
        )

        # Placeholder - actual implementation would submit IndexJob
        return True
