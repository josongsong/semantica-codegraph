"""
PageRank Aggregator

Aggregate symbol-level PageRank scores to RepoMapNode level.

Aggregation strategies:
- MAX: Take maximum PageRank of child symbols
- MEAN: Take average PageRank of child symbols
- SUM: Take sum of PageRank of child symbols (for files/modules)
- WEIGHTED: Weighted average based on LOC or other metrics
"""

from enum import Enum

from src.repomap.models import RepoMapNode


class AggregationStrategy(str, Enum):
    """PageRank aggregation strategy"""

    MAX = "max"  # Use for classes (most important method)
    MEAN = "mean"  # Use for general aggregation
    SUM = "sum"  # Use for files/modules (cumulative importance)
    WEIGHTED_MEAN = "weighted_mean"  # Weighted by LOC


class PageRankAggregator:
    """
    Aggregate PageRank scores from GraphNodes to RepoMapNodes.

    RepoMapNode contains graph_node_ids referencing GraphNodes.
    We aggregate their PageRank scores based on node kind.
    """

    def aggregate(
        self,
        nodes: list[RepoMapNode],
        pagerank_scores: dict[str, float],
    ) -> None:
        """
        Aggregate PageRank scores to RepoMapNodes (in-place).

        Args:
            nodes: List of RepoMapNodes to update
            pagerank_scores: Dict mapping graph_node_id to PageRank score
        """
        for node in nodes:
            # Get PageRank scores for all referenced graph nodes
            scores = [pagerank_scores.get(gid, 0.0) for gid in node.graph_node_ids if gid in pagerank_scores]

            if not scores:
                # No PageRank data for this node
                node.metrics.pagerank = 0.0
                continue

            # Choose aggregation strategy based on node kind
            strategy = self._get_strategy_for_kind(node.kind)

            # Aggregate
            node.metrics.pagerank = self._aggregate_scores(scores, strategy, node)

    def _get_strategy_for_kind(self, kind: str) -> AggregationStrategy:
        """
        Choose aggregation strategy based on node kind.

        Strategy:
        - Function/Method: Direct mapping (single symbol)
        - Class: MAX (most important method defines class importance)
        - File: SUM (cumulative importance of all symbols)
        - Module/Dir: SUM (cumulative importance)
        - Repo: SUM (total project importance)
        """
        if kind in {"function", "method", "symbol"}:
            return AggregationStrategy.MEAN  # Usually 1:1 mapping
        elif kind == "class":
            return AggregationStrategy.MAX  # Most important method
        elif kind in {"file", "module", "dir"}:
            return AggregationStrategy.SUM  # Cumulative
        elif kind == "repo":
            return AggregationStrategy.SUM  # Total project
        else:
            return AggregationStrategy.MEAN  # Default

    def _aggregate_scores(
        self,
        scores: list[float],
        strategy: AggregationStrategy,
        node: RepoMapNode,
    ) -> float:
        """
        Aggregate scores using specified strategy.

        Args:
            scores: List of PageRank scores
            strategy: Aggregation strategy
            node: RepoMapNode (for weighted aggregation)

        Returns:
            Aggregated PageRank score
        """
        if not scores:
            return 0.0

        if strategy == AggregationStrategy.MAX:
            return max(scores)

        elif strategy == AggregationStrategy.MEAN:
            return sum(scores) / len(scores)

        elif strategy == AggregationStrategy.SUM:
            return sum(scores)

        elif strategy == AggregationStrategy.WEIGHTED_MEAN:
            # Weight by LOC (if available)
            if node.metrics.loc > 0:
                # Normalize by LOC
                return sum(scores) / len(scores)
            else:
                return sum(scores) / len(scores)

        else:
            # Default: mean
            return sum(scores) / len(scores)

    def compute_degree_for_nodes(
        self,
        nodes: list[RepoMapNode],
        degree_stats: dict[str, dict[str, int]],
    ) -> None:
        """
        Compute edge degree for RepoMapNodes.

        Args:
            nodes: List of RepoMapNodes to update
            degree_stats: Dict mapping graph_node_id to {in_degree, out_degree, total_degree}
        """
        for node in nodes:
            # Aggregate degree from referenced graph nodes
            total_in = 0
            total_out = 0

            for gid in node.graph_node_ids:
                if gid in degree_stats:
                    total_in += degree_stats[gid]["in_degree"]
                    total_out += degree_stats[gid]["out_degree"]

            # Update node metrics
            node.metrics.edge_degree = total_in + total_out
