"""
Mock Vector Store for Testing

In-memory implementation of VectorStorePort.
"""

from typing import Any, Optional

import numpy as np

from ...core.domain.chunks import VectorChunkPayload
from ...core.ports.vector_store import VectorStorePort


class MockVectorStore(VectorStorePort):
    """
    In-memory mock vector store for testing.
    """

    def __init__(self):
        """Initialize mock storage."""
        self.collections: dict[str, dict[str, Any]] = {}

    async def upsert_chunks(
        self,
        collection_name: str,
        chunks: list[VectorChunkPayload],
        vectors: list[list[float]],
    ) -> None:
        """Store chunks in memory."""
        if collection_name not in self.collections:
            self.collections[collection_name] = {"vectors": [], "payloads": []}

        for chunk, vector in zip(chunks, vectors, strict=False):
            self.collections[collection_name]["vectors"].append(vector)
            self.collections[collection_name]["payloads"].append(chunk.model_dump())

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Perform cosine similarity search."""
        if collection_name not in self.collections:
            return []

        # Simple cosine similarity
        vectors = np.array(self.collections[collection_name]["vectors"])
        query = np.array(query_vector)

        similarities = np.dot(vectors, query) / (
            np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
        )

        # Get top k
        top_indices = np.argsort(similarities)[::-1][:limit]

        results = []
        for idx in top_indices:
            results.append(
                {
                    "score": float(similarities[idx]),
                    "payload": self.collections[collection_name]["payloads"][idx],
                }
            )

        return results

    async def delete_by_filter(
        self,
        collection_name: str,
        filters: dict[str, Any],
    ) -> int:
        """Delete matching chunks."""
        # TODO: Implement filtering
        return 0

    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance_metric: str = "cosine",
    ) -> None:
        """Create collection."""
        self.collections[collection_name] = {"vectors": [], "payloads": []}

    async def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists."""
        return collection_name in self.collections

    async def get_chunk_by_id(
        self,
        collection_name: str,
        chunk_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get chunk by ID."""
        if collection_name not in self.collections:
            return None

        for payload in self.collections[collection_name]["payloads"]:
            if payload.get("id") == chunk_id:
                return payload

        return None
