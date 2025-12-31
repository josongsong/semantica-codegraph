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
import time
import uuid
from dataclasses import dataclass, field

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

from codegraph_engine.multi_index.infrastructure.common.documents import clamp_search_limit
from codegraph_shared.infra.observability import get_logger
from codegraph_shared.ports import IndexDocument, SearchHit  # ✅ Port (공통 인터페이스)

logger = get_logger(__name__)


@dataclass
class DeletionQueueEntry:
    """TTL 기반 deletion queue entry."""

    point_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class BoundedDeletionQueue:
    """
    Bounded deletion queue with TTL-based auto-flush.

    Features:
    - 최대 크기 제한 (메모리 보호)
    - TTL 기반 자동 flush
    - Thread-safe (asyncio.Lock)
    - Race-condition free (computed total, not tracked)

    Usage:
        queue = BoundedDeletionQueue(max_size=10000, ttl_seconds=300)
        await queue.add("collection1", ["id1", "id2"])
        entries = await queue.pop_expired()  # TTL 초과된 것들
        entries = await queue.pop_if_full("collection1", threshold=100)
    """

    def __init__(
        self,
        max_size: int = 10000,
        ttl_seconds: float = 300.0,  # 5분
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._queues: dict[str, DeletionQueueEntry] = {}
        self._lock = asyncio.Lock()

    def _compute_total_count(self) -> int:
        """
        Compute total count from actual queue state (race-condition free).

        MUST be called while holding _lock.
        """
        return sum(len(entry.point_ids) for entry in self._queues.values())

    async def add(self, collection: str, point_ids: list[str]) -> bool:
        """
        Add point IDs to deletion queue.

        Returns:
            True if added, False if queue full (caller should force flush)
        """
        async with self._lock:
            # Check max size (computed from actual state, not tracked)
            current_total = self._compute_total_count()
            if current_total + len(point_ids) > self.max_size:
                logger.warning(
                    "deletion_queue_full",
                    current_size=current_total,
                    max_size=self.max_size,
                    attempted_add=len(point_ids),
                )
                return False

            if collection not in self._queues:
                self._queues[collection] = DeletionQueueEntry()

            self._queues[collection].point_ids.extend(point_ids)
            return True

    async def pop_all(self, collection: str) -> list[str]:
        """Pop all point IDs for a collection."""
        async with self._lock:
            entry = self._queues.pop(collection, None)
            if entry:
                return entry.point_ids
            return []

    async def pop_expired(self) -> dict[str, list[str]]:
        """Pop all TTL-expired entries."""
        now = time.time()
        expired: dict[str, list[str]] = {}

        async with self._lock:
            for collection, entry in list(self._queues.items()):
                if now - entry.created_at >= self.ttl_seconds:
                    expired[collection] = entry.point_ids
                    del self._queues[collection]

        return expired

    async def check_threshold(self, collection: str, threshold: int) -> list[str] | None:
        """
        Check if collection exceeds threshold and pop if so.

        Returns:
            point_ids if threshold exceeded, None otherwise
        """
        async with self._lock:
            entry = self._queues.get(collection)
            if entry and len(entry.point_ids) >= threshold:
                del self._queues[collection]
                return entry.point_ids
            return None

    async def get_stats(self) -> dict:
        """Get queue statistics."""
        async with self._lock:
            return {
                "total_count": self._compute_total_count(),
                "collection_count": len(self._queues),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "collections": {c: len(e.point_ids) for c, e in self._queues.items()},
            }


# EmbeddingProvider는 별도 모듈로 분리됨 (OCP 준수)
# 하위 호환성을 위해 re-export
from codegraph_engine.multi_index.infrastructure.vector.embedding_provider import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
)


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
        upsert_batch_size: int = 256,  # 🔥 SOTA: Configurable batch size
        enable_soft_delete: bool = True,  # 🔥 SOTA: Soft delete for better performance
        batch_delete_threshold: int = 100,  # 🔥 SOTA: Batch compaction threshold
    ):
        self.client = client
        self.embedding_provider = embedding_provider
        self.collection_prefix = collection_prefix
        self.vector_size = vector_size
        self.upsert_concurrency = upsert_concurrency
        self.upsert_batch_size = upsert_batch_size
        self.enable_soft_delete = enable_soft_delete
        self.batch_delete_threshold = batch_delete_threshold

        # 🔥 SOTA: Bounded deletion queue with TTL (메모리 보호 + 자동 flush)
        self._deletion_queue = BoundedDeletionQueue(
            max_size=10000,  # 최대 10K point IDs
            ttl_seconds=300.0,  # 5분 후 자동 flush
        )
        self._compaction_lock: dict[str, bool] = {}  # collection -> is_compacting

        # 🔥 SOTA: Background TTL flush task
        self._ttl_flush_task: asyncio.Task | None = None
        self._running = False

        # 🔥 SOTA: Collection existence cache (avoids repeated list-all API calls)
        self._existing_collections: set[str] = set()
        self._collection_cache_created_at: float = 0.0  # Cache TTL 관리용

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

        # Parallel batch upsert (configurable, default 256 recommended by Qdrant)
        batches = [points[i : i + self.upsert_batch_size] for i in range(0, len(points), self.upsert_batch_size)]
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

        Phase 2: Optimize by checking existing embeddings (see _docs/_backlog/PHASE_2_FUTURE_FEATURES.md)

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
                from datetime import datetime, timezone

                await self.client.set_payload(
                    collection_name=collection_name,
                    payload={
                        "is_active": False,
                        "deleted_at": datetime.now(timezone.utc).isoformat(),
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

                # 🔥 SOTA: Add to bounded deletion queue
                added = await self._deletion_queue.add(collection_name, point_ids)

                if not added:
                    # Queue full - force immediate compaction
                    logger.warning(
                        "deletion_queue_full_forcing_compaction",
                        collection=collection_name,
                    )
                    await self._compact_deleted_points(collection_name)
                    # Retry adding after compaction
                    retry_added = await self._deletion_queue.add(collection_name, point_ids)
                    if not retry_added:
                        # Still full after compaction - this is critical data loss risk
                        logger.error(
                            "deletion_queue_add_failed_after_compaction",
                            collection=collection_name,
                            point_ids_count=len(point_ids),
                            reason="queue_still_full_after_compaction",
                        )
                        raise RuntimeError(
                            f"Failed to add {len(point_ids)} points to deletion queue "
                            f"for collection {collection_name} after compaction - data loss risk"
                        )
                else:
                    # Check threshold for background compaction
                    threshold_ids = await self._deletion_queue.check_threshold(
                        collection_name, self.batch_delete_threshold
                    )
                    if threshold_ids:
                        # 🔥 SOTA: Trigger background compaction with error tracking + re-queue
                        # Capture threshold_ids in closure for re-queue on failure
                        captured_ids = threshold_ids
                        captured_collection = collection_name

                        async def _background_compact_with_requeue():
                            """Background compaction with automatic re-queue on failure."""
                            try:
                                await self._compact_with_ids(captured_collection, captured_ids)
                            except Exception as e:
                                logger.error(
                                    "background_compaction_failed_requeuing",
                                    collection=captured_collection,
                                    error=str(e),
                                    error_type=type(e).__name__,
                                    point_ids_count=len(captured_ids),
                                )
                                # Re-queue for retry (best effort)
                                try:
                                    await self._deletion_queue.add(captured_collection, captured_ids)
                                    logger.info(
                                        "background_compaction_requeued",
                                        collection=captured_collection,
                                        point_ids_count=len(captured_ids),
                                    )
                                except Exception as requeue_error:
                                    logger.error(
                                        "background_compaction_requeue_failed",
                                        collection=captured_collection,
                                        error=str(requeue_error),
                                        lost_point_ids_count=len(captured_ids),
                                    )

                        asyncio.create_task(_background_compact_with_requeue())

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
            # Get queued deletions from bounded queue
            point_ids = await self._deletion_queue.pop_all(collection_name)

            if not point_ids:
                return

            await self._do_hard_delete_batch(collection_name, point_ids)

        except Exception as e:
            logger.error(
                "vector_compaction_failed",
                collection=collection_name,
                error=str(e),
            )
            # Re-queue on failure (best effort, may fail if queue full)
            await self._deletion_queue.add(collection_name, point_ids)

        finally:
            # Release lock
            self._compaction_lock[collection_name] = False

    async def _compact_with_ids(self, collection_name: str, point_ids: list[str]) -> None:
        """
        Compact specific point IDs (already popped from queue).

        Args:
            collection_name: Qdrant collection name
            point_ids: List of point IDs to delete
        """
        # Check if already compacting
        if self._compaction_lock.get(collection_name, False):
            logger.debug("compaction_already_running", collection=collection_name)
            # Re-queue since we can't process now
            await self._deletion_queue.add(collection_name, point_ids)
            return

        self._compaction_lock[collection_name] = True

        try:
            await self._do_hard_delete_batch(collection_name, point_ids)
        except Exception as e:
            logger.error(
                "vector_compaction_with_ids_failed",
                collection=collection_name,
                error=str(e),
            )
            # Re-queue on failure
            await self._deletion_queue.add(collection_name, point_ids)
        finally:
            self._compaction_lock[collection_name] = False

    async def _do_hard_delete_batch(self, collection_name: str, point_ids: list[str]) -> None:
        """
        Perform actual hard delete (shared logic).

        Args:
            collection_name: Qdrant collection name
            point_ids: List of point IDs to delete
        """
        logger.info(
            "vector_compaction_started",
            collection=collection_name,
            queued_deletions=len(point_ids),
        )

        await self.client.delete(
            collection_name=collection_name,
            points_selector=point_ids,
        )

        logger.info(
            "vector_compaction_completed",
            collection=collection_name,
            compacted_count=len(point_ids),
        )

    async def start_ttl_flush_task(self) -> None:
        """Start background TTL flush task."""
        if self._running:
            return

        self._running = True
        self._ttl_flush_task = asyncio.create_task(self._ttl_flush_loop())
        logger.info("ttl_flush_task_started")

    async def stop_ttl_flush_task(self) -> None:
        """Stop background TTL flush task."""
        self._running = False
        if self._ttl_flush_task:
            self._ttl_flush_task.cancel()
            try:
                await self._ttl_flush_task
            except asyncio.CancelledError:
                pass
            self._ttl_flush_task = None
        logger.info("ttl_flush_task_stopped")

    async def _ttl_flush_loop(self) -> None:
        """Background loop to flush TTL-expired entries."""
        while self._running:
            try:
                # Check every 60 seconds
                await asyncio.sleep(60)

                expired = await self._deletion_queue.pop_expired()
                for collection, point_ids in expired.items():
                    logger.info(
                        "ttl_flush_triggered",
                        collection=collection,
                        count=len(point_ids),
                    )
                    try:
                        await self._do_hard_delete_batch(collection, point_ids)
                    except Exception as e:
                        logger.error(
                            "ttl_flush_failed",
                            collection=collection,
                            error=str(e),
                        )
                        # Re-queue on failure
                        await self._deletion_queue.add(collection, point_ids)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ttl_flush_loop_error", error=str(e))

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
            limit: Maximum results (clamped to 1-1000)
            chunk_ids: Optional list of chunk IDs to filter (DB-level filtering)

        Returns:
            List of SearchHit with source="vector"
        """
        # Validate and clamp limit to prevent DOS
        limit = clamp_search_limit(limit)

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

        Uses in-memory cache with TTL to avoid repeated list-all API calls.
        Cache hit: O(1), Cache miss: O(n) where n = total collections.
        Cache TTL: 5 minutes (invalidates stale cache if collections deleted externally)

        Args:
            collection_name: Qdrant collection name
        """
        import time

        # Cache TTL: 5분 후 캐시 무효화 (외부에서 컬렉션 삭제 시 대응)
        cache_ttl_seconds = 300
        current_time = time.time()
        if current_time - self._collection_cache_created_at > cache_ttl_seconds:
            self._existing_collections.clear()
            self._collection_cache_created_at = current_time

        # Fast path: Check cache first
        if collection_name in self._existing_collections:
            return

        try:
            # Cache miss: Check via API
            collections = await self.client.get_collections()
            existing_names = {c.name for c in collections.collections}

            # Update cache with all existing collections
            self._existing_collections.update(existing_names)
            self._collection_cache_created_at = current_time

            if collection_name not in existing_names:
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
                # Add to cache after successful creation
                self._existing_collections.add(collection_name)
            else:
                logger.debug("qdrant_collection_exists", collection=collection_name)

        except Exception as e:
            logger.error("qdrant_ensure_collection_failed", collection=collection_name, error=str(e))
            raise

    def invalidate_collection_cache(self) -> None:
        """컬렉션 캐시 수동 무효화 (테스트/디버깅용)."""
        self._existing_collections.clear()
        self._collection_cache_created_at = 0.0

    async def flush_deletion_queue(self, collection_name: str | None = None) -> int:
        """
        Deletion queue 강제 flush (메모리 누수 방지).

        Args:
            collection_name: 특정 컬렉션만 flush (None이면 전체)

        Returns:
            삭제된 포인트 수
        """
        total_deleted = 0

        if collection_name:
            # Specific collection
            point_ids = await self._deletion_queue.pop_all(collection_name)
            if point_ids:
                try:
                    await self._do_hard_delete_batch(collection_name, point_ids)
                    total_deleted = len(point_ids)
                except Exception as e:
                    logger.warning("flush_deletion_queue_failed", collection=collection_name, error=str(e))
                    # Re-queue on failure
                    await self._deletion_queue.add(collection_name, point_ids)
        else:
            # All collections via TTL flush
            expired = await self._deletion_queue.pop_expired()
            # Also get non-expired (force flush all)
            stats = await self._deletion_queue.get_stats()
            for coll in list(stats.get("collections", {}).keys()):
                if coll not in expired:
                    expired[coll] = await self._deletion_queue.pop_all(coll)

            for coll, point_ids in expired.items():
                if point_ids:
                    try:
                        await self._do_hard_delete_batch(coll, point_ids)
                        total_deleted += len(point_ids)
                    except Exception as e:
                        logger.warning("flush_deletion_queue_failed", collection=coll, error=str(e))
                        await self._deletion_queue.add(coll, point_ids)

        return total_deleted

    async def get_deletion_queue_stats(self) -> dict:
        """Get deletion queue statistics."""
        return await self._deletion_queue.get_stats()


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
