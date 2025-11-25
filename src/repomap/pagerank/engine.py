"""
PageRank Engine

Compute PageRank scores for code graph.

Uses NetworkX implementation of PageRank algorithm.
Supports customizable damping factor and convergence criteria.
"""

try:
    import networkx as nx
except ImportError:
    nx = None  # NetworkX is optional dependency

from src.foundation.graph.models import GraphDocument
from src.repomap.models import RepoMapBuildConfig

from .graph_adapter import GraphAdapter


class PageRankEngine:
    """
    Compute PageRank scores for code graph.

    PageRank measures the importance of nodes based on
    their position in the graph topology.
    """

    def __init__(self, config: RepoMapBuildConfig):
        """
        Initialize PageRank engine.

        Args:
            config: RepoMap build configuration
        """
        self.config = config
        self.adapter = GraphAdapter(
            include_calls=True,
            include_imports=True,
            include_inherits=False,  # Can enable later
            include_references=False,  # Too noisy
        )

    def compute_pagerank(self, graph_doc: GraphDocument) -> dict[str, float]:
        """
        Compute PageRank for all nodes in graph.

        Args:
            graph_doc: GraphDocument with code graph

        Returns:
            Dict mapping node_id to PageRank score (0.0 - 1.0)

        Raises:
            ImportError: If networkx is not installed
        """
        if nx is None:
            raise ImportError("networkx is required for PageRank. Install with: pip install networkx")

        # Build NetworkX graph
        G = self.adapter.build_graph(graph_doc)

        # Handle empty graph
        if len(G.nodes()) == 0:
            return {}

        # Compute PageRank
        pagerank_scores = nx.pagerank(
            G,
            alpha=self.config.pagerank_damping,
            max_iter=self.config.pagerank_max_iterations,
            tol=1e-06,
        )

        return pagerank_scores

    def compute_with_degree(self, graph_doc: GraphDocument) -> dict[str, dict[str, float]]:
        """
        Compute PageRank along with degree centrality.

        Args:
            graph_doc: GraphDocument

        Returns:
            Dict mapping node_id to {pagerank, in_degree, out_degree, degree_centrality}
        """
        if nx is None:
            raise ImportError("networkx is required for PageRank. Install with: pip install networkx")

        # Build graph
        G = self.adapter.build_graph(graph_doc)

        if len(G.nodes()) == 0:
            return {}

        # Compute metrics
        pagerank_scores = nx.pagerank(
            G,
            alpha=self.config.pagerank_damping,
            max_iter=self.config.pagerank_max_iterations,
        )

        degree_centrality = nx.degree_centrality(G)
        in_degree_centrality = nx.in_degree_centrality(G)
        out_degree_centrality = nx.out_degree_centrality(G)

        # Combine results
        results = {}
        for node_id in G.nodes():
            results[node_id] = {
                "pagerank": pagerank_scores[node_id],
                "degree_centrality": degree_centrality[node_id],
                "in_degree_centrality": in_degree_centrality[node_id],
                "out_degree_centrality": out_degree_centrality[node_id],
            }

        return results

    def get_top_nodes(self, graph_doc: GraphDocument, top_n: int = 20) -> list[tuple[str, float]]:
        """
        Get top N nodes by PageRank score.

        Args:
            graph_doc: GraphDocument
            top_n: Number of top nodes to return

        Returns:
            List of (node_id, score) tuples sorted by score descending
        """
        scores = self.compute_pagerank(graph_doc)

        # Sort by score descending
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        return sorted_scores[:top_n]
