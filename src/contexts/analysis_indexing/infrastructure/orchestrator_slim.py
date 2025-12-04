"""
Slim Indexing Orchestrator

Refactored orchestrator that delegates to specialized handlers.
Maintains API compatibility with the original IndexingOrchestrator.

This file is ~600 lines compared to the original ~3,200 lines.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeDetector, ChangeSet
from src.contexts.analysis_indexing.infrastructure.file_discovery import FileDiscovery
from src.contexts.analysis_indexing.infrastructure.git_helper import GitHelper
from src.contexts.analysis_indexing.infrastructure.handlers import (
    ChunkingHandler,
    GraphBuildingHandler,
    HandlerContext,
    IndexingHandler,
    IRBuildingHandler,
    ParsingHandler,
)
from src.contexts.analysis_indexing.infrastructure.mode_manager import ModeManager
from src.contexts.analysis_indexing.infrastructure.models import (
    IndexingConfig,
    IndexingResult,
    IndexingStage,
    IndexingStatus,
    IndexSessionContext,
    OrchestratorComponents,
)
from src.contexts.analysis_indexing.infrastructure.models.job import JobProgress
from src.contexts.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from src.contexts.code_foundation.infrastructure.graph.edge_validator import EdgeValidator
from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer
from src.infra.observability import get_logger, record_counter, record_histogram
from src.pipeline.decorators import stage_execution

logger = get_logger(__name__)


class IndexingOrchestratorSlim:
    """
    Slim orchestrator that delegates to specialized handlers.

    Pipeline Stages:
        1. Git operations
        2. File discovery
        3. Parsing (ParsingHandler)
        4. IR building (IRBuildingHandler)
        5. Semantic IR building (IRBuildingHandler)
        6. Graph building (GraphBuildingHandler)
        7. Chunk generation (ChunkingHandler)
        8. RepoMap building
        9. Indexing (IndexingHandler)
    """

    def __init__(
        self,
        # Grouped components (recommended)
        components: OrchestratorComponents | None = None,
        # Configuration
        config: IndexingConfig | None = None,
        progress_callback: Callable[[IndexingStage, float], None] | None = None,
        container=None,
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
            container: Optional DI container for Pyright integration
        """
        self.config = config or IndexingConfig()
        self.container = container
        self.progress_callback = progress_callback

        # Extract components from grouped or legacy parameters
        if components:
            parser_registry = components.builders.parser_registry
            ir_builder = components.builders.ir_builder
            semantic_ir_builder = components.builders.semantic_ir_builder
            graph_builder = components.builders.graph_builder
            chunk_builder = components.builders.chunk_builder
            repomap_tree_builder_class = components.repomap.tree_builder_class
            repomap_pagerank_engine = components.repomap.pagerank_engine
            repomap_summarizer = components.repomap.summarizer
            graph_store = components.stores.graph_store
            chunk_store = components.stores.chunk_store
            repomap_store = components.stores.repomap_store
            lexical_index = components.indexes.lexical
            vector_index = components.indexes.vector
            symbol_index = components.indexes.symbol
            fuzzy_index = components.indexes.fuzzy
            domain_index = components.indexes.domain

        # Store references for direct use
        self.parser_registry = parser_registry
        self.graph_store = graph_store
        self.chunk_store = chunk_store
        self.repomap_store = repomap_store
        self.repomap_tree_builder_class = repomap_tree_builder_class
        self.repomap_pagerank_engine = repomap_pagerank_engine
        self.repomap_summarizer = repomap_summarizer

        # Initialize handlers
        self.parsing_handler = ParsingHandler(parser_registry, self.config)
        self.ir_building_handler = IRBuildingHandler(ir_builder, semantic_ir_builder, self.config, container)
        self.graph_building_handler = GraphBuildingHandler(
            graph_builder,
            graph_store,
            EdgeValidator(stale_ttl_hours=24.0, auto_cleanup=False),
            GraphImpactAnalyzer(max_depth=3, max_affected=500, include_test_files=False),
        )
        self.chunking_handler = ChunkingHandler(chunk_builder, chunk_store, self.config)
        # embedding_queue 가져오기 (있으면)
        embedding_queue = None
        if hasattr(container, "_index"):
            try:
                embedding_queue = container._index.embedding_queue
                if embedding_queue:
                    logger.info("embedding_queue_enabled_for_indexing_handler")
                else:
                    logger.info("embedding_queue_disabled_no_vector_or_queue")
            except Exception as e:
                logger.warning(f"embedding_queue_initialization_failed: {e}")

        self.indexing_handler = IndexingHandler(
            lexical_index,
            vector_index,
            symbol_index,
            fuzzy_index,
            domain_index,
            self.config,
            chunk_store,
            embedding_queue,
        )

        # Runtime state
        self.project_root: Path | None = None
        self._session_ctx: IndexSessionContext | None = None
        self._stop_event: asyncio.Event | None = None

        # Mode management
        self.mode_manager: ModeManager | None = None
        self.change_detector: ChangeDetector | None = None
        self.scope_expander: ScopeExpander | None = None
        self.metadata_store = None

    async def index_repository_full(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str = "main",
        force: bool = False,
    ) -> IndexingResult:
        """Full repository indexing (API compatibility wrapper)."""
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
        """Incremental repository indexing (API compatibility wrapper)."""
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
        Index a complete repository.

        Main entry point that orchestrates the entire pipeline.
        """
        repo_path = Path(repo_path)
        self.project_root = repo_path
        start_time = datetime.now()

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

        # Create handler context
        ctx = HandlerContext(
            repo_path=repo_path,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            config=self.config,
            incremental=incremental,
            project_root=repo_path,
            session_ctx=self._session_ctx,
            stop_event=stop_event,
            progress=progress,
            progress_callback=self.progress_callback,
            progress_persist_callback=progress_persist_callback,
            container=self.container,
        )

        logger.info(
            "indexing_started",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            incremental=incremental,
        )
        record_counter("indexing_jobs_started_total", labels={"mode": "incremental" if incremental else "full"})

        try:
            # === Stage 1: Git Operations ===
            await self._stage_git_operations(repo_path, result)

            # === Stage 2: File Discovery ===
            if incremental:
                change_set, files = await self._stage_file_discovery_incremental(result, repo_path, repo_id)
                if change_set.is_empty():
                    logger.info("no_changes_detected", repo_id=repo_id)
                    result.mark_completed()
                    return result
                ctx.change_set = change_set
            else:
                files = await self._stage_file_discovery(result, repo_path)
                ctx.change_set = None

            if not files:
                logger.warning("no_files_to_process", repo_id=repo_id)
                result.mark_completed()
                return result

            if progress:
                progress.total_files = len(files)

            # === Stage 3: Parsing ===
            ast_results = await self.parsing_handler.execute(ctx, result, files)

            if self._check_cancelled(ctx, result, "parsing"):
                return result

            if not ast_results:
                logger.warning("no_ast_results", repo_id=repo_id)
                result.mark_completed()
                return result

            # === Stage 4: IR Building ===
            ir_doc, source_map = await self.ir_building_handler.execute_ir_building(ctx, result, ast_results)

            if ir_doc is None:
                result.mark_failed("IR building returned empty result")
                return result

            # === Stage 5: Semantic IR Building ===
            semantic_ir = await self.ir_building_handler.execute_semantic_ir_building(ctx, result, ir_doc)

            if semantic_ir is None:
                result.mark_failed("Semantic IR building returned empty result")
                return result

            # === Stage 6: Graph Building ===
            if incremental and ctx.change_set:
                graph_doc = await self.graph_building_handler.execute_incremental(
                    ctx, result, semantic_ir, ir_doc, ctx.change_set
                )
            else:
                graph_doc = await self.graph_building_handler.execute(ctx, result, semantic_ir, ir_doc)

            if graph_doc is None:
                result.mark_failed("Graph building returned empty result")
                return result

            # === Stage 7: Chunk Generation ===
            if incremental and ctx.change_set:
                chunk_ids = await self.chunking_handler.execute_incremental(
                    ctx, result, graph_doc, ir_doc, semantic_ir, ctx.change_set
                )
            else:
                chunk_ids = await self.chunking_handler.execute(ctx, result, graph_doc, ir_doc, semantic_ir)

            if chunk_ids is None:
                result.mark_failed("Chunk generation returned empty result")
                return result

            if not chunk_ids:
                logger.warning("no_chunks_generated", repo_id=repo_id)
                result.mark_completed()
                return result

            # === Stage 8: RepoMap Building ===
            repomap = None
            if self.config.repomap_enabled:
                repomap = await self._stage_repomap_building(result, chunk_ids, graph_doc, repo_id, snapshot_id)

            # === Stage 9: Indexing ===
            await self.indexing_handler.execute(ctx, result, chunk_ids, graph_doc, ir_doc, repomap)

            # === Stage 10: Finalization ===
            await self._stage_finalization(result)

            result.mark_completed()
            logger.info(
                "indexing_completed",
                repo_id=repo_id,
                files_processed=result.files_processed,
                chunks_created=result.chunks_created,
                duration_seconds=result.total_duration_seconds,
            )
            record_counter("indexing_jobs_completed_total", labels={"status": "success"})
            record_histogram("indexing_duration_seconds", result.total_duration_seconds)

            return result

        except Exception as e:
            logger.error("indexing_failed", repo_id=repo_id, error=str(e), exc_info=True)
            result.mark_failed(str(e))
            record_counter("indexing_jobs_completed_total", labels={"status": "failed"})
            raise

        finally:
            self._session_ctx = None
            self._stop_event = None

    def _check_cancelled(self, ctx: HandlerContext, result: IndexingResult, stage: str) -> bool:
        """Check if cancellation was requested."""
        if ctx.stop_event and ctx.stop_event.is_set():
            logger.info("indexing_stopped_by_request", stage=stage)
            result.status = IndexingStatus.IN_PROGRESS
            result.metadata["stopped_at_stage"] = stage
            return True
        return False

    async def _stage_git_operations(self, repo_path: Path, result: IndexingResult) -> None:
        """Stage 1: Git operations."""
        self._report_progress(IndexingStage.GIT_OPERATIONS, 0.0)

        try:
            git = GitHelper(repo_path)

            if git.is_git_repo():
                commit_hash = git.get_current_commit_hash()
                result.git_commit_hash = commit_hash
                repo_info = git.get_repo_info()
                result.metadata["git_info"] = repo_info

                logger.info(
                    f"Git repo: {repo_info['current_branch']} @ {commit_hash[:8] if commit_hash else 'unknown'}"
                )
            else:
                logger.warning(f"Not a Git repository: {repo_path}")
                result.add_warning("Not a Git repository")

        except Exception as e:
            logger.warning(f"Git operations failed: {e}")
            result.add_warning(f"Git operations failed: {e}")

        self._report_progress(IndexingStage.GIT_OPERATIONS, 100.0)

    @stage_execution(IndexingStage.FILE_DISCOVERY)
    async def _stage_file_discovery(self, result: IndexingResult, repo_path: Path) -> list[Path]:
        """Stage 2: File discovery (full mode)."""
        discovery = FileDiscovery(self.config)
        files = discovery.discover_files(repo_path)

        logger.info("files_discovered", mode="full", count=len(files))
        record_counter("files_discovered_total", value=len(files), labels={"mode": "full"})

        result.files_discovered = len(files)
        stats = discovery.get_file_stats(files)
        result.metadata["file_stats"] = stats

        return files

    @stage_execution(IndexingStage.FILE_DISCOVERY)
    async def _stage_file_discovery_incremental(
        self, result: IndexingResult, repo_path: Path, repo_id: str
    ) -> tuple[ChangeSet, list[Path]]:
        """Stage 2: Incremental file discovery with change detection."""
        discovery = FileDiscovery(self.config)
        git = GitHelper(repo_path)

        if not self.change_detector:
            self.change_detector = ChangeDetector(git_helper=git)

        change_set = self.change_detector.detect_changes(repo_path, repo_id)

        logger.info(
            "incremental_changes_detected",
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
        )

        changed_paths = []
        for file_path in change_set.all_changed:
            full_path = repo_path / file_path
            if full_path.exists():
                changed_paths.append(full_path)

        files = discovery.discover_files(repo_path, changed_files=[str(p) for p in changed_paths])

        result.files_discovered = len(files)
        result.metadata["change_set"] = {
            "added": len(change_set.added),
            "modified": len(change_set.modified),
            "deleted": len(change_set.deleted),
        }
        result.metadata["changed_files"] = list(change_set.all_changed)

        if files:
            stats = discovery.get_file_stats(files)
            result.metadata["file_stats"] = stats

        return change_set, files

    @stage_execution(IndexingStage.REPOMAP_BUILDING)
    async def _stage_repomap_building(
        self,
        result: IndexingResult,
        chunk_ids: list[str],
        graph_doc: Any,
        repo_id: str,
        snapshot_id: str,
    ) -> Any:
        """Stage 8: RepoMap building."""
        logger.info("Building RepoMap...")

        if not self.repomap_store:
            logger.warning("RepoMap store missing; skipping stage")
            return None

        # Load chunks from store
        chunks = await self._load_chunks_by_ids(chunk_ids)

        # Build chunk_to_graph mapping
        from src.contexts.code_foundation.infrastructure.chunk.mapping import ChunkGraphMapper

        mapper = ChunkGraphMapper()
        chunk_to_graph = mapper.map_graph(chunks, graph_doc)

        # Create RepoMapBuildConfig
        from src.contexts.repo_structure.infrastructure.models import RepoMapBuildConfig

        repomap_config = RepoMapBuildConfig(
            pagerank_enabled=True,
            summarizer_enabled=self.repomap_summarizer is not None,
            summarizer_batch_size=10,
        )

        # Build repomap
        from src.contexts.repo_structure.infrastructure.builder.orchestrator import RepoMapBuilder

        repomap_builder = RepoMapBuilder(
            tree_builder_class=self.repomap_tree_builder_class,
            pagerank_engine=self.repomap_pagerank_engine,
            summarizer=self.repomap_summarizer,
            repomap_store=self.repomap_store,
            config=repomap_config,
        )

        repomap_snapshot = await repomap_builder.build(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            chunks=chunks,
            graph_doc=graph_doc,
            chunk_to_graph=chunk_to_graph,
        )

        if repomap_snapshot:
            result.repomap_nodes_created = len(getattr(repomap_snapshot, "nodes", []))
            logger.info("repomap_building_completed", nodes=result.repomap_nodes_created)

        return repomap_snapshot

    @stage_execution(IndexingStage.FINALIZATION)
    async def _stage_finalization(self, result: IndexingResult) -> None:
        """Stage 10: Finalization."""
        if result.git_commit_hash:
            result.metadata["previous_commit"] = result.git_commit_hash

            if self.metadata_store and hasattr(self.metadata_store, "save_last_commit"):
                self.metadata_store.save_last_commit(result.repo_id, result.git_commit_hash)

    async def _load_chunks_by_ids(self, chunk_ids: list[str], batch_size: int = 100) -> list:
        """Load chunks from store by IDs with batching."""
        if not chunk_ids:
            return []

        all_chunks = []
        for i in range(0, len(chunk_ids), batch_size):
            batch_ids = chunk_ids[i : i + batch_size]
            batch_result = await self.chunk_store.get_chunks_batch(batch_ids)

            for chunk_id in batch_ids:
                if chunk_id in batch_result:
                    all_chunks.append(batch_result[chunk_id])

        return all_chunks

    def _report_progress(self, stage: IndexingStage, progress: float) -> None:
        """Report progress for a stage."""
        if self.progress_callback:
            self.progress_callback(stage, progress)

    def initialize_mode_system(self, metadata_store=None, file_hash_store=None) -> None:
        """Initialize mode management system."""
        self.metadata_store = metadata_store
        self.mode_manager = ModeManager(
            metadata_store=metadata_store,
            file_hash_store=file_hash_store,
        )
        self.scope_expander = ScopeExpander()


# Backward compatibility alias
IndexingOrchestrator = IndexingOrchestratorSlim
