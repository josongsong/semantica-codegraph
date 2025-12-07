"""
In-Memory Graph Store (Memgraph Fallback)

로컬 개발 환경에서 Memgraph 없이 사용할 수 있는 메모리 기반 그래프 저장소.
완전한 그래프 분석 기능은 제공하지 않지만 기본적인 저장/조회는 가능합니다.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class InMemoryGraphStore:
    """
    메모리 기반 그래프 저장소 (Memgraph 대체).

    특징:
    - 메모리에만 저장 (재시작 시 소실)
    - 기본 CRUD 작업 지원
    - 복잡한 그래프 쿼리는 제한적
    - 로컬 개발용으로 적합
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._initialized = False
        logger.info("InMemoryGraphStore initialized (Memgraph fallback mode)")

    def add_node(self, node_id: str, labels: list[str] | None = None, **properties) -> None:
        """
        노드 추가.

        Args:
            node_id: 노드 ID
            labels: 노드 라벨 리스트
            **properties: 노드 속성
        """
        self.nodes[node_id] = {"id": node_id, "labels": labels or [], "properties": properties}

    def add_edge(self, source: str, target: str, edge_type: str = "RELATED", **properties) -> None:
        """
        엣지 추가.

        Args:
            source: 출발 노드 ID
            target: 도착 노드 ID
            edge_type: 엣지 타입
            **properties: 엣지 속성
        """
        self.edges.append({"source": source, "target": target, "type": edge_type, "properties": properties})

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """
        노드 조회.

        Args:
            node_id: 노드 ID

        Returns:
            노드 데이터 또는 None
        """
        return self.nodes.get(node_id)

    def get_edges(
        self, source: str | None = None, target: str | None = None, edge_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        엣지 조회.

        Args:
            source: 출발 노드 ID (optional)
            target: 도착 노드 ID (optional)
            edge_type: 엣지 타입 (optional)

        Returns:
            엣지 리스트
        """
        results = self.edges

        if source:
            results = [e for e in results if e["source"] == source]
        if target:
            results = [e for e in results if e["target"] == target]
        if edge_type:
            results = [e for e in results if e["type"] == edge_type]

        return results

    def query(self, cypher_query: str, **params) -> list[dict[str, Any]]:
        """
        Cypher 쿼리 실행 (제한적 지원).

        Args:
            cypher_query: Cypher 쿼리
            **params: 쿼리 파라미터

        Returns:
            결과 리스트 (빈 리스트 반환 - 복잡한 쿼리 미지원)
        """
        logger.warning(
            "InMemoryGraphStore는 복잡한 Cypher 쿼리를 지원하지 않습니다. 전체 기능을 사용하려면 Memgraph를 설치하세요."
        )
        return []

    def execute(self, cypher_query: str, **params) -> None:
        """
        Cypher 쿼리 실행 (쓰기 작업, 제한적 지원).

        Args:
            cypher_query: Cypher 쿼리
            **params: 쿼리 파라미터
        """
        # 간단한 CREATE/MERGE 파싱 (매우 제한적)
        if "CREATE" in cypher_query.upper() or "MERGE" in cypher_query.upper():
            logger.debug("InMemoryGraphStore: 쿼리 무시 (제한적 지원)")
        else:
            logger.warning("InMemoryGraphStore: 복잡한 쿼리는 지원하지 않습니다")

    def clear(self) -> None:
        """모든 데이터 삭제."""
        self.nodes.clear()
        self.edges.clear()
        logger.info("InMemoryGraphStore cleared")

    def close(self) -> None:
        """연결 종료 (no-op)."""
        logger.info("InMemoryGraphStore closed")

    def health_check(self) -> bool:
        """
        헬스 체크.

        Returns:
            항상 True (메모리 저장소)
        """
        return True

    def get_stats(self) -> dict[str, int]:
        """
        통계 조회.

        Returns:
            노드/엣지 개수
        """
        return {"nodes": len(self.nodes), "edges": len(self.edges)}

    # ========================================================================
    # Batch Operations (Memgraph 호환성)
    # ========================================================================

    def batch_add_nodes(self, nodes: list[dict[str, Any]]) -> None:
        """
        노드 배치 추가.

        Args:
            nodes: 노드 리스트
        """
        for node in nodes:
            node_id = node.get("id")
            labels = node.get("labels", [])
            properties = node.get("properties", {})

            if node_id:
                self.add_node(node_id, labels, **properties)

    def batch_add_edges(self, edges: list[dict[str, Any]]) -> None:
        """
        엣지 배치 추가.

        Args:
            edges: 엣지 리스트
        """
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            edge_type = edge.get("type", "RELATED")
            properties = edge.get("properties", {})

            if source and target:
                self.add_edge(source, target, edge_type, **properties)

    # ========================================================================
    # Context Manager
    # ========================================================================

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
