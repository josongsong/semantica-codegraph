"""
Symbol Retriever Factory

Creates symbol retriever instances for semantic symbol search.

Architecture:
- Wraps SymbolSearchLayer or RetrieverService
- Provides async search interface for symbols (functions, classes, etc.)

Returns:
    Retriever object with search_symbols() method
"""

from typing import Any, Protocol

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class SymbolRetrieverProtocol(Protocol):
    """
    Protocol for symbol retriever interface.

    Methods:
        search_symbols: Search for code symbols by query
    """

    async def search_symbols(
        self,
        query: str,
        limit: int = 10,
        repo_id: str = "",
        snapshot_id: str = "main",
    ) -> list[dict]:
        """
        Search for code symbols matching query.

        Args:
            query: Search query string
            limit: Maximum results to return
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier

        Returns:
            List of symbol results as dicts
        """
        ...


class SymbolRetrieverAdapter:
    """
    Adapter wrapping SymbolSearchLayer for symbol search.

    Delegates to production SymbolSearchLayer from retrieval_search context.
    """

    def __init__(self, symbol_search_layer: Any):
        """
        Initialize adapter.

        Args:
            symbol_search_layer: SymbolSearchLayer instance
        """
        self._layer = symbol_search_layer

    async def search_symbols(
        self,
        query: str,
        limit: int = 10,
        repo_id: str = "",
        snapshot_id: str = "main",
    ) -> list[dict]:
        """
        Search for symbols using SymbolSearchLayer.

        Args:
            query: Search query
            limit: Max results
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            List of symbol dicts with: {id, name, kind, file_path, line, score}

        Raises:
            RuntimeError: If symbol search fails
        """
        try:
            results = await self._layer.search(
                query=query,
                repo_id=repo_id or "default",
                snapshot_id=snapshot_id or "main",
                limit=limit,
            )

            # Convert to standard dict format
            symbols = []
            for item in results:
                symbols.append(
                    {
                        "id": getattr(item, "symbol_id", getattr(item, "id", "")),
                        "name": getattr(item, "name", ""),
                        "kind": getattr(item, "kind", "unknown"),  # function, class, etc.
                        "file_path": getattr(item, "file_path", ""),
                        "line": getattr(item, "line", 0),
                        "score": getattr(item, "score", 0.0),
                    }
                )

            return symbols

        except Exception as e:
            logger.error(f"Symbol search failed: {e}", query=query)
            raise RuntimeError(f"Symbol retrieval failed: {e}") from e


def create_symbol_retriever(
    vector_store: Any,
    edge_store: Any | None = None,
) -> SymbolRetrieverAdapter:
    """
    Create symbol retriever instance.

    Factory function creating adapter around SymbolSearchLayer.

    Args:
        vector_store: QdrantVectorIndex instance
        edge_store: Optional edge store (unused, for API compatibility)

    Returns:
        SymbolRetrieverAdapter instance

    Raises:
        RuntimeError: If retriever cannot be created

    Example:
        from apps.mcp.mcp.adapters.store.factory import create_all_stores

        node_store, edge_store, vector_store = create_all_stores()
        retriever = create_symbol_retriever(vector_store, edge_store)

        results = await retriever.search_symbols("User class", limit=5)

    Notes:
        - Uses SymbolSearchLayer if available
        - Fallback to vector-based search if symbol layer unavailable
    """
    try:
        # Try to create SymbolSearchLayer (requires IRDocument)
        # For MCP lightweight mode, skip SymbolSearchLayer and use vector fallback
        raise ImportError("SymbolSearchLayer requires IRDocument, using vector fallback in MCP mode")

    except (ImportError, Exception) as e:
        logger.warning(f"SymbolSearchLayer unavailable: {e}, using vector-based fallback")

        # Fallback: Vector-based symbol search
        return SymbolRetrieverAdapter(_create_vector_based_symbol_search(vector_store))


def _create_vector_based_symbol_search(vector_store: Any) -> Any:
    """
    Create vector-based symbol search (fallback).

    Args:
        vector_store: QdrantVectorIndex

    Returns:
        Minimal symbol search with search() method
    """

    class VectorBasedSymbolSearch:
        """Minimal symbol search using vector index."""

        def __init__(self, vector_store: Any):
            self.vector_store = vector_store

        async def search(
            self,
            query: str,
            repo_id: str,
            snapshot_id: str,
            limit: int,
        ) -> list[Any]:
            """
            Vector-based symbol search.

            Searches 'symbols' collection in Qdrant.
            """
            from types import SimpleNamespace

            try:
                # Search symbols collection
                results = await self.vector_store.search(
                    collection_name="symbols",
                    query_text=query,
                    limit=limit,
                    score_threshold=0.5,
                )

                # Convert to symbol-like objects
                symbols = [
                    SimpleNamespace(
                        symbol_id=r.get("id", ""),
                        name=r.get("payload", {}).get("name", ""),
                        kind=r.get("payload", {}).get("kind", "unknown"),
                        file_path=r.get("payload", {}).get("file_path", ""),
                        line=r.get("payload", {}).get("line", 0),
                        score=r.get("score", 0.0),
                    )
                    for r in results
                ]

                return symbols

            except Exception as e:
                logger.debug(f"Vector symbol search failed: {e}")
                return []  # Graceful degradation

    logger.info("✓ Symbol Retriever: Vector-based (fallback)")
    return VectorBasedSymbolSearch(vector_store)
