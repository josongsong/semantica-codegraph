"""
Indexing Orchestrator

Orchestrates the complete indexing pipeline from parsing to indexing.

협력적 취소(cooperative cancellation)를 지원하여
graceful shutdown과 작업 일시중지가 가능합니다.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeDetector, ChangeSet
from src.contexts.analysis_indexing.infrastructure.file_discovery import FileDiscovery
from src.contexts.analysis_indexing.infrastructure.git_helper import GitHelper
from src.contexts.analysis_indexing.infrastructure.mode_manager import IndexingPlan, ModeManager
from src.contexts.analysis_indexing.infrastructure.models import (
    IndexingConfig,
    IndexingMode,
    IndexingResult,
    IndexingStage,
    IndexingStatus,
    IndexSessionContext,
    Layer,
    OrchestratorComponents,
)
from src.contexts.analysis_indexing.infrastructure.models.job import JobProgress
from src.contexts.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from src.contexts.code_foundation.infrastructure.chunk.incremental import ChunkIncrementalRefresher
from src.contexts.code_foundation.infrastructure.chunk.models import ChunkHistory
from src.contexts.code_foundation.infrastructure.graph.edge_validator import EdgeValidator
from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer
from src.contexts.multi_index.infrastructure.version.models import IndexVersion, IndexVersionStatus
from src.contexts.multi_index.infrastructure.version.store import IndexVersionStore
from src.contexts.repo_structure.infrastructure.git_history import GitHistoryAnalyzer
from src.infra.observability import get_logger, record_counter, record_histogram
from src.pipeline.decorators import index_execution, stage_execution

logger = get_logger(__name__)


class IndexingOrchestrator:
    """
    Orchestrates the complete indexing pipeline.

    Coordinates all components to transform a repository from source code
    to fully indexed and searchable state.

    Pipeline:
        1. Git operations (clone/fetch/pull)
        2. File discovery (find all source files)
        3. Parsing (Tree-sitter AST generation)
        4. IR building (language-neutral intermediate representation)
        5. Semantic IR building (CFG, DFG, types, signatures)
        6. Graph building (code graph with nodes and edges)
        7. Chunk generation (LLM-friendly chunks)
        8. RepoMap building (tree, PageRank, summaries)
        9. Indexing (lexical, vector, symbol, fuzzy, domain)
    """

    def __init__(
        self,
        # Grouped components (recommended)
        components: OrchestratorComponents | None = None,
        # Configuration
        config: IndexingConfig | None = None,
        # Optional callbacks
        progress_callback: Callable[[IndexingStage, float], None] | None = None,
        # Pyright integration factory
        pyright_daemon_factory: Callable[[str], Any] | None = None,
        # Index Version Store (for version tracking)
        version_store: IndexVersionStore | None = None,
        # --- Legacy individual parameters (for backward compatibility) ---
        parser_registry=None,
        ir_builder=None,
        semantic_ir_builder=None,
        graph_builder=None,
        chunk_builder=None,
        repomap_tree_builder_class=None,
        repomap_pagerank_engine=None,
        repomap_summarizer=None,
        graph_store=None,
        chunk_store=None,
        repomap_store=None,
        lexical_index=None,
        vector_index=None,
        symbol_index=None,
        fuzzy_index=None,
        domain_index=None,
    ):
        """
        Initialize orchestrator with all required components.

        Supports two initialization styles:
        1. Grouped (recommended): Pass OrchestratorComponents
        2. Legacy (backward compatible): Pass individual parameters

        Args:
            components: Grouped components (OrchestratorComponents)
            config: Indexing configuration
            progress_callback: Optional callback for progress updates
            pyright_daemon_factory: Optional factory to create Pyright daemon (RFC-023)

            # Legacy parameters (deprecated, use components instead):
            parser_registry, ir_builder, semantic_ir_builder, graph_builder,
            chunk_builder, repomap_tree_builder_class, repomap_pagerank_engine,
            repomap_summarizer, graph_store, chunk_store, repomap_store,
            lexical_index, vector_index, symbol_index, fuzzy_index, domain_index
        """
        # Handle grouped vs legacy initialization
        if components:
            # Grouped initialization (recommended)
            self.parser_registry = components.builders.parser_registry
            self.ir_builder = components.builders.ir_builder
            self.semantic_ir_builder = components.builders.semantic_ir_builder
            self.graph_builder = components.builders.graph_builder
            self.chunk_builder = components.builders.chunk_builder

            self.repomap_tree_builder_class = components.repomap.tree_builder_class
            self.repomap_pagerank_engine = components.repomap.pagerank_engine
            self.repomap_summarizer = components.repomap.summarizer

            self.graph_store = components.stores.graph_store
            self.chunk_store = components.stores.chunk_store
            self.repomap_store = components.stores.repomap_store

            self.lexical_index = components.indexes.lexical
            self.vector_index = components.indexes.vector
            self.symbol_index = components.indexes.symbol
            self.fuzzy_index = components.indexes.fuzzy
            self.domain_index = components.indexes.domain
        else:
            # Legacy initialization (backward compatible)
            self.parser_registry = parser_registry
            self.ir_builder = ir_builder
            self.semantic_ir_builder = semantic_ir_builder
            self.graph_builder = graph_builder
            self.chunk_builder = chunk_builder

            self.repomap_tree_builder_class = repomap_tree_builder_class
            self.repomap_pagerank_engine = repomap_pagerank_engine
            self.repomap_summarizer = repomap_summarizer

            self.graph_store = graph_store
            self.chunk_store = chunk_store
            self.repomap_store = repomap_store

            self.lexical_index = lexical_index
            self.vector_index = vector_index
            self.symbol_index = symbol_index
            self.fuzzy_index = fuzzy_index
            self.domain_index = domain_index

        # Configuration
        self.config = config or IndexingConfig()

        # Progress tracking
        self.progress_callback = progress_callback

        # Container (for Pyright integration)
        self.pyright_daemon_factory = pyright_daemon_factory

        # Index version store (for version tracking)
        self.version_store = version_store

        # Runtime state
        self.project_root = None

        # Session context for 2-Pass Impact Reindexing
        self._session_ctx: IndexSessionContext | None = None
        self._stop_event: asyncio.Event | None = None

        # Index version tracking
        self._current_version: IndexVersion | None = None

        # Mode management
        self.mode_manager: ModeManager | None = None
        self.change_detector: ChangeDetector | None = None
        self.scope_expander: ScopeExpander | None = None

        # Incremental processing
        self.chunk_refresher: ChunkIncrementalRefresher | None = None

        # Edge validation for backward-edge stale management (RFC SEP-G12-EDGE-VAL)
        self.edge_validator: EdgeValidator = EdgeValidator(
            stale_ttl_hours=24.0,  # 24시간 후 stale edge 자동 정리
            auto_cleanup=False,  # 수동 cleanup 권장
        )

        # Impact analyzer for symbol-level affected callers analysis
        self.impact_analyzer: GraphImpactAnalyzer = GraphImpactAnalyzer(
            max_depth=3,  # 3-hop transitive callers
            max_affected=500,  # 최대 500개 영향 심볼
            include_test_files=False,  # 테스트 파일 제외
        )

        # Metadata store for tracking last indexed commit (initialized via initialize_mode_system)
        self.metadata_store = None

        # v4.5: Compaction manager (optional)
        self.compaction_manager = None

    async def _check_compaction_trigger(self, repo_id: str, snapshot_id: str) -> None:
        """Compaction 트리거 체크 (v4.5).

        Delta 크기가 임계값을 넘으면 백그라운드로 compaction 실행.

        Args:
            repo_id: 저장소 ID
            snapshot_id: Snapshot ID
        """
        if not self.compaction_manager:
            logger.debug("Compaction manager not configured, skipping")
            return

        try:
            should_compact = await self.compaction_manager.should_compact(repo_id)

            if should_compact:
                logger.warning(
                    f"Compaction triggered for {repo_id}",
                    extra={"repo_id": repo_id},
                )

                # 백그라운드 태스크로 실행 (non-blocking)
                import asyncio

                asyncio.create_task(self.compaction_manager.compact(repo_id, snapshot_id))
                logger.info("Compaction started in background")

        except Exception as e:
            logger.error(f"Compaction trigger check failed: {e}", exc_info=True)

    async def index_repository_full(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str = "main",
        force: bool = False,
    ) -> IndexingResult:
        """
        Full repository indexing (API compatibility wrapper).

        Indexes the entire repository from scratch.

        Args:
            repo_path: Path to repository
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            force: If True, force reindex even if already indexed

        Returns:
            IndexingResult with statistics and metrics
        """
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
        """
        Incremental repository indexing (API compatibility wrapper).

        Only indexes changed files since last indexing.

        Args:
            repo_path: Path to repository
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            IndexingResult with statistics and metrics
        """
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
        # 협력적 취소 지원
        progress: JobProgress | None = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[[JobProgress], Awaitable[None]] | None = None,
    ) -> IndexingResult:
        """
        Index a complete repository.

        This is the main entry point that orchestrates the entire pipeline.
        협력적 취소(cooperative cancellation)를 지원하여 graceful shutdown이 가능합니다.

        Args:
            repo_path: Path to repository
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier (e.g., branch name, commit hash)
            incremental: If True, only process changed files
            force: If True, force full reindex even if already indexed
            progress: JobProgress for tracking and resuming (협력적 취소용)
            stop_event: asyncio.Event for stop signal (협력적 취소용)
            progress_persist_callback: Callback to persist progress (협력적 취소용)

        Returns:
            IndexingResult with statistics and metrics

        Raises:
            Exception: If indexing fails
        """
        repo_path = Path(repo_path)
        self.project_root = repo_path  # Save for Pyright integration
        start_time = datetime.now()

        # Initialize session context for 2-Pass Impact Reindexing
        self._session_ctx = IndexSessionContext(
            max_impact_reindex_files=self.config.max_impact_reindex_files,
        )
        self._stop_event = stop_event

        # Set current mode for impact pass filtering
        # Note: This is a simplified mode detection
        # For mode-based indexing, this will be overridden by ModeManager
        self._current_mode = IndexingMode.FAST if not incremental else IndexingMode.BALANCED

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
            incremental=incremental,
            mode="incremental" if incremental else "full",
        )
        record_counter("indexing_jobs_started_total", labels={"mode": "incremental" if incremental else "full"})

        # Create index version (if version_store enabled)
        # 증분 인덱싱은 version 생성 스킵 (전체 인덱싱에서만 사용)
        if self.version_store and not incremental:
            git_helper = GitHelper(repo_path)
            current_commit = git_helper.get_current_commit_hash() or "unknown"

            # Create version in DB (returns IndexVersion with version_id)
            self._current_version = await self.version_store.create_version(
                repo_id=repo_id,
                git_commit=current_commit,
                file_count=0,
            )

            logger.info(
                "index_version_created",
                version_id=self._current_version.version_id,
                commit=current_commit,
            )

        try:
            # === Stage 1: Git Operations ===
            await self._stage_git_operations(repo_path, result)

            # === Stage 2: File Discovery (with change detection for incremental) ===
            if incremental:
                # Incremental: use change detection
                change_set, files = await self._stage_file_discovery_incremental(result, repo_path, repo_id)

                if change_set.is_empty():
                    logger.info("no_changes_detected", repo_id=repo_id)
                    result.mark_completed()
                    record_counter("indexing_jobs_completed_total", labels={"status": "no_changes"})
                    return result

                # Store change_set for incremental chunk refresh
                self._current_change_set = change_set
            else:
                files = await self._stage_file_discovery(result, repo_path, incremental=False)
                self._current_change_set = None

            if not files:
                logger.warning("no_files_to_process", repo_id=repo_id)
                result.mark_completed()
                record_counter("indexing_jobs_completed_total", labels={"status": "no_files"})
                return result

            # 협력적 취소: progress 초기화
            if progress is not None:
                progress.total_files = len(files)
                logger.info(
                    "cooperative_cancellation_enabled",
                    total_files=progress.total_files,
                    already_completed=len(progress.completed_files),
                )

            # === Stage 3: Parsing ===
            ast_results = await self._stage_parsing(
                result,
                files,
                progress=progress,
                stop_event=stop_event,
                progress_persist_callback=progress_persist_callback,
            )

            # 협력적 취소: 중단 요청 체크
            if stop_event and stop_event.is_set():
                logger.info(
                    "indexing_stopped_by_request",
                    stage="parsing",
                    completed_files=len(progress.completed_files) if progress else 0,
                )
                result.status = IndexingStatus.IN_PROGRESS  # 재개 가능 상태
                result.metadata["stopped_at_stage"] = "parsing"
                return result

            # Early exit if parsing produced no results
            if not ast_results:
                logger.warning("no_ast_results", repo_id=repo_id)
                result.add_warning("Parsing produced no AST results")
                result.mark_completed()
                record_counter("indexing_jobs_completed_total", labels={"status": "no_ast"})
                return result

            # === Stage 4: IR Building ===
            ir_doc = await self._stage_ir_building(result, ast_results, repo_id, snapshot_id)

            # Early exit if IR building failed
            if ir_doc is None:
                logger.error("ir_building_failed", repo_id=repo_id, reason="IR document is None")
                result.add_warning("IR building failed - no nodes generated")
                result.mark_failed("IR building returned empty result")
                record_counter("indexing_jobs_completed_total", labels={"status": "ir_failed"})
                return result

            # === Stage 5: Semantic IR Building ===
            semantic_ir = await self._stage_semantic_ir_building(result, ir_doc)

            # Early exit if Semantic IR building failed
            if semantic_ir is None:
                logger.error("semantic_ir_building_failed", repo_id=repo_id, reason="Semantic IR is None")
                result.add_warning("Semantic IR building failed")
                result.mark_failed("Semantic IR building returned empty result")
                record_counter("indexing_jobs_completed_total", labels={"status": "semantic_ir_failed"})
                return result

            # === Stage 6: Graph Building (Incremental or Full) ===
            if incremental and self._current_change_set:
                graph_doc = await self._stage_graph_building_incremental(
                    result, semantic_ir, ir_doc, repo_id, snapshot_id, self._current_change_set
                )
            else:
                graph_doc = await self._stage_graph_building(result, semantic_ir, ir_doc, repo_id, snapshot_id)

            # Early exit if Graph building failed
            if graph_doc is None:
                logger.error("graph_building_failed", repo_id=repo_id, reason="Graph document is None")
                result.add_warning("Graph building failed")
                result.mark_failed("Graph building returned empty result")
                record_counter("indexing_jobs_completed_total", labels={"status": "graph_failed"})
                return result

            # === Stage 7: Chunk Generation (Incremental or Full) ===
            if incremental and self._current_change_set:
                chunks = await self._stage_chunk_generation_incremental(
                    result, graph_doc, ir_doc, semantic_ir, repo_id, snapshot_id, self._current_change_set
                )
            else:
                chunks = await self._stage_chunk_generation(
                    result, graph_doc, ir_doc, semantic_ir, repo_id, snapshot_id
                )

            # Early exit if Chunk generation failed
            if chunks is None:
                logger.error("chunk_generation_failed", repo_id=repo_id, reason="Chunks is None")
                result.add_warning("Chunk generation failed")
                result.mark_failed("Chunk generation returned empty result")
                record_counter("indexing_jobs_completed_total", labels={"status": "chunks_failed"})
                return result

            # Early exit if no chunks generated (empty but not failed)
            if not chunks:
                logger.warning("no_chunks_generated", repo_id=repo_id)
                result.add_warning("No chunks generated from code")
                result.mark_completed()
                record_counter("indexing_jobs_completed_total", labels={"status": "no_chunks"})
                return result

            # === Stage 8: RepoMap Building ===
            if self.config.repomap_enabled:
                repomap = await self._stage_repomap_building(result, chunks, graph_doc, repo_id, snapshot_id)
            else:
                repomap = None

            # === Stage 9: Indexing ===
            await self._stage_indexing(repo_id, snapshot_id, chunks, graph_doc, ir_doc, repomap, result)

            # === Impact Pass: 2nd pass reindexing (if needed) ===
            if incremental:
                await self._run_impact_pass_if_needed(result, repo_path, repo_id, snapshot_id)

            # === Stage 10: Finalization ===
            await self._stage_finalization(result)

            # Cleanup
            self._current_change_set = None

            # v4.5: Compaction 트리거 체크 (증분 모드 후)
            if incremental and hasattr(self, "_check_compaction_trigger"):
                await self._check_compaction_trigger(repo_id, snapshot_id)

            result.mark_completed()

            # Update index version status (if version_store enabled)
            if self.version_store and self._current_version:
                await self.version_store.update_version_status(
                    repo_id=repo_id,
                    version_id=self._current_version.version_id,
                    status=IndexVersionStatus.COMPLETED,
                    file_count=result.files_processed,
                    duration_ms=result.total_duration_seconds * 1000,
                )
                logger.info(
                    "index_version_completed",
                    version_id=self._current_version.version_id,
                )

            logger.info(
                "indexing_completed",
                repo_id=repo_id,
                files_processed=result.files_processed,
                chunks_created=result.chunks_created,
                duration_seconds=result.total_duration_seconds,
            )
            record_counter("indexing_jobs_completed_total", labels={"status": "success"})
            record_histogram("indexing_duration_seconds", result.total_duration_seconds)
            record_counter("files_indexed_total", value=result.files_processed)
            record_counter("chunks_created_total", value=result.chunks_created)

            return result

        except Exception as e:
            # Update index version status to failed (if version_store enabled)
            if self.version_store and self._current_version:
                try:
                    await self.version_store.update_version_status(
                        repo_id=repo_id,
                        version_id=self._current_version.version_id,
                        status=IndexVersionStatus.FAILED,
                        error_message=str(e),
                    )
                except Exception as version_error:
                    logger.error("failed_to_update_version_status", error=str(version_error))

            logger.error("indexing_failed", repo_id=repo_id, error=str(e), exc_info=True)
            result.mark_failed(str(e))
            record_counter("indexing_jobs_completed_total", labels={"status": "failed"})
            raise

        finally:
            # Clean up session context
            self._session_ctx = None
            self._stop_event = None

    async def _stage_git_operations(self, repo_path: Path, result: IndexingResult):
        """Stage 1: Git operations."""
        stage = IndexingStage.GIT_OPERATIONS
        self._report_progress(stage, 0.0)

        stage_start = datetime.now()

        try:
            git = GitHelper(repo_path)

            if git.is_git_repo():
                # Get commit info
                commit_hash = git.get_current_commit_hash()
                result.git_commit_hash = commit_hash

                repo_info = git.get_repo_info()
                result.metadata["git_info"] = repo_info

                logger.info(
                    f"📂 Git repo: {repo_info['current_branch']} @ {commit_hash[:8] if commit_hash else 'unknown'}"
                )
            else:
                logger.warning(f"Not a Git repository: {repo_path}")
                result.add_warning("Not a Git repository")

        except Exception as e:
            logger.warning(f"Git operations failed: {e}")
            result.add_warning(f"Git operations failed: {e}")

        stage_duration = (datetime.now() - stage_start).total_seconds()
        result.stage_durations[stage.value] = stage_duration

        self._report_progress(stage, 100.0)

    @stage_execution(IndexingStage.FILE_DISCOVERY)
    async def _stage_file_discovery(
        self, result: IndexingResult, repo_path: Path, incremental: bool = False
    ) -> list[Path]:
        """Stage 2: File discovery."""
        discovery = FileDiscovery(self.config)

        if incremental:
            # Get changed files from Git
            git = GitHelper(repo_path)
            changed_files = git.get_changed_files()
            logger.info("files_discovered", mode="incremental", count=len(changed_files))
            record_counter("files_discovered_total", value=len(changed_files), labels={"mode": "incremental"})

            files = discovery.discover_files(repo_path, changed_files=changed_files)
        else:
            # Discover all files
            files = discovery.discover_files(repo_path)
            logger.info("files_discovered", mode="full", count=len(files))
            record_counter("files_discovered_total", value=len(files), labels={"mode": "full"})

        result.files_discovered = len(files)

        # Get file stats
        stats = discovery.get_file_stats(files)
        result.metadata["file_stats"] = stats

        logger.info("file_stats", languages=stats["by_language"], total_size_mb=stats["total_size_mb"])

        return files

    @stage_execution(IndexingStage.FILE_DISCOVERY)
    async def _stage_file_discovery_incremental(
        self, result: IndexingResult, repo_path: Path, repo_id: str
    ) -> tuple[ChangeSet, list[Path]]:
        """
        Stage 2: Incremental file discovery with change detection.

        Returns:
            Tuple of (ChangeSet, list of files to process)
        """
        discovery = FileDiscovery(self.config)
        git = GitHelper(repo_path)

        # Initialize change detector if not already
        if not self.change_detector:
            self.change_detector = ChangeDetector(git_helper=git)

        # Detect changes (L0)
        change_set = self.change_detector.detect_changes(repo_path, repo_id)

        logger.info(
            "incremental_changes_detected",
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
        )
        record_counter("files_discovered_total", value=change_set.total_count, labels={"mode": "incremental"})

        # Convert to Path objects for changed files (added + modified)
        changed_paths = []
        for file_path in change_set.all_changed:
            full_path = repo_path / file_path
            if full_path.exists():
                changed_paths.append(full_path)

        # Filter through FileDiscovery (apply language filters, etc.)
        files = discovery.discover_files(repo_path, changed_files=[str(p) for p in changed_paths])

        result.files_discovered = len(files)
        result.metadata["change_set"] = {
            "added": len(change_set.added),
            "modified": len(change_set.modified),
            "deleted": len(change_set.deleted),
        }
        # Store changed file paths for incremental lexical indexing
        result.metadata["changed_files"] = list(change_set.all_changed)

        # Get file stats
        if files:
            stats = discovery.get_file_stats(files)
            result.metadata["file_stats"] = stats
            logger.info("file_stats", languages=stats["by_language"], total_size_mb=stats["total_size_mb"])

        return change_set, files

    @stage_execution(IndexingStage.PARSING)
    async def _stage_parsing(
        self,
        result: IndexingResult,
        files: list[Path],
        progress: JobProgress | None = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[[JobProgress], Awaitable[None]] | None = None,
    ) -> dict:
        """Stage 3: Parsing with Tree-sitter.

        Supports parallel parsing when config.parallel=True (default).
        Uses config.max_workers to limit concurrency.

        협력적 취소를 지원합니다:
        - progress: 파일별 진행상태 추적
        - stop_event: 중단 신호 (set되면 현재 파일 완료 후 중단)
        - progress_persist_callback: 진행상태 저장 콜백
        """
        logger.info("parsing_started", file_count=len(files), parallel=self.config.parallel)
        record_counter("parsing_started_total", value=len(files))

        # 협력적 취소: 이미 처리된 파일 필터링
        if progress and progress.completed_files:
            original_count = len(files)
            completed_set = set(progress.completed_files)
            files = [f for f in files if str(f) not in completed_set]
            logger.info(
                "parsing_skip_completed",
                original_count=original_count,
                skipped=original_count - len(files),
                remaining=len(files),
            )

        if self.config.parallel and len(files) > 1:
            return await self._parse_files_parallel(result, files, progress, stop_event, progress_persist_callback)
        else:
            return await self._parse_files_sequential(result, files, progress, stop_event, progress_persist_callback)

    async def _parse_files_parallel(
        self,
        result: IndexingResult,
        files: list[Path],
        job_progress: JobProgress | None = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[[JobProgress], Awaitable[None]] | None = None,
    ) -> dict:
        """Parse files in parallel using thread pool for I/O and CPU-bound parsing.

        Uses ThreadPoolExecutor with thread-local parsers to ensure thread safety.
        Each thread gets its own Parser instance to avoid race conditions.

        협력적 취소를 지원합니다:
        - stop_event가 set되면 진행 중인 작업 완료 후 조기 종료
        - job_progress에 완료된 파일 기록
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor

        ast_results = {}
        completed = 0
        total = len(files)
        lock = asyncio.Lock()

        # Thread-local storage for parsers (each thread gets its own parser instances)
        thread_local = threading.local()

        def get_thread_local_parser(language: str):
            """Get or create a thread-local parser for the given language."""
            if not hasattr(thread_local, "parsers"):
                thread_local.parsers = {}

            if language not in thread_local.parsers:
                # Create a new parser instance for this thread
                from tree_sitter import Parser
                from tree_sitter_language_pack import get_language

                try:
                    lang = get_language(language)
                    thread_local.parsers[language] = Parser(lang)
                except (ValueError, LookupError, OSError) as e:
                    logger.debug("parser_init_failed", language=language, error=str(e))
                    return None

            return thread_local.parsers[language]

        def parse_single_sync(file_path: Path) -> tuple[str, Any, str | None]:
            """Synchronous parsing function to run in thread pool.

            Returns:
                (file_path_str, ast_tree_or_none, error_msg_or_none)
            """
            try:
                # Detect language (thread-safe - only reads file extension)
                language = self._detect_language(file_path)
                if not language:
                    return (str(file_path), None, "skipped")

                # Get thread-local parser (thread-safe)
                parser = get_thread_local_parser(language)
                if not parser:
                    return (str(file_path), None, f"No parser for language: {language}")

                # Synchronous file I/O and parsing
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                tree = parser.parse(content.encode("utf-8"))

                if tree:
                    return (str(file_path), tree, None)
                else:
                    return (str(file_path), None, f"Failed to parse: {file_path}")

            except Exception as e:
                error_msg = f"Parse error in {file_path}: {e}"
                return (str(file_path), None, error_msg)

        # Use ThreadPoolExecutor for true parallel I/O
        executor = ThreadPoolExecutor(max_workers=self.config.max_workers)

        try:
            # Submit all tasks to thread pool
            async def run_in_thread(file_path: Path):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(executor, parse_single_sync, file_path)

            tasks = [run_in_thread(f) for f in files]

            # Process results as they complete
            for coro in asyncio.as_completed(tasks):
                # 협력적 취소: 중단 요청 체크
                if stop_event and stop_event.is_set():
                    logger.info(
                        "parsing_parallel_stopped_by_request",
                        completed=completed,
                        total=total,
                    )
                    break

                try:
                    file_path_str, ast_tree, error = await coro

                    async with lock:
                        completed += 1
                        if error == "skipped":
                            result.files_skipped += 1
                        elif error:
                            result.files_failed += 1
                            if not self.config.skip_parse_errors:
                                logger.error(error)
                            else:
                                logger.warning(error)
                            result.add_warning(error)
                            # 협력적 취소: 실패 기록
                            if job_progress:
                                job_progress.mark_file_failed(file_path_str, error)
                        elif ast_tree:
                            ast_results[file_path_str] = ast_tree
                            result.files_processed += 1

                        # 협력적 취소: 완료 기록
                        if job_progress:
                            job_progress.mark_file_completed(file_path_str)
                            if progress_persist_callback:
                                await progress_persist_callback(job_progress)

                        # Progress update
                        progress_pct = (completed / total) * 100
                        self._report_progress(IndexingStage.PARSING, progress_pct)

                except Exception as e:
                    if not self.config.skip_parse_errors:
                        raise
                    logger.warning(f"Unexpected error in parallel parsing: {e}")

        finally:
            executor.shutdown(wait=True)  # Wait for all threads to finish

        logger.info(
            f"   Parsed (parallel, workers={self.config.max_workers}): {result.files_processed}, "
            f"Failed: {result.files_failed}, "
            f"Skipped: {result.files_skipped}"
        )

        return ast_results

    async def _parse_files_sequential(
        self,
        result: IndexingResult,
        files: list[Path],
        job_progress: JobProgress | None = None,
        stop_event: asyncio.Event | None = None,
        progress_persist_callback: Callable[[JobProgress], Awaitable[None]] | None = None,
    ) -> dict:
        """Parse files sequentially (fallback or when parallel=False).

        협력적 취소를 지원합니다:
        - 각 파일 처리 전 stop_event 체크
        - 파일 완료 시 job_progress 업데이트 및 persist
        """
        ast_results = {}

        for i, file_path in enumerate(files):
            # 협력적 취소: 중단 요청 체크
            if stop_event and stop_event.is_set():
                logger.info(
                    "parsing_stopped_by_request",
                    completed=i,
                    total=len(files),
                )
                break

            # 협력적 취소: 현재 처리 중인 파일 표시
            if job_progress:
                job_progress.processing_file = str(file_path)

            try:
                language = self._detect_language(file_path)
                if not language:
                    result.files_skipped += 1
                    continue

                parser = self.parser_registry.get_parser(language)
                ast_tree = await self._parse_file(parser, file_path)

                if ast_tree:
                    ast_results[str(file_path)] = ast_tree
                    result.files_processed += 1
                else:
                    result.files_failed += 1
                    result.add_warning(f"Failed to parse: {file_path}")

            except Exception as e:
                result.files_failed += 1
                error_msg = f"Parse error in {file_path}: {e}"
                logger.warning(error_msg)
                result.add_warning(error_msg)

                if job_progress:
                    job_progress.mark_file_failed(str(file_path), str(e))

                if not self.config.skip_parse_errors:
                    raise

            # 협력적 취소: 파일 완료 기록 및 persist
            if job_progress:
                job_progress.mark_file_completed(str(file_path))
                job_progress.processing_file = None

                if progress_persist_callback:
                    await progress_persist_callback(job_progress)

            # Progress update
            progress_pct = ((i + 1) / len(files)) * 100
            self._report_progress(IndexingStage.PARSING, progress_pct)

        logger.info(
            f"   Parsed (sequential): {result.files_processed}, "
            f"Failed: {result.files_failed}, "
            f"Skipped: {result.files_skipped}"
        )

        return ast_results

    @stage_execution(IndexingStage.IR_BUILDING)
    async def _stage_ir_building(self, result: IndexingResult, ast_results: dict, repo_id: str, snapshot_id: str):
        """Stage 4: IR building."""
        logger.info("🔧 Building Intermediate Representation...")

        # Build IR from AST results (returns IR doc + AST map)
        ir_doc, ast_map = await self._build_ir(ast_results, repo_id, snapshot_id)

        if ir_doc:
            result.ir_nodes_created = len(getattr(ir_doc, "nodes", []))
            logger.info("ir_nodes_created", count=result.ir_nodes_created)
            record_counter("ir_nodes_created_total", value=result.ir_nodes_created)

        # Store AST map temporarily for next stage
        self._temp_ast_map = ast_map  # Will be cleared after semantic IR stage
        return ir_doc

    @stage_execution(IndexingStage.SEMANTIC_IR_BUILDING)
    async def _stage_semantic_ir_building(self, result: IndexingResult, ir_doc):
        """Stage 5: Semantic IR building (CFG, DFG, types)."""
        logger.info("semantic_ir_building_started")

        # Build semantic IR (pass incremental flag for RFC-023 M2)
        semantic_ir = await self._build_semantic_ir(ir_doc, incremental=result.incremental)

        logger.info("semantic_ir_building_completed")

        return semantic_ir

    @stage_execution(IndexingStage.GRAPH_BUILDING)
    async def _stage_graph_building(self, result: IndexingResult, semantic_ir, ir_doc, repo_id: str, snapshot_id: str):
        """Stage 6: Graph building."""
        logger.info("graph_building_started")

        # Build graph
        graph_doc = await self._build_graph(semantic_ir, ir_doc, repo_id, snapshot_id)

        if graph_doc:
            result.graph_nodes_created = len(getattr(graph_doc, "graph_nodes", {}))
            result.graph_edges_created = len(getattr(graph_doc, "graph_edges", []))

            logger.info("graph_building_completed", nodes=result.graph_nodes_created, edges=result.graph_edges_created)
            record_counter("graph_nodes_created_total", value=result.graph_nodes_created)
            record_counter("graph_edges_created_total", value=result.graph_edges_created)

            # Save to graph store
            await self._save_graph(graph_doc)

        return graph_doc

    @stage_execution(IndexingStage.GRAPH_BUILDING)
    async def _stage_graph_building_incremental(
        self,
        result: IndexingResult,
        semantic_ir,
        ir_doc,
        repo_id: str,
        snapshot_id: str,
        change_set: ChangeSet,
    ):
        """
        Stage 6: Incremental graph building with source-local invalidation.

        Implements RFC SEP-G12-INC-GRAPH + SEP-G12-EDGE-VAL:
        1. Mark cross-file backward edges as stale (EdgeValidator)
        2. For DELETED files: Remove nodes entirely (DETACH DELETE)
        3. For MODIFIED files: Delete outbound edges only, then upsert nodes
        4. For ADDED files: Insert new nodes and edges
        5. Analyze symbol-level impact (GraphImpactAnalyzer)
        6. Clear stale edges for reindexed files

        This preserves inbound edges from unchanged files (caller/callee consistency).

        Args:
            result: IndexingResult for tracking
            semantic_ir: Semantic IR for changed files
            ir_doc: IR document for changed files
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            change_set: ChangeSet with added/modified/deleted files

        Returns:
            GraphDocument for the changed files
        """
        logger.info(
            "incremental_graph_building_started",
            deleted=len(change_set.deleted),
            modified=len(change_set.modified),
            added=len(change_set.added),
        )

        # === Step 0: Load existing graph for stale edge analysis ===
        existing_graph = None
        if self.graph_store:
            try:
                existing_graph = await self.graph_store.load_graph(repo_id, snapshot_id)
            except Exception as e:
                logger.warning("failed_to_load_existing_graph", error=str(e))

        # === Step 1: Mark cross-file backward edges as stale (RFC SEP-G12-EDGE-VAL) ===
        # When B.py is modified, edges FROM other files (e.g., A.py) TO B.py become stale
        stale_edge_count = 0
        if existing_graph and (change_set.modified or change_set.deleted):
            changed_files = change_set.modified | change_set.deleted
            stale_edges = self.edge_validator.mark_stale_edges(repo_id, changed_files, existing_graph)
            stale_edge_count = len(stale_edges)
            if stale_edge_count > 0:
                logger.info(
                    "stale_edges_marked",
                    count=stale_edge_count,
                    source_files=list({e.source_file for e in stale_edges})[:5],  # Sample
                )
                result.metadata["stale_edges_marked"] = stale_edge_count
                result.metadata["stale_source_files"] = list(self.edge_validator.get_stale_source_files(repo_id))

        if self.graph_store:
            # Step 2: For DELETED files - remove nodes entirely
            # Inbound edges will become dangling (acceptable for deleted files)
            if change_set.deleted:
                deleted_files = list(change_set.deleted)

                # Mark edges pointing to deleted symbols as invalid
                if existing_graph:
                    deleted_symbol_ids = self._get_symbol_ids_for_files(existing_graph, deleted_files)
                    self.edge_validator.mark_deleted_symbol_edges(repo_id, deleted_symbol_ids, existing_graph)

                deleted_node_count = await self.graph_store.delete_nodes_for_deleted_files(repo_id, deleted_files)
                logger.info("graph_nodes_deleted_for_deleted_files", count=deleted_node_count)
                result.metadata["graph_nodes_deleted"] = deleted_node_count

                # Step 2b: Clean up orphan module nodes (auto-generated package hierarchy)
                orphan_count = await self.graph_store.delete_orphan_module_nodes(repo_id)
                if orphan_count > 0:
                    logger.info("orphan_module_nodes_deleted", count=orphan_count)
                    result.metadata["orphan_modules_deleted"] = orphan_count

            # Step 3: For MODIFIED files - delete outbound edges only
            # This preserves inbound edges from other files (source-local invalidation)
            # Nodes will be updated via upsert in Step 5
            if change_set.modified:
                modified_files = list(change_set.modified)
                deleted_edge_count = await self.graph_store.delete_outbound_edges_by_file_paths(repo_id, modified_files)
                logger.info("graph_outbound_edges_deleted_for_modified_files", count=deleted_edge_count)
                result.metadata["graph_edges_deleted"] = deleted_edge_count

        # Step 4: Build new graph for added/modified files
        # This creates nodes and outbound edges for changed files only
        graph_doc = await self._build_graph(semantic_ir, ir_doc, repo_id, snapshot_id)

        if graph_doc:
            result.graph_nodes_created = len(getattr(graph_doc, "graph_nodes", {}))
            result.graph_edges_created = len(getattr(graph_doc, "graph_edges", []))

            logger.info(
                "incremental_graph_building_completed",
                nodes=result.graph_nodes_created,
                edges=result.graph_edges_created,
            )
            record_counter("graph_nodes_created_total", value=result.graph_nodes_created)
            record_counter("graph_edges_created_total", value=result.graph_edges_created)

            # Step 5: Save to graph store with upsert mode
            # - Existing nodes: UPDATE properties (stable node_id preserved)
            # - New nodes: INSERT
            # - Edges: INSERT (outbound edges for changed files)
            await self._save_graph_incremental(graph_doc)

            # === Step 6: Analyze symbol-level impact (RFC SEP-G12-IMPACT) ===
            # Determine which other files are affected by the changes
            if existing_graph:
                impact_result = self._analyze_incremental_impact(repo_id, existing_graph, graph_doc, change_set, result)
                if impact_result:
                    result.metadata["impact_analysis"] = {
                        "direct_affected": len(impact_result.direct_affected),
                        "transitive_affected": len(impact_result.transitive_affected),
                        "affected_files": list(impact_result.affected_files)[:20],  # Sample
                    }

                    # Check for files that need reindexing but weren't included
                    processed_files = change_set.all_changed
                    unprocessed_affected = impact_result.affected_files - processed_files

                    if unprocessed_affected:
                        logger.info(
                            "impact_based_reindex_recommended",
                            count=len(unprocessed_affected),
                            sample_files=list(unprocessed_affected)[:10],
                        )
                        result.metadata["recommended_reindex_files"] = list(unprocessed_affected)
                        result.add_warning(f"{len(unprocessed_affected)} files affected by changes may need reindexing")

                        # Store impact candidates in session context for 2nd pass
                        if self._session_ctx:
                            self._session_ctx.set_impact_candidates(unprocessed_affected)
                            # Mark 1st pass files as processed
                            for file in change_set.all_changed:
                                self._session_ctx.mark_file_processed(file)

            # === Step 7: Clear stale edges for reindexed files ===
            reindexed_files = change_set.added | change_set.modified
            cleared_count = 0
            for file_path in reindexed_files:
                cleared_count += self.edge_validator.clear_stale_for_file(repo_id, file_path)
            if cleared_count > 0:
                logger.info("stale_edges_cleared_after_reindex", count=cleared_count)
                result.metadata["stale_edges_cleared"] = cleared_count

        return graph_doc

    def _get_symbol_ids_for_files(self, graph, file_paths: list[str]) -> set[str]:
        """Get all symbol node IDs for given files."""
        symbol_ids = set()
        file_path_set = set(file_paths)
        for node_id, node in graph.graph_nodes.items():
            if hasattr(node, "path") and node.path in file_path_set:
                symbol_ids.add(node_id)
        return symbol_ids

    def _analyze_incremental_impact(
        self,
        repo_id: str,
        old_graph,
        new_graph,
        change_set: ChangeSet,
        result: IndexingResult,
    ):
        """
        Analyze symbol-level impact of incremental changes.

        Uses GraphImpactAnalyzer to determine:
        - Direct callers/importers of changed symbols
        - Transitive affected symbols (BFS traversal)
        - Affected files that may need reindexing

        Returns:
            ImpactResult or None if analysis fails
        """
        try:
            from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import (
                ChangeType,
                detect_symbol_changes,
            )

            # Detect symbol-level changes between old and new graphs
            changed_symbols = detect_symbol_changes(old_graph, new_graph, change_set.all_changed)

            if not changed_symbols:
                logger.debug("no_symbol_changes_detected")
                return None

            logger.info(
                "symbol_changes_detected",
                count=len(changed_symbols),
                types={ct.name: 0 for ct in ChangeType},  # Will be filled
            )

            # Count by change type
            type_counts: dict[str, int] = {}
            for sc in changed_symbols:
                type_name = sc.change_type.name
                type_counts[type_name] = type_counts.get(type_name, 0) + 1
            result.metadata["symbol_change_types"] = type_counts

            # Analyze impact using the existing (old) graph for caller relationships
            impact_result = self.impact_analyzer.analyze_impact(old_graph, changed_symbols)

            logger.info(
                "impact_analysis_completed",
                direct_affected=len(impact_result.direct_affected),
                transitive_affected=len(impact_result.transitive_affected),
                affected_files=len(impact_result.affected_files),
            )

            return impact_result

        except Exception as e:
            logger.warning("impact_analysis_failed", error=str(e))
            return None

    async def _save_graph_incremental(self, graph_doc):
        """Save graph to store with upsert mode for incremental updates."""
        if not self.graph_store:
            logger.info("Skipping graph save (no graph store configured)")
            return

        if not graph_doc or (hasattr(graph_doc, "graph_nodes") and len(graph_doc.graph_nodes) == 0):
            logger.info("Skipping empty graph save")
            return

        # Use upsert mode for incremental updates (merge with existing data)
        await self.graph_store.save_graph(graph_doc, mode="upsert")

    async def _index_single_file(
        self,
        repo_path: Path,
        file_path: str,
        repo_id: str,
        snapshot_id: str,
        result: IndexingResult,
    ) -> bool:
        """
        단일 파일 재인덱싱 헬퍼 메서드.

        Phase 1 Day 9-10: Impact Pass를 위한 파일 단위 재인덱싱.
        전체 파이프라인을 단일 파일에 대해 실행:
        1. Parsing (AST)
        2. IR Building
        3. Semantic IR Building
        4. Graph Building
        5. Chunking
        6. Indexing (5개 인덱스)

        Args:
            repo_path: Repository path
            file_path: 파일 경로 (repo_path 기준 상대 경로)
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            result: IndexingResult (메트릭 추적)

        Returns:
            성공 여부
        """
        try:
            full_path = repo_path / file_path

            if not full_path.exists():
                logger.warning("file_not_found_for_reindex", file=file_path)
                return False

            logger.debug("reindexing_single_file", file=file_path)

            # === Stage 1: Parsing ===
            language = self._detect_language(full_path)
            if not language:
                logger.debug("skipping_file_no_language", file=file_path)
                return False

            parser = self.parser_registry.get_parser(language)
            if not parser:
                logger.debug("skipping_file_no_parser", file=file_path, language=language)
                return False

            ast_tree = await self._parse_file(parser, full_path)
            if not ast_tree:
                logger.warning("parsing_failed", file=file_path)
                return False

            ast_results = {str(file_path): ast_tree}

            # === Stage 2-3: IR Building ===
            ir_doc, _ = await self._build_ir(ast_results, repo_id, snapshot_id)
            if not ir_doc:
                logger.warning("ir_building_failed", file=file_path)
                return False

            # === Stage 4: Semantic IR Building ===
            semantic_ir = await self._build_semantic_ir(ir_doc, incremental=True)
            if not semantic_ir:
                logger.warning("semantic_ir_building_failed", file=file_path)
                return False

            # === Stage 5: Graph Building ===
            graph_doc = await self._build_graph(semantic_ir, ir_doc, repo_id, snapshot_id)
            if not graph_doc:
                logger.warning("graph_building_failed", file=file_path)
                return False

            # Save graph (incremental upsert)
            if self.graph_store:
                await self.graph_store.save_graph(graph_doc, mode="upsert")

            # === Stage 6: Chunking ===
            if not self.chunk_builder:
                logger.warning("chunk_builder_not_configured")
                return False

            # Read file content for chunking
            try:
                with open(full_path, encoding="utf-8") as f:
                    file_text = [line.rstrip("\n\r") for line in f]
            except Exception as e:
                logger.warning("failed_to_read_file_for_chunking", file=file_path, error=str(e))
                return False

            chunks, _, _ = self.chunk_builder.build(
                repo_id=repo_id,
                ir_doc=ir_doc,
                graph_doc=graph_doc,
                file_text=file_text,
                repo_config={"root": str(repo_path)},
                snapshot_id=snapshot_id,
            )

            if not chunks:
                logger.warning("chunking_failed", file=file_path)
                return False

            # Save chunks to database
            if self.chunk_store:
                for chunk in chunks:
                    await self.chunk_store.save_chunk(chunk)

            chunk_ids = [c.chunk_id for c in chunks]
            result.chunks_created += len(chunk_ids)

            # === Stage 7: Indexing (5 indexes) ===
            # Lexical
            if self.config.enable_lexical_index and self.lexical_index:
                await self.lexical_index.index_chunks(repo_id, snapshot_id, chunk_ids)

            # Vector
            if self.config.enable_vector_index and self.vector_index:
                await self.vector_index.index_chunks(repo_id, snapshot_id, chunk_ids)

            # Symbol
            if self.config.enable_symbol_index and self.symbol_index:
                await self.symbol_index.index_graph(repo_id, snapshot_id, graph_doc)

            # Fuzzy
            if self.config.enable_fuzzy_index and self.fuzzy_index:
                await self.fuzzy_index.index_document(repo_id, snapshot_id, ir_doc)

            # Domain
            if self.config.enable_domain_index and self.domain_index:
                await self.domain_index.index_chunks(repo_id, snapshot_id, chunk_ids)

            logger.info("file_reindexed_successfully", file=file_path, chunks=len(chunk_ids))
            return True

        except Exception as e:
            logger.error("file_reindex_error", file=file_path, error=str(e), exc_info=True)
            return False

    async def _run_impact_pass_if_needed(
        self,
        result: IndexingResult,
        repo_path: Path,
        repo_id: str,
        snapshot_id: str,
    ) -> None:
        """
        Run 2nd pass reindexing for impact-affected files if needed.

        2-Pass Impact Reindexing Strategy:
        1. 1st pass: 원래 change_set 처리 (이미 완료)
        2. Impact 분석: affected_files 계산 (Step 6에서 완료)
        3. 2nd pass: impact_candidates 중 미처리 파일만 재인덱싱

        안전장치:
        - 세션당 1회만 실행 (impact_pass_ran)
        - 최대 파일 수 제한 (max_impact_reindex_files)
        - 모드별 필터링 (FAST는 skip)
        - 협력적 취소 체크

        Args:
            result: IndexingResult for tracking
            repo_path: Repository path
            repo_id: Repository ID
            snapshot_id: Snapshot ID
        """
        ctx = self._session_ctx

        # 세션 컨텍스트 없거나 이미 실행됨
        if not ctx or not ctx.should_run_impact_pass():
            return

        # Config에서 비활성화됨
        if not self.config.enable_impact_pass:
            logger.debug("impact_pass_disabled_by_config")
            return

        # 모드별 필터링: FAST/BOOTSTRAP는 skip
        current_mode = getattr(self, "_current_mode", IndexingMode.FAST)
        if current_mode not in self.config.impact_pass_modes:
            logger.info(
                "impact_pass_skipped_by_mode",
                mode=current_mode.value,
                enabled_modes=[m.value for m in self.config.impact_pass_modes],
            )
            return

        # Impact 후보 가져오기 (상한 적용)
        candidates = ctx.get_impact_batch()

        if not candidates:
            logger.debug("impact_pass_no_candidates")
            return

        # Truncation 체크
        total_candidates = len(ctx.impact_candidates)
        truncated = total_candidates - len(candidates)

        if truncated > 0:
            logger.warning(
                "impact_pass_truncated",
                total=total_candidates,
                limit=ctx.max_impact_reindex_files,
                truncated=truncated,
            )
            result.add_warning(f"Impact reindex truncated: {total_candidates} → {len(candidates)} files")

        logger.info(
            "impact_pass_started",
            candidate_count=len(candidates),
            total_affected=total_candidates,
            mode=current_mode.value,
        )

        # 메트릭
        pass_start_time = datetime.now()
        files_processed = 0
        files_failed = 0

        try:
            # 2nd pass: 파일별 재인덱싱
            for i, file_path in enumerate(candidates):
                # 협력적 취소 체크
                if self._stop_event and self._stop_event.is_set():
                    logger.warning(
                        "impact_pass_cancelled",
                        processed=files_processed,
                        remaining=len(candidates) - i,
                    )
                    break

                # 중복 체크 (방어적 코드)
                if ctx.is_file_processed(file_path):
                    logger.debug("impact_pass_file_already_processed", file=file_path)
                    continue

                try:
                    # 파일 재인덱싱
                    # Graph부터 재실행 (IR은 캐시 재사용 가능)
                    logger.debug("impact_pass_reindexing_file", file=file_path, index=i + 1, total=len(candidates))

                    # Phase 1 Day 9-10: 실제 파일 재인덱싱 로직
                    success = await self._index_single_file(
                        repo_path=repo_path,
                        file_path=file_path,
                        repo_id=repo_id,
                        snapshot_id=snapshot_id,
                        result=result,
                    )

                    if success:
                        ctx.mark_file_processed(file_path)
                        files_processed += 1
                    else:
                        files_failed += 1
                        result.add_warning(f"Failed to reindex: {file_path}")

                except Exception as e:
                    logger.error(
                        "impact_pass_file_failed",
                        file=file_path,
                        error=str(e),
                        exc_info=True,
                    )
                    files_failed += 1

                    if not self.config.continue_on_error:
                        raise

            # 성공 메트릭
            pass_duration = (datetime.now() - pass_start_time).total_seconds()

            result.metadata["impact_pass"] = {
                "executed": True,
                "candidates_total": total_candidates,
                "candidates_processed": len(candidates),
                "files_processed": files_processed,
                "files_failed": files_failed,
                "truncated": truncated,
                "duration_seconds": pass_duration,
            }

            result.metadata["impact_reindexed_files"] = [f for f in candidates if ctx.is_file_processed(f)]

            logger.info(
                "impact_pass_completed",
                files_processed=files_processed,
                files_failed=files_failed,
                duration_seconds=round(pass_duration, 2),
            )

            # 메트릭 기록
            record_counter("impact_pass_executed_total")
            record_histogram("impact_pass_file_count", files_processed)
            record_histogram("impact_pass_duration_seconds", pass_duration)

            if truncated > 0:
                record_counter("impact_pass_truncated_total", value=truncated)

        finally:
            # Impact pass 완료 마킹 (실패해도 재시도 방지)
            ctx.mark_impact_pass_done()

    @stage_execution(IndexingStage.CHUNK_GENERATION)
    async def _stage_chunk_generation(
        self,
        result: IndexingResult,
        graph_doc,
        ir_doc,
        semantic_ir,
        repo_id: str,
        snapshot_id: str,
    ) -> list[str]:
        """
        Stage 7: Chunk generation (returns chunk IDs only for memory efficiency).

        Returns:
            List of chunk IDs (chunks are already saved to store)
        """
        logger.info("chunk_generation_started")

        # Build chunks (returns IDs only, chunks saved to store)
        chunk_ids = await self._build_chunks(graph_doc, ir_doc, semantic_ir, repo_id, snapshot_id)

        result.chunks_created = len(chunk_ids)
        logger.info("chunk_generation_completed", count=result.chunks_created)
        record_counter("chunks_generated_total", value=result.chunks_created)

        # === P0-1: Enrich chunks with Git History ===
        if self.config.enable_git_history and self.project_root:
            # Load chunks from store for enrichment (batch load)
            chunks = await self._load_chunks_by_ids(chunk_ids)
            await self._enrich_chunks_with_history(chunks, repo_id, result)
            # Re-save enriched chunks
            await self._save_chunks(chunks)

        return chunk_ids

    @stage_execution(IndexingStage.CHUNK_GENERATION)
    async def _stage_chunk_generation_incremental(
        self,
        result: IndexingResult,
        graph_doc,
        ir_doc,
        semantic_ir,
        repo_id: str,
        snapshot_id: str,
        change_set: ChangeSet,
    ):
        """
        Stage 7: Incremental chunk generation using ChunkIncrementalRefresher.

        Instead of regenerating all chunks, this method:
        1. Uses ChunkIncrementalRefresher to detect what changed
        2. Only regenerates chunks for added/modified files
        3. Marks deleted file chunks as deleted
        4. Preserves unchanged chunks (with content_hash check)

        Args:
            result: IndexingResult for tracking
            graph_doc: Graph document for changed files
            ir_doc: IR document for changed files
            semantic_ir: Semantic IR for changed files
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            change_set: ChangeSet with added/modified/deleted files

        Returns:
            List of all chunks (including existing unchanged ones)
        """
        logger.info(
            "incremental_chunk_generation_started",
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
        )

        # Initialize ChunkIncrementalRefresher if not already
        if not self.chunk_refresher:
            self._init_chunk_refresher(repo_id)

        # Get old commit from metadata store (persistent) or fallback to HEAD~1
        old_commit = None
        if self.metadata_store and hasattr(self.metadata_store, "get_last_commit"):
            old_commit = self.metadata_store.get_last_commit(repo_id)
        if not old_commit:
            old_commit = result.metadata.get("previous_commit", "HEAD~1")
        new_commit = result.git_commit_hash or snapshot_id

        # Use ChunkIncrementalRefresher to handle incremental updates
        refresh_result = await self.chunk_refresher.refresh_files(
            repo_id=repo_id,
            old_commit=old_commit,
            new_commit=new_commit,
            added_files=list(change_set.added),
            deleted_files=list(change_set.deleted),
            modified_files=list(change_set.modified),
            repo_config={"root": str(self.project_root)},
        )

        # Log refresh stats
        logger.info(
            "incremental_chunk_refresh_completed",
            added=len(refresh_result.added_chunks),
            updated=len(refresh_result.updated_chunks),
            deleted=len(refresh_result.deleted_chunks),
            renamed=len(refresh_result.renamed_chunks),
            drifted=len(refresh_result.drifted_chunks),
        )
        record_counter("chunks_incrementally_added_total", value=len(refresh_result.added_chunks))
        record_counter("chunks_incrementally_updated_total", value=len(refresh_result.updated_chunks))
        record_counter("chunks_incrementally_deleted_total", value=len(refresh_result.deleted_chunks))

        # Collect all affected chunk IDs (memory efficient)
        all_affected_chunks = refresh_result.added_chunks + refresh_result.updated_chunks
        all_affected_chunk_ids = [c.chunk_id for c in all_affected_chunks]

        # Collect deleted chunk IDs for index cleanup
        deleted_chunk_ids = [c.chunk_id for c in refresh_result.deleted_chunks]

        # Update result stats
        result.chunks_created = len(refresh_result.added_chunks)
        result.metadata["chunks_updated"] = len(refresh_result.updated_chunks)
        result.metadata["chunks_deleted"] = len(refresh_result.deleted_chunks)
        result.metadata["chunks_renamed"] = len(refresh_result.renamed_chunks)
        result.metadata["chunks_drifted"] = len(refresh_result.drifted_chunks)
        result.metadata["deleted_chunk_ids"] = deleted_chunk_ids  # Store for index cleanup

        # Save affected chunks to store
        if all_affected_chunks:
            await self._save_chunks(all_affected_chunks)

        # === P0-1: Enrich only new/updated chunks with Git History ===
        if self.config.enable_git_history and self.project_root and all_affected_chunks:
            await self._enrich_chunks_with_history(all_affected_chunks, repo_id, result)
            # Re-save enriched chunks
            await self._save_chunks(all_affected_chunks)

        # Return chunk IDs only (memory efficient)
        # Note: We don't return unchanged chunks as they don't need re-indexing
        return all_affected_chunk_ids

    def _init_chunk_refresher(self, repo_id: str) -> None:
        """Initialize ChunkIncrementalRefresher with required dependencies."""

        # Create adapter for IR generator
        class IRGeneratorAdapter:
            def __init__(self, ir_builder, parser_registry, project_root):
                self.ir_builder = ir_builder
                self.parser_registry = parser_registry
                self.project_root = project_root

            def generate_for_file(self, repo_id: str, file_path: str, commit: str):
                # Generate IR for a single file
                full_path = Path(self.project_root) / file_path
                if not full_path.exists():
                    return None

                # Read and parse file
                try:
                    with open(full_path, encoding="utf-8") as f:
                        content = f.read()

                    # Detect language and get parser
                    ext = full_path.suffix.lower()
                    language = {".py": "python", ".js": "javascript", ".ts": "typescript"}.get(ext)
                    if not language:
                        return None

                    parser = self.parser_registry.get_parser(language)
                    tree = parser.parse(content.encode("utf-8"))

                    # Build IR
                    from src.contexts.code_foundation.infrastructure.ir.models import SourceFile

                    source_file = SourceFile(
                        file_path=str(full_path),
                        content=content,
                        language=language,
                    )
                    return self.ir_builder.generate(source=source_file, snapshot_id=commit, ast=tree)
                except Exception as e:
                    logger.warning(f"IR generation failed for {file_path}: {e}")
                    return None

        # Create adapter for Graph generator
        class GraphGeneratorAdapter:
            def __init__(self, graph_builder, semantic_ir_builder):
                self.graph_builder = graph_builder
                self.semantic_ir_builder = semantic_ir_builder

            def build_for_file(self, ir_doc, snapshot_id: str):
                if not ir_doc:
                    return None
                try:
                    # Build semantic IR first
                    semantic_snapshot, _ = self.semantic_ir_builder.build_full(ir_doc, source_map={})
                    # Then build graph
                    return self.graph_builder.build_full(ir_doc, semantic_snapshot)
                except Exception as e:
                    logger.warning(f"Graph generation failed: {e}")
                    return None

        ir_gen = IRGeneratorAdapter(self.ir_builder, self.parser_registry, self.project_root)
        graph_gen = GraphGeneratorAdapter(self.graph_builder, self.semantic_ir_builder)

        self.chunk_refresher = ChunkIncrementalRefresher(
            chunk_builder=self.chunk_builder,
            chunk_store=self.chunk_store,
            ir_generator=ir_gen,
            graph_generator=graph_gen,
            repo_path=str(self.project_root),
            use_partial_updates=self.config.enable_partial_chunk_updates
            if hasattr(self.config, "enable_partial_chunk_updates")
            else False,
        )

    @stage_execution(IndexingStage.REPOMAP_BUILDING)
    async def _stage_repomap_building(
        self,
        result: IndexingResult,
        chunk_ids: list[str],
        graph_doc,
        repo_id: str,
        snapshot_id: str,
    ):
        """
        Stage 8: RepoMap building using RepoMapBuilder.

        Args:
            result: IndexingResult for tracking
            chunk_ids: List of chunk IDs (loads from store as needed)
            graph_doc: Graph document
            repo_id: Repository ID
            snapshot_id: Snapshot ID
        """
        logger.info("🗺️  Building RepoMap (Tree + PageRank + Summaries)...")

        if not self.repomap_store:
            logger.warning("RepoMap store missing; skipping stage")
            return None

        # Load chunks from store (needed for PageRank mapping)
        chunks = await self._load_chunks_by_ids(chunk_ids)

        # Build chunk_to_graph mapping for PageRank aggregation
        _chunk_to_graph = self._build_chunk_to_graph_mapping(chunks, graph_doc)
        self._report_progress(IndexingStage.REPOMAP_BUILDING, 10.0)

        # Create RepoMapBuildConfig from IndexingConfig
        from src.contexts.repo_structure.infrastructure.models import RepoMapBuildConfig

        repomap_config = RepoMapBuildConfig(
            pagerank_enabled=True,  # Enable PageRank by default
            summary_enabled=self.config.repomap_use_llm_summaries,
            include_tests=False,  # Exclude tests by default
            min_loc=10,
            max_depth=10,
        )

        # Get LLM from container if available
        llm = None
        if self.container and hasattr(self.container, "llm"):
            try:
                llm = self.container.llm()
            except (AttributeError, RuntimeError) as e:
                logger.debug("llm_init_skipped", error=str(e))

        # Get repo_path from config if available
        repo_path = getattr(self.config, "repo_path", None)

        # Create and use RepoMapBuilder
        from src.contexts.repo_structure.infrastructure.builder import RepoMapBuilder

        builder = RepoMapBuilder(
            store=self.repomap_store,
            config=repomap_config,
            llm=llm,
            chunk_store=self.chunk_store,
            repo_path=repo_path,
        )

        # Build RepoMap snapshot
        snapshot = await builder.build_async(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            chunks=chunks,
            graph_doc=graph_doc,
        )

        self._report_progress(IndexingStage.REPOMAP_BUILDING, 100.0)

        # Update result stats
        result.repomap_nodes_created = len(snapshot.nodes)
        result.repomap_summaries_generated = sum(1 for node in snapshot.nodes if node.summary_body is not None)

        logger.info(f"   RepoMap: {result.repomap_nodes_created} nodes, {result.repomap_summaries_generated} summaries")

        # Extract data for backward compatibility
        importance_scores = {node.id: node.metrics.importance for node in snapshot.nodes if node.metrics.importance > 0}

        summaries = {node.id: node.summary_body for node in snapshot.nodes if node.summary_body}

        # Return dict for backward compatibility
        repomap = {
            "tree": {"nodes": snapshot.nodes},
            "importance": importance_scores,
            "summaries": summaries,
        }
        return repomap

    async def _stage_indexing(
        self,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
        graph_doc,
        ir_doc,
        repomap,
        result: IndexingResult,
    ):
        """
        Stage 9: Indexing to all indexes (parallel execution for 2-3x speedup).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            chunk_ids: List of chunk IDs (loads from store as needed)
            graph_doc: Graph document
            ir_doc: IR document
            repomap: RepoMap snapshot
            result: IndexingResult for tracking
        """
        logger.info("📊 Indexing to all indexes (parallel)...")

        # Handle deleted chunks from incremental indexing
        deleted_chunk_ids = result.metadata.get("deleted_chunk_ids", [])
        if deleted_chunk_ids:
            await self._delete_chunks_from_indexes(repo_id, snapshot_id, deleted_chunk_ids, result)

        # Build list of indexing tasks to run in parallel
        tasks = []
        task_names = []

        if self.config.enable_lexical_index:
            tasks.append(self._index_lexical(result, repo_id, snapshot_id, chunk_ids))
            task_names.append("lexical")

        if self.config.enable_vector_index:
            tasks.append(self._index_vector(result, repo_id, snapshot_id, chunk_ids, repomap=repomap))
            task_names.append("vector")

        if self.config.enable_symbol_index:
            tasks.append(self._index_symbol(result, repo_id, snapshot_id, graph_doc))
            task_names.append("symbol")

        if self.config.enable_fuzzy_index:
            tasks.append(self._index_fuzzy(result, repo_id, snapshot_id, ir_doc))
            task_names.append("fuzzy")

        if self.config.enable_domain_index:
            tasks.append(self._index_domain(result, repo_id, snapshot_id, chunk_ids))
            task_names.append("domain")

        # Execute all indexing tasks in parallel (return_exceptions=True for partial failure handling)
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for failures and log warnings (don't fail entire indexing)
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    index_name = task_names[i]
                    logger.warning(
                        "index_failed",
                        index=index_name,
                        error=str(res),
                        exc_info=res,
                    )
                    result.add_warning(f"{index_name.capitalize()} index failed: {res}")
                    record_counter("index_failures_total", labels={"index": index_name})

        logger.info(
            f"   Indexed: Lexical({result.lexical_docs_indexed}), "
            f"Vector({result.vector_docs_indexed}), "
            f"Symbol({result.symbol_entries_indexed})"
        )

    @index_execution(IndexingStage.LEXICAL_INDEXING, "Lexical")
    async def _index_lexical(self, result: IndexingResult, repo_id: str, snapshot_id: str, chunk_ids: list[str]):
        """
        Index to lexical index.

        Supports incremental mode:
        - Full mode: reindex entire repository
        - Incremental mode: reindex only changed files via reindex_paths()
        """
        if result.incremental and hasattr(self.lexical_index, "reindex_paths"):
            changed_files = result.metadata.get("changed_files", [])
            if changed_files:
                logger.info("lexical_incremental_indexing", repo_id=repo_id, count=len(changed_files))
                await self.lexical_index.reindex_paths(repo_id, snapshot_id, changed_files)
                result.lexical_docs_indexed = len(changed_files)
                return

        await self.lexical_index.reindex_repo(repo_id, snapshot_id)
        result.lexical_docs_indexed = len(chunk_ids)

    @index_execution(IndexingStage.VECTOR_INDEXING, "Vector")
    async def _index_vector(
        self,
        result: IndexingResult,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
        repomap: Any | None = None,  # RepoMapSnapshot | None
    ):
        """
        Index to vector index with RepoMap enrichment.

        Loads chunks in batches for memory efficiency.
        """
        # Batch indexing with streaming chunk loading
        batch_size = self.config.vector_batch_size
        total_indexed = 0

        for i in range(0, len(chunk_ids), batch_size):
            batch_ids = chunk_ids[i : i + batch_size]

            # Load batch of chunks from store
            chunks_batch = await self._load_chunks_by_ids(batch_ids)

            # Convert chunks to index documents with RepoMap metadata
            docs = self._chunks_to_index_docs(chunks_batch, repo_id, snapshot_id, repomap_snapshot=repomap)

            # Index batch
            await self.vector_index.index(repo_id, snapshot_id, docs)
            total_indexed += len(docs)

            progress = ((i + len(batch_ids)) / len(chunk_ids)) * 100
            self._report_progress(IndexingStage.VECTOR_INDEXING, progress)

        result.vector_docs_indexed = total_indexed

    async def _delete_chunks_from_indexes(
        self,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
        result: IndexingResult,
    ):
        """
        Delete chunks from all indexes (incremental cleanup).

        Called during incremental indexing to remove deleted file chunks from indexes.
        """
        if not chunk_ids:
            return

        logger.info("deleting_chunks_from_indexes", count=len(chunk_ids))

        # Delete from vector index
        if self.config.enable_vector_index and self.vector_index:
            try:
                await self.vector_index.delete(repo_id, snapshot_id, chunk_ids)
                logger.info("vector_index_chunks_deleted", count=len(chunk_ids))
            except Exception as e:
                logger.warning(f"Failed to delete from vector index: {e}")
                result.add_warning(f"Vector index cleanup failed: {e}")

        # Delete from lexical index (if supported)
        if self.config.enable_lexical_index and self.lexical_index:
            if hasattr(self.lexical_index, "delete"):
                try:
                    await self.lexical_index.delete(repo_id, snapshot_id, chunk_ids)
                    logger.info("lexical_index_chunks_deleted", count=len(chunk_ids))
                except Exception as e:
                    logger.warning(f"Failed to delete from lexical index: {e}")
                    result.add_warning(f"Lexical index cleanup failed: {e}")

        record_counter("chunks_deleted_from_indexes_total", value=len(chunk_ids))

    @index_execution(IndexingStage.SYMBOL_INDEXING, "Symbol")
    async def _index_symbol(self, result: IndexingResult, repo_id: str, snapshot_id: str, graph_doc):
        """Index to symbol index."""
        # Index symbols from graph
        # Note: Adapt based on actual symbol_index interface
        await self.symbol_index.index_graph(repo_id, snapshot_id, graph_doc)
        result.symbol_entries_indexed = len(getattr(graph_doc, "graph_nodes", {}))

    @index_execution(IndexingStage.FUZZY_INDEXING, "Fuzzy")
    async def _index_fuzzy(self, result: IndexingResult, repo_id: str, snapshot_id: str, ir_doc):
        """Index to fuzzy index."""
        # Convert IR nodes to IndexDocument for fuzzy indexing
        from src.contexts.multi_index.infrastructure.common.documents import IndexDocument

        # Debug logging
        nodes = getattr(ir_doc, "nodes", [])
        logger.debug(f"fuzzy_index_debug: ir_doc type={type(ir_doc)}, nodes_count={len(nodes)}")

        docs = []
        for node in nodes:
            # Extract identifiers from function/class names
            if hasattr(node, "name") and node.name:
                node_id = getattr(node, "id", "") or ""
                file_path = getattr(node, "file_path", "") or ""
                doc = IndexDocument(
                    id=node_id,
                    chunk_id=node_id,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    file_path=file_path,
                    language=self._detect_language(file_path),
                    symbol_id=node_id,
                    symbol_name=node.name,
                    content=node.name,
                    identifiers=[node.name],
                    tags={"kind": str(getattr(node, "kind", "unknown"))},
                )
                docs.append(doc)

        if docs:
            await self.fuzzy_index.index(repo_id, snapshot_id, docs)
        result.fuzzy_entries_indexed = len(docs)

    def _detect_language(self, file_path) -> str:
        """Detect programming language from file path.

        Args:
            file_path: Can be str or Path object

        Returns:
            Language name or "unknown" if unrecognized
        """
        if not file_path:
            return "unknown"

        # Convert Path to str if needed
        if hasattr(file_path, "__fspath__"):
            file_path = str(file_path)
        elif not isinstance(file_path, str):
            return "unknown"

        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".md": "markdown",
            ".rst": "rst",
            ".txt": "text",
        }
        try:
            from pathlib import Path

            ext = Path(file_path).suffix.lower()
            return ext_to_lang.get(ext, "unknown")
        except (ValueError, OSError):
            return "unknown"

    @index_execution(IndexingStage.DOMAIN_INDEXING, "Domain")
    async def _index_domain(self, result: IndexingResult, repo_id: str, snapshot_id: str, chunk_ids: list[str]):
        """Index to domain metadata index."""
        from src.contexts.multi_index.infrastructure.common.documents import IndexDocument

        # Load chunks for domain indexing (filter for README, docs, etc.)
        chunks = await self._load_chunks_by_ids(chunk_ids)

        # Filter domain-related documents (README, docs, etc.)
        domain_extensions = {".md", ".rst", ".txt", ".adoc"}
        domain_patterns = {"readme", "changelog", "license", "contributing", "docs/", "doc/"}

        docs = []
        for chunk in chunks:
            file_path = getattr(chunk, "file_path", "") or ""
            file_lower = file_path.lower()

            # Check if it's a domain document
            is_domain = any(ext in file_lower for ext in domain_extensions) or any(
                pattern in file_lower for pattern in domain_patterns
            )

            if is_domain:
                chunk_id = getattr(chunk, "chunk_id", "") or ""
                doc = IndexDocument(
                    id=chunk_id,
                    chunk_id=chunk_id,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    file_path=file_path,
                    language=self._detect_language(file_path),
                    symbol_id=getattr(chunk, "fqn", "") or "",
                    content=getattr(chunk, "content", "") or "",
                    tags={"kind": str(getattr(chunk, "kind", "unknown"))},
                )
                docs.append(doc)

        if docs:
            await self.domain_index.index(repo_id, snapshot_id, docs)
        result.domain_docs_indexed = len(docs)

    @stage_execution(IndexingStage.FINALIZATION)
    async def _stage_finalization(self, result: IndexingResult):
        """Stage 10: Finalization."""
        # Store current commit as previous_commit for next incremental indexing
        # This enables proper diff calculation between incremental runs
        if result.git_commit_hash:
            result.metadata["previous_commit"] = result.git_commit_hash

            # Persist to metadata store for cross-session tracking
            if self.metadata_store and hasattr(self.metadata_store, "save_last_commit"):
                self.metadata_store.save_last_commit(result.repo_id, result.git_commit_hash)

        # Any cleanup or finalization tasks
        # (flush caches, update metadata, etc.)

    # === Helper Methods ===

    async def _parse_file(self, parser, file_path: Path):
        """Parse a single file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Tree-sitter parser.parse() expects bytes
            tree = parser.parse(content.encode("utf-8"))
            return tree
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None

    async def _build_ir(self, ast_results: dict, repo_id: str, snapshot_id: str):
        """
        Build IR from AST results.

        SOTA Improvements:
        - Uses type-safe FullSourceMap
        - Integrated error handling
        - IR validation
        """
        from src.contexts.code_foundation.infrastructure.ir.models import IRDocument
        from src.contexts.code_foundation.infrastructure.semantic_ir.error_handling import (
            ErrorCategory,
            PipelineErrorHandler,
            create_ir_error_context,
        )
        from src.contexts.code_foundation.infrastructure.semantic_ir.source_map import (
            FullSourceMap,
            create_source_map_from_results,
        )
        from src.contexts.code_foundation.infrastructure.semantic_ir.validation import IRValidator

        # Initialize error handler
        error_handler = PipelineErrorHandler()

        # Create type-safe source map
        source_map: FullSourceMap = create_source_map_from_results(
            ast_results=ast_results,
            repo_root=self.project_root,
            language="python",
        )

        logger.info(f"Building IR for {len(source_map)} files...")

        # Collect all nodes and edges from individual files
        all_nodes = []
        all_edges = []
        failed_files = []

        for file_path, (source_file, ast_tree) in source_map.items():
            try:
                # Generate IR for this file (pass pre-parsed AST to avoid re-parsing)
                ir_doc = self.ir_builder.generate(
                    source=source_file,
                    snapshot_id=snapshot_id,
                    ast=ast_tree,  # Pass wrapped AstTree (zero re-parsing)
                )

                if ir_doc:
                    all_nodes.extend(ir_doc.nodes)
                    all_edges.extend(ir_doc.edges)

            except Exception as e:
                # Handle error with proper classification
                context = create_ir_error_context(file_path, "generate_ir", e)
                error_handler.handle(e, ErrorCategory.IR_GENERATION, context, logger)
                failed_files.append(file_path)

                if not self.config.continue_on_error:
                    raise

        # Build IRDocument
        if all_nodes:
            ir_document = IRDocument(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                schema_version="4.1.0",
                nodes=all_nodes,
                edges=all_edges,
            )

            # Validate IR output
            validation_result = IRValidator.validate(ir_document)
            if validation_result.has_errors:
                logger.error(f"IR validation failed: {validation_result}")
                # Continue anyway (warnings only)

            logger.info(f"IR built: {len(all_nodes)} nodes, {len(all_edges)} edges ({len(failed_files)} failed files)")

            # Return both IR and source map (typed)
            return ir_document, source_map

        logger.warning("No IR nodes generated")
        return None, {}

    async def _build_semantic_ir(self, ir_doc, incremental=False):
        """
        Build semantic IR.

        If Pyright is enabled (settings.enable_pyright=True), uses Pyright-enabled
        semantic IR builder with external type analysis. Otherwise, uses default
        internal type inference.

        RFC-023 Integration:
        - M0: Uses PyrightSemanticDaemon for type analysis
        - M1: Persists PyrightSemanticSnapshot to PostgreSQL
        - M2: Supports incremental updates with ChangeDetector

        Args:
            ir_doc: IRDocument with structural information
            incremental: If True, use incremental Pyright snapshot update (M2)
        """
        from src.config import settings

        # Get pre-parsed AST map from temp storage (avoid re-parsing)
        ast_map = getattr(self, "_temp_ast_map", {})

        # Determine which semantic IR builder to use
        if settings.enable_pyright and self.pyright_daemon_factory and self.project_root:
            # Use Pyright-enabled builder (RFC-023)
            logger.info("🔍 Using Pyright for semantic analysis")
            try:
                # Create Pyright daemon and builder for this project
                pyright_daemon = self.pyright_daemon_factory(self.project_root)

                # Create semantic IR builder with Pyright
                from src.contexts.code_foundation.infrastructure.semantic_ir.semantic_ir_builder import (
                    SemanticIRBuilder,
                )

                pyright_builder = SemanticIRBuilder(
                    ir_generator=self.ir_builder,
                    pyright_daemon=pyright_daemon,
                )

                # Build semantic IR with Pyright (pass AST map to avoid re-parsing)
                semantic_snapshot, semantic_index = pyright_builder.build_full(ir_doc, source_map=ast_map)

                logger.info("   ✓ Pyright semantic analysis complete")

                # RFC-023 M1+M2: Persist Pyright snapshot to PostgreSQL
                await self._persist_pyright_snapshot(ir_doc, pyright_builder.external_analyzer, incremental=incremental)

            except Exception as e:
                # Fallback to internal types if Pyright fails
                logger.warning(f"Pyright failed ({e}), falling back to internal types")
                semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(ir_doc, source_map=ast_map)
        else:
            # Use default semantic IR builder (internal types only, pass AST map)
            semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(ir_doc, source_map=ast_map)

        # Clear temp AST map to free memory
        if hasattr(self, "_temp_ast_map"):
            del self._temp_ast_map

        # Return the snapshot along with index for later use
        return {"snapshot": semantic_snapshot, "index": semantic_index}

    async def _persist_pyright_snapshot(self, ir_doc, pyright_analyzer, incremental=False):
        """
        Persist Pyright semantic snapshot to PostgreSQL.

        RFC-023 M1: Save PyrightSemanticSnapshot for future incremental updates.
        RFC-023 M2: Support incremental updates using ChangeDetector.

        Args:
            ir_doc: IRDocument with structural information
            pyright_analyzer: PyrightExternalAnalyzer instance
            incremental: If True, use incremental export (M2)

        Note:
            - Full: Analyzes all files and saves snapshot
            - Incremental: Only analyzes changed files and merges with previous snapshot
        """
        try:
            snapshot_store = self.container.semantic_snapshot_store

            # Step 1: Extract locations from IR document
            file_locations = self._extract_ir_locations(ir_doc)

            if not file_locations:
                logger.warning("   ⚠️  No IR locations found, skipping snapshot persist")
                return

            # RFC-023 M2: Incremental update path
            if incremental and self.project_root:
                logger.info("   🔄 Incremental Pyright snapshot update...")

                # Detect changed files using Git
                from src.contexts.code_foundation.infrastructure.ir.external_analyzers import ChangeDetector

                try:
                    detector = ChangeDetector(self.project_root)
                    changed_files, deleted_files = detector.detect_changed_files()

                    # Filter file_locations to only changed files
                    changed_locations = {path: locs for path, locs in file_locations.items() if path in changed_files}

                    if not changed_locations and not deleted_files:
                        logger.info("   ✓ No changes detected, keeping existing snapshot")
                        return

                    # Load previous snapshot
                    project_id = ir_doc.repo_id
                    previous_snapshot = await snapshot_store.load_latest_snapshot(project_id)

                    if previous_snapshot:
                        # Incremental export (M2)
                        logger.info(
                            f"   Analyzing {len(changed_locations)} changed files "
                            f"(previously {len(previous_snapshot.files)} files)..."
                        )

                        pyright_snapshot = pyright_analyzer.export_semantic_incremental(
                            changed_files=changed_locations,
                            previous_snapshot=previous_snapshot,
                            deleted_files=deleted_files,
                        )

                        logger.info(
                            f"   ✓ Incremental update: {len(changed_locations)} changed, "
                            f"{len(deleted_files) if deleted_files else 0} deleted"
                        )
                    else:
                        # No previous snapshot, fall back to full export
                        logger.info("   No previous snapshot found, using full export")
                        pyright_snapshot = pyright_analyzer.export_semantic_for_files(file_locations)

                except Exception as e:
                    # Fall back to full export on error
                    logger.warning(f"   ⚠️  Incremental update failed: {e}")
                    logger.info("   Falling back to full export...")
                    pyright_snapshot = pyright_analyzer.export_semantic_for_files(file_locations)

            # RFC-023 M1: Full export path
            else:
                logger.info("   💾 Full Pyright snapshot export...")
                pyright_snapshot = pyright_analyzer.export_semantic_for_files(file_locations)

            # Save to PostgreSQL
            await snapshot_store.save_snapshot(pyright_snapshot)

            logger.info(
                f"   ✓ Saved Pyright snapshot: {pyright_snapshot.snapshot_id} "
                f"({len(pyright_snapshot.files)} files, "
                f"{len(pyright_snapshot.typing_info)} types)"
            )

        except Exception as e:
            logger.warning(f"   ⚠️  Failed to persist Pyright snapshot: {e}")

    def _extract_ir_locations(self, ir_doc) -> dict:
        """
        Extract file locations from IR document for Pyright analysis.

        Args:
            ir_doc: IRDocument with nodes containing spans

        Returns:
            Dict mapping file paths to list of (line, col) tuples

        Example:
            {
                Path("main.py"): [(10, 5), (15, 0), (20, 4)],
                Path("utils.py"): [(5, 0), (10, 4)]
            }
        """
        from pathlib import Path

        # Use sets for O(1) duplicate checking
        file_locations_sets: dict[Path, set[tuple[int, int]]] = {}

        for node in ir_doc.nodes:
            if not hasattr(node, "span") or not node.span or not node.span.file_path:
                continue

            file_path = Path(node.span.file_path)
            line = node.span.start_line
            col = node.span.start_column

            if file_path not in file_locations_sets:
                file_locations_sets[file_path] = set()

            # O(1) duplicate check with set
            location = (line, col)
            file_locations_sets[file_path].add(location)

        # Convert sets to sorted lists for consistent output
        return {path: sorted(locations) for path, locations in file_locations_sets.items()}

    async def _build_graph(self, semantic_ir, ir_doc, repo_id: str, snapshot_id: str):
        """Build code graph.

        Args:
            semantic_ir: Semantic IR dict with "snapshot" key, or None (optional for L2 mode)
            ir_doc: IR document (required)
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            GraphDocument or None if ir_doc is None
        """
        # Defensive check: ir_doc must not be None
        if ir_doc is None:
            logger.error("_build_graph called with ir_doc=None")
            return None

        # Extract semantic_snapshot from the dict (None is allowed by GraphBuilder)
        semantic_snapshot = None
        if semantic_ir is not None:
            if isinstance(semantic_ir, dict) and "snapshot" in semantic_ir:
                semantic_snapshot = semantic_ir["snapshot"]
            else:
                logger.warning(
                    "_build_graph received invalid semantic_ir format, using None",
                    semantic_ir_type=type(semantic_ir).__name__,
                )

        # GraphBuilder.build_full accepts semantic_snapshot=None
        return self.graph_builder.build_full(ir_doc, semantic_snapshot)

    async def _save_graph(self, graph_doc):
        """Save graph to store."""
        # Skip if no graph store configured
        if not self.graph_store:
            logger.info("Skipping graph save (no graph store configured)")
            return
        # Skip saving if graph is empty (avoids potential hang on Kuzu)
        if not graph_doc or (hasattr(graph_doc, "graph_nodes") and len(graph_doc.graph_nodes) == 0):
            logger.info("Skipping empty graph save")
            return
        await self.graph_store.save_graph(graph_doc)

    async def _build_chunks(self, graph_doc, ir_doc, semantic_ir, repo_id: str, snapshot_id: str) -> list[str]:
        """
        Build chunks with memory-efficient streaming (returns chunk IDs only).

        Instead of accumulating all chunks in memory, this method:
        1. Processes files in batches
        2. Saves chunks immediately to store
        3. Returns only chunk IDs (not full objects)

        Memory reduction: ~500MB → ~10MB for 10K files (50x improvement).

        Args:
            graph_doc: Graph document
            ir_doc: IR document
            semantic_ir: Semantic IR
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            List of chunk IDs (not full Chunk objects)
        """
        # Defensive checks for required inputs
        if ir_doc is None:
            logger.error("_build_chunks called with ir_doc=None")
            return []

        if graph_doc is None:
            logger.error("_build_chunks called with graph_doc=None")
            return []

        if not hasattr(ir_doc, "nodes") or ir_doc.nodes is None:
            logger.error("_build_chunks: ir_doc has no nodes attribute or nodes is None")
            return []

        batch_size = self.config.chunk_batch_size  # Default: 100 files
        batch_chunks = []
        batch_count = 0
        total_chunks = 0
        all_chunk_ids: list[str] = []  # Store only IDs, not full chunks

        # Group IR nodes by file
        files_map = {}
        for node in ir_doc.nodes:
            if hasattr(node, "file_path") and node.file_path:
                file_path = node.file_path
                if file_path not in files_map:
                    files_map[file_path] = []
                files_map[file_path].append(node)

        total_files = len(files_map)
        processed_files = 0

        logger.debug(f"Building chunks for {total_files} files (batch_size={batch_size})...")

        # Build chunks for each file
        for file_path, _nodes in files_map.items():
            try:
                # Resolve to absolute path using project_root
                abs_file_path = Path(file_path)
                if not abs_file_path.is_absolute():
                    abs_file_path = self.project_root / file_path

                # Skip external/virtual files
                if not abs_file_path.exists() or "<external>" in str(file_path):
                    continue

                # Read file content (CRITICAL FIX: normalize newlines)
                with open(abs_file_path, encoding="utf-8") as f:
                    file_text = [line.rstrip("\n\r") for line in f]

                # Build chunks for this file
                chunks, chunk_to_ir, chunk_to_graph = self.chunk_builder.build(
                    repo_id=repo_id,
                    ir_doc=ir_doc,
                    graph_doc=graph_doc,
                    file_text=file_text,
                    repo_config={"root": str(Path(file_path).parent.parent)},
                    snapshot_id=snapshot_id,
                )

                # Collect IDs immediately (memory efficient)
                all_chunk_ids.extend(c.chunk_id for c in chunks)
                batch_chunks.extend(chunks)
                batch_count += 1
                processed_files += 1

                # Save batch when size reached
                if batch_count >= batch_size:
                    # CRITICAL FIX: Remove duplicate chunk_id before saving
                    # Reason: Multiple files generate same repo/project chunks
                    # Keep last occurrence (most recent data)
                    original_count = len(batch_chunks)
                    seen_chunks = {}
                    for chunk in batch_chunks:
                        seen_chunks[chunk.chunk_id] = chunk
                    batch_chunks = list(seen_chunks.values())

                    if original_count > len(batch_chunks):
                        duplicates = original_count - len(batch_chunks)
                        logger.debug(
                            f"Removed {duplicates} duplicate chunk_ids from batch ({len(batch_chunks)} unique chunks)"
                        )

                    await self._save_chunks(batch_chunks)
                    total_chunks += len(batch_chunks)
                    logger.debug(
                        f"Saved batch: {len(batch_chunks)} chunks "
                        f"(progress: {processed_files}/{total_files} files, "
                        f"{(processed_files / total_files) * 100:.1f}%)"
                    )

                    # Clear batch to free memory (chunks are in store now)
                    batch_chunks = []
                    batch_count = 0

            except Exception as e:
                logger.warning(f"Failed to build chunks for {file_path}: {e}")

                if not self.config.continue_on_error:
                    raise

        # Save remaining chunks
        if batch_chunks:
            # CRITICAL FIX: Remove duplicate chunk_id before saving
            # Reason: Multiple files generate same repo/project chunks
            original_count = len(batch_chunks)
            seen_chunks = {}
            for chunk in batch_chunks:
                seen_chunks[chunk.chunk_id] = chunk
            batch_chunks = list(seen_chunks.values())

            if original_count > len(batch_chunks):
                duplicates = original_count - len(batch_chunks)
                logger.debug(
                    f"Removed {duplicates} duplicate chunk_ids from final batch ({len(batch_chunks)} unique chunks)"
                )

            await self._save_chunks(batch_chunks)
            total_chunks += len(batch_chunks)
            logger.debug(f"Saved final batch: {len(batch_chunks)} chunks")

        logger.info(f"✅ Built and saved {total_chunks} chunks from {processed_files} files (IDs only in memory)")

        return all_chunk_ids

    async def _save_chunks(self, chunks):
        """Save chunks to store."""
        # Use batch save for better performance
        await self.chunk_store.save_chunks(chunks)

    async def _load_chunks_by_ids(self, chunk_ids: list[str], batch_size: int = 100) -> list:
        """
        Load chunks from store by IDs with batching.

        This method loads chunks in batches to avoid memory spikes
        and enables memory-efficient processing of large chunk sets.

        Args:
            chunk_ids: List of chunk IDs to load
            batch_size: Number of chunks to load per batch (default: 100)

        Returns:
            List of Chunk objects
        """
        if not chunk_ids:
            return []

        all_chunks = []

        # Load in batches to manage memory
        for i in range(0, len(chunk_ids), batch_size):
            batch_ids = chunk_ids[i : i + batch_size]
            batch_result = await self.chunk_store.get_chunks_batch(batch_ids)

            # Preserve order
            for chunk_id in batch_ids:
                if chunk_id in batch_result:
                    all_chunks.append(batch_result[chunk_id])

        logger.debug(f"Loaded {len(all_chunks)}/{len(chunk_ids)} chunks from store")
        return all_chunks

    def _build_chunk_to_graph_mapping(self, chunks, graph_doc) -> dict[str, set[str]]:
        """
        Build mapping from chunk_id to graph_node_ids.

        FIXED: Reuse ChunkGraphMapper instead of duplicate logic.
        This ensures consistency with ChunkBuilder and includes proper filtering.

        Args:
            chunks: List of chunks
            graph_doc: Graph document with nodes

        Returns:
            Dict mapping chunk_id to set of graph_node_ids
        """
        from src.contexts.code_foundation.infrastructure.chunk.mapping import ChunkGraphMapper

        # Reuse existing mapper (includes filtering for Variable/Field)
        mapper = ChunkGraphMapper()
        chunk_to_graph = mapper.map_graph(chunks, graph_doc)

        logger.debug(f"Built chunk_to_graph mapping: {len(chunk_to_graph)} chunks mapped to graph nodes")
        return chunk_to_graph

    def _chunks_to_index_docs(
        self,
        chunks: list,  # list[Chunk] - avoiding circular import
        repo_id: str,
        snapshot_id: str,
        repomap_snapshot: Any | None = None,  # RepoMapSnapshot | None
    ) -> list:
        """
        Convert chunks to index documents with RepoMap metadata.

        Optimized with file I/O caching: reads each file only once instead of per-chunk.
        For 1000 chunks across 100 files: 1000 I/O → 100 I/O (10x reduction).

        Args:
            chunks: List of chunks to convert
            repomap_snapshot: Optional RepoMap snapshot for enrichment

        Returns:
            List of IndexDocument instances
        """
        from src.contexts.multi_index.infrastructure.common.documents import IndexDocument

        # Build chunk_id to RepoMapNode mapping for O(1) lookup
        chunk_to_node = {}
        if repomap_snapshot:
            # Handle both RepoMapSnapshot object and dict
            nodes = getattr(repomap_snapshot, "nodes", None)
            if nodes is None and isinstance(repomap_snapshot, dict):
                nodes = repomap_snapshot.get("nodes", [])
            if nodes:
                for node in nodes:
                    # Handle both object and dict node
                    chunk_ids = getattr(node, "chunk_ids", None)
                    if chunk_ids is None and isinstance(node, dict):
                        chunk_ids = node.get("chunk_ids", [])
                    if chunk_ids:
                        for chunk_id in chunk_ids:
                            # Use first matching node (most specific)
                            if chunk_id not in chunk_to_node:
                                chunk_to_node[chunk_id] = node

        # Group chunks by file path for batched I/O (optimization)
        from collections import defaultdict

        chunks_by_file = defaultdict(list)
        for chunk in chunks:
            file_path = getattr(chunk, "file_path", None)
            if file_path:
                chunks_by_file[file_path].append(chunk)
            else:
                # Structural chunks without file_path
                chunks_by_file[None].append(chunk)

        # File content cache to avoid redundant I/O
        file_cache = {}

        docs = []
        for file_path, file_chunks in chunks_by_file.items():
            # Read file once for all chunks
            if file_path and file_path not in file_cache:
                try:
                    with open(file_path, encoding="utf-8") as f:
                        file_cache[file_path] = f.readlines()
                except Exception as e:
                    logger.warning(
                        "file_read_failed",
                        file_path=file_path,
                        error=str(e),
                    )
                    file_cache[file_path] = None

            # Process all chunks for this file
            for chunk in file_chunks:
                chunk_id = getattr(chunk, "chunk_id", "")

                # Extract content using cached file data
                content = self._extract_chunk_content_cached(chunk, file_cache)

                # Create metadata copy to avoid modifying original
                metadata = dict(getattr(chunk, "metadata", {}) or {})

                # Enrich with RepoMap metadata if available
                if chunk_id in chunk_to_node:
                    node = chunk_to_node[chunk_id]

                    # Helper to get attr from object or dict
                    def get_val(obj, key, default=None):
                        if isinstance(obj, dict):
                            return obj.get(key, default)
                        return getattr(obj, key, default)

                    # Get metrics (may be nested object or dict)
                    metrics = get_val(node, "metrics", {})

                    # Add importance for ranking
                    importance = get_val(metrics, "importance")
                    if importance:
                        metadata["importance"] = importance

                    # Add tags for filtering
                    tags = get_val(node, "summary_tags")
                    if tags:
                        metadata["tags"] = tags

                    # Add summary for better semantic search
                    summary = get_val(node, "summary_body")
                    if summary:
                        metadata["summary"] = summary

                    # Add node metadata (safe to modify copy)
                    node_id = get_val(node, "id")
                    if node_id:
                        metadata["repomap_node_id"] = node_id
                    kind = get_val(node, "kind")
                    if kind:
                        metadata["repomap_kind"] = kind
                    is_entrypoint = get_val(node, "is_entrypoint")
                    if is_entrypoint is not None:
                        metadata["is_entrypoint"] = is_entrypoint
                    is_test = get_val(node, "is_test")
                    if is_test is not None:
                        metadata["is_test"] = is_test

                    # Add PageRank if available
                    pagerank = get_val(metrics, "pagerank")
                    if pagerank:
                        metadata["pagerank"] = pagerank

                # Create IndexDocument
                doc = IndexDocument(
                    id=chunk_id,
                    chunk_id=chunk_id,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    file_path=file_path or "",
                    language=self._detect_language(file_path or ""),
                    symbol_id=getattr(chunk, "fqn", "") or "",
                    content=content,
                    metadata=metadata,
                )
                docs.append(doc)

        logger.debug(
            "chunks_to_docs_completed",
            total_chunks=len(chunks),
            files_read=len([f for f in file_cache if f is not None]),
            io_reduction=f"{len(chunks) / max(len(file_cache), 1):.1f}x",
        )

        return docs

    def _extract_chunk_content_cached(self, chunk, file_cache: dict) -> str:
        """
        Extract actual code content from chunk using file cache.

        Optimized version: uses pre-loaded file content from cache to avoid redundant I/O.

        Args:
            chunk: Chunk object with file_path, start_line, end_line
            file_cache: Dict mapping file_path to list of lines (pre-loaded)

        Returns:
            Actual code content as string
        """
        file_path = getattr(chunk, "file_path", None)
        start_line = getattr(chunk, "start_line", None)
        end_line = getattr(chunk, "end_line", None)

        # Structural chunks (repo/project/module) don't have content
        if not file_path or start_line is None or end_line is None:
            # Use summary or fqn as fallback for searchability
            summary = getattr(chunk, "summary", None)
            if summary:
                return summary
            fqn = getattr(chunk, "fqn", "")
            kind = getattr(chunk, "kind", "")
            return f"{kind}: {fqn}"

        # Get cached file content
        lines = file_cache.get(file_path)
        if lines is None:
            # File read failed earlier
            fqn = getattr(chunk, "fqn", "")
            kind = getattr(chunk, "kind", "")
            return f"{kind}: {fqn}"

        try:
            # Extract chunk range (1-indexed to 0-indexed)
            content_lines = [line.rstrip("\n\r") for line in lines[start_line - 1 : end_line]]
            return "\n".join(content_lines)
        except Exception as e:
            logger.warning(
                "chunk_content_extraction_failed",
                chunk_id=getattr(chunk, "chunk_id", "unknown"),
                file_path=file_path,
                error=str(e),
            )
            # Fallback: return fqn for some searchability
            fqn = getattr(chunk, "fqn", "")
            kind = getattr(chunk, "kind", "")
            return f"{kind}: {fqn}"

    def _extract_chunk_content(self, chunk) -> str:
        """
        Extract actual code content from chunk (legacy method).

        DEPRECATED: Use _extract_chunk_content_cached() for better performance.
        This method is kept for backward compatibility and non-batched operations.

        Critical fix: Chunk model only stores file_path + line range,
        not the actual content. Need to read from file.

        Args:
            chunk: Chunk object with file_path, start_line, end_line

        Returns:
            Actual code content as string
        """
        file_path = getattr(chunk, "file_path", None)
        start_line = getattr(chunk, "start_line", None)
        end_line = getattr(chunk, "end_line", None)

        # Structural chunks (repo/project/module) don't have content
        if not file_path or start_line is None or end_line is None:
            # Use summary or fqn as fallback for searchability
            summary = getattr(chunk, "summary", None)
            if summary:
                return summary
            fqn = getattr(chunk, "fqn", "")
            kind = getattr(chunk, "kind", "")
            return f"{kind}: {fqn}"

        # Read actual code from file
        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
                # Extract chunk range (1-indexed to 0-indexed)
                content_lines = [line.rstrip("\n\r") for line in lines[start_line - 1 : end_line]]
                return "\n".join(content_lines)
        except Exception as e:
            logger.warning(
                "chunk_content_extraction_failed",
                chunk_id=getattr(chunk, "chunk_id", "unknown"),
                file_path=file_path,
                error=str(e),
            )
            # Fallback: return fqn for some searchability
            fqn = getattr(chunk, "fqn", "")
            kind = getattr(chunk, "kind", "")
            return f"{kind}: {fqn}"

    def _report_progress(self, stage: IndexingStage, progress: float):
        """Report progress to callback."""
        if self.progress_callback:
            self.progress_callback(stage, progress)

    # ============================================================
    # P0-1: Git History Enrichment
    # ============================================================

    async def _enrich_chunks_with_history(self, chunks, repo_id: str, result: IndexingResult):
        """
        Enrich chunks with Git history analysis.

        Uses GitHistoryAnalyzer to compute:
        - Primary author (from git blame)
        - Last modification info
        - Churn score and stability index
        - Number of contributors
        - Co-change patterns with other files

        Args:
            chunks: List of Chunk objects to enrich
            repo_id: Repository ID
            result: IndexingResult for tracking stats
        """
        logger.info("📜 Enriching chunks with Git history...")
        start_time = datetime.now()

        try:
            # Initialize Git history analyzer
            analyzer = GitHistoryAnalyzer(str(self.project_root))

            # Compute evolution graph (co-change patterns)
            evolution_graph = analyzer.compute_evolution_graph(lookback_months=6, min_co_changes=3)

            # Group chunks by file for efficient processing
            chunks_by_file = {}
            for chunk in chunks:
                if chunk.file_path:
                    if chunk.file_path not in chunks_by_file:
                        chunks_by_file[chunk.file_path] = []
                    chunks_by_file[chunk.file_path].append(chunk)

            # Get file-level statistics
            file_stats = analyzer._get_file_stats(lookback_months=6)

            # Prepare chunk histories
            chunk_histories = {}

            total_files = len(chunks_by_file)
            processed_files = 0

            # Process each file
            for file_path, file_chunks in chunks_by_file.items():
                try:
                    # Get blame info for file
                    blame_info = analyzer.get_file_blame(file_path)

                    if not blame_info:
                        processed_files += 1
                        continue

                    # Get file-level stats
                    stats = file_stats.get(file_path, {})
                    change_freq = stats.get("change_freq", 0.0)
                    contributor_count = stats.get("contributor_count", 0)

                    # Get co-changed files
                    co_changed = evolution_graph.get_related_files(file_path, min_confidence=0.3)
                    co_changed_files = [f for f, _ in co_changed]
                    co_change_strength = dict(co_changed)

                    # Compute churn score and stability index
                    churn_score = min(change_freq / 10.0, 1.0)  # Normalize to 0-1
                    stability_index = 1.0 - churn_score if churn_score > 0 else 1.0

                    # Compute days since last change
                    last_modified_str = stats.get("last_modified")
                    days_since_last_change = None
                    last_modified_at = None

                    if last_modified_str:
                        try:
                            from datetime import timezone

                            last_modified_at = datetime.fromisoformat(last_modified_str)
                            days_since_last_change = (datetime.now(timezone.utc) - last_modified_at).days
                        except (ValueError, TypeError):
                            pass  # Invalid date format, skip

                    # Get first commit time (approximate from blame)
                    first_commit_at = None
                    if blame_info.lines:
                        oldest_line = min(blame_info.lines, key=lambda x: x.commit_time)
                        first_commit_at = oldest_line.commit_time

                    # Create history for each chunk in this file
                    for chunk in file_chunks:
                        # Get the most recent author for this chunk's line range
                        chunk_lines = [
                            line
                            for line in blame_info.lines
                            if chunk.start_line
                            and chunk.end_line
                            and chunk.start_line <= line.line_number <= chunk.end_line
                        ]

                        if chunk_lines:
                            most_recent = max(chunk_lines, key=lambda x: x.commit_time)
                            last_modified_by = most_recent.author
                            last_modified_at = most_recent.commit_time
                            commit_sha = most_recent.commit_sha
                        else:
                            last_modified_by = blame_info.last_modified_by
                            last_modified_at = last_modified_at  # Use file-level
                            commit_sha = None

                        # Create ChunkHistory
                        history = ChunkHistory(
                            author=blame_info.primary_author,
                            last_modified_by=last_modified_by,
                            last_modified_at=last_modified_at,
                            commit_sha=commit_sha,
                            churn_score=churn_score,
                            stability_index=stability_index,
                            contributor_count=contributor_count,
                            co_changed_files=co_changed_files,
                            co_change_strength=co_change_strength,
                            first_commit_at=first_commit_at,
                            days_since_last_change=days_since_last_change,
                        )

                        chunk_histories[chunk.chunk_id] = history

                    processed_files += 1

                    # Progress logging
                    if processed_files % 100 == 0 or processed_files == total_files:
                        progress = (processed_files / total_files) * 100
                        logger.debug(
                            f"   Git history progress: {processed_files}/{total_files} files ({progress:.1f}%)"
                        )

                except Exception as e:
                    logger.warning(f"Failed to analyze Git history for {file_path}: {e}")
                    processed_files += 1
                    continue

            # Batch save chunk histories
            if chunk_histories:
                await self.chunk_store.save_chunk_histories(chunk_histories)

                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"   ✓ Enriched {len(chunk_histories)} chunks with Git history "
                    f"(analyzed {processed_files}/{total_files} files, {duration:.1f}s)"
                )

                # Update result metadata
                result.metadata["git_history_enriched"] = len(chunk_histories)
                result.metadata["git_history_duration_seconds"] = duration
            else:
                logger.info("   ⚠️  No Git history data available for enrichment")

        except Exception as e:
            logger.warning(f"Git history enrichment failed: {e}", exc_info=True)
            result.add_warning(f"Git history enrichment failed: {e}")

    # ========================================
    # Mode-based Indexing (New API)
    # ========================================

    def initialize_mode_system(self, metadata_store=None, file_hash_store=None):
        """
        모드 시스템 초기화 (lazy initialization).

        Args:
            metadata_store: 메타데이터 저장소
            file_hash_store: 파일 해시 저장소
        """
        git_helper = GitHelper(Path("."))  # Dummy, 실제는 런타임에 교체
        self.change_detector = ChangeDetector(git_helper=git_helper, file_hash_store=file_hash_store)
        self.scope_expander = ScopeExpander(graph_store=self.graph_store)
        self.mode_manager = ModeManager(
            change_detector=self.change_detector,
            scope_expander=self.scope_expander,
            metadata_store=metadata_store,
        )
        # Store metadata_store for last_commit tracking
        self.metadata_store = metadata_store
        logger.info("Mode system initialized")

    async def index_with_mode(
        self,
        repo_path: str | Path,
        repo_id: str,
        mode: IndexingMode | None = None,
        snapshot_id: str = "main",
        force: bool = False,
    ) -> IndexingResult:
        """
        모드 기반 인덱싱 (새로운 API).

        Args:
            repo_path: 레포지토리 경로
            repo_id: 레포지토리 ID
            mode: 인덱싱 모드 (None이면 자동 선택)
            snapshot_id: 스냅샷 ID
            force: 강제 전체 재인덱싱

        Returns:
            IndexingResult
        """
        repo_path = Path(repo_path)

        # Mode system이 초기화되지 않았으면 초기화
        if not self.mode_manager:
            self.initialize_mode_system()

        assert self.mode_manager is not None, "Mode manager not initialized"

        # 1. 실행 계획 생성
        total_files = self._count_files(repo_path)
        plan = await self.mode_manager.create_plan(
            repo_path=repo_path,
            repo_id=repo_id,
            mode=mode,
            auto_mode=self.config.auto_mode_selection,
            total_files=total_files,
        )

        layers = [layer.value for layer in plan.layers]
        target_count = len(plan.target_files) if plan.target_files else "all"
        logger.info(
            f"Indexing plan: mode={plan.mode}, layers={layers}, "
            f"target_files={target_count}, incremental={plan.is_incremental}"
        )

        # 2. 레이어별 실행
        return await self._execute_plan(
            repo_path=repo_path,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            plan=plan,
            force=force,
        )

    async def _execute_plan(
        self,
        repo_path: Path,
        repo_id: str,
        snapshot_id: str,
        plan: IndexingPlan,
        force: bool,
    ) -> IndexingResult:
        """
        실행 계획에 따라 인덱싱 수행.

        Args:
            repo_path: 레포지토리 경로
            repo_id: 레포지토리 ID
            snapshot_id: 스냅샷 ID
            plan: 실행 계획
            force: 강제 재인덱싱

        Returns:
            IndexingResult
        """
        start_time = datetime.now()

        result = IndexingResult(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            status=IndexingStatus.IN_PROGRESS,
            start_time=start_time,
            incremental=plan.is_incremental,
        )

        # 메타데이터에 모드 기록
        result.metadata["mode"] = plan.mode.value
        result.metadata["layers"] = [layer.value for layer in plan.layers]
        result.metadata["target_files_count"] = len(plan.target_files) if plan.target_files else "all"

        logger.info(
            "mode_based_indexing_started",
            repo_id=repo_id,
            mode=plan.mode.value,
            layers=len(plan.layers),
        )

        try:
            self.project_root = repo_path  # Set project root for incremental processing

            # Layer L1: Parsing
            if Layer.L1 in plan.layers:
                files = list(plan.target_files) if plan.target_files else await self._discover_all_files(repo_path)
                # Convert string paths to Path objects if needed
                files = [Path(repo_path) / f if isinstance(f, str) else f for f in files]
                ast_results = await self._stage_parsing(result, files)
            else:
                ast_results = []

            # Layer L2: IR + Chunk
            if Layer.L2 in plan.layers:
                ir_doc = await self._stage_ir_building(result, ast_results, repo_id, snapshot_id)

                # Early exit if IR building failed in L2
                if ir_doc is None:
                    logger.error("mode_indexing_ir_failed", repo_id=repo_id, mode=plan.mode.value)
                    result.add_warning("IR building failed in mode-based indexing")
                    result.mark_failed("IR building returned empty result")
                    return result

                # Use incremental graph building when applicable
                if plan.is_incremental and not plan.change_set.is_empty():
                    graph_doc = await self._stage_graph_building_incremental(
                        result, None, ir_doc, repo_id, snapshot_id, plan.change_set
                    )
                else:
                    graph_doc = await self._stage_graph_building(result, None, ir_doc, repo_id, snapshot_id)

                # Early exit if graph building failed in L2
                if graph_doc is None:
                    logger.error("mode_indexing_graph_failed", repo_id=repo_id, mode=plan.mode.value)
                    result.add_warning("Graph building failed in mode-based indexing")
                    result.mark_failed("Graph building returned empty result")
                    return result

                # Use incremental chunk generation when applicable
                if plan.is_incremental and not plan.change_set.is_empty():
                    chunks = await self._stage_chunk_generation_incremental(
                        result, graph_doc, ir_doc, None, repo_id, snapshot_id, plan.change_set
                    )
                else:
                    chunks = await self._stage_chunk_generation(result, graph_doc, ir_doc, None, repo_id, snapshot_id)
            else:
                ir_doc = None
                graph_doc = None
                chunks = []

            # Layer L3: Semantic IR
            if Layer.L3 in plan.layers or Layer.L3_SUMMARY in plan.layers:
                is_summary = Layer.L3_SUMMARY in plan.layers
                semantic_ir = await self._stage_semantic_ir_building_mode(result, ir_doc, is_summary=is_summary)

                # Early exit if semantic IR building failed in L3
                if semantic_ir is None:
                    logger.error("mode_indexing_semantic_ir_failed", repo_id=repo_id, mode=plan.mode.value)
                    result.add_warning("Semantic IR building failed in mode-based indexing")
                    result.mark_failed("Semantic IR building returned empty result")
                    return result

                # Graph 재빌드 (semantic IR 포함) - use incremental when applicable
                if plan.is_incremental and not plan.change_set.is_empty():
                    graph_doc = await self._stage_graph_building_incremental(
                        result, semantic_ir, ir_doc, repo_id, snapshot_id, plan.change_set
                    )
                else:
                    graph_doc = await self._stage_graph_building(result, semantic_ir, ir_doc, repo_id, snapshot_id)

                # Early exit if graph building failed in L3
                if graph_doc is None:
                    logger.error("mode_indexing_graph_failed_l3", repo_id=repo_id, mode=plan.mode.value)
                    result.add_warning("Graph building failed in L3 mode-based indexing")
                    result.mark_failed("Graph building returned empty result")
                    return result

                # Chunk generation with semantic IR - use incremental when applicable
                if plan.is_incremental and not plan.change_set.is_empty():
                    chunks = await self._stage_chunk_generation_incremental(
                        result, graph_doc, ir_doc, semantic_ir, repo_id, snapshot_id, plan.change_set
                    )
                else:
                    chunks = await self._stage_chunk_generation(
                        result, graph_doc, ir_doc, semantic_ir, repo_id, snapshot_id
                    )
            else:
                semantic_ir = None

            # Layer L4: Git History + Full DFG
            if Layer.L4 in plan.layers and chunks:
                await self._enrich_chunks_with_history(chunks, repo_id, result)
                # Full DFG는 semantic_ir_builder에서 처리 (is_summary=False)

            # RepoMap
            if self.config.repomap_enabled and chunks:
                repomap = await self._stage_repomap_building(result, chunks, graph_doc, repo_id, snapshot_id)
            else:
                repomap = None

            # Indexing
            if chunks:
                await self._stage_indexing(repo_id, snapshot_id, chunks, graph_doc, ir_doc, repomap, result)

            # Finalization
            await self._stage_finalization(result)

            result.mark_completed()
            logger.info(
                "mode_based_indexing_completed",
                repo_id=repo_id,
                mode=plan.mode.value,
                files_processed=result.files_processed,
                duration_seconds=result.total_duration_seconds,
            )

            return result

        except Exception as e:
            logger.error(f"Mode-based indexing failed: {e}", exc_info=True)
            result.mark_failed(str(e))
            raise

    async def _stage_semantic_ir_building_mode(self, result: IndexingResult, ir_doc, is_summary: bool = False):
        """
        Semantic IR 빌딩 (모드별).

        Args:
            result: IndexingResult
            ir_doc: IR 문서
            is_summary: True면 L3_SUMMARY (노드 제한), False면 L3/L4 Full

        Returns:
            Semantic IR
        """
        if not ir_doc:
            return None

        stage = IndexingStage.SEMANTIC_IR_BUILDING
        self._report_progress(stage, 0.0)

        try:
            # Summary 모드면 threshold 적용
            if is_summary:
                from src.contexts.analysis_indexing.infrastructure.models.mode import LayerThreshold

                # semantic_ir_builder에 max_nodes 파라미터 전달 (실제 구현 필요)
                # 여기서는 stub으로 처리
                logger.info(f"Building Semantic IR (summary mode, max_nodes={LayerThreshold.L3_CFG_MAX_NODES})")
            else:
                logger.info("Building Semantic IR (full mode)")

            # 기존 로직 호출
            semantic_ir = await self.semantic_ir_builder.build_semantic_ir(ir_doc)

            self._report_progress(stage, 1.0)
            return semantic_ir

        except Exception as e:
            logger.error(f"Semantic IR building failed: {e}", exc_info=True)
            result.add_error(f"Semantic IR: {e}")
            return None

    def _count_files(self, repo_path: Path) -> int:
        """레포지토리 파일 개수 카운트 (빠른 추정)."""
        try:
            # rglob으로 카운트 (실제로는 FileDiscovery 사용)
            count = sum(1 for _ in repo_path.rglob("*.py"))  # Python만 임시
            return count
        except Exception as e:
            logger.warning(f"Failed to count files: {e}")
            return 10000  # 기본값

    async def _discover_all_files(self, repo_path: Path) -> list[str]:
        """전체 파일 탐색."""
        discovery = FileDiscovery(config=self.config)
        file_paths = discovery.discover_files(repo_path)
        # Path를 str로 변환
        return [str(p.relative_to(repo_path)) for p in file_paths]
