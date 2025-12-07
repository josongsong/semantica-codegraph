"""
Qdrant-based Vector Index Adapter

Implements VectorIndexPort using Qdrant for semantic search.

Architecture:
    IndexDocument → Embedding (LLM) → Qdrant Vector → SearchHit

Collection Strategy:
    - Collection per repo+snapshot: `code_embeddings_{repo_id}_{snapshot_id}`
    - Alternative: Single collection with repo_id + snapshot_id filters (Phase 2)

Performance Optimizations:
    - Parallel embedding generation (configurable concurrency)
    - Parallel batch upsert with semaphore control
    - gRPC transport for reduced latency
"""

import asyncio
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.infra.observability import get_logger
from src.ports import IndexDocument, SearchHit  # ✅ Port (공통 인터페이스)

logger = get_logger(__name__)


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

    Performance: Uses parallel batch processing with configurable concurrency.
    """

    def __init__(self, model: str = "text-embedding-3-small", concurrency: int = 8):
        """
        Initialize OpenAI embedding provider.

        Args:
            model: OpenAI embedding model (default: text-embedding-3-small)
            concurrency: Max concurrent API requests (default: 8, optimized for performance)
        """
        self.model = model
        self.concurrency = concurrency
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
        """
        Generate batch embeddings with parallel processing.

        Uses asyncio.gather with semaphore for concurrent API calls.
        OpenAI allows up to 2048 texts per batch request.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors in same order as input
        """
        if not texts:
            return []

        client = await self._get_client()

        # OpenAI allows up to 2048 texts per batch
        batch_size = 2048
        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

        if len(batches) == 1:
            # Single batch - no parallelization needed
            response = await client.embeddings.create(input=texts, model=self.model)
            return [data.embedding for data in response.data]

        # Parallel processing for multiple batches
        semaphore = asyncio.Semaphore(self.concurrency)
        results: list[list[list[float]]] = [[] for _ in range(len(batches))]

        async def embed_batch_chunk(idx: int, batch: list[str]) -> None:
            async with semaphore:
                response = await client.embeddings.create(input=batch, model=self.model)
                results[idx] = [data.embedding for data in response.data]

        await asyncio.gather(*[embed_batch_chunk(i, batch) for i, batch in enumerate(batches)])

        # Flatten results maintaining order
        return [emb for batch_result in results for emb in batch_result]


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
        upsert_concurrency: int = 8,  # 🔥 OPTIMIZED: 4 → 8 for better throughput
        enable_soft_delete: bool = True,  # 🔥 SOTA: Soft delete for better performance
        batch_delete_threshold: int = 100,  # 🔥 SOTA: Batch compaction threshold
    ):
        self.client = client
        self.embedding_provider = embedding_provider
        self.collection_prefix = collection_prefix
        self.vector_size = vector_size
        self.upsert_concurrency = upsert_concurrency
        self.enable_soft_delete = enable_soft_delete
        self.batch_delete_threshold = batch_delete_threshold

        # 🔥 SOTA: Deletion queue for batch compaction
        self._deletion_queue: dict[str, list[str]] = {}  # collection -> point_ids
        self._compaction_lock: dict[str, bool] = {}  # collection -> is_compacting

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
        logger.info(
            "qdrant_generating_embeddings",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            documents_count=len(index_docs),
        )
        texts = [doc.content for doc in index_docs]
        embeddings = await self.embedding_provider.embed_batch(texts)

        # Create Qdrant points
        points = []
        for doc, vector in zip(index_docs, embeddings, strict=False):
            # Extract values with fallbacks for IndexDocument compatibility
            tags = getattr(doc, "tags", {}) or {}
            symbol_fqn = getattr(doc, "symbol_fqn", None) or doc.symbol_id or ""
            kind = getattr(doc, "kind", None) or tags.get("kind", "unknown")
            importance_score = getattr(doc, "importance_score", None) or float(tags.get("repomap_score", 0.0))

            # Convert chunk_id to UUID (Qdrant requires UUID or unsigned int)
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.chunk_id))

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                        "chunk_id": doc.chunk_id,  # Store original chunk_id in payload
                        "file_path": doc.file_path,
                        "symbol_fqn": symbol_fqn,
                        "kind": kind,
                        "language": doc.language,
                        "tags": tags,
                        "importance_score": importance_score,
                        "content": doc.content[:500],  # Store preview only
                        "is_active": True,  # 🔥 SOTA: For soft delete filtering
                    },
                )
            )

        # Parallel batch upsert (256 recommended by Qdrant)
        batch_size = 256
        batches = [points[i : i + batch_size] for i in range(0, len(points), batch_size)]
        total_batches = len(batches)

        if total_batches <= 1:
            # Single batch - no parallelization needed
            if points:
                await self.client.upsert(collection_name=collection_name, points=points)
        else:
            # Parallel upsert with concurrency limit
            semaphore = asyncio.Semaphore(self.upsert_concurrency)

            async def upsert_batch(batch_idx: int, batch: list[PointStruct]) -> None:
                async with semaphore:
                    await self.client.upsert(collection_name=collection_name, points=batch)
                    logger.debug(
                        "qdrant_batch_upserted",
                        batch_number=batch_idx + 1,
                        total_batches=total_batches,
                        batch_size=len(batch),
                    )

            await asyncio.gather(*[upsert_batch(i, batch) for i, batch in enumerate(batches)])

        logger.info(
            "qdrant_index_completed",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            documents_count=len(points),
            batches=total_batches,
            upsert_concurrency=self.upsert_concurrency,
            collection=collection_name,
        )

    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Incremental upsert (same as full index for MVP).

        Phase 2: Optimize by checking existing embeddings (see _backlog/PHASE_2_FUTURE_FEATURES.md)

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances to upsert
        """
        await self.index(repo_id, snapshot_id, docs)

    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """
        Delete documents by ID (SOTA: Soft delete + batch compaction).

        Strategy:
        1. Soft delete: Mark is_active=False in payload (fast, no segment merge)
        2. Queue for compaction: Accumulate deletions in memory
        3. Batch compaction: When threshold reached, perform actual hard delete in background

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            doc_ids: List of chunk_ids to delete
        """
        collection_name = self._get_collection_name(repo_id, snapshot_id)

        if self.enable_soft_delete:
            # 🔥 SOTA: Soft delete - update payload only (no segment merge)
            try:
                # Convert chunk_ids to point_ids (UUID)
                point_ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id)) for doc_id in doc_ids]

                # Update payload: is_active=False
                from datetime import datetime

                await self.client.set_payload(
                    collection_name=collection_name,
                    payload={
                        "is_active": False,
                        "deleted_at": datetime.utcnow().isoformat(),
                    },
                    points=point_ids,
                )

                logger.info(
                    "qdrant_soft_delete_completed",
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    deleted_count=len(doc_ids),
                    collection=collection_name,
                    mode="soft",
                )

                # 🔥 SOTA: Add to deletion queue for batch compaction
                if collection_name not in self._deletion_queue:
                    self._deletion_queue[collection_name] = []

                self._deletion_queue[collection_name].extend(point_ids)

                # Check if we should trigger compaction
                if len(self._deletion_queue[collection_name]) >= self.batch_delete_threshold:
                    # 🔥 SOTA: Trigger background compaction with error tracking
                    import asyncio

                    task = asyncio.create_task(self._compact_deleted_points(collection_name))

                    # Add done callback for error tracking
                    def _handle_compaction_result(t: asyncio.Task):
                        try:
                            t.result()  # Raises exception if task failed
                        except Exception as e:
                            logger.error(
                                "background_compaction_failed_unhandled",
                                collection=collection_name,
                                error=str(e),
                                error_type=type(e).__name__,
                            )

                    task.add_done_callback(_handle_compaction_result)

            except Exception as e:
                logger.error(
                    "qdrant_soft_delete_failed",
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    doc_ids_count=len(doc_ids),
                    error=str(e),
                )
                # Fallback to hard delete on soft delete failure
                logger.warning("falling_back_to_hard_delete")
                await self._hard_delete(collection_name, doc_ids)
        else:
            # Hard delete (original behavior)
            await self._hard_delete(collection_name, doc_ids)

    async def _hard_delete(self, collection_name: str, doc_ids: list[str]) -> None:
        """
        Hard delete (immediate removal).

        Args:
            collection_name: Qdrant collection name
            doc_ids: List of chunk_ids to delete
        """
        try:
            # Convert chunk_ids to point_ids
            point_ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id)) for doc_id in doc_ids]

            await self.client.delete(
                collection_name=collection_name,
                points_selector=point_ids,
            )
            logger.info(
                "qdrant_hard_delete_completed",
                collection=collection_name,
                deleted_count=len(doc_ids),
                mode="hard",
            )
        except Exception as e:
            logger.error(
                "qdrant_hard_delete_failed",
                collection=collection_name,
                doc_ids_count=len(doc_ids),
                error=str(e),
            )
            raise

    async def _compact_deleted_points(self, collection_name: str) -> None:
        """
        Background compaction of soft-deleted points (SOTA).

        Performs actual hard delete of accumulated soft-deleted points.
        This is called asynchronously when deletion queue reaches threshold.

        Args:
            collection_name: Qdrant collection name
        """
        # Check if already compacting
        if self._compaction_lock.get(collection_name, False):
            logger.debug("compaction_already_running", collection=collection_name)
            return

        # Set lock
        self._compaction_lock[collection_name] = True

        try:
            # Get queued deletions
            point_ids = self._deletion_queue.pop(collection_name, [])

            if not point_ids:
                return

            logger.info(
                "vector_compaction_started",
                collection=collection_name,
                queued_deletions=len(point_ids),
            )

            # Perform hard delete
            await self.client.delete(
                collection_name=collection_name,
                points_selector=point_ids,
            )

            logger.info(
                "vector_compaction_completed",
                collection=collection_name,
                compacted_count=len(point_ids),
            )

        except Exception as e:
            logger.error(
                "vector_compaction_failed",
                collection=collection_name,
                error=str(e),
            )
            # Re-queue on failure
            if collection_name not in self._deletion_queue:
                self._deletion_queue[collection_name] = []
            self._deletion_queue[collection_name].extend(point_ids)

        finally:
            # Release lock
            self._compaction_lock[collection_name] = False

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
        chunk_ids: list[str] | None = None,
        include_inactive: bool = False,  # 🔥 SOTA: Filter soft-deleted docs
    ) -> list[SearchHit]:
        """
        Semantic search using query embedding.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            limit: Maximum results
            chunk_ids: Optional list of chunk IDs to filter (DB-level filtering)

        Returns:
            List of SearchHit with source="vector"
        """
        collection_name = self._get_collection_name(repo_id, snapshot_id)

        # Generate query embedding
        logger.debug("qdrant_embedding_query", query_preview=query[:50])
        query_vector = await self.embedding_provider.embed(query)

        # 🔥 SOTA: Build filter for chunk_ids AND is_active (soft delete)
        must_conditions = []

        # Filter 1: is_active=True (exclude soft-deleted)
        if not include_inactive:
            must_conditions.append(
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=True),  # Only active documents
                )
            )

        # Filter 2: chunk_ids if provided
        if chunk_ids:
            must_conditions.append(
                FieldCondition(
                    key="id",  # Qdrant uses 'id' for point IDs
                    match=MatchAny(any=chunk_ids),
                )
            )
            logger.debug("qdrant_applying_chunk_filter", chunk_ids_count=len(chunk_ids))

        query_filter = Filter(must=must_conditions) if must_conditions else None

        # SOTA: Adaptive search strategy with proper error handling
        # Small collections (< 10k): Use exact search (brute-force, O(n), no HNSW needed)
        # Large collections (≥ 10k): Use approximate search (HNSW, O(log n), faster)
        search_params = None
        try:
            collection_info = await self.client.get_collection(collection_name)
            points_count = collection_info.points_count
            use_exact = points_count < 10000

            if use_exact:
                from qdrant_client.models import SearchParams

                search_params = SearchParams(exact=True)
                logger.debug(
                    "qdrant_using_exact_search",
                    collection=collection_name,
                    points_count=points_count,
                    reason="small_collection",
                )
        except Exception as e:
            logger.warning(
                "qdrant_collection_info_failed",
                collection=collection_name,
                error=str(e),
                fallback="approximate_search",
            )
            # Fallback to approximate search if collection info fails

        try:
            results = await self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                search_params=search_params,
            )
        except Exception as e:
            logger.error(
                "qdrant_search_failed",
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query_preview=query[:50],
                error=str(e),
            )
            return []

        # Convert to SearchHits
        hits = []
        for result in results:
            payload = result.payload or {}
            # Get chunk_id from payload (original ID stored there)
            chunk_id = payload.get("chunk_id") or str(result.id)
            hits.append(
                SearchHit(
                    chunk_id=chunk_id,
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

        logger.info(
            "qdrant_search_completed",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            results_count=len(hits),
        )
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
                logger.info("qdrant_collection_creating", collection=collection_name, vector_size=self.vector_size)
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE,
                    ),
                    # SOTA: Adaptive search strategy handles small collections via exact=True
                    # No need to force HNSW indexing for small collections (< 10k)
                    # Let Qdrant optimizer handle HNSW indexing naturally for large collections
                )
            else:
                logger.debug("qdrant_collection_exists", collection=collection_name)

        except Exception as e:
            logger.error("qdrant_ensure_collection_failed", collection=collection_name, error=str(e))
            raise


# ============================================================
# Convenience Factory
# ============================================================


async def create_qdrant_vector_index(
    qdrant_host: str = "localhost",
    qdrant_port: int = 7203,
    qdrant_grpc_port: int = 7204,
    prefer_grpc: bool = True,
    embedding_model: str = "text-embedding-3-small",
    embedding_concurrency: int = 8,  # 🔥 OPTIMIZED: 4 → 8
    upsert_concurrency: int = 8,  # 🔥 OPTIMIZED: 4 → 8
) -> QdrantVectorIndex:
    """
    Factory function for QdrantVectorIndex with optimized settings.

    Args:
        qdrant_host: Qdrant server host
        qdrant_port: Qdrant HTTP port
        qdrant_grpc_port: Qdrant gRPC port (faster)
        prefer_grpc: Use gRPC for better performance (default: True)
        embedding_model: OpenAI embedding model
        embedding_concurrency: Max concurrent embedding API calls (optimized: 8)
        upsert_concurrency: Max concurrent upsert batches (optimized: 8)

    Returns:
        Configured QdrantVectorIndex instance
    """
    client = AsyncQdrantClient(
        host=qdrant_host,
        port=qdrant_port,
        grpc_port=qdrant_grpc_port,
        prefer_grpc=prefer_grpc,
    )
    embedding_provider = OpenAIEmbeddingProvider(
        model=embedding_model,
        concurrency=embedding_concurrency,
    )

    return QdrantVectorIndex(
        client=client,
        embedding_provider=embedding_provider,
        upsert_concurrency=upsert_concurrency,
    )
