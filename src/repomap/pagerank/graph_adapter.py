"""
Graph Adapter for PageRank

Converts GraphDocument to PageRank input format.

Process:
1. Extract CALLS/IMPORTS edges from GraphDocument
2. Filter by edge kind (configurable)
3. Build NetworkX DiGraph for PageRank computation
"""

from collections import defaultdict

try:
    import networkx as nx
except ImportError:
    nx = None  # NetworkX is optional dependency

from src.foundation.graph.models import GraphDocument, GraphEdgeKind, GraphNodeKind


class GraphAdapter:
    """
    Adapt GraphDocument for PageRank computation.

    Extracts relevant edges and builds NetworkX graph.
    """

    def __init__(
        self,
        include_calls: bool = True,
        include_imports: bool = True,
        include_inherits: bool = False,
        include_references: bool = False,
    ):
        """
        Initialize adapter with edge type filters.

        Args:
            include_calls: Include CALLS edges
            include_imports: Include IMPORTS edges
            include_inherits: Include INHERITS edges
            include_references: Include REFERENCES_TYPE edges
        """
        self.include_calls = include_calls
        self.include_imports = include_imports
        self.include_inherits = include_inherits
        self.include_references = include_references

    def build_graph(self, graph_doc: GraphDocument) -> "nx.DiGraph":
        """
        Build NetworkX DiGraph from GraphDocument.

        Args:
            graph_doc: GraphDocument with nodes and edges

        Returns:
            NetworkX DiGraph with node IDs

        Raises:
            ImportError: If networkx is not installed
        """
        if nx is None:
            raise ImportError("networkx is required for PageRank. Install with: pip install networkx")

        G = nx.DiGraph()

        # Add all nodes (symbols only, exclude CFG blocks, variables)
        for node in graph_doc.graph_nodes.values():
            if self._should_include_node(node.kind):
                G.add_node(node.id, **node.attrs)

        # Add filtered edges
        for edge in graph_doc.graph_edges:
            if self._should_include_edge(edge.kind):
                # Only add edge if both nodes are in graph
                if edge.source_id in G and edge.target_id in G:
                    G.add_edge(edge.source_id, edge.target_id, kind=edge.kind.value)

        return G

    def _should_include_node(self, kind: GraphNodeKind) -> bool:
        """Check if node should be included in PageRank graph."""
        # Include: Functions, Methods, Classes, Modules, Files
        # Exclude: CFG blocks, Variables, Fields (too low-level)
        return kind in {
            GraphNodeKind.FILE,
            GraphNodeKind.MODULE,
            GraphNodeKind.CLASS,
            GraphNodeKind.FUNCTION,
            GraphNodeKind.METHOD,
            GraphNodeKind.EXTERNAL_MODULE,
            GraphNodeKind.EXTERNAL_FUNCTION,
        }

    def _should_include_edge(self, kind: GraphEdgeKind) -> bool:
        """Check if edge should be included in PageRank graph."""
        if kind == GraphEdgeKind.CALLS and self.include_calls:
            return True
        if kind == GraphEdgeKind.IMPORTS and self.include_imports:
            return True
        if kind == GraphEdgeKind.INHERITS and self.include_inherits:
            return True
        if kind == GraphEdgeKind.REFERENCES_TYPE and self.include_references:
            return True
        return False

    def get_degree_stats(self, graph_doc: GraphDocument) -> dict[str, dict[str, int]]:
        """
        Get in-degree and out-degree for all nodes.

        Args:
            graph_doc: GraphDocument

        Returns:
            Dict mapping node_id to {in_degree, out_degree, total_degree}
        """
        in_degree: dict[str, int] = defaultdict(int)
        out_degree: dict[str, int] = defaultdict(int)

        for edge in graph_doc.graph_edges:
            if self._should_include_edge(edge.kind):
                out_degree[edge.source_id] += 1
                in_degree[edge.target_id] += 1

        # Combine stats
        all_nodes = set(in_degree.keys()) | set(out_degree.keys())
        stats = {}
        for node_id in all_nodes:
            in_deg = in_degree[node_id]
            out_deg = out_degree[node_id]
            stats[node_id] = {
                "in_degree": in_deg,
                "out_degree": out_deg,
                "total_degree": in_deg + out_deg,
            }

        return stats
