"""
IRDocument Resolver (Production-Ready)

RFC-052: MCP Service Layer Architecture
Resolves repo_id + snapshot_id → IRDocument.

Design:
- Primary: Load from IRDocumentStore (if available)
- Fallback: Load from file system
- Cache: In-memory cache for hot IRDocuments

Critical: No mock/stub - real implementation only.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import (
        IRDocument,
    )

logger = get_logger(__name__)


class IRDocumentResolver:
    """
    Resolves (repo_id, snapshot_id) → IRDocument.

    Production-ready implementation (no mocks).
    """

    def __init__(self, ir_store=None, file_system_path: Path | None = None):
        """
        Initialize resolver.

        Args:
            ir_store: Optional IRDocumentStore
            file_system_path: Optional file system path for fallback
        """
        self.ir_store = ir_store
        self.file_system_path = file_system_path
        self._cache: dict[tuple[str, str], "IRDocument"] = {}

    async def resolve(
        self,
        repo_id: str,
        snapshot_id: str | None = None,
    ) -> "IRDocument":
        """
        Resolve IRDocument.

        Args:
            repo_id: Repository ID
            snapshot_id: Optional snapshot ID (latest if None)

        Returns:
            IRDocument

        Raises:
            ValueError: If IRDocument not found
            NotImplementedError: If ir_store not configured
        """
        # Check cache
        cache_key = (repo_id, snapshot_id or "latest")
        if cache_key in self._cache:
            logger.debug("ir_document_cache_hit", repo_id=repo_id, snapshot_id=snapshot_id)
            return self._cache[cache_key]

        # Try IRDocumentStore
        if self.ir_store:
            try:
                ir_doc = await self._load_from_store(repo_id, snapshot_id)
                self._cache[cache_key] = ir_doc
                return ir_doc
            except Exception as e:
                logger.warning("ir_store_load_failed", error=str(e))

        # Try file system fallback
        if self.file_system_path:
            try:
                ir_doc = self._load_from_file_system(repo_id, snapshot_id)
                self._cache[cache_key] = ir_doc
                return ir_doc
            except Exception as e:
                logger.warning("filesystem_load_failed", error=str(e))

        # No valid source
        raise NotImplementedError(
            f"Cannot resolve IRDocument for repo_id={repo_id}, snapshot_id={snapshot_id}. "
            "Configure ir_store or file_system_path."
        )

    async def _load_from_store(
        self,
        repo_id: str,
        snapshot_id: str | None,
    ) -> "IRDocument":
        """Load from IRDocumentStore"""
        if snapshot_id:
            return await self.ir_store.load_by_id(repo_id, snapshot_id)
        else:
            return await self.ir_store.load_latest(repo_id)

    def _load_from_file_system(
        self,
        repo_id: str,
        snapshot_id: str | None,
    ) -> "IRDocument":
        """Load from file system (fallback)"""
        # Find IR file
        if not self.file_system_path:
            raise ValueError("file_system_path not configured")

        ir_file = self.file_system_path / repo_id / f"{snapshot_id or 'latest'}.json"

        if not ir_file.exists():
            raise ValueError(f"IRDocument not found: {ir_file}")

        # Load and deserialize
        import json

        with open(ir_file) as f:
            data = json.load(f)

        # Deserialize to IRDocument
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        # Basic deserialization (TODO: Use proper serializer)
        return IRDocument(
            repo_id=data.get("repo_id", repo_id),
            snapshot_id=data.get("snapshot_id", snapshot_id or "unknown"),
            schema_version=data.get("schema_version", "2.3"),
            nodes=data.get("nodes", []),
            edges=data.get("edges", []),
        )

    def clear_cache(self) -> None:
        """Clear cache (for testing)"""
        self._cache.clear()
