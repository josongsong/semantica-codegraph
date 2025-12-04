"""PostgreSQL-based Patch Store."""

import json

from src.infra.observability import get_logger
from src.infra.storage.postgres import PostgresStore

from .models import PatchProposal, PatchStatus

logger = get_logger(__name__)


class PostgresPatchStore:
    """Persists patch proposals in PostgreSQL."""

    def __init__(self, postgres_store: PostgresStore):
        """Initialize with postgres store.

        Args:
            postgres_store: PostgreSQL connection pool
        """
        self.postgres = postgres_store

    async def save(self, patch: PatchProposal) -> None:
        """Save a patch proposal.

        Args:
            patch: Patch to save
        """
        query = """
            INSERT INTO patch_proposals (
                patch_id, repo_id, file_path, base_content, base_version_id,
                index_version_id, patch_content, description, status,
                created_at, applied_at, agent_mode, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (patch_id) DO UPDATE SET
                status = EXCLUDED.status,
                applied_at = EXCLUDED.applied_at,
                metadata = EXCLUDED.metadata
        """

        await self.postgres.execute(
            query,
            patch.patch_id,
            patch.repo_id,
            patch.file_path,
            patch.base_content,
            patch.base_version_id,
            patch.index_version_id,
            patch.patch_content,
            patch.description,
            patch.status.value,
            patch.created_at,
            patch.applied_at,
            patch.agent_mode,
            json.dumps(patch.metadata),
        )

        logger.debug(
            "patch_saved",
            patch_id=patch.patch_id,
            file_path=patch.file_path,
            status=patch.status.value,
        )

    async def get(self, patch_id: str) -> PatchProposal | None:
        """Get a patch by ID.

        Args:
            patch_id: Patch ID

        Returns:
            PatchProposal or None
        """
        query = "SELECT * FROM patch_proposals WHERE patch_id = $1"
        row = await self.postgres.fetchrow(query, patch_id)

        if not row:
            return None

        return self._row_to_patch(row)

    async def list_pending(
        self,
        repo_id: str,
        limit: int = 100,
    ) -> list[PatchProposal]:
        """List pending patches for a repo in FIFO order.

        Args:
            repo_id: Repository ID
            limit: Maximum number of patches

        Returns:
            List of pending patches
        """
        query = """
            SELECT * FROM patch_proposals
            WHERE repo_id = $1 AND status = $2
            ORDER BY created_at ASC, patch_id ASC
            LIMIT $3
        """

        rows = await self.postgres.fetch(
            query,
            repo_id,
            PatchStatus.PENDING.value,
            limit,
        )

        return [self._row_to_patch(row) for row in rows]

    async def count_pending(self, repo_id: str) -> int:
        """Count pending patches for a repo.

        Args:
            repo_id: Repository ID

        Returns:
            Number of pending patches
        """
        query = """
            SELECT COUNT(*) FROM patch_proposals
            WHERE repo_id = $1 AND status = $2
        """

        result = await self.postgres.fetchval(
            query,
            repo_id,
            PatchStatus.PENDING.value,
        )

        return result or 0

    async def list_by_file(
        self,
        repo_id: str,
        file_path: str,
        status: PatchStatus | None = None,
    ) -> list[PatchProposal]:
        """List patches for a specific file.

        Args:
            repo_id: Repository ID
            file_path: File path
            status: Filter by status

        Returns:
            List of patches
        """
        if status:
            query = """
                SELECT * FROM patch_proposals
                WHERE repo_id = $1 AND file_path = $2 AND status = $3
                ORDER BY created_at ASC, patch_id ASC
            """
            rows = await self.postgres.fetch(query, repo_id, file_path, status.value)
        else:
            query = """
                SELECT * FROM patch_proposals
                WHERE repo_id = $1 AND file_path = $2
                ORDER BY created_at ASC, patch_id ASC
            """
            rows = await self.postgres.fetch(query, repo_id, file_path)

        return [self._row_to_patch(row) for row in rows]

    async def update_status(
        self,
        patch_id: str,
        status: PatchStatus,
        metadata: dict | None = None,
    ) -> None:
        """Update patch status.

        Args:
            patch_id: Patch ID
            status: New status
            metadata: Updated metadata
        """
        if metadata:
            query = """
                UPDATE patch_proposals
                SET status = $1, metadata = $2
                WHERE patch_id = $3
            """
            await self.postgres.execute(query, status.value, json.dumps(metadata), patch_id)
        else:
            query = """
                UPDATE patch_proposals
                SET status = $1
                WHERE patch_id = $2
            """
            await self.postgres.execute(query, status.value, patch_id)

        logger.debug("patch_status_updated", patch_id=patch_id, status=status.value)

    async def delete(self, patch_id: str) -> None:
        """Delete a patch.

        Args:
            patch_id: Patch ID
        """
        query = "DELETE FROM patch_proposals WHERE patch_id = $1"
        await self.postgres.execute(query, patch_id)

        logger.debug("patch_deleted", patch_id=patch_id)

    async def cleanup_old_patches(
        self,
        repo_id: str,
        days: int = 30,
    ) -> int:
        """Delete old applied/failed patches.

        Args:
            repo_id: Repository ID
            days: Delete patches older than this

        Returns:
            Number of deleted patches
        """
        query = """
            DELETE FROM patch_proposals
            WHERE repo_id = $1
              AND status IN ($2, $3, $4)
              AND created_at < NOW() - $5::interval
        """

        result = await self.postgres.execute(
            query,
            repo_id,
            PatchStatus.APPLIED.value,
            PatchStatus.FAILED.value,
            PatchStatus.SUPERSEDED.value,
            f"{days} days",
        )

        deleted_count = int(result.split()[-1]) if result else 0

        logger.info(
            "patches_cleaned_up",
            repo_id=repo_id,
            deleted_count=deleted_count,
        )

        return deleted_count

    def _row_to_patch(self, row: dict) -> PatchProposal:
        """Convert database row to PatchProposal."""
        metadata = row.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        # Convert timezone-aware datetime to naive for consistency
        created_at = row["created_at"]
        if created_at and created_at.tzinfo:
            created_at = created_at.replace(tzinfo=None)

        applied_at = row.get("applied_at")
        if applied_at and applied_at.tzinfo:
            applied_at = applied_at.replace(tzinfo=None)

        return PatchProposal(
            patch_id=str(row["patch_id"]),
            repo_id=row["repo_id"],
            file_path=row["file_path"],
            patch_content=row["patch_content"],
            base_content=row.get("base_content"),
            base_version_id=row.get("base_version_id"),
            index_version_id=row.get("index_version_id"),
            description=row.get("description"),
            status=PatchStatus(row["status"]),
            created_at=created_at,
            applied_at=applied_at,
            agent_mode=row.get("agent_mode"),
            metadata=metadata or {},
        )
