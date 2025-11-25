"""
RepoMap Incremental Updater

Efficiently updates RepoMap based on Chunk/Graph changes.

Strategy:
1. Identify affected subtrees from ChunkRefreshResult
2. Rebuild only those subtrees
3. Recompute PageRank for affected subgraph
4. Regenerate summaries only for changed nodes
"""

from typing import Any

from src.foundation.chunk.incremental import ChunkRefreshResult
from src.foundation.chunk.models import Chunk
from src.foundation.graph.models import GraphDocument
from src.repomap.builder import RepoMapBuilder
from src.repomap.models import RepoMapBuildConfig, RepoMapNode, RepoMapSnapshot
from src.repomap.pagerank import GraphAdapter, PageRankAggregator, PageRankEngine
from src.repomap.storage import RepoMapStore
from src.repomap.tree import (
    EntrypointDetector,
    HeuristicMetricsCalculator,
    RepoMapTreeBuilder,
    TestDetector,
)


class RepoMapIncrementalUpdater:
    """
    Incrementally update RepoMap based on chunk/graph changes.

    Optimizations:
    - Only rebuild affected file/module subtrees
    - Partial PageRank recomputation (affected subgraph)
    - Selective summary regeneration
    """

    def __init__(
        self,
        store: RepoMapStore,
        config: RepoMapBuildConfig | None = None,
        llm: Any | None = None,
        chunk_store: Any | None = None,
        repo_path: str | None = None,
    ):
        """
        Initialize incremental updater.

        Args:
            store: RepoMap storage
            config: Build configuration
            llm: Optional LLM for summaries
            chunk_store: Chunk store for content
            repo_path: Repository path for git history
        """
        self.store = store
        self.config = config or RepoMapBuildConfig()
        self.llm = llm
        self.chunk_store = chunk_store
        self.repo_path = repo_path

    def update(
        self,
        repo_id: str,
        snapshot_id: str,
        refresh_result: ChunkRefreshResult,
        all_chunks: list[Chunk],
        graph_doc: GraphDocument | None = None,
    ) -> RepoMapSnapshot:
        """
        Incrementally update RepoMap.

        Args:
            repo_id: Repository identifier
            snapshot_id: New snapshot identifier
            refresh_result: Chunk refresh result with changes
            all_chunks: All chunks (after refresh)
            graph_doc: Optional updated GraphDocument

        Returns:
            Updated RepoMapSnapshot
        """
        # Get previous snapshot
        old_snapshot = self.store.get_snapshot(repo_id, snapshot_id)

        # If no previous snapshot or too many changes, do full rebuild
        if old_snapshot is None or self._should_rebuild_full(refresh_result, old_snapshot):
            return self._rebuild_full(repo_id, snapshot_id, all_chunks, graph_doc)

        # Identify affected files
        affected_files = self._get_affected_files(refresh_result)

        # Rebuild affected subtrees
        updated_nodes = self._rebuild_subtrees(old_snapshot, affected_files, all_chunks, repo_id, snapshot_id)

        # Recompute PageRank (partial if possible)
        if self.config.pagerank_enabled and graph_doc:
            updated_nodes = self._recompute_pagerank(updated_nodes, graph_doc)

        # Recompute metrics
        updated_nodes = self._recompute_metrics(updated_nodes)

        # Create new snapshot
        new_snapshot = RepoMapSnapshot(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            root_node_id=old_snapshot.root_node_id,
            nodes=updated_nodes,
            schema_version=old_snapshot.schema_version,
        )

        # Save and return
        self.store.save_snapshot(new_snapshot)
        return new_snapshot

    def _should_rebuild_full(self, refresh_result: ChunkRefreshResult, old_snapshot: RepoMapSnapshot) -> bool:
        """
        Decide whether to do full rebuild vs incremental update.

        Full rebuild if:
        - More than 50% of files changed
        - Structural changes (module reorganization)
        """
        total_changes = (
            len(refresh_result.added_chunks) + len(refresh_result.updated_chunks) + len(refresh_result.deleted_chunks)
        )

        total_nodes = len(old_snapshot.nodes)

        # If changes exceed 50% threshold, full rebuild is faster
        if total_nodes > 0 and (total_changes / total_nodes) > 0.5:
            return True

        return False

    def _rebuild_full(
        self,
        repo_id: str,
        snapshot_id: str,
        all_chunks: list[Chunk],
        graph_doc: GraphDocument | None,
    ) -> RepoMapSnapshot:
        """Full rebuild using RepoMapBuilder."""
        builder = RepoMapBuilder(
            store=self.store,
            config=self.config,
            llm=self.llm,
            chunk_store=self.chunk_store,
            repo_path=self.repo_path,
        )
        return builder.build(repo_id, snapshot_id, all_chunks, graph_doc)

    def _get_affected_files(self, refresh_result: ChunkRefreshResult) -> set[str]:
        """Extract affected file paths from refresh result."""
        affected = set()

        for chunk in refresh_result.added_chunks + refresh_result.updated_chunks:
            if chunk.file_path:
                affected.add(chunk.file_path)

        for chunk in refresh_result.deleted_chunks:
            if chunk.file_path:
                affected.add(chunk.file_path)

        return affected

    def _rebuild_subtrees(
        self,
        old_snapshot: RepoMapSnapshot,
        affected_files: set[str],
        all_chunks: list[Chunk],
        repo_id: str,
        snapshot_id: str,
    ) -> list[RepoMapNode]:
        """
        Rebuild subtrees for affected files (optimized).

        Strategy:
        1. Build indexes (O(N))
        2. Collect directly affected nodes (O(affected_files))
        3. BFS to mark all descendants (O(N) single pass)
        4. Rebuild affected subtrees from chunks
        5. Merge back

        Time complexity: O(N) instead of O(N²)
        """
        # Step 1: Build indexes for O(1) lookups
        path_to_node = {node.path: node for node in old_snapshot.nodes if node.path}
        id_to_node = {node.id: node for node in old_snapshot.nodes}

        # Step 2: Collect directly affected nodes (by file path)
        affected_node_ids = set()
        for file_path in affected_files:
            node = path_to_node.get(file_path)
            if node:
                affected_node_ids.add(node.id)

        # Step 3: BFS to collect all descendants (single pass)
        # Use queue to process nodes level by level
        from collections import deque

        queue = deque(affected_node_ids)
        visited = set(affected_node_ids)

        while queue:
            node_id = queue.popleft()
            node = id_to_node.get(node_id)
            if not node:
                continue

            # Add all children to affected set
            for child_id in node.children_ids:
                if child_id not in visited:
                    visited.add(child_id)
                    affected_node_ids.add(child_id)
                    queue.append(child_id)

        # Keep unaffected nodes
        kept_nodes = [n for n in old_snapshot.nodes if n.id not in affected_node_ids]

        # Get chunks for affected files
        affected_chunks = [c for c in all_chunks if c.file_path in affected_files]

        # Rebuild affected subtrees
        if affected_chunks:
            tree_builder = RepoMapTreeBuilder(repo_id, snapshot_id)
            new_nodes = tree_builder.build(affected_chunks)

            # Detect entrypoints/tests
            EntrypointDetector.detect(new_nodes)
            TestDetector.detect(new_nodes)

            # Merge
            all_nodes = kept_nodes + new_nodes
        else:
            all_nodes = kept_nodes

        return all_nodes

    def _recompute_pagerank(self, nodes: list[RepoMapNode], graph_doc: GraphDocument) -> list[RepoMapNode]:
        """
        Recompute PageRank scores.

        TODO: Optimize to only recompute affected subgraph.
        For now, recompute全体.
        """
        try:
            pagerank_engine = PageRankEngine(self.config)
            pagerank_scores = pagerank_engine.compute_pagerank(graph_doc)

            # Aggregate to nodes
            aggregator = PageRankAggregator()
            aggregator.aggregate(nodes, pagerank_scores)

            # Compute degree
            adapter = GraphAdapter()
            degree_stats = adapter.get_degree_stats(graph_doc)
            aggregator.compute_degree_for_nodes(nodes, degree_stats)

        except ImportError as e:
            print(f"Warning: PageRank skipped - {e}")

        return nodes

    def _recompute_metrics(self, nodes: list[RepoMapNode]) -> list[RepoMapNode]:
        """Recompute heuristic metrics for nodes."""
        metrics_calc = HeuristicMetricsCalculator(self.config)
        metrics_calc.compute_importance(nodes)
        metrics_calc.boost_entrypoints(nodes)

        if not self.config.include_tests:
            metrics_calc.penalize_tests(nodes)

        return nodes
