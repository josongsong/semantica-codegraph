"""
MCP Services

High-level services for Model Context Protocol (MCP) server.

Services:
- MCPSearchService: Semantic code search (chunks + symbols)

Architecture:
- Application Service Layer (Hexagonal Architecture)
- Delegates to infrastructure retrievers/query builders
- Clean interface for MCP handlers

Usage:
    from apps.mcp.mcp.adapters.mcp.services import MCPSearchService
    from apps.mcp.mcp.adapters.store.factory import create_all_stores
    from apps.mcp.mcp.adapters.search import create_chunk_retriever, create_symbol_retriever

    # Initialize stores
    node_store, edge_store, vector_store = create_all_stores()

    # Create retrievers
    chunk_retriever = create_chunk_retriever(vector_store, edge_store)
    symbol_retriever = create_symbol_retriever(vector_store, edge_store)

    # Create service
    search_service = MCPSearchService(chunk_retriever, symbol_retriever, node_store)

    # Use service
    chunks = await search_service.search_chunks("authentication", limit=5)
    symbols = await search_service.search_symbols("User", limit=10)
"""

from typing import Any, Protocol

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


# ============================================================
# Protocols (Type Safety)
# ============================================================


class ChunkRetrieverProtocol(Protocol):
    """
    Protocol for chunk retriever interface.

    Ensures type safety for chunk retriever implementations.
    """

    async def search_chunks(
        self,
        query: str,
        limit: int,
        repo_id: str,
        snapshot_id: str,
    ) -> list[dict]:
        """Search for code chunks."""
        ...


class SymbolRetrieverProtocol(Protocol):
    """
    Protocol for symbol retriever interface.

    Ensures type safety for symbol retriever implementations.
    """

    async def search_symbols(
        self,
        query: str,
        limit: int,
        repo_id: str,
        snapshot_id: str,
    ) -> list[dict]:
        """Search for code symbols."""
        ...


class NodeStoreProtocol(Protocol):
    """
    Protocol for node store interface.

    Ensures type safety for node store implementations.
    """

    async def get_by_id(self, chunk_id: str) -> Any:
        """Get chunk by ID."""
        ...


# ============================================================
# Domain Models (Simple DTOs)
# ============================================================


class SearchResult:
    """
    Search result DTO.

    Attributes:
        id: Result identifier
        content: Content snippet
        file_path: Source file path
        line: Line number
        score: Relevance score (0.0 - 1.0)
        metadata: Additional metadata
    """

    def __init__(
        self,
        id: str,
        content: str,
        file_path: str,
        line: int,
        score: float,
        metadata: dict | None = None,
    ):
        self.id = id
        self.content = content
        self.file_path = file_path
        self.line = line
        self.score = score
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "file_path": self.file_path,
            "line": self.line,
            "score": self.score,
            **self.metadata,
        }


# ============================================================
# MCPSearchService (Semantic Code Search)
# ============================================================


class MCPSearchService:
    """
    Search service for MCP server.

    Provides semantic search over:
    - Code chunks (multi-line code blocks)
    - Symbols (functions, classes, variables)

    Architecture:
    - Application Service (Hexagonal Architecture)
    - Delegates to chunk_retriever and symbol_retriever
    - Returns simple DTOs (SearchResult)

    Example:
        service = MCPSearchService(chunk_retriever, symbol_retriever, node_store)

        # Search chunks
        chunks = await service.search_chunks("authentication logic", limit=5)
        for chunk in chunks:
            print(f"{chunk.file_path}:{chunk.line} - {chunk.content[:50]}...")

        # Search symbols
        symbols = await service.search_symbols("User class", limit=10)
        for symbol in symbols:
            print(f"{symbol.file_path}:{symbol.line} - {symbol.content}")
    """

    def __init__(
        self,
        chunk_retriever: ChunkRetrieverProtocol,
        symbol_retriever: SymbolRetrieverProtocol,
        node_store: NodeStoreProtocol,
    ):
        """
        Initialize search service.

        Args:
            chunk_retriever: ChunkRetrieverAdapter instance
            symbol_retriever: SymbolRetrieverAdapter instance
            node_store: ChunkStore instance (for get_chunk/get_symbol)
        """
        self._chunk_retriever = chunk_retriever
        self._symbol_retriever = symbol_retriever
        self._node_store = node_store

        logger.info("MCPSearchService initialized")

    async def search_chunks(
        self,
        query: str,
        limit: int = 10,
        repo_id: str = "",
        snapshot_id: str = "main",
    ) -> list[SearchResult]:
        """
        Search for code chunks matching query.

        Args:
            query: Search query string
            limit: Maximum results (default: 10)
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier

        Returns:
            List of SearchResult objects

        Raises:
            ValueError: If query is empty
            RuntimeError: If search fails

        Example:
            results = await service.search_chunks("JWT token validation", limit=5)
            for result in results:
                print(f"{result.score:.2f} - {result.file_path}:{result.line}")
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        try:
            # Delegate to chunk retriever
            raw_results = await self._chunk_retriever.search_chunks(
                query=query.strip(),
                limit=limit,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
            )

            # Convert to SearchResult DTOs
            results = [
                SearchResult(
                    id=r.get("id", ""),
                    content=r.get("content", ""),
                    file_path=r.get("file_path", ""),
                    line=r.get("line", 0),
                    score=r.get("score", 0.0),
                    metadata={"type": "chunk"},
                )
                for r in raw_results
            ]

            logger.info(f"search_chunks: {len(results)} results", query=query[:50])
            return results

        except Exception as e:
            logger.error(f"search_chunks failed: {e}", query=query)
            raise RuntimeError(f"Chunk search failed: {e}") from e

    async def search_symbols(
        self,
        query: str,
        limit: int = 10,
        repo_id: str = "",
        snapshot_id: str = "main",
    ) -> list[SearchResult]:
        """
        Search for code symbols matching query.

        Args:
            query: Search query string
            limit: Maximum results (default: 10)
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier

        Returns:
            List of SearchResult objects

        Raises:
            ValueError: If query is empty
            RuntimeError: If search fails

        Example:
            results = await service.search_symbols("authenticate function", limit=10)
            for result in results:
                print(f"{result.content} - {result.metadata.get('kind', 'unknown')}")
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        try:
            # Delegate to symbol retriever
            raw_results = await self._symbol_retriever.search_symbols(
                query=query.strip(),
                limit=limit,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
            )

            # Convert to SearchResult DTOs
            results = [
                SearchResult(
                    id=r.get("id", ""),
                    content=r.get("name", ""),  # Symbol name as content
                    file_path=r.get("file_path", ""),
                    line=r.get("line", 0),
                    score=r.get("score", 0.0),
                    metadata={
                        "type": "symbol",
                        "kind": r.get("kind", "unknown"),
                        "name": r.get("name", ""),
                    },
                )
                for r in raw_results
            ]

            logger.info(f"search_symbols: {len(results)} results", query=query[:50])
            return results

        except Exception as e:
            logger.error(f"search_symbols failed: {e}", query=query)
            raise RuntimeError(f"Symbol search failed: {e}") from e

    async def get_chunk(self, chunk_id: str) -> SearchResult | None:
        """
        Get chunk by ID.

        Args:
            chunk_id: Chunk identifier

        Returns:
            SearchResult or None if not found

        Raises:
            ValueError: If chunk_id is empty
        """
        if not chunk_id:
            raise ValueError("chunk_id cannot be empty")

        try:
            # Query node_store (ChunkStore)
            chunk = await self._node_store.get_by_id(chunk_id)

            if not chunk:
                return None

            return SearchResult(
                id=chunk.id,
                content=chunk.content,
                file_path=chunk.file_path,
                line=chunk.start_line,
                score=1.0,  # Direct lookup, perfect score
                metadata={"type": "chunk"},
            )

        except Exception as e:
            logger.error(f"get_chunk failed: {e}", chunk_id=chunk_id)
            return None  # Graceful degradation

    async def get_symbol(self, symbol_id: str) -> SearchResult | None:
        """
        Get symbol by ID.

        Args:
            symbol_id: Symbol identifier

        Returns:
            SearchResult or None if not found

        Raises:
            ValueError: If symbol_id is empty
        """
        if not symbol_id:
            raise ValueError("symbol_id cannot be empty")

        try:
            # Search with exact ID match
            results = await self.search_symbols(
                query=symbol_id,
                limit=1,
            )

            return results[0] if results else None

        except Exception as e:
            logger.error(f"get_symbol failed: {e}", symbol_id=symbol_id)
            return None  # Graceful degradation
