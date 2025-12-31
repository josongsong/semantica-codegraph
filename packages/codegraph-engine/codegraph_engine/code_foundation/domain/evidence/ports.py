"""
Evidence Repository Port

RFC-052: MCP Service Layer Architecture
Domain-defined interface for evidence storage.

Implementation: SQLite-based (see infrastructure layer)
"""

from typing import Protocol

from .models import Evidence, EvidenceKind


class EvidenceRepositoryPort(Protocol):
    """
    Port for evidence storage.

    Domain-defined interface (implementation in infrastructure).
    """

    async def save(self, evidence: Evidence) -> None:
        """
        Save evidence.

        Args:
            evidence: Evidence to save

        Raises:
            ValueError: If evidence_id conflicts
        """
        ...

    async def get_by_id(self, evidence_id: str) -> Evidence | None:
        """
        Retrieve evidence by ID.

        Args:
            evidence_id: Evidence ID

        Returns:
            Evidence or None if not found/expired
        """
        ...

    async def list_by_snapshot(
        self,
        snapshot_id: str,
        kind: EvidenceKind | None = None,
        limit: int = 100,
    ) -> list[Evidence]:
        """
        List evidence for a snapshot.

        Args:
            snapshot_id: Snapshot ID
            kind: Optional filter by kind
            limit: Max results

        Returns:
            List of evidence (sorted by created_at desc)
        """
        ...

    async def delete_by_snapshot(self, snapshot_id: str) -> int:
        """
        Delete all evidence for a snapshot (GC).

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Number of evidence deleted
        """
        ...

    async def delete_expired(self) -> int:
        """
        Delete expired evidence (TTL cleanup).

        Returns:
            Number of evidence deleted
        """
        ...

    async def exists(self, evidence_id: str) -> bool:
        """
        Check if evidence exists and is valid.

        Args:
            evidence_id: Evidence ID

        Returns:
            True if exists and not expired
        """
        ...
