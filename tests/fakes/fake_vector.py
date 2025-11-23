"""
Fake Vector Store for Unit Testing

외부 Qdrant 없이 in-memory로 동작하는 VectorStorePort 구현.
Behavior-driven: 실제 유사도 검색 시뮬레이션.
"""

from typing import Any

import numpy as np


class FakeVectorStore:
    """
    VectorStorePort Fake 구현.

    in-memory storage + cosine similarity 기반 검색.
    """

    def __init__(self):
        self.vectors: dict[str, np.ndarray] = {}
        self.payloads: dict[str, dict[str, Any]] = {}
        self.collection_name: str | None = None

    def create_collection(self, name: str, vector_size: int):
        """컬렉션 생성."""
        self.collection_name = name
        self.vectors.clear()
        self.payloads.clear()

    def upsert(
        self,
        collection_name: str,
        points: list[dict[str, Any]],
    ):
        """벡터 삽입/업데이트."""
        for point in points:
            point_id = point["id"]
            vector = np.array(point["vector"])
            payload = point.get("payload", {})

            self.vectors[point_id] = vector
            self.payloads[point_id] = payload

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filter_: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Cosine similarity 기반 검색.

        Args:
            collection_name: 컬렉션 이름
            query_vector: 쿼리 벡터
            limit: 결과 수
            filter_: 페이로드 필터 (선택)

        Returns:
            검색 결과 (id, score, payload)
        """
        query = np.array(query_vector)
        results = []

        for point_id, vector in self.vectors.items():
            # Filter 적용
            if filter_:
                payload = self.payloads[point_id]
                if not self._match_filter(payload, filter_):
                    continue

            # Cosine similarity
            score = self._cosine_similarity(query, vector)
            results.append(
                {
                    "id": point_id,
                    "score": float(score),
                    "payload": self.payloads[point_id],
                }
            )

        # 점수 내림차순 정렬
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def delete(self, collection_name: str, point_ids: list[str]):
        """벡터 삭제."""
        for point_id in point_ids:
            self.vectors.pop(point_id, None)
            self.payloads.pop(point_id, None)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity 계산."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def _match_filter(self, payload: dict, filter_: dict) -> bool:
        """
        간단한 필터 매칭.

        filter = {"key": "value"} 형태만 지원.
        """
        for key, value in filter_.items():
            if payload.get(key) != value:
                return False
        return True
