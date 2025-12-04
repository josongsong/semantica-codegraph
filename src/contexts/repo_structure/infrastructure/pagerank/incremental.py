"""
Incremental PageRank Engine

Provides optimized PageRank computation for incremental updates.

Implements intelligent change-based strategies:
- Minor changes (<10%): Skip recomputation
- Moderate changes (10-50%): Local propagation algorithm
- Major changes (>50%): Full recomputation
"""

try:
    import networkx as nx
except ImportError:
    nx = None

from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
from src.contexts.repo_structure.infrastructure.models import RepoMapBuildConfig
from src.contexts.repo_structure.infrastructure.pagerank.graph_adapter import GraphAdapter


class IncrementalPageRankEngine:
    """
    Incremental PageRank computation engine.

    Change Ratio Thresholds:
    - Minor (<10%): Skip recomputation, use previous scores.
      Rationale: PageRank is relatively stable for small changes.
      Error bound: ~O(change_ratio) for random walk convergence.
    - Moderate (10-50%): Incremental algorithm with local propagation.
      Rationale: Extract affected subgraph (k-hop neighbors) and run
      localized PageRank with boundary conditions. Much faster than
      full recompute while maintaining accuracy.
    - Major (>50%): Full recompute without personalization.
      Rationale: Graph structure changed significantly, uniform
      random walk is more appropriate.

    Implementation:
    - Minor changes: Return cached scores
    - Moderate changes: BFS-based subgraph extraction + local PageRank
    - Major changes: Full NetworkX PageRank

    References:
    - Bahmani et al., "Fast Incremental and Personalized PageRank" (2010)
    - Ohsaka et al., "Dynamic PageRank: Theory and Applications" (2015)
    """

    def __init__(self, config: RepoMapBuildConfig):
        """
        Initialize incremental PageRank engine.

        Args:
            config: RepoMap build configuration
        """
        self.config = config
        self.adapter = GraphAdapter(
            include_calls=True,
            include_imports=True,
            include_inherits=False,
            include_references=False,
        )

    def compute_with_changes(
        self,
        graph_doc: GraphDocument,
        affected_node_ids: set[str],
        previous_scores: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """
        Compute PageRank with intelligent handling of changes.

        Strategy:
        1. Minor changes (<10%): Return previous scores (or uniform if None)
        2. Moderate changes (10-50%): Incremental algorithm (local propagation)
        3. Major changes (>50%): Full recompute

        Args:
            graph_doc: Updated graph document
            affected_node_ids: Set of changed node IDs
            previous_scores: Previous PageRank scores (optional)

        Returns:
            Dict mapping node_id to PageRank score
        """
        if nx is None:
            raise ImportError("networkx is required for PageRank. Install with: pip install networkx")

        # Build graph
        G = self.adapter.build_graph(graph_doc)

        if len(G.nodes()) == 0:
            return {}

        # Calculate change ratio
        total_nodes = len(G.nodes())
        affected_count = len(affected_node_ids)
        change_ratio = affected_count / total_nodes if total_nodes > 0 else 1.0

        # Strategy 1: Minor changes (<10%) - Skip PageRank
        if change_ratio < 0.1:
            if previous_scores:
                # Return previous scores (still mostly accurate)
                # New nodes will get average score
                avg_score = (
                    sum(previous_scores.values()) / len(previous_scores) if previous_scores else 1.0 / total_nodes
                )
                result = dict(previous_scores)
                for node_id in G.nodes():
                    if node_id not in result:
                        result[node_id] = avg_score
                return result
            else:
                # No previous scores - return uniform
                return dict.fromkeys(G.nodes(), 1.0 / total_nodes)

        # Strategy 2: Moderate changes (10-50%) - Incremental algorithm
        if change_ratio < 0.5 and previous_scores:
            return self._compute_incremental_pagerank(
                G=G,
                affected_node_ids=affected_node_ids,
                previous_scores=previous_scores,
            )

        # Strategy 3: Major changes (>50%) or no previous scores - Full recompute
        if len(G.edges()) == 0:
            # Graph with no edges - return uniform scores
            return dict.fromkeys(G.nodes(), 1.0 / total_nodes)

        # Full PageRank computation
        pagerank_scores = nx.pagerank(
            G,
            alpha=self.config.pagerank_damping,
            max_iter=self.config.pagerank_max_iterations,
            tol=1e-06,
            personalization=self._get_personalization(G, affected_node_ids) if change_ratio < 0.5 else None,
        )

        return pagerank_scores

    def _get_personalization(self, G, affected_node_ids: set[str]) -> dict[str, float] | None:
        """
        Get personalization vector for partial PageRank.

        Biases random walk towards affected nodes for faster convergence.

        Args:
            G: NetworkX graph
            affected_node_ids: Set of affected node IDs

        Returns:
            Personalization vector (None for uniform)
        """
        if not affected_node_ids:
            return None

        # Create personalization vector
        # Affected nodes: higher probability (0.8)
        # Other nodes: lower probability (0.2)
        affected_weight = 0.8
        normal_weight = 0.2

        # Use set intersection for O(min(N,M)) instead of O(N) list comprehension
        graph_nodes = set(G.nodes())
        affected_in_graph = graph_nodes & affected_node_ids
        if not affected_in_graph:
            return None

        # Pre-compute counts once (not in loop)
        affected_count = len(affected_in_graph)
        total_count = len(graph_nodes)
        other_count = total_count - affected_count

        # Pre-compute weights
        affected_node_weight = affected_weight / affected_count
        other_node_weight = normal_weight / other_count if other_count > 0 else 0

        # Single pass over nodes
        personalization = {}
        for node in graph_nodes:
            if node in affected_in_graph:
                personalization[node] = affected_node_weight
            else:
                personalization[node] = other_node_weight

        return personalization

    def _compute_incremental_pagerank(
        self,
        G,
        affected_node_ids: set[str],
        previous_scores: dict[str, float],
        boundary_depth: int = 2,
        max_iterations: int = 50,
    ) -> dict[str, float]:
        """
        Compute incremental PageRank using local propagation.

        Algorithm (based on Bahmani et al. 2010):
        1. Extract affected subgraph (affected nodes + k-hop neighbors)
        2. Run PageRank on subgraph with boundary conditions
        3. Merge subgraph scores with previous scores

        This is much faster than full recompute when only 10-50% of nodes changed.

        Args:
            G: Full NetworkX graph
            affected_node_ids: Set of changed node IDs
            previous_scores: Previous PageRank scores
            boundary_depth: Hops to include around affected nodes (default: 2)
            max_iterations: Max iterations for local PageRank

        Returns:
            Updated PageRank scores
        """
        from collections import deque

        graph_nodes = set(G.nodes())
        total_nodes = len(graph_nodes)

        # If no previous scores or very few nodes, do full recompute
        if not previous_scores or total_nodes < 10:
            return nx.pagerank(
                G,
                alpha=self.config.pagerank_damping,
                max_iter=self.config.pagerank_max_iterations,
            )

        # Step 1: Find affected subgraph via BFS
        subgraph_node_ids: set[str] = set()
        queue: deque[tuple[str, int]] = deque()

        # Initialize with affected nodes
        for node_id in affected_node_ids:
            if node_id in graph_nodes:
                queue.append((node_id, 0))
                subgraph_node_ids.add(node_id)

        # BFS to boundary_depth
        while queue:
            current_id, depth = queue.popleft()
            if depth >= boundary_depth:
                continue

            # Get neighbors (both in and out edges)
            for neighbor in G.predecessors(current_id):
                if neighbor not in subgraph_node_ids:
                    subgraph_node_ids.add(neighbor)
                    queue.append((neighbor, depth + 1))
            for neighbor in G.successors(current_id):
                if neighbor not in subgraph_node_ids:
                    subgraph_node_ids.add(neighbor)
                    queue.append((neighbor, depth + 1))

        # Step 2: Extract subgraph
        subgraph = G.subgraph(subgraph_node_ids).copy()

        if len(subgraph.nodes()) == 0:
            return previous_scores

        # Step 3: Create boundary personalization
        # Boundary nodes (nodes at the edge) get their previous scores as teleport probability
        boundary_nodes = set()
        for node in subgraph_node_ids:
            # Check if any neighbor is outside subgraph
            for neighbor in G.predecessors(node):
                if neighbor not in subgraph_node_ids:
                    boundary_nodes.add(node)
                    break
            else:
                for neighbor in G.successors(node):
                    if neighbor not in subgraph_node_ids:
                        boundary_nodes.add(node)
                        break

        # Personalization: bias towards boundary nodes with their previous scores
        personalization = {}
        for node in subgraph.nodes():
            if node in boundary_nodes and node in previous_scores:
                personalization[node] = previous_scores[node]
            else:
                personalization[node] = 1.0 / len(subgraph.nodes())

        # Normalize personalization
        total = sum(personalization.values())
        if total > 0:
            personalization = {k: v / total for k, v in personalization.items()}

        # Step 4: Run PageRank on subgraph
        if len(subgraph.edges()) == 0:
            # No edges - use uniform for subgraph
            subgraph_scores = {node: 1.0 / len(subgraph.nodes()) for node in subgraph.nodes()}
        else:
            subgraph_scores = nx.pagerank(
                subgraph,
                alpha=self.config.pagerank_damping,
                max_iter=max_iterations,
                personalization=personalization,
                tol=1e-04,  # Slightly looser tolerance for speed
            )

        # Step 5: Merge scores
        # - Subgraph nodes: use new scores
        # - Other nodes: use previous scores (or average if new)
        result = dict(previous_scores)
        avg_score = sum(previous_scores.values()) / len(previous_scores) if previous_scores else 1.0 / total_nodes

        # Update subgraph node scores
        for node_id, score in subgraph_scores.items():
            result[node_id] = score

        # Add new nodes not in previous scores
        for node in graph_nodes:
            if node not in result:
                result[node] = avg_score

        # Remove nodes that no longer exist
        result = {k: v for k, v in result.items() if k in graph_nodes}

        return result

    def extract_affected_subgraph(
        self,
        graph_doc: GraphDocument,
        affected_node_ids: set[str],
        boundary_depth: int = 2,
    ) -> GraphDocument:
        """
        Extract subgraph affected by changes (Phase 2).

        Uses BFS to find all nodes within boundary_depth hops of affected nodes,
        then extracts all edges between these nodes.

        Includes:
        - Affected nodes
        - Neighbors within boundary_depth hops
        - All edges between these nodes

        Args:
            graph_doc: Full graph document
            affected_node_ids: Set of changed node IDs
            boundary_depth: How many hops to include (default: 2)

        Returns:
            Subgraph GraphDocument containing affected nodes and their neighbors
        """
        from collections import deque

        from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument as GD
        from src.contexts.code_foundation.infrastructure.graph.models import GraphIndex

        # Build adjacency for BFS (both directions for undirected traversal)
        adjacency: dict[str, set[str]] = {}
        for edge in graph_doc.graph_edges:
            if edge.source_id not in adjacency:
                adjacency[edge.source_id] = set()
            if edge.target_id not in adjacency:
                adjacency[edge.target_id] = set()
            adjacency[edge.source_id].add(edge.target_id)
            adjacency[edge.target_id].add(edge.source_id)  # Bidirectional for neighbor discovery

        # BFS to find all nodes within boundary_depth
        subgraph_node_ids: set[str] = set()
        queue: deque[tuple[str, int]] = deque()

        # Initialize with affected nodes (depth 0)
        for node_id in affected_node_ids:
            if node_id in graph_doc.graph_nodes:
                queue.append((node_id, 0))
                subgraph_node_ids.add(node_id)

        # BFS traversal
        while queue:
            current_id, depth = queue.popleft()

            if depth >= boundary_depth:
                continue

            # Get neighbors
            neighbors = adjacency.get(current_id, set())
            for neighbor_id in neighbors:
                if neighbor_id not in subgraph_node_ids:
                    subgraph_node_ids.add(neighbor_id)
                    queue.append((neighbor_id, depth + 1))

        # Extract nodes
        subgraph_nodes = {
            node_id: graph_doc.graph_nodes[node_id] for node_id in subgraph_node_ids if node_id in graph_doc.graph_nodes
        }

        # Extract edges (only those with both endpoints in subgraph)
        subgraph_edges = [
            edge
            for edge in graph_doc.graph_edges
            if edge.source_id in subgraph_node_ids and edge.target_id in subgraph_node_ids
        ]

        # Build edge index
        edge_by_id = {edge.id: edge for edge in subgraph_edges}

        # Create new GraphDocument
        return GD(
            repo_id=graph_doc.repo_id,
            snapshot_id=graph_doc.snapshot_id,
            graph_nodes=subgraph_nodes,
            graph_edges=subgraph_edges,
            edge_by_id=edge_by_id,
            indexes=GraphIndex(),  # Will be rebuilt if needed
        )
