"""
Graph Stage - Code Graph Building

Stage 6: Build code graph from IR and Semantic IR
"""

from contextlib import nullcontext
from datetime import datetime
from typing import Any

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeSet
from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_engine.code_foundation.infrastructure.profiling import Profiler
from codegraph_shared.infra.observability import get_logger, record_counter

from .base import BaseStage, StageContext

logger = get_logger(__name__)


class GraphStage(BaseStage):
    """Graph Building Stage"""

    stage_name = IndexingStage.GRAPH_BUILDING

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.graph_builder = getattr(components, "graph_builder", None)
        self.graph_store = getattr(components, "graph_store", None)
        self.edge_validator = getattr(components, "edge_validator", None)
        self.impact_analyzer = getattr(components, "impact_analyzer", None)
        self._profiler = getattr(components, "profiler", None)

    async def execute(self, ctx: StageContext) -> None:
        """Execute graph building stage."""
        stage_start = datetime.now()

        # Use profiler from context or components
        profiler = ctx.profiler or self._profiler

        logger.info("graph_building_started")

        with profiler.phase("graph_building") if profiler else nullcontext():
            if ctx.is_incremental and ctx.change_set:
                graph_doc = await self._build_incremental(ctx, profiler)
            else:
                graph_doc = await self._build_full(ctx, profiler)

        ctx.graph_doc = graph_doc

        self._record_duration(ctx, stage_start)

    async def _build_full(self, ctx: StageContext, profiler: Profiler | None = None):
        """Build full graph."""
        graph_doc = await self._build_graph(
            ctx.semantic_ir,
            ctx.ir_doc,
            ctx.repo_id,
            ctx.snapshot_id,
            profiler=profiler,
        )

        if graph_doc:
            ctx.result.graph_nodes_created = len(getattr(graph_doc, "graph_nodes", {}))
            ctx.result.graph_edges_created = len(getattr(graph_doc, "graph_edges", []))

            logger.info(
                "graph_building_completed",
                nodes=ctx.result.graph_nodes_created,
                edges=ctx.result.graph_edges_created,
            )
            record_counter("graph_nodes_created_total", value=ctx.result.graph_nodes_created)
            record_counter("graph_edges_created_total", value=ctx.result.graph_edges_created)

            await self._save_graph(graph_doc)

        return graph_doc

    async def _build_incremental(self, ctx: StageContext, profiler: Profiler | None = None):
        """Build incremental graph with source-local invalidation."""
        change_set: ChangeSet = ctx.change_set

        logger.info(
            "incremental_graph_building_started",
            deleted=len(change_set.deleted),
            modified=len(change_set.modified),
            added=len(change_set.added),
        )

        # Load existing graph for stale edge analysis
        existing_graph = None
        if self.graph_store:
            try:
                existing_graph = await self.graph_store.load_graph(ctx.repo_id, ctx.snapshot_id)
            except Exception as e:
                logger.warning("failed_to_load_existing_graph", error=str(e))

        # Mark cross-file backward edges as stale
        stale_edge_count = 0
        if existing_graph and self.edge_validator and (change_set.modified or change_set.deleted):
            changed_files = change_set.modified | change_set.deleted
            stale_edges = self.edge_validator.mark_stale_edges(ctx.repo_id, changed_files, existing_graph)
            stale_edge_count = len(stale_edges)
            if stale_edge_count > 0:
                logger.info(
                    "stale_edges_marked",
                    count=stale_edge_count,
                    source_files=list({e.source_file for e in stale_edges})[:5],
                )
                ctx.result.metadata["stale_edges_marked"] = stale_edge_count

        if self.graph_store:
            # Handle DELETED files
            if change_set.deleted:
                deleted_files = list(change_set.deleted)

                if existing_graph and self.edge_validator:
                    deleted_symbol_ids = self._get_symbol_ids_for_files(existing_graph, deleted_files)
                    self.edge_validator.mark_deleted_symbol_edges(ctx.repo_id, deleted_symbol_ids, existing_graph)

                deleted_node_count = await self.graph_store.delete_nodes_for_deleted_files(ctx.repo_id, deleted_files)
                logger.info("graph_nodes_deleted_for_deleted_files", count=deleted_node_count)
                ctx.result.metadata["graph_nodes_deleted"] = deleted_node_count

                orphan_count = await self.graph_store.delete_orphan_module_nodes(ctx.repo_id)
                if orphan_count > 0:
                    logger.info("orphan_module_nodes_deleted", count=orphan_count)
                    ctx.result.metadata["orphan_modules_deleted"] = orphan_count

            # Handle MODIFIED files
            if change_set.modified:
                modified_files = list(change_set.modified)
                deleted_edge_count = await self.graph_store.delete_outbound_edges_by_file_paths(
                    ctx.repo_id, modified_files
                )
                logger.info("graph_outbound_edges_deleted_for_modified_files", count=deleted_edge_count)
                ctx.result.metadata["graph_edges_deleted"] = deleted_edge_count

        # Build new graph for added/modified files
        graph_doc = await self._build_graph(
            ctx.semantic_ir, ctx.ir_doc, ctx.repo_id, ctx.snapshot_id, profiler=profiler
        )

        if graph_doc:
            ctx.result.graph_nodes_created = len(getattr(graph_doc, "graph_nodes", {}))
            ctx.result.graph_edges_created = len(getattr(graph_doc, "graph_edges", []))

            logger.info(
                "incremental_graph_building_completed",
                nodes=ctx.result.graph_nodes_created,
                edges=ctx.result.graph_edges_created,
            )
            record_counter("graph_nodes_created_total", value=ctx.result.graph_nodes_created)
            record_counter("graph_edges_created_total", value=ctx.result.graph_edges_created)

            await self._save_graph_incremental(graph_doc)

            # Analyze impact
            if existing_graph and self.impact_analyzer:
                self._analyze_impact(ctx, existing_graph, graph_doc, change_set)

            # Clear stale edges for reindexed files
            if self.edge_validator:
                reindexed_files = change_set.added | change_set.modified
                cleared_count = 0
                for file_path in reindexed_files:
                    cleared_count += self.edge_validator.clear_stale_for_file(ctx.repo_id, file_path)
                if cleared_count > 0:
                    logger.info("stale_edges_cleared_after_reindex", count=cleared_count)
                    ctx.result.metadata["stale_edges_cleared"] = cleared_count

        return graph_doc

    def _get_symbol_ids_for_files(self, graph, file_paths: list[str]) -> set[str]:
        """Get all symbol node IDs for given files."""
        symbol_ids = set()
        file_path_set = set(file_paths)
        for node_id, node in graph.graph_nodes.items():
            if hasattr(node, "path") and node.path in file_path_set:
                symbol_ids.add(node_id)
        return symbol_ids

    def _analyze_impact(self, ctx: StageContext, old_graph, new_graph, change_set: ChangeSet):
        """Analyze symbol-level impact of incremental changes."""
        try:
            from codegraph_engine.code_foundation.infrastructure.graph.impact_analyzer import (
                detect_symbol_changes,
            )

            changed_symbols = detect_symbol_changes(old_graph, new_graph, change_set.all_changed)

            if not changed_symbols:
                logger.debug("no_symbol_changes_detected")
                return

            logger.info("symbol_changes_detected", count=len(changed_symbols))

            type_counts: dict[str, int] = {}
            for sc in changed_symbols:
                type_name = sc.change_type.name
                type_counts[type_name] = type_counts.get(type_name, 0) + 1
            ctx.result.metadata["symbol_change_types"] = type_counts

            impact_result = self.impact_analyzer.analyze_impact(old_graph, changed_symbols)

            logger.info(
                "impact_analysis_completed",
                direct_affected=len(impact_result.direct_affected),
                transitive_affected=len(impact_result.transitive_affected),
                affected_files=len(impact_result.affected_files),
            )

            ctx.result.metadata["impact_analysis"] = {
                "direct_affected": len(impact_result.direct_affected),
                "transitive_affected": len(impact_result.transitive_affected),
                "affected_files": list(impact_result.affected_files)[:20],
            }

            processed_files = change_set.all_changed
            unprocessed_affected = impact_result.affected_files - processed_files

            if unprocessed_affected:
                logger.info(
                    "impact_based_reindex_recommended",
                    count=len(unprocessed_affected),
                    sample_files=list(unprocessed_affected)[:10],
                )
                ctx.result.metadata["recommended_reindex_files"] = list(unprocessed_affected)
                ctx.result.add_warning(f"{len(unprocessed_affected)} files affected by changes may need reindexing")

        except Exception as e:
            logger.warning("impact_analysis_failed", error=str(e))

    async def _build_graph(
        self,
        semantic_ir,
        ir_doc,
        repo_id: str,
        snapshot_id: str,
        profiler: Profiler | None = None,
    ):
        """Build code graph."""
        if ir_doc is None:
            logger.error("_build_graph called with ir_doc=None")
            return None

        semantic_snapshot = None
        if semantic_ir is not None:
            if isinstance(semantic_ir, dict) and "snapshot" in semantic_ir:
                semantic_snapshot = semantic_ir["snapshot"]
            else:
                logger.warning(
                    "_build_graph received invalid semantic_ir format, using None",
                    semantic_ir_type=type(semantic_ir).__name__,
                )

        with profiler.phase("graph_builder.build_full") if profiler else nullcontext():
            result = self.graph_builder.build_full(ir_doc, semantic_snapshot)

        if profiler and result:
            profiler.increment("graph_nodes_total", len(getattr(result, "graph_nodes", {})))
            profiler.increment("graph_edges_total", len(getattr(result, "graph_edges", [])))

        return result

    async def _save_graph(self, graph_doc):
        """Save graph to store."""
        if not self.graph_store:
            logger.info("Skipping graph save (no graph store configured)")
            return

        if not graph_doc or (hasattr(graph_doc, "graph_nodes") and len(graph_doc.graph_nodes) == 0):
            logger.info("Skipping empty graph save")
            return

        await self.graph_store.save_graph(graph_doc)

    async def _save_graph_incremental(self, graph_doc):
        """Save graph with upsert mode for incremental updates."""
        if not self.graph_store:
            logger.info("Skipping graph save (no graph store configured)")
            return

        if not graph_doc or (hasattr(graph_doc, "graph_nodes") and len(graph_doc.graph_nodes) == 0):
            logger.info("Skipping empty graph save")
            return

        await self.graph_store.save_graph(graph_doc, mode="upsert")
