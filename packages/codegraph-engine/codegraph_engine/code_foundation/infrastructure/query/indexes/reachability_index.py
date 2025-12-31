"""
ReachabilityIndex - Transitive Closure Cache (SOTA)

Pre-computed reachability for O(1) "can A reach B?" queries.

Architecture:
- Lazy computation (on-demand)
- Sparse matrix storage (only reachable pairs)
- BFS-based transitive closure
- Bloom filter pre-filter for negative queries

Performance:
- Build: O(V * (V + E)) worst case, batched BFS
- Query: O(1) after build
- Memory: O(R) where R = reachable pairs (sparse)

SOTA Reference:
- PostgreSQL recursive CTE WITH RECURSIVE
- Neo4j APOC path algorithms
- Google Pregel for distributed graphs
"""

from collections import deque
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

from .bloom_filter import ReachabilityBloomFilter

if TYPE_CHECKING:
    from ..graph_index import UnifiedGraphIndex

logger = get_logger(__name__)


class ReachabilityIndex:
    """
    Transitive Closure Index for O(1) reachability queries.

    Features:
    - O(1) "can reach?" queries
    - Lazy computation (compute on first query)
    - Bloom filter for quick negative answers
    - Sparse storage (memory efficient)
    - Depth tracking (hop count)

    Usage:
        idx = ReachabilityIndex(graph)
        idx.build()  # Optional: pre-compute

        if idx.can_reach("source", "sink"):
            # There exists a path
            depth = idx.get_distance("source", "sink")

        # Or lazy:
        if idx.can_reach("source", "sink", lazy=True):
            # Computes only if needed
    """

    def __init__(
        self,
        graph: "UnifiedGraphIndex",
        max_depth: int = 20,
        max_sources: int = 1000,
    ):
        """
        Initialize Reachability Index.

        Args:
            graph: UnifiedGraphIndex to analyze
            max_depth: Maximum traversal depth
            max_sources: Maximum number of source nodes to index

        Note:
            For large graphs, consider using lazy mode or
            limiting sources to known entry points (e.g., Q.Call("input")).
        """
        self._graph = graph
        self._max_depth = max_depth
        self._max_sources = max_sources

        # Sparse reachability matrix: source -> {target -> distance}
        self._reachability: dict[str, dict[str, int]] = {}

        # Bloom filter for quick negative answers
        self._bloom = ReachabilityBloomFilter(
            expected_pairs=max_sources * 100,  # Estimate 100 reachable per source
            fpr=0.001,  # 0.1% FPR for fewer false positives
        )

        self._built = False
        self._sources_indexed: set[str] = set()

    def build(self, sources: list[str] | None = None) -> None:
        """
        Build transitive closure from sources.

        Args:
            sources: Specific source nodes to index.
                     If None, indexes all nodes (expensive!).

        Performance:
            O(|sources| * (V + E)) time
            O(|sources| * avg_reachable) memory

        Thread Safety:
            Not thread-safe. Call from QueryEngine with lock.
        """
        if sources is None:
            # Index all nodes (expensive - use sparingly)
            all_nodes = self._graph.get_all_nodes()
            sources = [n.id for n in all_nodes[: self._max_sources]]

        # Limit sources
        sources = sources[: self._max_sources]

        for source in sources:
            if source in self._sources_indexed:
                continue

            reachable = self._compute_reachability_bfs(source)
            self._reachability[source] = reachable
            self._sources_indexed.add(source)

            # Add to bloom filter
            for target in reachable:
                self._bloom.add_reachable(source, target)

        self._built = True
        logger.info(
            "reachability_index_built",
            sources_indexed=len(self._sources_indexed),
            total_pairs=sum(len(v) for v in self._reachability.values()),
            bloom_stats=self._bloom.get_stats(),
        )

    def build_for_source(self, source: str) -> None:
        """
        Lazily build index for a single source.

        Args:
            source: Source node to index

        Use this for lazy/on-demand indexing.
        """
        if source in self._sources_indexed:
            return

        reachable = self._compute_reachability_bfs(source)
        self._reachability[source] = reachable
        self._sources_indexed.add(source)

        # Add to bloom filter
        for target in reachable:
            self._bloom.add_reachable(source, target)

    def _compute_reachability_bfs(self, source: str) -> dict[str, int]:
        """
        Compute all reachable nodes from source using BFS.

        Returns:
            {target_id: distance} for all reachable targets
        """
        reachable: dict[str, int] = {}
        visited: set[str] = {source}
        queue: deque[tuple[str, int]] = deque([(source, 0)])

        while queue:
            current, depth = queue.popleft()

            if depth >= self._max_depth:
                continue

            # Get outgoing edges (forward traversal)
            edges = self._graph.get_outgoing_edges(current)

            for edge in edges:
                target = edge.to_node
                if target not in visited:
                    visited.add(target)
                    new_depth = depth + 1
                    reachable[target] = new_depth
                    queue.append((target, new_depth))

        return reachable

    def can_reach(self, source: str, target: str, lazy: bool = True) -> bool:
        """
        Check if source can reach target.

        Args:
            source: Source node ID
            target: Target node ID
            lazy: If True, compute on-demand if not indexed

        Returns:
            True if path exists, False otherwise

        Performance:
            O(1) if indexed
            O(V + E) if lazy computation needed
        """
        # Quick negative check with bloom filter
        if self._built and self._bloom.definitely_unreachable(source, target):
            return False

        # Check cached reachability
        if source in self._reachability:
            return target in self._reachability[source]

        # Lazy computation
        if lazy:
            self.build_for_source(source)
            return target in self._reachability.get(source, {})

        return False

    def get_distance(self, source: str, target: str) -> int | None:
        """
        Get shortest path distance from source to target.

        Args:
            source: Source node ID
            target: Target node ID

        Returns:
            Hop count if reachable, None otherwise
        """
        if source not in self._reachability:
            return None

        return self._reachability[source].get(target)

    def get_reachable_from(self, source: str) -> set[str]:
        """
        Get all nodes reachable from source.

        Args:
            source: Source node ID

        Returns:
            Set of reachable node IDs
        """
        if source not in self._reachability:
            self.build_for_source(source)

        return set(self._reachability.get(source, {}).keys())

    def invalidate(self, source: str | None = None) -> None:
        """
        Invalidate reachability cache.

        Args:
            source: Specific source to invalidate, or None for all
        """
        if source is None:
            self._reachability.clear()
            self._sources_indexed.clear()
            self._bloom = ReachabilityBloomFilter()
            self._built = False
        elif source in self._sources_indexed:
            del self._reachability[source]
            self._sources_indexed.discard(source)
            # Note: Can't remove from bloom filter (rebuild needed)

    def get_stats(self) -> dict:
        """Get index statistics"""
        return {
            "sources_indexed": len(self._sources_indexed),
            "total_pairs": sum(len(v) for v in self._reachability.values()),
            "max_depth": self._max_depth,
            "built": self._built,
            "bloom_stats": self._bloom.get_stats(),
        }


class BidirectionalReachabilityIndex:
    """
    Bidirectional reachability index for faster path finding.

    Stores both forward and backward reachability.
    Enables meet-in-the-middle optimization.

    Algorithm:
    1. Build forward reachability from sources
    2. Build backward reachability from sinks
    3. For path query: check if forward[source] ∩ backward[sink] non-empty

    Performance:
    - Query: O(min(|forward|, |backward|)) intersection
    - Much faster for source-sink queries
    """

    def __init__(
        self,
        graph: "UnifiedGraphIndex",
        max_depth: int = 10,
    ):
        self._graph = graph
        self._max_depth = max_depth

        # Forward: source -> {reachable targets}
        self._forward: dict[str, set[str]] = {}

        # Backward: sink -> {nodes that can reach sink}
        self._backward: dict[str, set[str]] = {}

    def build_forward(self, source: str) -> set[str]:
        """Build forward reachability from source"""
        if source in self._forward:
            return self._forward[source]

        reachable = self._bfs_forward(source)
        self._forward[source] = reachable
        return reachable

    def build_backward(self, sink: str) -> set[str]:
        """Build backward reachability to sink"""
        if sink in self._backward:
            return self._backward[sink]

        can_reach = self._bfs_backward(sink)
        self._backward[sink] = can_reach
        return can_reach

    def _bfs_forward(self, source: str) -> set[str]:
        """BFS forward from source"""
        reachable: set[str] = set()
        visited: set[str] = {source}
        queue: deque[tuple[str, int]] = deque([(source, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= self._max_depth:
                continue

            edges = self._graph.get_outgoing_edges(current)
            for edge in edges:
                if edge.to_node not in visited:
                    visited.add(edge.to_node)
                    reachable.add(edge.to_node)
                    queue.append((edge.to_node, depth + 1))

        return reachable

    def _bfs_backward(self, sink: str) -> set[str]:
        """BFS backward to sink"""
        can_reach: set[str] = set()
        visited: set[str] = {sink}
        queue: deque[tuple[str, int]] = deque([(sink, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= self._max_depth:
                continue

            edges = self._graph.get_incoming_edges(current)
            for edge in edges:
                if edge.from_node not in visited:
                    visited.add(edge.from_node)
                    can_reach.add(edge.from_node)
                    queue.append((edge.from_node, depth + 1))

        return can_reach

    def can_reach(self, source: str, sink: str) -> bool:
        """
        Check if source can reach sink (meet-in-the-middle).

        Performance: O(min(|forward|, |backward|))
        """
        forward = self.build_forward(source)
        backward = self.build_backward(sink)

        # Check intersection
        if len(forward) < len(backward):
            return sink in forward or bool(forward & backward)
        else:
            return source in backward or bool(forward & backward)

    def get_meeting_points(self, source: str, sink: str) -> set[str]:
        """
        Get nodes where forward and backward paths meet.

        These are potential intermediate nodes on the path.
        """
        forward = self.build_forward(source)
        backward = self.build_backward(sink)
        return forward & backward

    def invalidate(self) -> None:
        """Clear all caches"""
        self._forward.clear()
        self._backward.clear()
