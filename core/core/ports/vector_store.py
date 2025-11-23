"""
Vector Store Port

Abstract interface for vector database operations.
Implementations: Qdrant, Pinecone, Weaviate, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from ..domain.chunks import VectorChunkPayload


class VectorStorePort(ABC):
    """
    Port for vector database operations.

    Responsibilities:
    - Store and retrieve vector embeddings
    - Perform similarity search
    - Manage collections/indexes
    """

    @abstractmethod
    async def upsert_chunks(
        self,
        collection_name: str,
        chunks: List[VectorChunkPayload],
        vectors: List[List[float]],
    ) -> None:
        """
        Insert or update chunks with their vector embeddings.

        Args:
            collection_name: Name of the collection/index
            chunks: Chunk payloads to store
            vectors: Corresponding embedding vectors
        """
        pass

    @abstractmethod
    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search.

        Args:
            collection_name: Collection to search in
            query_vector: Query embedding vector
            limit: Maximum number of results
            filters: Optional metadata filters

        Returns:
            List of search results with scores and payloads
        """
        pass

    @abstractmethod
    async def delete_by_filter(
        self,
        collection_name: str,
        filters: Dict[str, Any],
    ) -> int:
        """
        Delete chunks matching filters.

        Args:
            collection_name: Collection to delete from
            filters: Metadata filters

        Returns:
            Number of deleted chunks
        """
        pass

    @abstractmethod
    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance_metric: str = "cosine",
    ) -> None:
        """
        Create a new collection/index.

        Args:
            collection_name: Name for the new collection
            vector_size: Dimension of vectors
            distance_metric: Distance metric (cosine, euclidean, dot)
        """
        pass

    @abstractmethod
    async def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        pass

    @abstractmethod
    async def get_chunk_by_id(
        self,
        collection_name: str,
        chunk_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific chunk by ID.

        Args:
            collection_name: Collection to search in
            chunk_id: Chunk identifier

        Returns:
            Chunk payload if found, None otherwise
        """
        pass
