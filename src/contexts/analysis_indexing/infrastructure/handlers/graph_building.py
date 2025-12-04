"""
Graph Building Handler for Indexing Pipeline

Stage 6: Build code graph with nodes and edges.
Supports both full and incremental graph building.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.contexts.analysis_indexing.infrastructure.handlers.base import BaseHandler, HandlerContext
from src.contexts.analysis_indexing.infrastructure.models import IndexingResult, IndexingStage
from src.infra.observability import get_logger, record_counter
from src.pipeline.decorators import stage_execution

if TYPE_CHECKING:
    from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeSet
    from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder
    from src.contexts.code_foundation.infrastructure.graph.edge_validator import EdgeValidator
    from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer

logger = get_logger(__name__)


class GraphBuildingHandler(BaseHandler):
    """
    Stage 6: Build code graph from semantic IR.

    Supports:
    - Full graph building
    - Incremental graph building with source-local invalidation
    - Edge validation and stale edge management
    - Impact analysis for symbol-level changes
    """

    stage = IndexingStage.GRAPH_BUILDING

    def __init__(
        self,
        graph_builder: GraphBuilder,
        graph_store: Any,
        edge_validator: EdgeValidator,
        impact_analyzer: GraphImpactAnalyzer,
    ):
        """
        Initialize graph building handler.

        Args:
            graph_builder: Graph builder for IR->Graph conversion
            graph_store: Graph storage (Memgraph/Kuzu)
            edge_validator: Edge validator for stale edge management
            impact_analyzer: Impact analyzer for symbol-level analysis
        """
        super().__init__()
        self.graph_builder = graph_builder
        self.graph_store = graph_store
        self.edge_validator = edge_validator
        self.impact_analyzer = impact_analyzer

    @stage_execution(IndexingStage.GRAPH_BUILDING)
    async def execute(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        semantic_ir: dict[str, Any] | None,
        ir_doc: Any,
    ) -> Any:
        """
        Execute full graph building stage.

        Args:
            ctx: Handler context
            result: Indexing result to update
            semantic_ir: Semantic IR dict with "snapshot" key
            ir_doc: IR document

        Returns:
            GraphDocument
        """
        logger.info("graph_building_started")

        graph_doc = await self._build_graph(semantic_ir, ir_doc, ctx.repo_id, ctx.snapshot_id)

        if graph_doc:
            result.graph_nodes_created = len(getattr(graph_doc, "graph_nodes", {}))
            result.graph_edges_created = len(getattr(graph_doc, "graph_edges", []))

            logger.info(
                "graph_building_completed",
                nodes=result.graph_nodes_created,
                edges=result.graph_edges_created,
            )
            record_counter("graph_nodes_created_total", value=result.graph_nodes_created)
            record_counter("graph_edges_created_total", value=result.graph_edges_created)

            await self._save_graph(graph_doc)

        return graph_doc

    @stage_execution(IndexingStage.GRAPH_BUILDING)
    async def execute_incremental(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        semantic_ir: dict[str, Any] | None,
        ir_doc: Any,
        change_set: ChangeSet,
    ) -> Any:
        """
        Execute incremental graph building with source-local invalidation.

        Implements RFC SEP-G12-INC-GRAPH + SEP-G12-EDGE-VAL:
        1. Mark cross-file backward edges as stale
        2. For DELETED files: Remove nodes entirely
        3. For MODIFIED files: Delete outbound edges only, then upsert nodes
        4. For ADDED files: Insert new nodes and edges
        5. Analyze symbol-level impact
        6. Clear stale edges for reindexed files

        Args:
            ctx: Handler context
            result: Indexing result to update
            semantic_ir: Semantic IR dict
            ir_doc: IR document
            change_set: ChangeSet with added/modified/deleted files

        Returns:
            GraphDocument
        """
        logger.info(
            "incremental_graph_building_started",
            deleted=len(change_set.deleted),
            modified=len(change_set.modified),
            added=len(change_set.added),
        )

        repo_id = ctx.repo_id
        snapshot_id = ctx.snapshot_id

        # Step 0: Load existing graph for stale edge analysis
        existing_graph = await self._load_existing_graph(repo_id, snapshot_id)

        # Step 1: Mark cross-file backward edges as stale
        self._mark_stale_edges(repo_id, existing_graph, change_set, result)

        # Step 2-3: Handle deleted and modified files
        await self._handle_deleted_files(repo_id, existing_graph, change_set, result)
        await self._handle_modified_files(repo_id, change_set, result)

        # Step 4: Build new graph for added/modified files
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

            # Step 5: Save with upsert mode
            await self._save_graph_incremental(graph_doc)

            # Step 6: Analyze symbol-level impact
            self._analyze_impact(repo_id, existing_graph, graph_doc, change_set, result, ctx)

            # Step 7: Clear stale edges for reindexed files
            self._clear_stale_edges(repo_id, change_set, result)

        return graph_doc

    async def _build_graph(
        self,
        semantic_ir: dict[str, Any] | None,
        ir_doc: Any,
        repo_id: str,
        snapshot_id: str,
    ) -> Any:
        """Build code graph from semantic IR and IR document."""
        if ir_doc is None:
            logger.error("_build_graph called with ir_doc=None")
            return None

        # Extract semantic_snapshot from dict
        semantic_snapshot = None
        if semantic_ir is not None:
            if isinstance(semantic_ir, dict) and "snapshot" in semantic_ir:
                semantic_snapshot = semantic_ir["snapshot"]
            else:
                logger.warning(
                    "_build_graph received invalid semantic_ir format",
                    semantic_ir_type=type(semantic_ir).__name__,
                )

        return self.graph_builder.build_full(ir_doc, semantic_snapshot)

    async def _load_existing_graph(self, repo_id: str, snapshot_id: str) -> Any:
        """Load existing graph for incremental analysis."""
        if not self.graph_store:
            return None

        try:
            return await self.graph_store.load_graph(repo_id, snapshot_id)
        except Exception as e:
            logger.warning("failed_to_load_existing_graph", error=str(e))
            return None

    def _mark_stale_edges(
        self,
        repo_id: str,
        existing_graph: Any,
        change_set: ChangeSet,
        result: IndexingResult,
    ) -> int:
        """Mark cross-file backward edges as stale."""
        if not existing_graph or not (change_set.modified or change_set.deleted):
            return 0

        changed_files = change_set.modified | change_set.deleted
        stale_edges = self.edge_validator.mark_stale_edges(repo_id, changed_files, existing_graph)
        stale_edge_count = len(stale_edges)

        if stale_edge_count > 0:
            logger.info(
                "stale_edges_marked",
                count=stale_edge_count,
                source_files=list({e.source_file for e in stale_edges})[:5],
            )
            result.metadata["stale_edges_marked"] = stale_edge_count
            result.metadata["stale_source_files"] = list(self.edge_validator.get_stale_source_files(repo_id))

        return stale_edge_count

    async def _handle_deleted_files(
        self,
        repo_id: str,
        existing_graph: Any,
        change_set: ChangeSet,
        result: IndexingResult,
    ) -> None:
        """Handle deleted files - remove nodes entirely."""
        if not self.graph_store or not change_set.deleted:
            return

        deleted_files = list(change_set.deleted)

        # Mark edges pointing to deleted symbols as invalid
        if existing_graph:
            deleted_symbol_ids = self._get_symbol_ids_for_files(existing_graph, deleted_files)
            self.edge_validator.mark_deleted_symbol_edges(repo_id, deleted_symbol_ids, existing_graph)

        deleted_node_count = await self.graph_store.delete_nodes_for_deleted_files(repo_id, deleted_files)
        logger.info("graph_nodes_deleted_for_deleted_files", count=deleted_node_count)
        result.metadata["graph_nodes_deleted"] = deleted_node_count

        # Clean up orphan module nodes
        orphan_count = await self.graph_store.delete_orphan_module_nodes(repo_id)
        if orphan_count > 0:
            logger.info("orphan_module_nodes_deleted", count=orphan_count)
            result.metadata["orphan_modules_deleted"] = orphan_count

    async def _handle_modified_files(
        self,
        repo_id: str,
        change_set: ChangeSet,
        result: IndexingResult,
    ) -> None:
        """Handle modified files - delete outbound edges only."""
        if not self.graph_store or not change_set.modified:
            return

        modified_files = list(change_set.modified)
        deleted_edge_count = await self.graph_store.delete_outbound_edges_by_file_paths(repo_id, modified_files)
        logger.info("graph_outbound_edges_deleted_for_modified_files", count=deleted_edge_count)
        result.metadata["graph_edges_deleted"] = deleted_edge_count

    def _get_symbol_ids_for_files(self, graph: Any, file_paths: list[str]) -> set[str]:
        """Get all symbol node IDs for given files."""
        symbol_ids = set()
        file_path_set = set(file_paths)
        for node_id, node in graph.graph_nodes.items():
            if hasattr(node, "path") and node.path in file_path_set:
                symbol_ids.add(node_id)
        return symbol_ids

    async def _save_graph(self, graph_doc: Any) -> None:
        """Save graph to store (full mode)."""
        if not self.graph_store:
            logger.info("Skipping graph save (no graph store configured)")
            return

        if not graph_doc or (hasattr(graph_doc, "graph_nodes") and len(graph_doc.graph_nodes) == 0):
            logger.info("Skipping empty graph save")
            return

        await self.graph_store.save_graph(graph_doc)

    async def _save_graph_incremental(self, graph_doc: Any) -> None:
        """Save graph to store with upsert mode for incremental updates."""
        if not self.graph_store:
            logger.info("Skipping graph save (no graph store configured)")
            return

        if not graph_doc or (hasattr(graph_doc, "graph_nodes") and len(graph_doc.graph_nodes) == 0):
            logger.info("Skipping empty graph save")
            return

        await self.graph_store.save_graph(graph_doc, mode="upsert")

    def _analyze_impact(
        self,
        repo_id: str,
        existing_graph: Any,
        new_graph: Any,
        change_set: ChangeSet,
        result: IndexingResult,
        ctx: HandlerContext,
    ) -> None:
        """Analyze symbol-level impact of changes."""
        if not existing_graph:
            return

        try:
            from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import detect_symbol_changes

            changed_symbols = detect_symbol_changes(existing_graph, new_graph, change_set.all_changed)

            if not changed_symbols:
                logger.debug("no_symbol_changes_detected")
                return

            logger.info("symbol_changes_detected", count=len(changed_symbols))

            # Count by change type
            type_counts: dict[str, int] = {}
            for sc in changed_symbols:
                type_name = sc.change_type.name
                type_counts[type_name] = type_counts.get(type_name, 0) + 1
            result.metadata["symbol_change_types"] = type_counts

            # Analyze impact
            impact_result = self.impact_analyzer.analyze_impact(existing_graph, changed_symbols)

            logger.info(
                "impact_analysis_completed",
                direct_affected=len(impact_result.direct_affected),
                transitive_affected=len(impact_result.transitive_affected),
                affected_files=len(impact_result.affected_files),
            )

            result.metadata["impact_analysis"] = {
                "direct_affected": len(impact_result.direct_affected),
                "transitive_affected": len(impact_result.transitive_affected),
                "affected_files": list(impact_result.affected_files)[:20],
            }

            # Check for files needing reindexing
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
                if ctx.session_ctx:
                    ctx.session_ctx.set_impact_candidates(unprocessed_affected)
                    for file in change_set.all_changed:
                        ctx.session_ctx.mark_file_processed(file)

        except Exception as e:
            logger.warning("impact_analysis_failed", error=str(e))

    def _clear_stale_edges(
        self,
        repo_id: str,
        change_set: ChangeSet,
        result: IndexingResult,
    ) -> None:
        """Clear stale edges for reindexed files."""
        reindexed_files = change_set.added | change_set.modified
        cleared_count = 0

        for file_path in reindexed_files:
            cleared_count += self.edge_validator.clear_stale_for_file(repo_id, file_path)

        if cleared_count > 0:
            logger.info("stale_edges_cleared_after_reindex", count=cleared_count)
            result.metadata["stale_edges_cleared"] = cleared_count
