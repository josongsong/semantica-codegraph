"""
Qdrant Vector Store Adapter

Provides async Qdrant operations for vector storage and similarity search.

Features:
- Lazy client initialization
- Collection management
- Vector upsert operations
- Similarity search with filtering
- Point retrieval and deletion
- Health checks

Requirements:
    pip install qdrant-client
"""

import asyncio
import uuid
from typing import Any, cast

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.conversions.common_types import Filter

from src.common.observability import get_logger
from src.common.utils import LazyClientInitializer

logger = get_logger(__name__)


class QdrantAdapter:
    """
    Production Qdrant adapter with async support.

    Uses qdrant-client for vector operations.
    Automatically handles collection creation and management.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        grpc_port: int = 6334,
        collection: str = "codegraph",
        prefer_grpc: bool = True,
        upsert_concurrency: int = 4,
    ) -> None:
        """
        Initialize Qdrant adapter.

        Args:
            host: Qdrant host (default: localhost)
            port: Qdrant HTTP port (default: 6333)
            grpc_port: Qdrant gRPC port (default: 6334)
            collection: Collection name (default: codegraph)
            prefer_grpc: Use gRPC for better performance (default: True)
            upsert_concurrency: Max concurrent upsert batches (default: 4)
        """
        self.host = host
        self.port = port
        self.grpc_port = grpc_port
        self.collection = collection
        self.prefer_grpc = prefer_grpc
        self.upsert_concurrency = upsert_concurrency
        self._client_init: LazyClientInitializer[AsyncQdrantClient] = LazyClientInitializer()

    async def _get_client(self) -> AsyncQdrantClient:
        """
        Get or create Qdrant client (lazy initialization).

        Returns:
            AsyncQdrantClient instance
        """

        def create_client() -> AsyncQdrantClient:
            client = AsyncQdrantClient(
                host=self.host,
                port=self.port,
                grpc_port=self.grpc_port,
                prefer_grpc=self.prefer_grpc,
                timeout=60,
            )
            logger.info(
                f"Qdrant client initialized: host={self.host}, grpc={self.prefer_grpc}, grpc_port={self.grpc_port}"
            )
            return client

        return await self._client_init.get_or_create(create_client)

    async def _ensure_collection(self, vector_size: int = 1536) -> None:
        """
        Ensure collection exists, create if not.

        Args:
            vector_size: Vector dimension size (default: 1536 for OpenAI embeddings)
        """
        client = await self._get_client()

        # Check if collection exists
        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if self.collection not in collection_names:
            logger.info(f"Creating collection: {self.collection}")
            await client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"Collection created: {self.collection}")

    async def upsert_vectors(self, vectors: list[dict[str, Any]]) -> None:
        """
        Upsert vector payloads into Qdrant.

        Each vector dict should contain:
        - id (optional): Point ID (UUID generated if not provided)
        - vector (required): List of floats
        - payload (optional): Metadata dict

        Args:
            vectors: List of vector dictionaries

        Raises:
            RuntimeError: If upsert fails
        """
        try:
            if not vectors:
                return

            # Ensure collection exists (use first vector's size)
            if "vector" not in vectors[0]:
                raise RuntimeError("Vector data is missing in first item")

            vector_size = len(vectors[0]["vector"])
            await self._ensure_collection(vector_size)

            client = await self._get_client()

            # Build points for upsert
            points = []
            for vec in vectors:
                if "vector" not in vec:
                    logger.warning(f"Skipping vector without 'vector' field: {vec}")
                    continue

                # Ensure point ID is UUID format (required by Qdrant)
                point_id_raw = vec.get("id")
                if point_id_raw:
                    try:
                        # Validate as UUID
                        uuid.UUID(str(point_id_raw))
                        point_id = str(point_id_raw)
                    except ValueError:
                        # Not a valid UUID, generate new one
                        logger.warning(f"ID '{point_id_raw}' is not UUID format, generating UUID")
                        point_id = str(uuid.uuid4())
                else:
                    point_id = str(uuid.uuid4())

                vector_data = vec["vector"]
                payload = vec.get("payload", {})

                point = models.PointStruct(
                    id=point_id,
                    vector=vector_data,
                    payload=payload,
                )
                points.append(point)

            # Batch and parallel upsert for performance
            batch_size = 256  # Qdrant recommended batch size
            batches = [points[i : i + batch_size] for i in range(0, len(points), batch_size)]

            if len(batches) <= 1:
                # Single batch - no parallelization needed
                await client.upsert(collection_name=self.collection, points=points)
            else:
                # Parallel upsert with concurrency limit
                semaphore = asyncio.Semaphore(self.upsert_concurrency)

                async def upsert_batch(batch: list[models.PointStruct]) -> None:
                    async with semaphore:
                        await client.upsert(collection_name=self.collection, points=batch)

                await asyncio.gather(*[upsert_batch(batch) for batch in batches])

            logger.info(
                f"Upserted {len(points)} vectors to {self.collection} "
                f"({len(batches)} batches, concurrency={self.upsert_concurrency})"
            )

        except Exception as e:
            logger.error(f"Failed to upsert vectors: {e}")
            raise RuntimeError(f"Failed to upsert vectors: {e}") from e

    async def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search similar vectors.

        Args:
            query_vector: Query vector
            limit: Maximum results (default: 10)
            score_threshold: Minimum similarity score (optional)
            filter_dict: Metadata filter (optional)

        Returns:
            List of result dictionaries with keys:
                - id: Point ID
                - score: Similarity score
                - payload: Metadata

        Raises:
            RuntimeError: If search fails
        """
        try:
            # Ensure collection exists
            await self._ensure_collection(len(query_vector))

            client = await self._get_client()

            # Build filter if provided
            query_filter = None
            if filter_dict:
                query_filter = filter_dict

            # Search
            search_results = await client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=cast(Filter | None, query_filter),
            )

            # Convert to dict format
            results = []
            for hit in search_results:
                results.append(
                    {
                        "id": hit.id,
                        "score": hit.score,
                        "payload": hit.payload or {},
                    }
                )

            logger.debug(f"Search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Failed to search vectors: {e}")
            raise RuntimeError(f"Failed to search vectors: {e}") from e

    async def get_by_id(self, point_id: str) -> dict[str, Any] | None:
        """
        Retrieve point by ID.

        Args:
            point_id: Point ID

        Returns:
            Point dict with id, vector, payload or None if not found
        """
        try:
            client = await self._get_client()

            points = await client.retrieve(
                collection_name=self.collection,
                ids=[point_id],
                with_vectors=True,
            )

            if not points:
                return None

            point = points[0]
            return {
                "id": point.id,
                "vector": point.vector,
                "payload": point.payload or {},
            }

        except Exception as e:
            logger.error(f"Failed to retrieve point {point_id}: {e}")
            return None

    async def delete_by_id(self, point_ids: list[str]) -> None:
        """
        Delete points by IDs.

        Args:
            point_ids: List of point IDs to delete
        """
        try:
            client = await self._get_client()

            await client.delete(
                collection_name=self.collection,
                points_selector=models.PointIdsList(points=cast(Any, point_ids)),
            )

            logger.info(f"Deleted {len(point_ids)} points from {self.collection}")

        except Exception as e:
            logger.error(f"Failed to delete points: {e}")
            raise RuntimeError(f"Failed to delete points: {e}") from e

    async def delete_collection(self) -> None:
        """
        Delete entire collection.

        Warning: This is a destructive operation!
        """
        try:
            client = await self._get_client()

            await client.delete_collection(collection_name=self.collection)
            logger.info(f"Deleted collection: {self.collection}")

        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            raise RuntimeError(f"Failed to delete collection: {e}") from e

    async def count(self) -> int:
        """
        Count vectors in collection.

        Returns:
            Number of vectors
        """
        try:
            client = await self._get_client()

            count_result = await client.count(collection_name=self.collection)
            return count_result.count

        except Exception as e:
            logger.error(f"Failed to count vectors: {e}")
            return 0

    async def healthcheck(self) -> bool:
        """
        Check Qdrant availability.

        Returns:
            True if Qdrant is available, False otherwise
        """
        try:
            client = await self._get_client()
            await client.get_collections()
            return True

        except Exception as e:
            logger.error(f"Qdrant healthcheck failed: {e}")
            return False

    async def close(self) -> None:
        """
        Close Qdrant connection.

        Should be called during application shutdown.
        """
        if client := self._client_init.get_if_exists():
            await client.close()
            self._client_init.reset()
            logger.info("Qdrant connection closed")
