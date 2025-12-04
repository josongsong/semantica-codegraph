"""
Embedding-based Memory Store using Qdrant

Provides semantic similarity search for:
- Episode retrieval by task description similarity
- Entity search by semantic meaning
- Cross-session memory consolidation
"""

from typing import Any, Protocol
from uuid import uuid4

from src.common.observability import get_logger
from src.infra.vector.qdrant import QdrantAdapter

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        ...


class EmbeddingMemoryStore:
    """
    Qdrant-based embedding store for semantic memory search.

    Collections:
    - memory_episodes: Episode embeddings for similarity search
    - memory_entities: Entity embeddings for semantic lookup
    - memory_facts: Extracted fact embeddings (Mem0-style)
    """

    EPISODE_COLLECTION = "memory_episodes"
    ENTITY_COLLECTION = "memory_entities"
    FACT_COLLECTION = "memory_facts"

    def __init__(
        self,
        qdrant_adapter: QdrantAdapter,
        embedding_provider: EmbeddingProvider | None = None,
        default_dimension: int = 1536,
    ):
        """
        Initialize embedding memory store.

        Args:
            qdrant_adapter: Qdrant adapter instance
            embedding_provider: Provider for generating embeddings
            default_dimension: Default embedding dimension (1536 for OpenAI)
        """
        self.qdrant = qdrant_adapter
        self.embedder = embedding_provider
        self.dimension = default_dimension
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize collections."""
        if self._initialized:
            return

        # Create episode collection
        self.qdrant.collection = self.EPISODE_COLLECTION
        await self.qdrant._ensure_collection(self.dimension)

        # Create entity collection
        self.qdrant.collection = self.ENTITY_COLLECTION
        await self.qdrant._ensure_collection(self.dimension)

        # Create fact collection
        self.qdrant.collection = self.FACT_COLLECTION
        await self.qdrant._ensure_collection(self.dimension)

        self._initialized = True
        logger.info("EmbeddingMemoryStore initialized")

    async def _get_embedding(self, text: str) -> list[float]:
        """
        Get embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            RuntimeError: If no embedding provider configured
        """
        if not self.embedder:
            raise RuntimeError("No embedding provider configured. Initialize with embedding_provider parameter.")

        return await self.embedder.embed(text)

    async def _get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for multiple texts."""
        if not self.embedder:
            raise RuntimeError("No embedding provider configured")

        return await self.embedder.embed_batch(texts)

    # ============================================================
    # Episode Embedding Operations
    # ============================================================

    async def index_episode(
        self,
        episode_id: str,
        task_description: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Index episode for semantic search.

        Args:
            episode_id: Episode ID (from PostgresMemoryStore)
            task_description: Task description to embed
            metadata: Additional searchable metadata
        """
        try:
            embedding = await self._get_embedding(task_description)

            self.qdrant.collection = self.EPISODE_COLLECTION
            await self.qdrant.upsert_vectors(
                [
                    {
                        "id": episode_id,
                        "vector": embedding,
                        "payload": {
                            "episode_id": episode_id,
                            "task_description": task_description[:500],  # Truncate for payload
                            **(metadata or {}),
                        },
                    }
                ]
            )

            logger.debug(f"Indexed episode: {episode_id}")

        except Exception as e:
            logger.error(f"Failed to index episode {episode_id}: {e}")
            raise

    async def search_similar_episodes(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.7,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar episodes by semantic similarity.

        Args:
            query: Search query (natural language)
            limit: Maximum results
            score_threshold: Minimum similarity score
            filters: Payload filters (project_id, task_type, etc.)

        Returns:
            List of matching episodes with scores
        """
        try:
            query_embedding = await self._get_embedding(query)

            self.qdrant.collection = self.EPISODE_COLLECTION
            results = await self.qdrant.search(
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                filter_dict=filters,
            )

            return [
                {
                    "episode_id": r["payload"].get("episode_id", r["id"]),
                    "score": r["score"],
                    "task_description": r["payload"].get("task_description", ""),
                    "metadata": r["payload"],
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"Episode search failed: {e}")
            return []

    async def delete_episode_embedding(self, episode_id: str) -> None:
        """Delete episode embedding."""
        self.qdrant.collection = self.EPISODE_COLLECTION
        await self.qdrant.delete_by_id([episode_id])

    # ============================================================
    # Entity Embedding Operations
    # ============================================================

    async def index_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        description: str | None = None,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Index entity for semantic search.

        Args:
            entity_id: Entity ID (from PostgresMemoryStore)
            entity_type: Entity type (function, class, concept, etc.)
            name: Entity name
            description: Optional description
            context: Optional context (code snippet, etc.)
            metadata: Additional metadata
        """
        try:
            # Combine name, description, and context for embedding
            text_parts = [name]
            if description:
                text_parts.append(description)
            if context:
                text_parts.append(context[:500])  # Limit context length

            embed_text = " ".join(text_parts)
            embedding = await self._get_embedding(embed_text)

            self.qdrant.collection = self.ENTITY_COLLECTION
            await self.qdrant.upsert_vectors(
                [
                    {
                        "id": entity_id,
                        "vector": embedding,
                        "payload": {
                            "entity_id": entity_id,
                            "entity_type": entity_type,
                            "name": name,
                            "description": description,
                            **(metadata or {}),
                        },
                    }
                ]
            )

            logger.debug(f"Indexed entity: {name} ({entity_type})")

        except Exception as e:
            logger.error(f"Failed to index entity {name}: {e}")
            raise

    async def search_similar_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 10,
        score_threshold: float = 0.6,
    ) -> list[dict[str, Any]]:
        """
        Search entities by semantic similarity.

        Args:
            query: Search query
            entity_type: Filter by type
            limit: Maximum results
            score_threshold: Minimum score

        Returns:
            Matching entities with scores
        """
        try:
            query_embedding = await self._get_embedding(query)

            filters = None
            if entity_type:
                filters = {"must": [{"key": "entity_type", "match": {"value": entity_type}}]}

            self.qdrant.collection = self.ENTITY_COLLECTION
            results = await self.qdrant.search(
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                filter_dict=filters,
            )

            return [
                {
                    "entity_id": r["payload"].get("entity_id", r["id"]),
                    "entity_type": r["payload"].get("entity_type"),
                    "name": r["payload"].get("name"),
                    "score": r["score"],
                    "metadata": r["payload"],
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"Entity search failed: {e}")
            return []

    # ============================================================
    # Fact Embedding Operations (Mem0-style)
    # ============================================================

    async def store_fact(
        self,
        fact_text: str,
        project_id: str,
        source_type: str = "conversation",
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store a fact for future recall (Mem0-style).

        Facts are extracted pieces of knowledge that can be retrieved
        across sessions.

        Args:
            fact_text: The fact to store
            project_id: Project ID
            source_type: Where fact came from (conversation, episode, etc.)
            source_id: Optional source ID
            metadata: Additional metadata

        Returns:
            Fact ID
        """
        try:
            fact_id = str(uuid4())
            embedding = await self._get_embedding(fact_text)

            self.qdrant.collection = self.FACT_COLLECTION
            await self.qdrant.upsert_vectors(
                [
                    {
                        "id": fact_id,
                        "vector": embedding,
                        "payload": {
                            "fact_id": fact_id,
                            "fact_text": fact_text,
                            "project_id": project_id,
                            "source_type": source_type,
                            "source_id": source_id,
                            **(metadata or {}),
                        },
                    }
                ]
            )

            logger.debug(f"Stored fact: {fact_text[:50]}...")
            return fact_id

        except Exception as e:
            logger.error(f"Failed to store fact: {e}")
            raise

    async def recall_facts(
        self,
        query: str,
        project_id: str | None = None,
        limit: int = 5,
        score_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Recall relevant facts for a query.

        Args:
            query: Query to find relevant facts for
            project_id: Filter by project
            limit: Maximum facts to return
            score_threshold: Minimum relevance score

        Returns:
            List of relevant facts
        """
        try:
            query_embedding = await self._get_embedding(query)

            filters = None
            if project_id:
                filters = {"must": [{"key": "project_id", "match": {"value": project_id}}]}

            self.qdrant.collection = self.FACT_COLLECTION
            results = await self.qdrant.search(
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                filter_dict=filters,
            )

            return [
                {
                    "fact_id": r["payload"].get("fact_id", r["id"]),
                    "fact_text": r["payload"].get("fact_text"),
                    "score": r["score"],
                    "source_type": r["payload"].get("source_type"),
                    "metadata": r["payload"],
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"Fact recall failed: {e}")
            return []

    async def delete_fact(self, fact_id: str) -> None:
        """Delete a fact."""
        self.qdrant.collection = self.FACT_COLLECTION
        await self.qdrant.delete_by_id([fact_id])

    async def delete_project_facts(self, project_id: str) -> None:
        """Delete all facts for a project."""
        # Qdrant doesn't support bulk delete by filter directly
        # Need to search and delete in batches
        self.qdrant.collection = self.FACT_COLLECTION

        # This is a workaround - in production, use scroll API
        results = await self.qdrant.search(
            query_vector=[0.0] * self.dimension,  # Dummy vector
            limit=1000,
            filter_dict={"must": [{"key": "project_id", "match": {"value": project_id}}]},
        )

        if results:
            fact_ids = [r["id"] for r in results]
            await self.qdrant.delete_by_id(fact_ids)
            logger.info(f"Deleted {len(fact_ids)} facts for project {project_id}")

    # ============================================================
    # Batch Operations
    # ============================================================

    async def index_episodes_batch(
        self,
        episodes: list[dict[str, Any]],
    ) -> int:
        """
        Index multiple episodes in batch.

        Args:
            episodes: List of episode dicts with id, task_description, metadata

        Returns:
            Number of episodes indexed
        """
        if not episodes:
            return 0

        try:
            # Get embeddings in batch
            descriptions = [e["task_description"] for e in episodes]
            embeddings = await self._get_embeddings_batch(descriptions)

            # Prepare vectors
            vectors = []
            for episode, embedding in zip(episodes, embeddings, strict=False):
                vectors.append(
                    {
                        "id": episode["id"],
                        "vector": embedding,
                        "payload": {
                            "episode_id": episode["id"],
                            "task_description": episode["task_description"][:500],
                            **episode.get("metadata", {}),
                        },
                    }
                )

            self.qdrant.collection = self.EPISODE_COLLECTION
            await self.qdrant.upsert_vectors(vectors)

            logger.info(f"Indexed {len(episodes)} episodes in batch")
            return len(episodes)

        except Exception as e:
            logger.error(f"Batch indexing failed: {e}")
            raise

    # ============================================================
    # Statistics
    # ============================================================

    async def get_statistics(self) -> dict[str, Any]:
        """Get embedding store statistics."""
        stats = {}

        for collection_name in [
            self.EPISODE_COLLECTION,
            self.ENTITY_COLLECTION,
            self.FACT_COLLECTION,
        ]:
            self.qdrant.collection = collection_name
            try:
                count = await self.qdrant.count()
                stats[collection_name] = count
            except Exception:
                stats[collection_name] = 0

        return stats

    async def close(self) -> None:
        """Close Qdrant connection."""
        await self.qdrant.close()
