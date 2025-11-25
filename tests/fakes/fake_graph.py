"""
Fake Graph Store for Unit Testing

외부 Kùzu 없이 in-memory 그래프로 동작하는 GraphStorePort 구현.
"""

from collections import defaultdict
from typing import Any


class FakeGraphStore:
    """
    GraphStorePort Fake 구현.

    in-memory adjacency list 기반 그래프.
    """

    def __init__(self):
        # node_id -> node data
        self.nodes: dict[str, dict[str, Any]] = {}
        # (from_id, edge_type) -> [to_id, ...]
        self.edges: dict[tuple, list[str]] = defaultdict(list)
        # (to_id, edge_type) -> [from_id, ...] (reverse index)
        self.reverse_edges: dict[tuple, list[str]] = defaultdict(list)

    def add_node(self, node_id: str, node_type: str, properties: dict[str, Any]):
        """노드 추가."""
        self.nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            **properties,
        }

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ):
        """엣지 추가."""
        key = (from_id, edge_type)
        if to_id not in self.edges[key]:
            self.edges[key].append(to_id)

        # Reverse index
        reverse_key = (to_id, edge_type)
        if from_id not in self.reverse_edges[reverse_key]:
            self.reverse_edges[reverse_key].append(from_id)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """노드 조회."""
        return self.nodes.get(node_id)

    def get_neighbors(
        self,
        node_id: str,
        edge_type: str,
        direction: str = "outgoing",
    ) -> list[dict[str, Any]]:
        """
        이웃 노드 조회.

        Args:
            node_id: 시작 노드 ID
            edge_type: 엣지 타입 (예: "CALLS", "IMPORTS")
            direction: "outgoing" 또는 "incoming"

        Returns:
            이웃 노드 리스트
        """
        if direction == "outgoing":
            neighbor_ids = self.edges.get((node_id, edge_type), [])
        else:  # incoming
            neighbor_ids = self.reverse_edges.get((node_id, edge_type), [])

        return [self.nodes[nid] for nid in neighbor_ids if nid in self.nodes]

    def traverse(
        self,
        start_id: str,
        edge_types: list[str],
        max_depth: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Multi-hop 그래프 탐색 (BFS).

        Args:
            start_id: 시작 노드 ID
            edge_types: 탐색할 엣지 타입 리스트
            max_depth: 최대 깊이

        Returns:
            방문한 노드 리스트
        """
        visited = set()
        queue = [(start_id, 0)]  # (node_id, depth)
        result = []

        while queue:
            node_id, depth = queue.pop(0)

            if node_id in visited or depth > max_depth:
                continue

            visited.add(node_id)
            if node_id in self.nodes:
                result.append(self.nodes[node_id])

            # 다음 레벨 탐색
            if depth < max_depth:
                for edge_type in edge_types:
                    neighbors = self.edges.get((node_id, edge_type), [])
                    for neighbor_id in neighbors:
                        if neighbor_id not in visited:
                            queue.append((neighbor_id, depth + 1))

        return result

    async def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get symbols that call this symbol.

        Args:
            symbol_id: Symbol ID to find callers for

        Returns:
            List of caller nodes
        """
        # Callers are nodes that have CALLS edges TO this symbol
        return self.get_neighbors(symbol_id, edge_type="CALLS", direction="incoming")

    async def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get symbols called by this symbol.

        Args:
            symbol_id: Symbol ID to find callees for

        Returns:
            List of callee nodes
        """
        # Callees are nodes that this symbol CALLS
        return self.get_neighbors(symbol_id, edge_type="CALLS", direction="outgoing")

    def query(self, cypher_like: str) -> list[dict[str, Any]]:
        """
        간단한 쿼리 시뮬레이션.

        실제 Cypher는 지원하지 않고, 테스트용 minimal 구현.
        """
        # TODO: 필요시 확장
        return []

    def clear(self):
        """모든 데이터 삭제."""
        self.nodes.clear()
        self.edges.clear()
        self.reverse_edges.clear()
