"""
Qdrant-based Vector Index Adapter

Implements VectorIndexPort using Qdrant for semantic search.

Architecture:
    IndexDocument → Embedding (LLM) → Qdrant Vector → SearchHit

Collection Strategy:
    - Collection per repo+snapshot: `code_embeddings_{repo_id}_{snapshot_id}`
    - Alternative: Single collection with repo_id + snapshot_id filters (Phase 2)
"""

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from src.index.common.documents import IndexDocument, SearchHit

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """
    Embedding generation interface.

    MVP: OpenAI text-embedding-3-small
    Phase 2: Support multiple providers (Cohere, local models)
    """

    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding for single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (typically 1536 dimensions for OpenAI)
        """
        raise NotImplementedError("EmbeddingProvider.embed must be implemented")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for batch of texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        raise NotImplementedError("EmbeddingProvider.embed_batch must be implemented")


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI embedding provider using text-embedding-3-small.

    Requires: openai library and OPENAI_API_KEY environment variable
    """

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._client = None

    async def _get_client(self):
        """Lazy initialize OpenAI client"""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI()
        return self._client

    async def embed(self, text: str) -> list[float]:
        """Generate single embedding"""
        client = await self._get_client()
        response = await client.embeddings.create(
            input=text,
            model=self.model,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate batch embeddings (max 2048 texts per batch)"""
        client = await self._get_client()

        # OpenAI allows up to 2048 texts per batch
        batch_size = 2048
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await client.embeddings.create(
                input=batch,
                model=self.model,
            )
            all_embeddings.extend([data.embedding for data in response.data])

        return all_embeddings


class QdrantVectorIndex:
    """
    Vector search implementation using Qdrant.

    Usage:
        vector_index = QdrantVectorIndex(
            client=AsyncQdrantClient(url="http://localhost:6333"),
            embedding_provider=OpenAIEmbeddingProvider(),
        )

        await vector_index.index("myrepo", "commit123", index_documents)
        hits = await vector_index.search("myrepo", "commit123", "how to search code?")
    """

    def __init__(
        self,
        client: AsyncQdrantClient,
        embedding_provider: EmbeddingProvider,
        collection_prefix: str = "code_embeddings",
        vector_size: int = 1536,  # OpenAI text-embedding-3-small
    ):
        self.client = client
        self.embedding_provider = embedding_provider
        self.collection_prefix = collection_prefix
        self.vector_size = vector_size

    # ============================================================
    # VectorIndexPort Implementation
    # ============================================================

    async def index(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Full index creation.

        Creates Qdrant collection and uploads all documents.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances
        """
        collection_name = self._get_collection_name(repo_id, snapshot_id)

        # Create collection if not exists
        await self._ensure_collection(collection_name)

        # Use documents directly (already IndexDocument instances)
        index_docs = docs

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(index_docs)} documents")
        texts = [doc.content for doc in index_docs]
        embeddings = await self.embedding_provider.embed_batch(texts)

        # Create Qdrant points
        points = []
        for doc, vector in zip(index_docs, embeddings, strict=False):
            points.append(
                PointStruct(
                    id=doc.chunk_id,
                    vector=vector,
                    payload={
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                        "file_path": doc.file_path,
                        "symbol_fqn": doc.symbol_fqn,
                        "kind": doc.kind,
                        "language": doc.language,
                        "tags": doc.tags,
                        "importance_score": doc.importance_score,
                        "content": doc.content[:500],  # Store preview only
                    },
                )
            )

        # Upsert in batches (256 recommended by Qdrant)
        batch_size = 256
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await self.client.upsert(
                collection_name=collection_name,
                points=batch,
            )
            logger.info(f"Upserted batch {i // batch_size + 1}/{(len(points) - 1) // batch_size + 1}")

        logger.info(f"Indexed {len(points)} documents to {collection_name}")

    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Incremental upsert (same as full index for MVP).

        TODO Phase 2: Optimize by checking existing embeddings.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances to upsert
        """
        await self.index(repo_id, snapshot_id, docs)

    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """
        Delete documents by ID.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            doc_ids: List of chunk_ids to delete
        """
        collection_name = self._get_collection_name(repo_id, snapshot_id)

        try:
            await self.client.delete(
                collection_name=collection_name,
                points_selector=doc_ids,
            )
            logger.info(f"Deleted {len(doc_ids)} documents from {collection_name}")
        except Exception as e:
            logger.error(f"Failed to delete documents: {e}")
            raise

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Semantic search using query embedding.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            limit: Maximum results

        Returns:
            List of SearchHit with source="vector"
        """
        collection_name = self._get_collection_name(repo_id, snapshot_id)

        # Generate query embedding
        logger.debug(f"Embedding query: {query[:50]}...")
        query_vector = await self.embedding_provider.embed(query)

        # Search Qdrant
        try:
            results = await self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

        # Convert to SearchHits
        hits = []
        for result in results:
            payload = result.payload or {}
            hits.append(
                SearchHit(
                    chunk_id=result.id,
                    file_path=payload.get("file_path"),
                    symbol_id=payload.get("symbol_id"),
                    score=result.score,
                    source="vector",
                    metadata={
                        "kind": payload.get("kind"),
                        "symbol_fqn": payload.get("symbol_fqn"),
                        "language": payload.get("language"),
                        "importance_score": payload.get("importance_score"),
                        "tags": payload.get("tags", {}),
                    },
                )
            )

        logger.info(f"Vector search returned {len(hits)} results")
        return hits

    # ============================================================
    # Private Helpers
    # ============================================================

    def _get_collection_name(self, repo_id: str, snapshot_id: str) -> str:
        """
        Get Qdrant collection name.

        Format: {prefix}_{repo_id}_{snapshot_id_short}

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            Collection name (e.g., "code_embeddings_myrepo_abc12345")
        """
        # Use first 8 chars of snapshot_id for collection name
        snapshot_short = snapshot_id[:8] if len(snapshot_id) > 8 else snapshot_id
        return f"{self.collection_prefix}_{repo_id}_{snapshot_short}"

    async def _ensure_collection(self, collection_name: str) -> None:
        """
        Create collection if it doesn't exist.

        Args:
            collection_name: Qdrant collection name
        """
        try:
            # Check if collection exists
            collections = await self.client.get_collections()
            exists = any(c.name == collection_name for c in collections.collections)

            if not exists:
                logger.info(f"Creating collection: {collection_name}")
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE,
                    ),
                )
            else:
                logger.debug(f"Collection already exists: {collection_name}")

        except Exception as e:
            logger.error(f"Failed to ensure collection {collection_name}: {e}")
            raise


# ============================================================
# Convenience Factory
# ============================================================


async def create_qdrant_vector_index(
    qdrant_url: str = "http://localhost:6333",
    embedding_model: str = "text-embedding-3-small",
) -> QdrantVectorIndex:
    """
    Factory function for QdrantVectorIndex.

    Args:
        qdrant_url: Qdrant server URL
        embedding_model: OpenAI embedding model

    Returns:
        Configured QdrantVectorIndex instance
    """
    client = AsyncQdrantClient(url=qdrant_url)
    embedding_provider = OpenAIEmbeddingProvider(model=embedding_model)

    return QdrantVectorIndex(
        client=client,
        embedding_provider=embedding_provider,
    )
