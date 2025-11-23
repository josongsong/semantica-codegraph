from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from core.chunking.hcr import Chunk
from core.core.config import settings


class VectorStore:
    """Qdrant 벡터 저장소"""

    def __init__(self):
        self.client = QdrantClient(url=settings.qdrant_url)
        self.collection_name = settings.qdrant_collection_name

    def create_collection(self, vector_size: int = 1536):
        """컬렉션 생성"""
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert_chunks(self, chunks: list[Chunk]):
        """청크 저장"""
        points = []
        for idx, chunk in enumerate(chunks):
            if chunk.embedding is not None:
                point = PointStruct(
                    id=idx,
                    vector=chunk.embedding.tolist(),
                    payload={
                        "content": chunk.content,
                        "file_path": chunk.file_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "level": chunk.level,
                        "metadata": chunk.metadata,
                    },
                )
                points.append(point)

        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)

    def search(self, query_vector: list[float], limit: int = 10, level: Optional[int] = None):
        """벡터 검색"""
        query_filter = None
        if level is not None:
            query_filter = {"level": {"$eq": level}}

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
        )

        return results

    def delete_collection(self):
        """컬렉션 삭제"""
        self.client.delete_collection(collection_name=self.collection_name)
