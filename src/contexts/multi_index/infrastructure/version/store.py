"""Index Version Store - PostgreSQL implementation."""

import json

from src.infra.observability import get_logger
from src.infra.storage.postgres import PostgresStore

from .models import IndexVersion, IndexVersionStatus

logger = get_logger(__name__)


class IndexVersionStore:
    """Manages index version persistence in PostgreSQL."""

    def __init__(self, postgres_store: PostgresStore):
        """Initialize with postgres store.

        Args:
            postgres_store: PostgreSQL connection pool
        """
        self.postgres = postgres_store

    async def create_version(
        self,
        repo_id: str,
        git_commit: str,
        file_count: int = 0,
    ) -> IndexVersion:
        """Create a new index version.

        Args:
            repo_id: Repository ID
            git_commit: Git commit hash
            file_count: Number of files indexed

        Returns:
            Created IndexVersion
        """
        query = """
            INSERT INTO index_versions (
                repo_id,
                version_id,
                git_commit,
                file_count,
                status
            ) VALUES (
                $1,
                nextval('index_version_seq'),
                $2,
                $3,
                $4
            )
            RETURNING *
        """

        row = await self.postgres.fetchrow(
            query,
            repo_id,
            git_commit,
            file_count,
            IndexVersionStatus.INDEXING.value,
        )

        logger.info(
            "index_version_created",
            repo_id=repo_id,
            version_id=row["version_id"],
            git_commit=git_commit,
        )

        return self._row_to_version(row)

    async def complete_version(
        self,
        repo_id: str,
        version_id: int,
        duration_ms: float,
        metadata: dict | None = None,
    ) -> None:
        """Mark version as completed.

        Args:
            repo_id: Repository ID
            version_id: Version ID
            duration_ms: Indexing duration in milliseconds
            metadata: Optional metadata
        """
        query = """
            UPDATE index_versions
            SET status = $1,
                duration_ms = $2,
                metadata = $3
            WHERE repo_id = $4 AND version_id = $5
        """

        await self.postgres.execute(
            query,
            IndexVersionStatus.COMPLETED.value,
            duration_ms,
            json.dumps(metadata or {}),
            repo_id,
            version_id,
        )

        logger.info(
            "index_version_completed",
            repo_id=repo_id,
            version_id=version_id,
            duration_ms=duration_ms,
        )

    async def fail_version(
        self,
        repo_id: str,
        version_id: int,
        error_message: str,
    ) -> None:
        """Mark version as failed.

        Args:
            repo_id: Repository ID
            version_id: Version ID
            error_message: Error description
        """
        query = """
            UPDATE index_versions
            SET status = $1,
                error_message = $2
            WHERE repo_id = $3 AND version_id = $4
        """

        await self.postgres.execute(
            query,
            IndexVersionStatus.FAILED.value,
            error_message,
            repo_id,
            version_id,
        )

        logger.error(
            "index_version_failed",
            repo_id=repo_id,
            version_id=version_id,
            error=error_message,
        )

    async def get_latest_version(self, repo_id: str) -> IndexVersion | None:
        """Get the latest completed version for a repo.

        Args:
            repo_id: Repository ID

        Returns:
            Latest IndexVersion or None
        """
        query = """
            SELECT * FROM index_versions
            WHERE repo_id = $1 AND status = $2
            ORDER BY version_id DESC
            LIMIT 1
        """

        row = await self.postgres.fetchrow(
            query,
            repo_id,
            IndexVersionStatus.COMPLETED.value,
        )

        if not row:
            return None

        return self._row_to_version(row)

    async def get_version(self, repo_id: str, version_id: int) -> IndexVersion | None:
        """Get a specific version.

        Args:
            repo_id: Repository ID
            version_id: Version ID

        Returns:
            IndexVersion or None
        """
        query = """
            SELECT * FROM index_versions
            WHERE repo_id = $1 AND version_id = $2
        """

        row = await self.postgres.fetchrow(query, repo_id, version_id)

        if not row:
            return None

        return self._row_to_version(row)

    async def get_version_by_commit(self, repo_id: str, git_commit: str) -> IndexVersion | None:
        """Get version by git commit.

        Args:
            repo_id: Repository ID
            git_commit: Git commit hash

        Returns:
            IndexVersion or None
        """
        query = """
            SELECT * FROM index_versions
            WHERE repo_id = $1 AND git_commit = $2
            ORDER BY version_id DESC
            LIMIT 1
        """

        row = await self.postgres.fetchrow(query, repo_id, git_commit)

        if not row:
            return None

        return self._row_to_version(row)

    async def list_versions(
        self,
        repo_id: str,
        limit: int = 10,
        status: IndexVersionStatus | None = None,
    ) -> list[IndexVersion]:
        """List versions for a repository.

        Args:
            repo_id: Repository ID
            limit: Maximum number of versions
            status: Filter by status

        Returns:
            List of IndexVersions
        """
        if status:
            query = """
                SELECT * FROM index_versions
                WHERE repo_id = $1 AND status = $2
                ORDER BY version_id DESC
                LIMIT $3
            """
            rows = await self.postgres.fetch(query, repo_id, status.value, limit)
        else:
            query = """
                SELECT * FROM index_versions
                WHERE repo_id = $1
                ORDER BY version_id DESC
                LIMIT $2
            """
            rows = await self.postgres.fetch(query, repo_id, limit)

        return [self._row_to_version(row) for row in rows]

    async def cleanup_old_versions(self, repo_id: str, keep_count: int = 10) -> int:
        """Delete old versions, keeping the latest N.

        Args:
            repo_id: Repository ID
            keep_count: Number of versions to keep

        Returns:
            Number of deleted versions
        """
        query = """
            DELETE FROM index_versions
            WHERE repo_id = $1 AND version_id NOT IN (
                SELECT version_id FROM index_versions
                WHERE repo_id = $1
                ORDER BY version_id DESC
                LIMIT $2
            )
        """

        result = await self.postgres.execute(query, repo_id, keep_count)

        # Parse result like "DELETE 5"
        deleted_count = int(result.split()[-1]) if result else 0

        logger.info(
            "index_versions_cleaned_up",
            repo_id=repo_id,
            deleted_count=deleted_count,
        )

        return deleted_count

    def _row_to_version(self, row: dict) -> IndexVersion:
        """Convert database row to IndexVersion."""
        metadata = row.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return IndexVersion(
            repo_id=row["repo_id"],
            version_id=row["version_id"],
            git_commit=row["git_commit"],
            indexed_at=row["indexed_at"],
            file_count=row.get("file_count", 0),
            status=IndexVersionStatus(row["status"]),
            duration_ms=row.get("duration_ms", 0.0),
            error_message=row.get("error_message"),
            metadata=metadata,
        )
