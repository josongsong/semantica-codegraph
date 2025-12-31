"""
Store Factory

Creates node_store, edge_store, vector_store instances.

Architecture:
- Uses existing ChunkStore (PostgreSQL) from code_foundation
- Uses existing QdrantVectorIndex from multi_index
- Edge store is a placeholder (UnifiedGraphIndex handles this)

Returns:
    Tuple[ChunkStore, None, VectorIndex]
"""

from typing import Any, Protocol

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Import vector store (still exists)
try:
    from codegraph_engine.multi_index.infrastructure.vector.adapter_qdrant import QdrantVectorIndex
except ImportError:
    QdrantVectorIndex = None  # type: ignore


# Protocol for ChunkStore (backward compatibility)
class ChunkStore(Protocol):
    """ChunkStore protocol for backward compatibility."""

    async def get_by_id(self, chunk_id: str) -> Any | None: ...

    async def save_chunk(self, chunk: Any) -> None: ...

    async def delete_chunk(self, chunk_id: str) -> None: ...


class SimpleInMemoryChunkStore:
    """
    Simple in-memory chunk store for MCP server (zero external dependencies).

    Big Tech L11: Minimal implementation, no test dependencies.
    """

    def __init__(self):
        self._chunks: dict[str, Any] = {}

    async def get_by_id(self, chunk_id: str) -> Any | None:
        """Get chunk by ID."""
        return self._chunks.get(chunk_id)

    async def save_chunk(self, chunk: Any) -> None:
        """Save chunk."""
        if hasattr(chunk, "id"):
            self._chunks[chunk.id] = chunk

    async def delete_chunk(self, chunk_id: str) -> None:
        """Delete chunk."""
        self._chunks.pop(chunk_id, None)


def create_all_stores() -> tuple[Any, None, Any]:
    """
    Create all storage instances required by MCP server.

    Returns:
        Tuple of (node_store, edge_store, vector_store)
        - node_store: ChunkStore (PostgreSQL or fallback)
        - edge_store: None (UnifiedGraphIndex handles edges)
        - vector_store: QdrantVectorIndex (embedded mode)

    Raises:
        RuntimeError: If critical stores cannot be initialized

    Example:
        node_store, edge_store, vector_store = create_all_stores()

    Notes:
        - This is a synchronous wrapper around async factories
        - Uses embedded Qdrant for zero external dependencies
        - ChunkStore fallback to in-memory if PostgreSQL unavailable
        - Safe to call from sync or async context
    """
    import asyncio

    logger.info("Initializing all stores...")

    # Check if we're in async context
    try:
        loop = asyncio.get_running_loop()
        # Already in async context - cannot use run_until_complete
        # Use sync factories only
        node_store = _create_node_store_fallback()
        vector_store = _create_vector_store_fallback()
    except RuntimeError:
        # Not in async context - safe to create new loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        node_store = _create_node_store_sync(loop)
        vector_store = _create_vector_store_sync(loop)

    # Edge Store (None - UnifiedGraphIndex handles this)
    edge_store = None

    logger.info("✓ All stores initialized successfully")
    return node_store, edge_store, vector_store


def _create_node_store_fallback() -> Any:
    """
    Create node store (sync fallback).

    Returns:
        SimpleInMemoryChunkStore (for MCP server lightweight mode)
    """
    # Use in-memory store for MCP server (zero deps)
    store = SimpleInMemoryChunkStore()
    logger.info("✓ Node Store: In-Memory (MCP lightweight mode)")
    return store


def _create_node_store_sync(loop: Any) -> Any:
    """
    Create node store (ChunkStore) synchronously.

    Strategy:
    For MCP server, just use fallback directly (no PostgreSQL dependency).

    Args:
        loop: asyncio event loop

    Returns:
        ChunkStore instance
    """
    # For MCP server: use fallback directly
    return _create_node_store_fallback()


def _create_vector_store_fallback() -> Any:
    """
    Create vector store (sync fallback).

    Returns:
        Qdrant in memory mode
    """
    try:
        from codegraph_engine.multi_index.infrastructure.vector.adapter_qdrant import (
            OpenAIEmbeddingProvider,
        )
        from codegraph_shared.infra.vector import create_qdrant_client

        client = create_qdrant_client(mode="memory")
        embedding_provider = OpenAIEmbeddingProvider(model="text-embedding-3-small")
        vector_store = QdrantVectorIndex(
            client=client,
            embedding_provider=embedding_provider,
        )

        logger.info("✓ Vector Store: Qdrant (memory)")
        return vector_store
    except Exception as e:
        raise RuntimeError(f"Cannot create vector store: {e}") from e


def _create_vector_store_sync(loop: Any) -> Any:
    """
    Create vector store (Qdrant) synchronously.

    Strategy:
    1. Try embedded Qdrant (zero external deps)
    2. Fallback to memory mode

    Args:
        loop: asyncio event loop

    Returns:
        QdrantVectorIndex instance

    Raises:
        RuntimeError: If Qdrant cannot be initialized
    """
    try:
        # Embedded mode (persistent storage)
        from codegraph_shared.infra.vector import create_qdrant_client
        from codegraph_engine.multi_index.infrastructure.vector.adapter_qdrant import OpenAIEmbeddingProvider

        client = create_qdrant_client(mode="embedded", storage_path="./data/qdrant_storage")

        embedding_provider = OpenAIEmbeddingProvider(model="text-embedding-3-small")

        vector_store = QdrantVectorIndex(
            client=client,
            embedding_provider=embedding_provider,
        )

        logger.info("✓ Vector Store: Qdrant (embedded)")
        return vector_store

    except Exception as e:
        logger.warning(f"Embedded Qdrant failed: {e}, trying memory mode")

        try:
            # Fallback: Memory mode
            from codegraph_shared.infra.vector import create_qdrant_client
            from codegraph_engine.multi_index.infrastructure.vector.adapter_qdrant import OpenAIEmbeddingProvider

            client = create_qdrant_client(mode="memory")
            embedding_provider = OpenAIEmbeddingProvider(model="text-embedding-3-small")

            vector_store = QdrantVectorIndex(
                client=client,
                embedding_provider=embedding_provider,
            )

            logger.info("✓ Vector Store: Qdrant (memory)")
            return vector_store

        except Exception as e2:
            raise RuntimeError(f"Cannot create vector store: {e2}") from e2
