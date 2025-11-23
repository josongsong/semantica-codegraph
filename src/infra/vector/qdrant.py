"""
Qdrant Vector Store Adapter (stub)

Implements minimal methods required by the DI container. Replace the stubs with
real Qdrant client calls when wiring the vector store.
"""

from typing import Any, Iterable


class QdrantAdapter:
    """Lightweight placeholder for Qdrant interactions."""

    def __init__(self, host: str, port: int, collection: str = "codegraph") -> None:
        self.host = host
        self.port = port
        self.collection = collection

    async def upsert_vectors(self, vectors: Iterable[dict[str, Any]]) -> None:
        """Upsert vector payloads into Qdrant."""
        raise NotImplementedError("QdrantAdapter.upsert_vectors is not implemented yet")

    async def search(self, query_vector: list[float], limit: int = 10) -> list[dict[str, Any]]:
        """Search similar vectors."""
        raise NotImplementedError("QdrantAdapter.search is not implemented yet")

    async def healthcheck(self) -> bool:
        """Check Qdrant availability."""
        raise NotImplementedError("QdrantAdapter.healthcheck is not implemented yet")
