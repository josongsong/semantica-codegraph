"""FIFO Patch Queue with conflict detection."""

from src.infra.observability import get_logger

from .models import PatchProposal, PatchStatus
from .store import PostgresPatchStore

logger = get_logger(__name__)


class PatchQueue:
    """FIFO queue for patch proposals with conflict detection.

    Ensures patches are processed in order and detects conflicts
    based on file version tracking.
    """

    def __init__(self, store: PostgresPatchStore):
        """Initialize with patch store.

        Args:
            store: PostgreSQL patch store
        """
        self.store = store

    async def enqueue(
        self,
        repo_id: str,
        file_path: str,
        patch_content: str,
        base_content: str | None = None,
        base_version_id: int | None = None,
        index_version_id: int | None = None,
        description: str | None = None,
        agent_mode: str | None = None,
    ) -> PatchProposal:
        """Add a patch to the queue.

        Args:
            repo_id: Repository ID
            file_path: Target file path
            patch_content: Unified diff content
            base_content: Original file content
            base_version_id: File version when patch created
            index_version_id: Index version used by agent
            description: Patch description
            agent_mode: Agent mode that created this patch

        Returns:
            Created PatchProposal
        """
        patch = PatchProposal.create(
            repo_id=repo_id,
            file_path=file_path,
            patch_content=patch_content,
            base_content=base_content,
            base_version_id=base_version_id,
            index_version_id=index_version_id,
            description=description,
            agent_mode=agent_mode,
        )

        await self.store.save(patch)

        logger.info(
            "patch_enqueued",
            patch_id=patch.patch_id,
            repo_id=repo_id,
            file_path=file_path,
            index_version=index_version_id,
        )

        return patch

    async def dequeue(self, repo_id: str) -> PatchProposal | None:
        """Get the next pending patch (FIFO).

        Args:
            repo_id: Repository ID

        Returns:
            Next PatchProposal or None if queue empty
        """
        patches = await self.store.list_pending(repo_id, limit=1)

        if not patches:
            return None

        return patches[0]

    async def peek(self, repo_id: str, count: int = 10) -> list[PatchProposal]:
        """Peek at pending patches without removing.

        Args:
            repo_id: Repository ID
            count: Number of patches to peek

        Returns:
            List of pending patches
        """
        return await self.store.list_pending(repo_id, limit=count)

    async def detect_conflicts(
        self,
        patch: PatchProposal,
        current_content: str,
    ) -> tuple[bool, dict | None]:
        """Detect if patch has conflicts with current file state.

        Args:
            patch: Patch to check
            current_content: Current file content

        Returns:
            Tuple of (has_conflict, conflict_details)
        """
        # If patch has base_content, check if current content matches
        if patch.base_content is not None:
            if current_content != patch.base_content:
                return True, {
                    "type": "content_mismatch",
                    "expected_hash": hash(patch.base_content),
                    "actual_hash": hash(current_content),
                    "message": "File content changed since patch was created",
                }

        # Check for concurrent patches on same file
        file_patches = await self.store.list_by_file(
            patch.repo_id,
            patch.file_path,
            status=PatchStatus.PENDING,
        )

        # If there are pending patches created before this one, there might be conflicts
        earlier_patches = [p for p in file_patches if p.created_at < patch.created_at and p.patch_id != patch.patch_id]

        if earlier_patches:
            return True, {
                "type": "concurrent_patches",
                "earlier_patch_count": len(earlier_patches),
                "earliest_patch_id": earlier_patches[0].patch_id,
                "message": f"{len(earlier_patches)} earlier patch(es) pending on same file",
            }

        return False, None

    async def mark_applied(self, patch_id: str) -> None:
        """Mark a patch as successfully applied.

        Args:
            patch_id: Patch ID
        """
        patch = await self.store.get(patch_id)
        if patch:
            patch.mark_applied()
            await self.store.save(patch)

            logger.info(
                "patch_applied",
                patch_id=patch_id,
                file_path=patch.file_path,
            )

    async def mark_failed(self, patch_id: str, reason: str) -> None:
        """Mark a patch as failed.

        Args:
            patch_id: Patch ID
            reason: Failure reason
        """
        patch = await self.store.get(patch_id)
        if patch:
            patch.mark_failed(reason)
            await self.store.save(patch)

            logger.error(
                "patch_failed",
                patch_id=patch_id,
                file_path=patch.file_path,
                reason=reason,
            )

    async def mark_conflict(self, patch_id: str, conflict_details: dict) -> None:
        """Mark a patch as having conflict.

        Args:
            patch_id: Patch ID
            conflict_details: Conflict information
        """
        patch = await self.store.get(patch_id)
        if patch:
            patch.mark_conflict(conflict_details)
            await self.store.save(patch)

            logger.warning(
                "patch_conflict",
                patch_id=patch_id,
                file_path=patch.file_path,
                conflict_type=conflict_details.get("type"),
            )

    async def supersede_patches(
        self,
        repo_id: str,
        file_path: str,
        superseding_patch_id: str,
    ) -> int:
        """Mark older pending patches for same file as superseded.

        Args:
            repo_id: Repository ID
            file_path: File path
            superseding_patch_id: ID of newer patch

        Returns:
            Number of patches superseded
        """
        patches = await self.store.list_by_file(
            repo_id,
            file_path,
            status=PatchStatus.PENDING,
        )

        superseding_patch = await self.store.get(superseding_patch_id)
        if not superseding_patch:
            return 0

        count = 0
        for patch in patches:
            if patch.patch_id != superseding_patch_id and patch.created_at < superseding_patch.created_at:
                patch.mark_superseded(superseding_patch_id)
                await self.store.save(patch)
                count += 1

        logger.info(
            "patches_superseded",
            repo_id=repo_id,
            file_path=file_path,
            superseded_count=count,
        )

        return count

    async def get_queue_size(self, repo_id: str) -> int:
        """Get number of pending patches.

        Args:
            repo_id: Repository ID

        Returns:
            Number of pending patches
        """
        return await self.store.count_pending(repo_id)

    async def clear_queue(self, repo_id: str) -> int:
        """Clear all pending patches (emergency use).

        Args:
            repo_id: Repository ID

        Returns:
            Number of patches cleared
        """
        patches = await self.store.list_pending(repo_id, limit=10000)

        for patch in patches:
            await self.store.delete(patch.patch_id)

        logger.warning(
            "queue_cleared",
            repo_id=repo_id,
            cleared_count=len(patches),
        )

        return len(patches)
