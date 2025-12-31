"""
RepoMap Stage - RepoMap Building

Stage 8: Build RepoMap (Tree + PageRank + Summaries)
"""

from datetime import datetime
from typing import Any

from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_shared.infra.observability import get_logger

from .base import BaseStage, StageContext

logger = get_logger(__name__)


class RepoMapStage(BaseStage):
    """RepoMap Building Stage"""

    stage_name = IndexingStage.REPOMAP_BUILDING

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.repomap_store = getattr(components, "repomap_store", None)
        self.chunk_store = getattr(components, "chunk_store", None)
        self.container = getattr(components, "container", None)
        self.config = getattr(components, "config", None)

    async def execute(self, ctx: StageContext) -> None:
        """Execute RepoMap building stage."""
        stage_start = datetime.now()

        logger.info("repomap_building_started")

        if not self.repomap_store:
            logger.warning("RepoMap store missing; skipping stage")
            self._record_duration(ctx, stage_start)
            return

        repomap = await self._build_repomap(ctx)
        ctx.result.metadata["repomap"] = repomap

        self._record_duration(ctx, stage_start)

    async def _build_repomap(self, ctx: StageContext) -> dict | None:
        """Build RepoMap using RepoMapBuilder."""
        # Load chunks from store
        chunks = await self._load_chunks_by_ids(ctx.chunk_ids)

        # Build chunk_to_graph mapping for PageRank aggregation
        _chunk_to_graph = self._build_chunk_to_graph_mapping(chunks, ctx.graph_doc)

        from codegraph_engine.repo_structure.infrastructure.models import RepoMapBuildConfig

        repomap_config = RepoMapBuildConfig(
            pagerank_enabled=True,
            summary_enabled=getattr(self.config, "repomap_use_llm_summaries", False),
            include_tests=False,
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

        repo_path = getattr(self.config, "repo_path", None)

        from codegraph_engine.repo_structure.infrastructure.builder import RepoMapBuilder

        builder = RepoMapBuilder(
            store=self.repomap_store,
            config=repomap_config,
            llm=llm,
            chunk_store=self.chunk_store,
            repo_path=repo_path,
        )

        snapshot = await builder.build_async(
            repo_id=ctx.repo_id,
            snapshot_id=ctx.snapshot_id,
            chunks=chunks,
            graph_doc=ctx.graph_doc,
        )

        ctx.result.repomap_nodes_created = len(snapshot.nodes)
        ctx.result.repomap_summaries_generated = sum(1 for node in snapshot.nodes if node.summary_body is not None)

        logger.info(
            f"RepoMap: {ctx.result.repomap_nodes_created} nodes, {ctx.result.repomap_summaries_generated} summaries"
        )

        # Extract data for backward compatibility
        importance_scores = {node.id: node.metrics.importance for node in snapshot.nodes if node.metrics.importance > 0}

        summaries = {node.id: node.summary_body for node in snapshot.nodes if node.summary_body}

        return {
            "tree": {"nodes": snapshot.nodes},
            "importance": importance_scores,
            "summaries": summaries,
        }

    # NOTE: _load_chunks_by_ids는 BaseStage에서 상속받음

    def _build_chunk_to_graph_mapping(self, chunks, graph_doc) -> dict[str, set[str]]:
        """Build mapping from chunk_id to graph_node_ids."""
        from codegraph_engine.code_foundation.infrastructure.chunk.mapping import ChunkGraphMapper

        mapper = ChunkGraphMapper()

        # Use map_graph() which returns dict[chunk_id, set[node_ids]]
        chunk_to_graph = mapper.map_graph(chunks, graph_doc)

        return chunk_to_graph
