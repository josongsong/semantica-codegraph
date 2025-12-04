"""
RepoMap Builder Orchestrator

Coordinates the full RepoMap building pipeline:
1. TreeBuilder: Build node tree from Chunks
2. MetricsCalculator: Compute importance scores
3. Store: Persist snapshot

Phase 1: Tree + Heuristics (MVP)
Phase 2: + PageRank
Phase 3: + LLM Summaries
Phase 4: + Retriever integration
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk
from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
from src.contexts.repo_structure.infrastructure.models import RepoMapBuildConfig, RepoMapSnapshot
from src.contexts.repo_structure.infrastructure.pagerank import PageRankAggregator, PageRankEngine
from src.contexts.repo_structure.infrastructure.storage import RepoMapStore
from src.contexts.repo_structure.infrastructure.summarizer import (
    CostController,
    InMemorySummaryCache,
    SummaryCostConfig,
)
from src.contexts.repo_structure.infrastructure.tree import (
    EntrypointDetector,
    HeuristicMetricsCalculator,
    RepoMapTreeBuilder,
    TestDetector,
)
from src.ports import LLMPort

logger = get_logger(__name__)


class RepoMapBuilder:
    """
    Build complete RepoMap from Chunk layer.

    Usage:
        builder = RepoMapBuilder(store, config)
        snapshot = builder.build(repo_id, snapshot_id, chunks)
    """

    def __init__(
        self,
        store: RepoMapStore,
        config: RepoMapBuildConfig | None = None,
        llm: LLMPort | None = None,
        chunk_store: Any | None = None,
        repo_path: str | None = None,
    ):
        self.store = store
        self.config = config or RepoMapBuildConfig()
        self.llm = llm
        self.chunk_store = chunk_store
        self.repo_path = repo_path

    def build(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list[Chunk],
        graph_doc: GraphDocument | None = None,
        chunk_to_graph: dict[str, set[str]] | None = None,
    ) -> RepoMapSnapshot:
        """
        Build RepoMap snapshot from chunks (synchronous version).

        NOTE: This synchronous version CANNOT generate LLM summaries if called
        from an async context. Use build_async() instead for full functionality
        including LLM summarization.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/commit/branch identifier
            chunks: List of chunks (all hierarchy levels)
            graph_doc: Optional GraphDocument for PageRank computation
            chunk_to_graph: Optional mapping from chunk_id to graph_node_ids for PageRank

        Returns:
            Complete RepoMapSnapshot (without LLM summaries if in async context)
        """
        # Check if we're being called from an async context
        # If asyncio.get_running_loop() succeeds, we're in an async context
        # and cannot use asyncio.run() (would cause "cannot be called from a running event loop" error)
        not_in_async_context = True
        try:
            asyncio.get_running_loop()
            # If we get here, we ARE in an async context
            not_in_async_context = False
        except RuntimeError:
            # If we get here, we are NOT in an async context
            pass

        if not not_in_async_context and self.config.summary_enabled and self.llm:
            logger.warning(
                "RepoMapBuilder.build() called from async context with summary_enabled=True. "
                "LLM summaries will be skipped. Use build_async() instead for full functionality."
            )

        return self._build_sync(
            repo_id, snapshot_id, chunks, graph_doc, chunk_to_graph, enable_summaries=not_in_async_context
        )

    async def build_async(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list[Chunk],
        graph_doc: GraphDocument | None = None,
        chunk_to_graph: dict[str, set[str]] | None = None,
    ) -> RepoMapSnapshot:
        """
        Build RepoMap snapshot from chunks (asynchronous version).

        This version fully supports LLM summarization in both sync and async contexts.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/commit/branch identifier
            chunks: List of chunks (all hierarchy levels)
            graph_doc: Optional GraphDocument for PageRank computation
            chunk_to_graph: Optional mapping from chunk_id to graph_node_ids for PageRank

        Returns:
            Complete RepoMapSnapshot with LLM summaries
        """
        return await self._build_async_impl(repo_id, snapshot_id, chunks, graph_doc, chunk_to_graph)

    def _build_sync(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list[Chunk],
        graph_doc: GraphDocument | None,
        chunk_to_graph: dict[str, set[str]] | None,
        enable_summaries: bool,
    ) -> RepoMapSnapshot:
        """
        Internal synchronous build implementation.

        Args:
            chunk_to_graph: Mapping from chunk_id to graph_node_ids for PageRank
            enable_summaries: Whether to attempt LLM summarization
        """
        # Step 1: Build tree structure
        tree_builder = RepoMapTreeBuilder(repo_id, snapshot_id)
        nodes = tree_builder.build(chunks, chunk_to_graph=chunk_to_graph)

        if not nodes:
            raise ValueError("No nodes generated from chunks")

        # Step 2: Detect entrypoints and tests
        EntrypointDetector.detect(nodes)
        TestDetector.detect(nodes)

        # Step 3: Filter nodes based on config
        nodes = self._filter_nodes(nodes)

        # Step 4: Compute PageRank (Phase 2)
        if self.config.pagerank_enabled and graph_doc is not None:
            try:
                pagerank_engine = PageRankEngine(self.config)
                pagerank_scores = pagerank_engine.compute_pagerank(graph_doc)

                # Aggregate PageRank to RepoMapNodes
                aggregator = PageRankAggregator()
                aggregator.aggregate(nodes, pagerank_scores)

                # Also compute degree centrality
                from src.contexts.repo_structure.infrastructure.pagerank import GraphAdapter

                adapter = GraphAdapter()
                degree_stats = adapter.get_degree_stats(graph_doc)
                aggregator.compute_degree_for_nodes(nodes, degree_stats)

            except ImportError as e:
                # NetworkX not installed, skip PageRank
                logger.warning(f"PageRank skipped - {e}")

        # Step 5: Compute git change frequency (if repo_path available)
        if self.repo_path:
            try:
                from src.contexts.repo_structure.infrastructure.git_history import GitHistoryAnalyzer

                git_analyzer = GitHistoryAnalyzer(self.repo_path)
                git_analyzer.compute_change_freq(nodes, lookback_months=6)
            except Exception as e:
                logger.warning(f"Git history analysis failed - {e}")

        # Step 6: Compute heuristic metrics
        metrics_calc = HeuristicMetricsCalculator(self.config)
        metrics_calc.compute_importance(nodes)
        metrics_calc.boost_entrypoints(nodes)

        if not self.config.include_tests:
            metrics_calc.penalize_tests(nodes)

        # Step 7: Generate LLM summaries (Phase 3) - only if enabled
        if enable_summaries and self.config.summary_enabled and self.llm and self.chunk_store:
            try:
                asyncio.run(self._generate_summaries(nodes))
            except Exception as e:
                logger.error(f"Summary generation failed: {e}", exc_info=True)

        # Step 8: Create snapshot
        root_node = next((n for n in nodes if n.kind == "repo"), None)
        if not root_node:
            raise ValueError("No repo root node found")

        snapshot = RepoMapSnapshot(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            root_node_id=root_node.id,
            nodes=nodes,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "total_nodes": len(nodes),
                "total_loc": sum(n.metrics.loc for n in nodes),
                "total_symbols": sum(n.metrics.symbol_count for n in nodes),
                "config": self.config.model_dump(),
            },
        )

        # Step 9: Save snapshot
        self.store.save_snapshot(snapshot)

        return snapshot

    async def _build_async_impl(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list[Chunk],
        graph_doc: GraphDocument | None,
        chunk_to_graph: dict[str, set[str]] | None,
    ) -> RepoMapSnapshot:
        """
        Internal asynchronous build implementation.

        Identical to _build_sync but with native async support for summaries.
        """
        # Step 1: Build tree structure
        tree_builder = RepoMapTreeBuilder(repo_id, snapshot_id)
        nodes = tree_builder.build(chunks, chunk_to_graph=chunk_to_graph)

        if not nodes:
            raise ValueError("No nodes generated from chunks")

        # Step 2: Detect entrypoints and tests
        EntrypointDetector.detect(nodes)
        TestDetector.detect(nodes)

        # Step 3: Filter nodes based on config
        nodes = self._filter_nodes(nodes)

        # Step 4: Compute PageRank (Phase 2)
        if self.config.pagerank_enabled and graph_doc is not None:
            try:
                pagerank_engine = PageRankEngine(self.config)
                pagerank_scores = pagerank_engine.compute_pagerank(graph_doc)

                # Aggregate PageRank to RepoMapNodes
                aggregator = PageRankAggregator()
                aggregator.aggregate(nodes, pagerank_scores)

                # Also compute degree centrality
                from src.contexts.repo_structure.infrastructure.pagerank import GraphAdapter

                adapter = GraphAdapter()
                degree_stats = adapter.get_degree_stats(graph_doc)
                aggregator.compute_degree_for_nodes(nodes, degree_stats)

            except ImportError as e:
                # NetworkX not installed, skip PageRank
                logger.warning(f"PageRank skipped - {e}")

        # Step 5: Compute git change frequency (if repo_path available)
        if self.repo_path:
            try:
                from src.contexts.repo_structure.infrastructure.git_history import GitHistoryAnalyzer

                git_analyzer = GitHistoryAnalyzer(self.repo_path)
                git_analyzer.compute_change_freq(nodes, lookback_months=6)
            except Exception as e:
                logger.warning(f"Git history analysis failed - {e}")

        # Step 6: Compute heuristic metrics
        metrics_calc = HeuristicMetricsCalculator(self.config)
        metrics_calc.compute_importance(nodes)
        metrics_calc.boost_entrypoints(nodes)

        if not self.config.include_tests:
            metrics_calc.penalize_tests(nodes)

        # Step 7: Generate LLM summaries (Phase 3) - async version
        if self.config.summary_enabled and self.llm and self.chunk_store:
            try:
                await self._generate_summaries(nodes)
            except Exception as e:
                logger.error(f"Summary generation failed: {e}", exc_info=True)

        # Step 8: Create snapshot
        root_node = next((n for n in nodes if n.kind == "repo"), None)
        if not root_node:
            raise ValueError("No repo root node found")

        snapshot = RepoMapSnapshot(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            root_node_id=root_node.id,
            nodes=nodes,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "total_nodes": len(nodes),
                "total_loc": sum(n.metrics.loc for n in nodes),
                "total_symbols": sum(n.metrics.symbol_count for n in nodes),
                "config": self.config.model_dump(),
            },
        )

        # Step 9: Save snapshot
        self.store.save_snapshot(snapshot)

        return snapshot

    def _filter_nodes(self, nodes: list) -> list:
        """
        Filter nodes based on config.

        Filters:
        - Test files (if include_tests=False)
        - Files with LOC < min_loc
        - Nodes with depth > max_depth
        """
        filtered = []

        for node in nodes:
            # Filter tests
            if node.is_test and not self.config.include_tests:
                continue

            # Filter by LOC
            if node.kind == "file" and node.metrics.loc < self.config.min_loc:
                continue

            # Filter by depth
            if node.depth > self.config.max_depth:
                continue

            filtered.append(node)

        return filtered

    def get_snapshot(self, repo_id: str, snapshot_id: str) -> RepoMapSnapshot | None:
        """Get existing snapshot."""
        return self.store.get_snapshot(repo_id, snapshot_id)

    def list_snapshots(self, repo_id: str) -> list[str]:
        """List all snapshots for a repo."""
        return self.store.list_snapshots(repo_id)

    def delete_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """Delete a snapshot."""
        self.store.delete_snapshot(repo_id, snapshot_id)

    async def _generate_summaries(self, nodes: list) -> None:
        """
        Generate LLM summaries for nodes.

        Supports two modes:
        - Hierarchical (NEW): Bottom-up tree summarization
        - Flat (legacy): Independent node summaries

        Hierarchical mode:
        - Leaf nodes: LLM directly summarizes
        - Parent nodes: LLM aggregates child summaries
        - Result: 2-level summaries (overview + detailed)

        Flat mode (legacy):
        - Selects top N% by importance
        - Each node summarized independently
        """
        # Initialize cache and cost control
        cache = InMemorySummaryCache()
        cost_config = SummaryCostConfig()
        cost_controller = CostController(cost_config)

        if self.config.use_hierarchical_summary:
            # NEW: Hierarchical summarization
            from src.contexts.repo_structure.infrastructure.summarizer import HierarchicalSummarizer

            logger.info("Using hierarchical summarization")

            summarizer = HierarchicalSummarizer(
                llm=self.llm,
                cache=cache,
                cost_controller=cost_controller,
                chunk_store=self.chunk_store,
                repo_path=self.repo_path,
            )

            # Summarize entire tree (bottom-up)
            summaries = await summarizer.summarize_tree(
                nodes=nodes,
                max_concurrent=5,
            )

            # Update nodes with 2-level summaries
            summarizer.update_node_summaries(nodes, summaries)

            logger.info(f"Hierarchical summarization completed: {len(summaries)}/{len(nodes)} nodes")

        else:
            # LEGACY: Flat summarization
            from src.contexts.repo_structure.infrastructure.summarizer import LLMSummarizer

            logger.info("Using flat (legacy) summarization")

            # Select nodes to summarize
            candidates = []

            # Add entrypoints if configured
            if self.config.summary_always_entrypoints:
                entrypoints = [n for n in nodes if n.is_entrypoint]
                candidates.extend(entrypoints)

            # Add top N% by importance
            sorted_nodes = sorted(nodes, key=lambda n: n.metrics.importance, reverse=True)
            top_n = int(len(sorted_nodes) * self.config.summary_top_percent)
            top_nodes = sorted_nodes[:top_n]
            candidates.extend(top_nodes)

            # Remove duplicates
            unique_candidates = list({n.id: n for n in candidates}.values())

            if not unique_candidates:
                logger.warning("No candidates for summarization")
                return

            summarizer = LLMSummarizer(
                llm=self.llm,
                cache=cache,
                cost_controller=cost_controller,
                chunk_store=self.chunk_store,
                repo_path=self.repo_path,
            )

            # Generate summaries
            summaries = await summarizer.summarize_nodes(unique_candidates, max_concurrent=5)

            # Update nodes
            summarizer.update_node_summaries(nodes, summaries)

            logger.info(f"Flat summarization completed: {len(summaries)}/{len(unique_candidates)} candidates")


class RepoMapQuery:
    """
    Query interface for RepoMap.

    Provides convenient methods for exploring RepoMap trees.
    """

    def __init__(self, store: RepoMapStore):
        self.store = store

    def get_top_nodes(self, repo_id: str, snapshot_id: str, top_n: int = 20, kind: str | None = None) -> list:
        """
        Get top N most important nodes.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            top_n: Number of nodes to return
            kind: Filter by node kind (optional)

        Returns:
            List of top nodes sorted by importance
        """
        snapshot = self.store.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        nodes = snapshot.nodes
        if kind:
            nodes = [n for n in nodes if n.kind == kind]

        # Sort by importance descending
        sorted_nodes = sorted(nodes, key=lambda n: n.metrics.importance, reverse=True)
        return sorted_nodes[:top_n]

    def get_entrypoints(self, repo_id: str, snapshot_id: str) -> list:
        """Get all entrypoint nodes."""
        snapshot = self.store.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        return [n for n in snapshot.nodes if n.is_entrypoint]

    def get_children(self, node_id: str) -> list:
        """Get direct children of a node."""
        node = self.store.get_node(node_id)
        if not node:
            return []

        return [self.store.get_node(cid) for cid in node.children_ids if self.store.get_node(cid)]

    def get_subtree(self, node_id: str) -> list:
        """Get node and all descendants."""
        return self.store.get_subtree(node_id)

    def search_by_path(self, repo_id: str, snapshot_id: str, path_pattern: str) -> list:
        """
        Search nodes by path pattern.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            path_pattern: Path substring to match

        Returns:
            Matching nodes
        """
        snapshot = self.store.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        return [n for n in snapshot.nodes if n.path and path_pattern in n.path]

    def search_by_name(self, repo_id: str, snapshot_id: str, name_pattern: str) -> list:
        """
        Search nodes by name pattern.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            name_pattern: Name substring to match

        Returns:
            Matching nodes
        """
        snapshot = self.store.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        return [n for n in snapshot.nodes if name_pattern.lower() in n.name.lower()]
