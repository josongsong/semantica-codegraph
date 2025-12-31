"""
Indexing Orchestrator (SOTA Slim Version)

Stage 기반 파이프라인 패턴으로 리팩토링된 슬림한 오케스트레이터.
각 Stage는 단일 책임을 가지며, Orchestrator는 조율만 담당합니다.

Pipeline:
    1. Git operations (GitStage)
    2. File discovery (DiscoveryStage)
    3. Parsing (ParsingStage)
    4. IR building (IRStage)
    5. Semantic IR building (SemanticIRStage)
    6. Graph building (GraphStage)
    7. Chunk generation (ChunkStage)
    8. RepoMap building (RepoMapStage)
    9. Multi-Index indexing (MultiIndexStage)
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeDetector
from codegraph_engine.analysis_indexing.infrastructure.git_helper import GitHelper
from codegraph_engine.analysis_indexing.infrastructure.models import (
    IndexingConfig,
    IndexingResult,
    IndexingStage,
    IndexingStatus,
    IndexSessionContext,
    OrchestratorComponents,
)
from codegraph_engine.analysis_indexing.infrastructure.models.job import JobProgress
from codegraph_engine.analysis_indexing.infrastructure.stages import (
    BaseStage,
    ChunkStage,
    DiscoveryStage,
    GitStage,
    GraphStage,
    IRStage,
    MultiIndexStage,
    ParsingStage,
    RepoMapStage,
    SemanticIRStage,
    StageContext,
)
from codegraph_engine.code_foundation.infrastructure.graph.edge_validator import EdgeValidator
from codegraph_engine.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer
from codegraph_engine.code_foundation.infrastructure.profiling import Profiler, get_noop_profiler

# Hexagonal: Optional import to break circular dependency
try:
    from codegraph_engine.multi_index.infrastructure.version.store import IndexVersionStore

    _VERSION_STORE_AVAILABLE = True
except ImportError:
    IndexVersionStore = None  # type: ignore
    _VERSION_STORE_AVAILABLE = False

from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

logger = get_logger(__name__)


@dataclass
class StageRegistry:
    """Stage 인스턴스 레지스트리"""

    git: GitStage
    discovery: DiscoveryStage
    parsing: ParsingStage
    ir: IRStage
    semantic_ir: SemanticIRStage
    graph: GraphStage
    chunk: ChunkStage
    repomap: RepoMapStage
    indexing: MultiIndexStage


class IndexingOrchestratorSlim:
    """
    SOTA급 슬림 오케스트레이터.

    Stage 기반 파이프라인 패턴:
    - 각 Stage는 독립적인 단일 책임
    - Orchestrator는 Stage 조율만 담당
    - StageContext로 데이터 전달
    """

    def __init__(
        self,
        components: OrchestratorComponents | None = None,
        config: IndexingConfig | None = None,
        progress_callback: Callable[[IndexingStage, float], None] | None = None,
        pyright_daemon_factory: Callable[[str], Any] | None = None,
        version_store: IndexVersionStore | None = None,
        profiler: Profiler | None = None,
        # Legacy individual parameters (backward compatibility)
        **kwargs,
    ):
        """Initialize orchestrator with components."""
        self.config = config or IndexingConfig()
        self.progress_callback = progress_callback
        self.pyright_daemon_factory = pyright_daemon_factory
        self.version_store = version_store
        self.profiler = profiler or get_noop_profiler()

        # Build components holder
        self._components = self._build_components(components, kwargs)

        # Set profiler on components (for Stage→Builder propagation)
        self._components.profiler = self.profiler

        # Initialize stages
        self._stages = self._init_stages()

        # Runtime state
        self.project_root: Path | None = None
        self._session_ctx: IndexSessionContext | None = None
        self._stop_event: asyncio.Event | None = None
        self._current_version = None

        # Edge validation & Impact analysis
        self.edge_validator = EdgeValidator(stale_ttl_hours=24.0, auto_cleanup=False)
        self.impact_analyzer = GraphImpactAnalyzer(max_depth=3, max_affected=500, include_test_files=False)

        # Change detector (lazy init)
        self.change_detector: ChangeDetector | None = None

    def _build_components(self, components: OrchestratorComponents | None, kwargs: dict) -> Any:
        """Build unified components holder from grouped or legacy params."""

        @dataclass
        class ComponentsHolder:
            parser_registry: Any = None
            ir_builder: Any = None
            semantic_ir_builder: Any = None
            graph_builder: Any = None
            chunk_builder: Any = None
            graph_store: Any = None
            chunk_store: Any = None
            repomap_store: Any = None
            lexical_index: Any = None
            vector_index: Any = None
            symbol_index: Any = None
            fuzzy_index: Any = None
            domain_index: Any = None
            config: Any = None
            project_root: Any = None
            pyright_daemon_factory: Any = None
            edge_validator: Any = None
            impact_analyzer: Any = None
            container: Any = None

            # RFC-028: Cost/Concurrency/Differential Analyzers
            cost_analyzer: Any = None

            # Profiler (optional, for benchmarking)
            profiler: Profiler | None = None

        holder = ComponentsHolder()

        if components:
            # Grouped initialization
            holder.parser_registry = components.builders.parser_registry
            holder.ir_builder = components.builders.ir_builder
            holder.semantic_ir_builder = components.builders.semantic_ir_builder
            holder.graph_builder = components.builders.graph_builder
            holder.chunk_builder = components.builders.chunk_builder
            holder.graph_store = components.stores.graph_store
            holder.chunk_store = components.stores.chunk_store
            holder.repomap_store = components.stores.repomap_store
            holder.lexical_index = components.indexes.lexical
            holder.vector_index = components.indexes.vector
            holder.symbol_index = components.indexes.symbol
            holder.fuzzy_index = components.indexes.fuzzy
            holder.domain_index = components.indexes.domain
        else:
            # Legacy initialization
            for key in [
                "parser_registry",
                "ir_builder",
                "semantic_ir_builder",
                "graph_builder",
                "chunk_builder",
                "graph_store",
                "chunk_store",
                "repomap_store",
                "lexical_index",
                "vector_index",
                "symbol_index",
                "fuzzy_index",
                "domain_index",
            ]:
                setattr(holder, key, kwargs.get(key))

        holder.config = self.config
        holder.pyright_daemon_factory = self.pyright_daemon_factory

        # RFC-028: Cost Analyzer (from kwargs or container)
        holder.cost_analyzer = kwargs.get("cost_analyzer")

        # If not provided via kwargs, try to get from container (OrchestratorComponents.container)
        if not holder.cost_analyzer and components and hasattr(components, "container"):
            try:
                # OrchestratorComponents has .container field
                container = components.container
                if container and hasattr(container, "_foundation"):
                    holder.cost_analyzer = container._foundation.cost_analyzer
                    logger.debug("cost_analyzer loaded from container")
            except Exception as e:
                logger.debug(f"Could not load cost_analyzer from container: {e}")
                # Optional: continue without cost_analyzer

        # Profiler will be set later after __init__ (self.profiler not yet available)
        # It's set via _components.profiler = self.profiler after _build_components call

        return holder

    def _init_stages(self) -> StageRegistry:
        """Initialize all pipeline stages."""
        return StageRegistry(
            git=GitStage(self._components),
            discovery=DiscoveryStage(self._components),
            parsing=ParsingStage(self._components),
            ir=IRStage(self._components),
            semantic_ir=SemanticIRStage(self._components),
            graph=GraphStage(self._components),
            chunk=ChunkStage(self._components),
            repomap=RepoMapStage(self._components),
            indexing=MultiIndexStage(self._components),
        )

    # ==================== Public API ====================

    async def index_repository_full(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str = "main",
        force: bool = False,
    ) -> IndexingResult:
        """Full repository indexing."""
        return await self.index_repository(
            repo_path=repo_path,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            incremental=False,
            force=force,
        )

    async def index_repository_incremental(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str = "main",
    ) -> IndexingResult:
        """Incremental repository indexing."""
        return await self.index_repository(
            repo_path=repo_path,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            incremental=True,
            force=False,
        )

    async def index_repository(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str = "main",
        incremental: bool = False,
        force: bool = False,
        progress: JobProgress | None = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[[JobProgress], Awaitable[None]] | None = None,
    ) -> IndexingResult:
        """
        Main entry point - orchestrates the entire pipeline.

        Args:
            repo_path: Path to repository
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            incremental: If True, only process changed files
            force: If True, force full reindex
            progress: JobProgress for cooperative cancellation
            stop_event: Stop signal for cooperative cancellation
            progress_persist_callback: Callback to persist progress

        Returns:
            IndexingResult with statistics
        """
        repo_path = Path(repo_path)
        self.project_root = repo_path
        self._components.project_root = repo_path

        # Initialize LayeredIRBuilder with project_root (lazy initialization)
        if self._components.ir_builder is None:
            from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

            self._components.ir_builder = LayeredIRBuilder(
                project_root=repo_path,
                profiler=self.profiler,
            )
            # Update stages with new ir_builder
            self._stages.ir.ir_builder = self._components.ir_builder

        self._indexing_start_time = datetime.now()
        start_time = self._indexing_start_time

        # Initialize session context
        self._session_ctx = IndexSessionContext(
            max_impact_reindex_files=self.config.max_impact_reindex_files,
        )
        self._stop_event = stop_event

        # Initialize result
        result = IndexingResult(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            status=IndexingStatus.IN_PROGRESS,
            start_time=start_time,
            incremental=incremental,
        )

        logger.info(
            "indexing_started",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            mode="incremental" if incremental else "full",
        )
        record_counter("indexing_jobs_started_total")

        # Create index version (full indexing only)
        await self._create_version_if_needed(repo_path, repo_id, snapshot_id, incremental)

        try:
            # Create stage context
            ctx = StageContext(
                repo_path=repo_path,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                result=result,
                config=self.config,
                is_incremental=incremental,
                profiler=self.profiler,
            )

            # Execute pipeline
            await self._execute_pipeline(
                ctx,
                progress=progress,
                stop_event=stop_event,
                progress_persist_callback=progress_persist_callback,
            )

            # Finalize
            if result.status != IndexingStatus.FAILED:
                result.mark_completed()
                await self._finalize_version()

            # Record metrics
            duration = (datetime.now() - start_time).total_seconds()
            record_histogram("indexing_duration_seconds", duration)
            record_counter("indexing_jobs_completed_total")

            logger.info(
                "indexing_completed",
                repo_id=repo_id,
                duration=duration,
                files_processed=result.files_processed,
                status=result.status.value,
            )

        except Exception as e:
            result.mark_failed(str(e))
            await self._fail_version(str(e))
            logger.error("indexing_failed", repo_id=repo_id, error=str(e), exc_info=True)
            record_counter("indexing_jobs_failed_total")
            raise

        return result

    # ==================== Pipeline Execution ====================

    async def _execute_pipeline(
        self,
        ctx: StageContext,
        progress: JobProgress | None = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[[JobProgress], Awaitable[None]] | None = None,
    ) -> None:
        """Execute the indexing pipeline through all stages."""

        # Stage 1: Git Operations
        await self._run_stage(self._stages.git, ctx)

        # Stage 2: File Discovery
        await self._run_stage(self._stages.discovery, ctx)

        if not ctx.files:
            logger.warning("no_files_to_process", repo_id=ctx.repo_id)
            return

        # Initialize progress tracking
        if progress:
            progress.total_files = len(ctx.files)

        # Stage 3: Parsing (supports cooperative cancellation)
        await self._stages.parsing.execute(ctx, progress, stop_event, progress_persist_callback)
        self._report_progress(IndexingStage.PARSING, 100.0)

        if self._should_stop(stop_event, ctx, "parsing"):
            return

        if not ctx.ast_results:
            logger.warning("parsing_produced_no_results", repo_id=ctx.repo_id)
            return

        # Stage 4: IR Building
        await self._run_stage(self._stages.ir, ctx)

        if not ctx.ir_doc:
            logger.warning("ir_building_produced_no_results", repo_id=ctx.repo_id)
            return

        # Stage 5: Semantic IR Building
        await self._run_stage(self._stages.semantic_ir, ctx)

        # Stage 6: Graph Building
        self._stages.graph.edge_validator = self.edge_validator
        self._stages.graph.impact_analyzer = self.impact_analyzer
        await self._run_stage(self._stages.graph, ctx)

        if not ctx.graph_doc:
            logger.warning("graph_building_produced_no_results", repo_id=ctx.repo_id)
            return

        # Stage 7: Chunk Generation
        await self._run_stage(self._stages.chunk, ctx)

        if not ctx.chunk_ids:
            logger.warning("chunk_generation_produced_no_results", repo_id=ctx.repo_id)
            return

        # Stage 8: RepoMap Building
        await self._run_stage(self._stages.repomap, ctx)

        # Stage 9: Multi-Index Indexing
        await self._run_stage(self._stages.indexing, ctx)

    async def _run_stage(self, stage: BaseStage, ctx: StageContext) -> None:
        """Run a single stage with progress reporting."""
        stage_name = stage.stage_name
        logger.debug(f"stage_started: {stage_name.value}")

        await stage.execute(ctx)

        self._report_progress(stage_name, 100.0)
        logger.debug(f"stage_completed: {stage_name.value}")

    def _should_stop(self, stop_event: asyncio.Event | None, ctx: StageContext, stage_name: str) -> bool:
        """Check if pipeline should stop (cooperative cancellation)."""
        if stop_event and stop_event.is_set():
            logger.info("indexing_stopped_by_request", stage=stage_name)
            ctx.result.status = IndexingStatus.IN_PROGRESS
            ctx.result.metadata["stopped_at_stage"] = stage_name
            return True
        return False

    def _report_progress(self, stage: IndexingStage, percent: float) -> None:
        """Report progress to callback if configured."""
        if self.progress_callback:
            self.progress_callback(stage, percent)

    # ==================== Version Management ====================

    async def _create_version_if_needed(
        self, repo_path: Path, repo_id: str, snapshot_id: str, incremental: bool
    ) -> None:
        """Create index version for full indexing."""
        if self.version_store and not incremental:
            git_helper = GitHelper(repo_path)
            current_commit = git_helper.get_current_commit_hash() or "unknown"
            self._current_version = await self.version_store.create_version(
                repo_id=repo_id,
                git_commit=current_commit,
                file_count=0,
                snapshot_id=snapshot_id,
            )
            logger.info("index_version_created", version_id=self._current_version.version_id)

    async def _finalize_version(self) -> None:
        """Finalize index version on success."""
        if self.version_store and self._current_version:
            # Hexagonal: Optional import
            try:
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus
            except ImportError:
                return  # multi_index not available

            # Calculate duration
            duration_ms = 0.0
            if hasattr(self, "_indexing_start_time") and self._indexing_start_time:
                duration_ms = (datetime.now() - self._indexing_start_time).total_seconds() * 1000

            await self.version_store.update_status(
                self._current_version.version_id,
                IndexVersionStatus.COMPLETED,
                repo_id=self._current_version.repo_id,
                duration_ms=duration_ms,
            )

    async def _fail_version(self, error: str) -> None:
        """Mark index version as failed."""
        if self.version_store and self._current_version:
            # Hexagonal: Optional import
            try:
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus
            except ImportError:
                return  # multi_index not available

            await self.version_store.update_status(
                self._current_version.version_id,
                IndexVersionStatus.FAILED,
                error_message=error,
                repo_id=self._current_version.repo_id,
            )
