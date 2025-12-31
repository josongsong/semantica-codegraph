"""
Chunk Retriever Factory

Creates chunk retriever instances for semantic code search.

Architecture:
- Wraps RetrieverService from retrieval_search context
- Provides async search interface for chunks

Returns:
    Retriever object with search_chunks() method
"""

from typing import Any, Protocol

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class ChunkRetrieverProtocol(Protocol):
    """
    Protocol for chunk retriever interface.

    Methods:
        search_chunks: Search for code chunks by query
    """

    async def search_chunks(
        self,
        query: str,
        limit: int = 10,
        repo_id: str = "",
        snapshot_id: str = "main",
    ) -> list[dict]:
        """
        Search for code chunks matching query.

        Args:
            query: Search query string
            limit: Maximum results to return
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier

        Returns:
            List of chunk results as dicts
        """
        ...


class ChunkRetrieverAdapter:
    """
    Adapter wrapping RetrieverService for chunk search.

    Delegates to production RetrieverService from retrieval_search context.
    """

    def __init__(self, retriever_service: Any):
        """
        Initialize adapter.

        Args:
            retriever_service: RetrieverService instance
        """
        self._service = retriever_service

    async def search_chunks(
        self,
        query: str,
        limit: int = 10,
        repo_id: str = "",
        snapshot_id: str = "main",
    ) -> list[dict]:
        """
        Search for chunks using RetrieverService.

        Args:
            query: Search query
            limit: Max results
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            List of chunk dicts with: {id, content, file_path, line, score}

        Raises:
            RuntimeError: If retrieval fails
        """
        try:
            result = await self._service.retrieve(
                repo_id=repo_id or "default",
                snapshot_id=snapshot_id or "main",
                query=query,
                token_budget=4000,  # Default budget
                timeout_seconds=10.0,
            )

            # Extract chunks from RetrievalResult
            chunks = []
            for item in result.results[:limit]:
                chunks.append(
                    {
                        "id": getattr(item, "chunk_id", getattr(item, "id", "")),
                        "content": getattr(item, "content", ""),
                        "file_path": getattr(item, "file_path", ""),
                        "line": getattr(item, "line", 0),
                        "score": getattr(item, "score", 0.0),
                    }
                )

            return chunks

        except Exception as e:
            logger.error(f"Chunk search failed: {e}", query=query)
            raise RuntimeError(f"Chunk retrieval failed: {e}") from e


def create_chunk_retriever(
    vector_store: Any,
    edge_store: Any | None = None,
) -> ChunkRetrieverAdapter:
    """
    Create chunk retriever instance.

    Factory function creating adapter around RetrieverService.

    Args:
        vector_store: QdrantVectorIndex instance
        edge_store: Optional edge store (unused, for API compatibility)

    Returns:
        ChunkRetrieverAdapter instance

    Raises:
        RuntimeError: If retriever cannot be created

    Example:
        from apps.mcp.mcp.adapters.store.factory import create_all_stores

        node_store, edge_store, vector_store = create_all_stores()
        retriever = create_chunk_retriever(vector_store, edge_store)

        results = await retriever.search_chunks("authentication logic", limit=5)

    Notes:
        - Uses RetrieverService with default configuration
        - Fallback to simple search if full service unavailable
    """
    try:
        # Try to create full RetrieverService
        from codegraph_search.infrastructure.di import create_retriever_service_minimal

        # Create minimal service (lexical + vector only)
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        service = loop.run_until_complete(create_retriever_service_minimal())

        logger.info("✓ Chunk Retriever: RetrieverService (full)")
        return ChunkRetrieverAdapter(service)

    except Exception as e:
        logger.warning(f"Full RetrieverService unavailable: {e}, using vector-only fallback")

        # Fallback: Vector-only search
        return ChunkRetrieverAdapter(_create_vector_only_retriever(vector_store))


def _create_vector_only_retriever(vector_store: Any) -> Any:
    """
    Create minimal vector-only retriever (fallback).

    Args:
        vector_store: QdrantVectorIndex

    Returns:
        Minimal retriever with retrieve() method
    """

    class VectorOnlyRetriever:
        """Minimal retriever using vector search only."""

        def __init__(self, vector_store: Any):
            self.vector_store = vector_store

        async def retrieve(
            self,
            repo_id: str,
            snapshot_id: str,
            query: str,
            token_budget: int,
            timeout_seconds: float,
        ) -> Any:
            """Simple vector search."""
            from types import SimpleNamespace

            # Vector search
            results = await self.vector_store.search(
                collection_name="chunks",
                query_text=query,
                limit=10,
                score_threshold=0.5,
            )

            # Convert to RetrievalResult-like structure
            items = [
                SimpleNamespace(
                    chunk_id=r.get("id", ""),
                    content=r.get("payload", {}).get("content", ""),
                    file_path=r.get("payload", {}).get("file_path", ""),
                    line=r.get("payload", {}).get("line", 0),
                    score=r.get("score", 0.0),
                )
                for r in results
            ]

            return SimpleNamespace(results=items)

    logger.info("✓ Chunk Retriever: Vector-only (fallback)")
    return VectorOnlyRetriever(vector_store)
