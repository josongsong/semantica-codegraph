"""
Indexing Orchestrator

Orchestrates the complete indexing pipeline from parsing to indexing.

협력적 취소(cooperative cancellation)를 지원하여
graceful shutdown과 작업 일시중지가 가능합니다.

이 클래스는 IndexingOrchestratorSlim을 상속하여 추가 기능을 제공합니다:
- Mode management (FULL/INCREMENTAL 자동 선택)
- Scope expansion (영향 범위 분석)
- Compaction trigger (Delta compaction)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_engine.analysis_indexing.infrastructure.mode_manager import ModeManager
from codegraph_engine.analysis_indexing.infrastructure.orchestrator_slim import (
    IndexingOrchestratorSlim,
)
from codegraph_engine.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from codegraph_engine.code_foundation.infrastructure.chunk.incremental import ChunkIncrementalRefresher
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class IndexingOrchestrator(IndexingOrchestratorSlim):
    """
    Orchestrates the complete indexing pipeline.

    Extends IndexingOrchestratorSlim with:
    - Mode management system (FULL/INCREMENTAL auto-selection)
    - Scope expansion (impact analysis)
    - Compaction trigger (delta compaction)

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

    def __init__(self, *args, **kwargs):
        """
        Initialize orchestrator with all required components.

        Supports two initialization styles:
        1. Grouped (recommended): Pass OrchestratorComponents
        2. Legacy (backward compatible): Pass individual parameters

        All parameters are passed to IndexingOrchestratorSlim.
        """
        super().__init__(*args, **kwargs)

        # Additional state (extensions to Slim)
        self.mode_manager: ModeManager | None = None
        self.scope_expander: ScopeExpander | None = None
        self.chunk_refresher: ChunkIncrementalRefresher | None = None
        self.metadata_store = None
        self.compaction_manager = None

    # ==================== Extension Methods ====================

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
                asyncio.create_task(self.compaction_manager.compact(repo_id, snapshot_id))
                logger.info("Compaction started in background")

        except Exception as e:
            logger.error(f"Compaction trigger check failed: {e}", exc_info=True)

    def initialize_mode_system(
        self,
        repo_path: str | Path,
        metadata_store: Any = None,
    ) -> None:
        """
        Initialize mode management system for a repository.

        Sets up ModeManager, ChangeDetector, and ScopeExpander for
        intelligent mode selection and impact analysis.

        Args:
            repo_path: Path to repository
            metadata_store: Optional metadata store for tracking commits
        """
        from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeDetector
        from codegraph_engine.analysis_indexing.infrastructure.git_helper import GitHelper

        repo_path = Path(repo_path)
        self.project_root = repo_path

        # Update components project_root if exists
        if hasattr(self._components, "project_root"):
            self._components.project_root = repo_path

        git_helper = GitHelper(repo_path)
        self.change_detector = ChangeDetector(git_helper=git_helper)

        # ScopeExpander must be created before ModeManager
        self.scope_expander = ScopeExpander(
            graph_store=getattr(self._components, "graph_store", None),
            impact_analyzer=self.impact_analyzer,
        )

        self.mode_manager = ModeManager(
            change_detector=self.change_detector,
            scope_expander=self.scope_expander,
            metadata_store=metadata_store,
        )

        self.metadata_store = metadata_store
        logger.info("Mode system initialized", repo_path=str(repo_path))

    def set_compaction_manager(self, compaction_manager: Any) -> None:
        """Set compaction manager for delta compaction support."""
        self.compaction_manager = compaction_manager

    # ==================== Backward Compatibility Properties ====================

    @property
    def parser_registry(self):
        """Access parser_registry from components."""
        return getattr(self._components, "parser_registry", None)

    @property
    def ir_builder(self):
        """Access ir_builder from components."""
        return getattr(self._components, "ir_builder", None)

    @property
    def semantic_ir_builder(self):
        """Access semantic_ir_builder from components."""
        return getattr(self._components, "semantic_ir_builder", None)

    @property
    def graph_builder(self):
        """Access graph_builder from components."""
        return getattr(self._components, "graph_builder", None)

    @property
    def chunk_builder(self):
        """Access chunk_builder from components."""
        return getattr(self._components, "chunk_builder", None)

    @property
    def graph_store(self):
        """Access graph_store from components."""
        return getattr(self._components, "graph_store", None)

    @property
    def chunk_store(self):
        """Access chunk_store from components."""
        return getattr(self._components, "chunk_store", None)

    @property
    def repomap_store(self):
        """Access repomap_store from components."""
        return getattr(self._components, "repomap_store", None)

    @property
    def lexical_index(self):
        """Access lexical_index from components."""
        return getattr(self._components, "lexical_index", None)

    @property
    def vector_index(self):
        """Access vector_index from components."""
        return getattr(self._components, "vector_index", None)

    @property
    def symbol_index(self):
        """Access symbol_index from components."""
        return getattr(self._components, "symbol_index", None)

    @property
    def fuzzy_index(self):
        """Access fuzzy_index from components."""
        return getattr(self._components, "fuzzy_index", None)

    @property
    def domain_index(self):
        """Access domain_index from components."""
        return getattr(self._components, "domain_index", None)
