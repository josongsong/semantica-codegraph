"""
Base Handler for Indexing Pipeline Stages

Provides common infrastructure for all stage handlers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from src.contexts.analysis_indexing.infrastructure.models import IndexingConfig, IndexingResult, IndexingStage
from src.contexts.analysis_indexing.infrastructure.models.job import JobProgress
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeSet
    from src.contexts.analysis_indexing.infrastructure.models import IndexSessionContext
    from src.contexts.code_foundation.infrastructure.chunk.incremental import ChunkIncrementalRefresher
    from src.contexts.code_foundation.infrastructure.graph.edge_validator import EdgeValidator
    from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer


logger = get_logger(__name__)


@dataclass
class HandlerContext:
    """
    Shared context passed between handlers during indexing.

    This replaces instance variables that were previously scattered
    across IndexingOrchestrator.
    """

    # Repository info
    repo_path: Path
    repo_id: str
    snapshot_id: str

    # Configuration
    config: IndexingConfig
    incremental: bool = False

    # Runtime state
    project_root: Path | None = None
    change_set: ChangeSet | None = None
    session_ctx: IndexSessionContext | None = None
    stop_event: asyncio.Event | None = None

    # Progress tracking
    progress: JobProgress | None = None
    progress_callback: Callable[[IndexingStage, float], None] | None = None
    progress_persist_callback: Callable[[JobProgress], Awaitable[None]] | None = None

    # Shared components (lazy initialized)
    chunk_refresher: ChunkIncrementalRefresher | None = None
    edge_validator: EdgeValidator | None = None
    impact_analyzer: GraphImpactAnalyzer | None = None

    # Container for DI
    container: Any = None

    # Intermediate results (populated during pipeline execution)
    ast_results: dict = field(default_factory=dict)
    ir_doc: Any = None
    semantic_ir: Any = None
    graph_doc: Any = None
    chunks: list = field(default_factory=list)
    repomap: Any = None


class StageHandler(Protocol):
    """Protocol for stage handlers."""

    async def execute(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
    ) -> None:
        """Execute the stage and update result."""
        ...


class BaseHandler:
    """
    Base class for indexing pipeline stage handlers.

    Provides common functionality:
    - Progress reporting
    - Stage timing
    - Error handling patterns
    - Cancellation checks
    """

    stage: IndexingStage  # Subclasses must define this

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def _report_progress(self, ctx: HandlerContext, progress: float) -> None:
        """Report progress for current stage."""
        if ctx.progress_callback:
            ctx.progress_callback(self.stage, progress)

    def _check_cancelled(self, ctx: HandlerContext) -> bool:
        """Check if cancellation was requested."""
        if ctx.stop_event and ctx.stop_event.is_set():
            self.logger.info(
                "stage_cancelled",
                stage=self.stage.value,
            )
            return True
        return False

    async def _persist_progress(self, ctx: HandlerContext) -> None:
        """Persist progress if callback is available."""
        if ctx.progress_persist_callback and ctx.progress:
            await ctx.progress_persist_callback(ctx.progress)

    def _start_stage(self, ctx: HandlerContext, result: IndexingResult) -> datetime:
        """Mark stage start and return start time."""
        self._report_progress(ctx, 0.0)
        self.logger.info("stage_started", stage=self.stage.value)
        return datetime.now()

    def _end_stage(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        start_time: datetime,
        **metrics: Any,
    ) -> None:
        """Mark stage end and record metrics."""
        duration = (datetime.now() - start_time).total_seconds()
        result.stage_timings[self.stage.value] = duration

        self._report_progress(ctx, 1.0)
        self.logger.info(
            "stage_completed",
            stage=self.stage.value,
            duration_seconds=duration,
            **metrics,
        )

    async def execute(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
    ) -> bool:
        """
        Execute the handler stage.

        Returns:
            True if stage completed successfully, False if cancelled or failed
        """
        raise NotImplementedError("Subclasses must implement execute()")
