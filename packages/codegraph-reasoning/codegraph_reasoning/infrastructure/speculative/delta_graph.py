"""
DeltaGraph - Copy-on-Write Graph Overlay

Phase 2 교훈:
- Logging 처음부터
- Error handling 완벽
- Type hints 100%
- 실제 구현 (no placeholder)
"""

import logging
from collections import defaultdict
from typing import Any

from ...domain.speculative_models import Delta, DeltaOperation
from .exceptions import SimulationError

logger = logging.getLogger(__name__)


class DeltaGraph:
    """
    Copy-on-Write 기반 Graph Overlay

    Base graph는 immutable하게 유지하고,
    Delta만으로 변경사항을 표현합니다.

    Example:
        base = Graph(...)
        delta_graph = DeltaGraph(base)

        # Add delta
        delta_graph.apply_delta(Delta(
            operation=DeltaOperation.UPDATE_NODE,
            node_id="node1",
            data={"name": "new_name"}
        ))

        # Query (Copy-on-Write)
        node = delta_graph.get_node("node1")  # Returns updated node

        # Rollback
        delta_graph.rollback(1)

    Performance:
        - get_node: O(1) average
        - apply_delta: O(1)
        - rollback: O(k) where k = rollback count
        - memory: O(deltas) typically < 2x base
    """

    def __init__(self, base_graph: Any, deltas: list[Delta] | None = None):
        """
        Initialize DeltaGraph

        Args:
            base_graph: Base graph (immutable)
            deltas: Initial deltas (optional)

        Raises:
            SimulationError: If base_graph is invalid
        """
        if base_graph is None:
            raise SimulationError("Base graph cannot be None")

        self.base = base_graph

        if not isinstance(base_graph, dict):
            raise SimulationError("Base graph must be a dictionary")

        if "nodes" not in base_graph or "edges" not in base_graph:
            raise SimulationError("Base graph must have 'nodes' and 'edges' keys")
        self.deltas: list[Delta] = deltas or []

        # Index for O(1) lookup
        self._node_index: dict[str, Delta] = {}
        self._edge_index: dict[str, list[Delta]] = defaultdict(list)
        self._deleted_nodes: set[str] = set()
        self._deleted_edges: set[str] = set()

        self._build_index()

        logger.debug(f"DeltaGraph initialized: base={type(base_graph).__name__}, deltas={len(self.deltas)}")

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """
        노드 조회 (Copy-on-Write)

        Resolution order:
        1. Check if deleted → return None
        2. Check delta index → return delta data
        3. Check base graph → return base data

        Args:
            node_id: Node ID

        Returns:
            Node data or None if deleted/not found
        """
        # Check deletion
        if node_id in self._deleted_nodes:
            logger.debug(f"Node {node_id} is deleted in delta")
            return None

        # Check delta
        if node_id in self._node_index:
            delta = self._node_index[node_id]
            logger.debug(f"Node {node_id} found in delta: {delta.operation.value}")
            return delta.new_data

        # Fallback to base
        try:
            base_node = self._get_base_node(node_id)
            if base_node is not None:
                logger.debug(f"Node {node_id} found in base")
            return base_node
        except Exception as e:
            logger.error(f"Error getting base node {node_id}: {e}")
            raise SimulationError(f"Failed to get node {node_id}: {e}") from e

    def get_all_nodes(self) -> dict[str, dict[str, Any]]:
        """
        모든 노드 조회

        Base + Delta merge

        Returns:
            {node_id: node_data}
        """
        # Start with base
        nodes = self._get_all_base_nodes()

        # Apply deltas
        for delta in self.deltas:
            if delta.operation == DeltaOperation.DELETE_NODE:
                nodes.pop(delta.node_id or delta.edge_id, None)

            elif delta.operation in [DeltaOperation.ADD_NODE, DeltaOperation.UPDATE_NODE]:
                nodes[delta.node_id or delta.edge_id] = delta.new_data or {}

        logger.debug(f"get_all_nodes: {len(nodes)} nodes")
        return nodes

    def get_edges(self, node_id: str) -> list[dict[str, Any]]:
        """
        노드의 edges 조회

        Args:
            node_id: Node ID

        Returns:
            List of edges
        """
        edges = []

        # Base edges
        try:
            base_edges = self._get_base_edges(node_id)
            edges.extend(base_edges)
        except Exception as e:
            logger.error(f"Error getting base edges for {node_id}: {e}")

        # Delta edges
        edge_key = f"edges:{node_id}"
        if edge_key in self._edge_index:
            for delta in self._edge_index[edge_key]:
                if delta.operation == DeltaOperation.ADD_EDGE:
                    edges.append(delta.new_data or {})
                elif delta.operation == DeltaOperation.DELETE_EDGE:
                    # Remove matching edge
                    edges = [e for e in edges if e.get("id") != delta.new_data.get("id")]

        return edges

    def apply_delta(self, delta: Delta) -> None:
        """
        Delta 추가 (Stack 구조)

        Args:
            delta: Delta to apply

        Raises:
            SimulationError: If delta is invalid
        """
        if not isinstance(delta, Delta):
            raise SimulationError(f"Invalid delta type: {type(delta)}")

        logger.debug(f"Applying delta: {delta}")

        # Add to stack
        self.deltas.append(delta)

        # Update index
        if delta.operation in [DeltaOperation.ADD_NODE, DeltaOperation.UPDATE_NODE]:
            self._node_index[delta.node_id or delta.edge_id] = delta
            self._deleted_nodes.discard(delta.node_id or delta.edge_id)

        elif delta.operation == DeltaOperation.DELETE_NODE:
            self._node_index.pop(delta.node_id or delta.edge_id, None)
            self._deleted_nodes.add(delta.node_id or delta.edge_id)

        elif delta.operation in [DeltaOperation.ADD_EDGE, DeltaOperation.DELETE_EDGE]:
            edge_key = f"edges:{delta.node_id or delta.edge_id}"
            self._edge_index[edge_key].append(delta)

    def rollback(self, n: int = 1) -> list[Delta]:
        """
        마지막 N개 delta rollback

        Args:
            n: Number of deltas to rollback

        Returns:
            Rolled back deltas

        Raises:
            SimulationError: If n > len(deltas)
        """
        if n > len(self.deltas):
            raise SimulationError(f"Cannot rollback {n} deltas (only {len(self.deltas)} available)")

        if n <= 0:
            return []

        logger.info(f"Rolling back {n} delta(s)")

        # Remove from stack
        rolled_back = []
        for _ in range(n):
            delta = self.deltas.pop()
            rolled_back.append(delta)

        # Rebuild index (simple but correct)
        self._build_index()

        return rolled_back

    def memory_overhead(self) -> int:
        """
        메모리 오버헤드 계산 (bytes)

        Returns:
            Approximate memory overhead in bytes
        """
        import sys

        # Deltas
        total = sys.getsizeof(self.deltas)
        for delta in self.deltas:
            total += sys.getsizeof(delta)
            if delta.new_data:
                total += sys.getsizeof(delta.new_data)
            if delta.metadata:
                total += sys.getsizeof(delta.metadata)

        # Indices
        total += sys.getsizeof(self._node_index)
        total += sys.getsizeof(self._edge_index)
        total += sys.getsizeof(self._deleted_nodes)
        total += sys.getsizeof(self._deleted_edges)

        return total

    def delta_count(self) -> int:
        """Delta 개수"""
        return len(self.deltas)

    def is_modified(self, node_id: str) -> bool:
        """노드가 delta에서 수정되었는가?"""
        return node_id in self._node_index or node_id in self._deleted_nodes

    def _build_index(self) -> None:
        """Delta index 재구성"""
        self._node_index.clear()
        self._edge_index.clear()
        self._deleted_nodes.clear()
        self._deleted_edges.clear()

        for delta in self.deltas:
            if delta.operation in [DeltaOperation.ADD_NODE, DeltaOperation.UPDATE_NODE]:
                self._node_index[delta.node_id or delta.edge_id] = delta

            elif delta.operation == DeltaOperation.DELETE_NODE:
                self._node_index.pop(delta.node_id or delta.edge_id, None)
                self._deleted_nodes.add(delta.node_id or delta.edge_id)

            elif delta.operation in [DeltaOperation.ADD_EDGE, DeltaOperation.DELETE_EDGE]:
                edge_key = f"edges:{delta.node_id or delta.edge_id}"
                self._edge_index[edge_key].append(delta)

    def _get_base_node(self, node_id: str) -> dict[str, Any] | None:
        """
        Base graph에서 노드 조회

        Adapter pattern: base graph type에 따라 다르게 조회
        """
        # Mock base graph (dict)
        if isinstance(self.base, dict):
            return self.base.get("nodes", {}).get(node_id)

        # Graph object with get_node method
        if hasattr(self.base, "get_node"):
            try:
                return self.base.get_node(node_id)
            except (KeyError, AttributeError, TypeError):
                return None

        # Graph object with nodes dict
        if hasattr(self.base, "nodes"):
            return self.base.nodes.get(node_id)

        return None

    def _get_all_base_nodes(self) -> dict[str, dict[str, Any]]:
        """Base graph의 모든 노드"""
        if isinstance(self.base, dict):
            return dict(self.base.get("nodes", {}))

        if hasattr(self.base, "get_all_nodes"):
            try:
                return self.base.get_all_nodes()
            except (KeyError, AttributeError, TypeError):
                return {}

        if hasattr(self.base, "nodes"):
            if isinstance(self.base.nodes, dict):
                return dict(self.base.nodes)

        return {}

    def _get_base_edges(self, node_id: str) -> list[dict[str, Any]]:
        """Base graph의 edges"""
        if isinstance(self.base, dict):
            return self.base.get("edges", {}).get(node_id, [])

        if hasattr(self.base, "get_edges"):
            try:
                return self.base.get_edges(node_id)
            except (KeyError, AttributeError, TypeError):
                return []

        return []

    def __repr__(self) -> str:
        return (
            f"DeltaGraph("
            f"base={type(self.base).__name__}, "
            f"deltas={len(self.deltas)}, "
            f"modified_nodes={len(self._node_index)}, "
            f"deleted_nodes={len(self._deleted_nodes)})"
        )
