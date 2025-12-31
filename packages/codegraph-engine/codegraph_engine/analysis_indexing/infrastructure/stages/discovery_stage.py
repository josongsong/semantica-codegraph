"""
Discovery Stage - 파일 탐색 처리

Stage 2: File discovery (find all source files)
"""

from typing import Any

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeDetector
from codegraph_engine.analysis_indexing.infrastructure.file_discovery import FileDiscovery
from codegraph_engine.analysis_indexing.infrastructure.git_helper import GitHelper
from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_shared.infra.observability import get_logger, record_counter

from .base import BaseStage, StageContext

logger = get_logger(__name__)


class DiscoveryStage(BaseStage):
    """파일 탐색 Stage"""

    stage_name = IndexingStage.FILE_DISCOVERY

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.config = getattr(components, "config", None)
        self.change_detector: ChangeDetector | None = None

    async def execute(self, ctx: StageContext) -> None:
        """파일 탐색 실행"""
        if ctx.is_incremental:
            await self._discover_incremental(ctx)
        else:
            await self._discover_full(ctx)

    async def _discover_full(self, ctx: StageContext) -> None:
        """Full 파일 탐색"""
        discovery = FileDiscovery(ctx.config or self.config)

        files = discovery.discover_files(ctx.repo_path)
        logger.info("files_discovered", mode="full", count=len(files))
        record_counter("files_discovered_total", value=len(files), labels={"mode": "full"})

        ctx.files = files
        ctx.result.files_discovered = len(files)

        # Get file stats
        stats = discovery.get_file_stats(files)
        ctx.result.metadata["file_stats"] = stats
        logger.info("file_stats", languages=stats["by_language"], total_size_mb=stats["total_size_mb"])

    async def _discover_incremental(self, ctx: StageContext) -> None:
        """Incremental 파일 탐색 (변경 감지 포함)"""
        discovery = FileDiscovery(ctx.config or self.config)
        git = GitHelper(ctx.repo_path)

        # Initialize change detector if not already
        if not self.change_detector:
            self.change_detector = ChangeDetector(git_helper=git)

        # Detect changes
        change_set = self.change_detector.detect_changes(ctx.repo_path, ctx.repo_id)
        ctx.change_set = change_set

        logger.info(
            "incremental_changes_detected",
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
        )
        record_counter("files_discovered_total", value=change_set.total_count, labels={"mode": "incremental"})

        # Convert to Path objects for changed files
        changed_paths = []
        for file_path in change_set.all_changed:
            full_path = ctx.repo_path / file_path
            if full_path.exists():
                changed_paths.append(full_path)

        # Filter through FileDiscovery
        files = discovery.discover_files(ctx.repo_path, changed_files=[str(p) for p in changed_paths])

        ctx.files = files
        ctx.result.files_discovered = len(files)
        ctx.result.metadata["change_set"] = {
            "added": len(change_set.added),
            "modified": len(change_set.modified),
            "deleted": len(change_set.deleted),
        }
        ctx.result.metadata["changed_files"] = list(change_set.all_changed)

        # Get file stats
        if files:
            stats = discovery.get_file_stats(files)
            ctx.result.metadata["file_stats"] = stats
            logger.info("file_stats", languages=stats["by_language"], total_size_mb=stats["total_size_mb"])
