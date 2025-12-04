"""Index Version Checker - Staleness detection and auto-reindex."""

from datetime import datetime, timedelta

from src.infra.observability import get_logger

from .models import IndexVersion
from .store import IndexVersionStore

logger = get_logger(__name__)


class StalenessPolicy:
    """Policy for determining index staleness."""

    def __init__(
        self,
        max_age_minutes: int = 60,
        allow_commit_mismatch: bool = False,
    ):
        """Initialize policy.

        Args:
            max_age_minutes: Maximum age before index is considered stale
            allow_commit_mismatch: Allow using index from different commit
        """
        self.max_age_minutes = max_age_minutes
        self.allow_commit_mismatch = allow_commit_mismatch


class IndexVersionChecker:
    """Checks index version consistency and staleness."""

    def __init__(
        self,
        version_store: IndexVersionStore,
        policy: StalenessPolicy | None = None,
    ):
        """Initialize checker.

        Args:
            version_store: Index version store
            policy: Staleness policy (default: 60min, no commit mismatch)
        """
        self.version_store = version_store
        self.policy = policy or StalenessPolicy()

    async def check_version(
        self,
        repo_id: str,
        current_commit: str,
        requested_version_id: int | None = None,
    ) -> tuple[bool, str, IndexVersion | None]:
        """Check if index version is valid and fresh.

        Args:
            repo_id: Repository ID
            current_commit: Current git commit hash
            requested_version_id: Specific version requested by agent

        Returns:
            Tuple of (is_valid, reason, version)
            - is_valid: True if version can be used
            - reason: Explanation
            - version: IndexVersion if found
        """
        # If specific version requested, check it
        if requested_version_id is not None:
            version = await self.version_store.get_version(repo_id, requested_version_id)
            if not version:
                return False, f"Version {requested_version_id} not found", None

            if not version.is_completed():
                return False, f"Version {requested_version_id} not completed", version

            return self._check_staleness(version, current_commit)

        # Otherwise, get latest version
        version = await self.version_store.get_latest_version(repo_id)
        if not version:
            return False, "No completed index version found", None

        return self._check_staleness(version, current_commit)

    def _check_staleness(
        self,
        version: IndexVersion,
        current_commit: str,
    ) -> tuple[bool, str, IndexVersion]:
        """Check if version is stale.

        Args:
            version: Index version to check
            current_commit: Current git commit

        Returns:
            Tuple of (is_valid, reason, version)
        """
        # Check commit match
        if version.git_commit != current_commit:
            if not self.policy.allow_commit_mismatch:
                return (
                    False,
                    f"Commit mismatch: index={version.git_commit[:8]}, current={current_commit[:8]}",
                    version,
                )
            logger.warning(
                "index_commit_mismatch_allowed",
                repo_id=version.repo_id,
                index_commit=version.git_commit[:8],
                current_commit=current_commit[:8],
            )

        # Check age
        age = datetime.now(version.indexed_at.tzinfo) - version.indexed_at
        max_age = timedelta(minutes=self.policy.max_age_minutes)

        if age > max_age:
            return (
                False,
                f"Index too old: {age.total_seconds() / 60:.1f}min (max {self.policy.max_age_minutes}min)",
                version,
            )

        logger.debug(
            "index_version_valid",
            repo_id=version.repo_id,
            version_id=version.version_id,
            age_minutes=age.total_seconds() / 60,
        )

        return True, "OK", version

    async def get_or_wait(
        self,
        repo_id: str,
        current_commit: str,
        timeout_seconds: int = 300,
    ) -> IndexVersion | None:
        """Get valid version or wait for indexing to complete.

        Args:
            repo_id: Repository ID
            current_commit: Current git commit
            timeout_seconds: Maximum wait time

        Returns:
            Valid IndexVersion or None if timeout
        """
        import asyncio

        start = datetime.now()
        timeout = timedelta(seconds=timeout_seconds)

        while datetime.now() - start < timeout:
            is_valid, reason, version = await self.check_version(repo_id, current_commit)

            if is_valid and version:
                return version

            logger.debug(
                "waiting_for_index_version",
                repo_id=repo_id,
                reason=reason,
            )

            # Wait and retry
            await asyncio.sleep(5)

        logger.warning(
            "index_version_wait_timeout",
            repo_id=repo_id,
            timeout_seconds=timeout_seconds,
        )

        return None

    async def require_reindex(
        self,
        repo_id: str,
        current_commit: str,
    ) -> bool:
        """Check if reindexing is required.

        Args:
            repo_id: Repository ID
            current_commit: Current git commit

        Returns:
            True if reindexing needed
        """
        is_valid, reason, _ = await self.check_version(repo_id, current_commit)

        if not is_valid:
            logger.info(
                "reindex_required",
                repo_id=repo_id,
                reason=reason,
            )
            return True

        return False
