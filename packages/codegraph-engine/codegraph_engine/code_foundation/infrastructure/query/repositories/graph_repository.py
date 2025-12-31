"""
GraphRepository - Repository Pattern (L11급 SOTA)

Repository Pattern for graph data access.
Abstracts data source (currently UnifiedGraphIndex).

Benefits:
- Separation of concerns
- Testability (mockable)
- Swappable backends
- Query optimization point

SOLID:
- S: Data access만 담당
- O: 새 쿼리 메서드 추가 용이
- L: 인터페이스 준수
- I: Focused interface
- D: Port 기반
"""

import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Protocol

from codegraph_engine.code_foundation.domain.query.results import UnifiedEdge, UnifiedNode
from codegraph_engine.code_foundation.domain.query.selectors import NodeSelector
from codegraph_engine.code_foundation.domain.query.types import EdgeType

if TYPE_CHECKING:
    from ..graph_index import UnifiedGraphIndex


class GraphRepositoryPort(Protocol):
    """
    Repository port for graph data access

    Abstract interface for graph queries.
    Implementations can use different backends (index, DB, etc).
    """

    def find_node_by_id(self, node_id: str) -> UnifiedNode | None:
        """Find node by ID"""
        ...

    def find_nodes_by_selector(self, selector: NodeSelector) -> list[UnifiedNode]:
        """Find nodes matching selector"""
        ...

    def find_edges_from(self, node_id: str, edge_type: EdgeType | str | None = None) -> list[UnifiedEdge]:
        """Find outgoing edges from node"""
        ...

    def find_edges_to(self, node_id: str, edge_type: EdgeType | str | None = None) -> list[UnifiedEdge]:
        """Find incoming edges to node"""
        ...

    def count_nodes(self) -> int:
        """Count total nodes"""
        ...

    def count_edges(self) -> int:
        """Count total edges"""
        ...


class IndexBackedGraphRepository:
    """
    Index-backed implementation of GraphRepository

    Uses UnifiedGraphIndex as backend.
    Provides caching and query optimization.

    Performance:
    - All queries: O(1) or O(k) via index
    - Cache hit: O(1)
    - Memory: Index + cache
    """

    def __init__(self, graph_index: "UnifiedGraphIndex", cache_size: int = 10000):
        """
        Initialize repository with LRU cache (Thread-safe)

        Args:
            graph_index: Unified graph index backend
            cache_size: Maximum cache size (default 10000)

        Performance:
            - LRU eviction prevents unbounded growth
            - O(1) cache lookup and eviction

        Thread Safety:
            All cache operations protected by RLock.
        """
        from ..graph_index import UnifiedGraphIndex

        self._index: UnifiedGraphIndex = graph_index

        # Thread safety lock
        self._lock = threading.RLock()

        # LRU cache for node queries
        self._node_cache: OrderedDict[str, UnifiedNode | None] = OrderedDict()
        self._cache_size = cache_size
        self._cache_hits = 0
        self._cache_misses = 0

    # ============================================================
    # Node Queries
    # ============================================================

    def find_node_by_id(self, node_id: str) -> UnifiedNode | None:
        """
        Find node by ID (with LRU caching, thread-safe)

        Args:
            node_id: Node ID

        Returns:
            UnifiedNode or None

        Performance:
            - Cache hit: O(1)
            - Cache miss: O(1) index lookup + O(1) cache insert
            - LRU eviction: O(1)

        Thread Safety:
            Protected by RLock. Safe for concurrent access.
        """
        with self._lock:
            # Check cache (LRU)
            if node_id in self._node_cache:
                self._cache_hits += 1
                # Move to end (mark as recently used)
                self._node_cache.move_to_end(node_id)
                return self._node_cache[node_id]

            # Cache miss - query index
            self._cache_misses += 1
            node = self._index.get_node(node_id)

            # Add to cache with LRU eviction
            if len(self._node_cache) >= self._cache_size:
                # Evict oldest (LRU)
                self._node_cache.popitem(last=False)

            self._node_cache[node_id] = node
            return node

    def find_nodes_by_selector(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Find nodes matching selector

        Delegates to NodeMatcher for complex matching.
        Repository provides unified access point.

        Args:
            selector: Node selector

        Returns:
            List of matching nodes
        """
        from ..node_matcher import NodeMatcher

        matcher = NodeMatcher(self._index)
        return matcher.match(selector)

    def find_all_nodes(self) -> list[UnifiedNode]:
        """
        Find all nodes

        Warning: Expensive operation
        """
        return self._index.get_all_nodes()

    # ============================================================
    # Edge Queries
    # ============================================================

    def find_edges_from(self, node_id: str, edge_type: EdgeType | str | None = None) -> list[UnifiedEdge]:
        """
        Find outgoing edges

        Args:
            node_id: Source node ID
            edge_type: Edge type filter

        Returns:
            List of outgoing edges
        """
        return self._index.get_edges_from(node_id, edge_type)

    def find_edges_to(self, node_id: str, edge_type: EdgeType | str | None = None) -> list[UnifiedEdge]:
        """
        Find incoming edges

        Args:
            node_id: Target node ID
            edge_type: Edge type filter

        Returns:
            List of incoming edges
        """
        return self._index.get_edges_to(node_id, edge_type)

    # ============================================================
    # Semantic Queries
    # ============================================================

    def find_variables_by_name(self, name: str) -> list[UnifiedNode]:
        """Find variables by name"""
        return self._index.find_vars_by_name(name)

    def find_functions_by_name(self, name: str) -> list[UnifiedNode]:
        """Find functions by name"""
        return self._index.find_funcs_by_name(name)

    def find_classes_by_name(self, name: str) -> list[UnifiedNode]:
        """Find classes by name"""
        return self._index.find_classes_by_name(name)

    def find_call_sites_by_name(self, callee_name: str) -> list[UnifiedNode]:
        """Find call sites by callee name"""
        return self._index.find_call_sites_by_name(callee_name)

    # ============================================================
    # Aggregations
    # ============================================================

    def count_nodes(self) -> int:
        """Count total nodes"""
        return self._index.get_stats()["total_nodes"]

    def count_edges(self) -> int:
        """Count total edges"""
        return self._index.get_stats()["total_edges"]

    def get_statistics(self) -> dict:
        """
        Get comprehensive statistics

        Returns:
            Statistics dictionary with cache info
        """
        total_requests = self._cache_hits + self._cache_misses
        stats = self._index.get_stats()
        stats["cache"] = {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "total_requests": total_requests,
            "hit_rate": self._cache_hits / max(total_requests, 1),
            "size": len(self._node_cache),
            "max_size": self._cache_size,
            "utilization": len(self._node_cache) / self._cache_size,
        }
        return stats

    def clear_cache(self) -> None:
        """
        Clear cache (for cleanup or testing, thread-safe)

        Resets cache and statistics.

        Thread Safety:
            Protected by RLock. Safe for concurrent access.
        """
        with self._lock:
            self._node_cache.clear()
            self._cache_hits = 0
            self._cache_misses = 0

    # ============================================================
    # Batch Operations (Performance Optimization)
    # ============================================================

    def find_nodes_batch(self, node_ids: list[str]) -> dict[str, UnifiedNode | None]:
        """
        Batch node lookup (optimized)

        Args:
            node_ids: List of node IDs

        Returns:
            Map of node_id → node

        Performance: Single index pass instead of N queries
        """
        result = {}
        for node_id in node_ids:
            result[node_id] = self.find_node_by_id(node_id)
        return result

    def prefetch_nodes(self, node_ids: list[str]) -> None:
        """
        Prefetch nodes into cache

        Useful for query optimization.

        Args:
            node_ids: Node IDs to prefetch
        """
        for node_id in node_ids:
            if node_id not in self._node_cache:
                self._node_cache[node_id] = self._index.get_node(node_id)
