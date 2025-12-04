"""
Qdrant Client

Qdrant 벡터 DB 클라이언트
"""


class QdrantClient:
    """Qdrant 클라이언트 래퍼"""

    def __init__(self, qdrant_adapter):
        """
        초기화

        Args:
            qdrant_adapter: Qdrant 어댑터
        """
        self.qdrant = qdrant_adapter

    async def upsert(self, collection: str, points: list[dict], repo_id: str) -> dict:
        """포인트 업서트"""
        # 실제 Qdrant adapter 호출
        return await self.qdrant.upsert(collection_name=collection, points=points, wait=True)

    async def search(self, collection: str, vector: list[float], limit: int, repo_id: str) -> list[dict]:
        """벡터 검색"""
        return await self.qdrant.search(collection_name=collection, query_vector=vector, limit=limit)

    async def delete(self, collection: str, point_ids: list[str], repo_id: str) -> None:
        """포인트 삭제"""
        await self.qdrant.delete(collection_name=collection, points_selector=point_ids)
