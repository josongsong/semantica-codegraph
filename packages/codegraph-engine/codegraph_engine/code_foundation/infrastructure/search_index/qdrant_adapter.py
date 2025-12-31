"""
Qdrant Vector Search Adapter

Adapter for Qdrant vector database.
Implements semantic search using embeddings.
"""

import uuid
from typing import TYPE_CHECKING, Protocol

from codegraph_engine.code_foundation.infrastructure.search_index.models import SearchableSymbol, SearchIndex

if TYPE_CHECKING:
    from codegraph_shared.infra.vector.qdrant import QdrantAdapter
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for embedding generation."""

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        ...


class QdrantVectorAdapter:
    """
    Qdrant implementation of SearchIndexPort (vector search).

    Uses Qdrant for:
    - Semantic search using embeddings
    - Similarity search for code snippets
    - Cross-language symbol matching

    Note: Embeddings are generated using LLM (OpenAI/local).
    """

    def __init__(
        self,
        qdrant_adapter: "QdrantAdapter",
        embedding_provider: EmbeddingProvider | None = None,
    ):
        """
        Initialize Qdrant adapter.

        Args:
            qdrant_adapter: QdrantAdapter instance for vector operations
            embedding_provider: Optional embedding provider (required for indexing/search)
        """
        self.qdrant = qdrant_adapter
        self.embedding_provider = embedding_provider

    def _build_symbol_text(self, symbol: SearchableSymbol) -> str:
        """
        Build searchable text from symbol for embedding.

        Combines name, docstring, and signature for better semantic matching.
        """
        parts = [symbol.name]

        if symbol.fqn and symbol.fqn != symbol.name:
            parts.append(symbol.fqn)

        if symbol.docstring:
            parts.append(symbol.docstring)

        if symbol.signature:
            parts.append(symbol.signature)

        return " ".join(parts)

    def _build_collection_name(self, repo_id: str, snapshot_id: str) -> str:
        """Build Qdrant collection name from repo and snapshot."""
        # Sanitize for Qdrant collection naming rules
        safe_repo = repo_id.replace("/", "_").replace("-", "_")
        safe_snapshot = snapshot_id[:12] if len(snapshot_id) > 12 else snapshot_id
        return f"symbols_{safe_repo}_{safe_snapshot}"

    async def index_symbols(self, search_index: SearchIndex) -> int:
        """
        Index symbols in Qdrant.

        Generates embeddings for symbols and stores in Qdrant.

        Args:
            search_index: SearchIndex to be indexed

        Returns:
            Number of symbols indexed

        Raises:
            RuntimeError: If embedding provider not configured
        """
        if not self.embedding_provider:
            raise RuntimeError("Embedding provider not configured")

        symbols = list(search_index.symbols.values())
        if not symbols:
            logger.info("No symbols to index")
            return 0

        # Build texts for embedding
        texts = [self._build_symbol_text(s) for s in symbols]

        # Generate embeddings in batch
        logger.info(f"Generating embeddings for {len(texts)} symbols")
        embeddings = await self.embedding_provider.embed_batch(texts)

        # Prepare vectors for Qdrant
        vectors = []
        for symbol, embedding in zip(symbols, embeddings, strict=False):
            # Generate UUID for Qdrant (required format)
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, symbol.id))

            vectors.append(
                {
                    "id": point_id,
                    "vector": embedding,
                    "payload": {
                        "symbol_id": symbol.id,
                        "name": symbol.name,
                        "fqn": symbol.fqn,
                        "kind": symbol.kind.value if hasattr(symbol.kind, "value") else str(symbol.kind),
                        "repo_id": symbol.repo_id,
                        "snapshot_id": symbol.snapshot_id,
                        "docstring": symbol.docstring or "",
                        "signature": symbol.signature or "",
                        "is_public": symbol.is_public,
                        "relevance_score": symbol.relevance_score(),
                    },
                }
            )

        # Upsert to Qdrant
        await self.qdrant.upsert_vectors(vectors)
        logger.info(f"Indexed {len(vectors)} symbols in Qdrant")

        return len(vectors)

    async def search_semantic(
        self,
        query: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[SearchableSymbol]:
        """
        Semantic search using embeddings.

        Converts query to embedding and finds similar symbols.

        Args:
            query: Natural language query
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results
            threshold: Similarity threshold (0.0-1.0)

        Returns:
            List of matching symbols
        """
        if not self.embedding_provider:
            logger.warning("Embedding provider not configured, returning empty results")
            return []

        # Generate query embedding
        query_embedding = await self.embedding_provider.embed(query)

        # Build filter for repo/snapshot
        filter_dict = {
            "must": [
                {"key": "repo_id", "match": {"value": repo_id}},
                {"key": "snapshot_id", "match": {"value": snapshot_id}},
            ]
        }

        # Search Qdrant
        results = await self.qdrant.search(
            query_vector=query_embedding,
            limit=limit,
            score_threshold=threshold,
            filter_dict=filter_dict,
        )

        # Convert to SearchableSymbol
        symbols = []
        for result in results:
            payload = result.get("payload", {})

            # Reconstruct SearchableSymbol from payload
            from codegraph_engine.code_foundation.infrastructure.symbol_graph.models import SymbolKind

            kind_str = payload.get("kind", "FUNCTION")
            try:
                kind = SymbolKind(kind_str)
            except ValueError:
                kind = SymbolKind.FUNCTION

            symbol = SearchableSymbol(
                id=payload.get("symbol_id", ""),
                kind=kind,
                fqn=payload.get("fqn", ""),
                name=payload.get("name", ""),
                repo_id=payload.get("repo_id", repo_id),
                snapshot_id=payload.get("snapshot_id", snapshot_id),
                docstring=payload.get("docstring") or None,
                signature=payload.get("signature") or None,
                is_public=payload.get("is_public", True),
            )
            symbols.append(symbol)

        return symbols

    async def search_fuzzy(
        self,
        query: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
    ) -> list[SearchableSymbol]:
        """
        Fuzzy search (falls back to semantic search).

        Args:
            query: Fuzzy search query
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        # Lower threshold for fuzzy matching
        return await self.search_semantic(query, repo_id, snapshot_id, limit, threshold=0.5)

    async def search_prefix(
        self,
        prefix: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
    ) -> list[SearchableSymbol]:
        """
        Prefix search (not supported by Qdrant).

        Returns empty list - use Tantivy or PostgreSQL for prefix search.

        Args:
            prefix: Name prefix
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            Empty list
        """
        return []

    async def search_signature(
        self,
        signature_pattern: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
    ) -> list[SearchableSymbol]:
        """
        Signature search using embeddings.

        Args:
            signature_pattern: Signature pattern
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        return await self.search_semantic(signature_pattern, repo_id, snapshot_id, limit)

    async def delete_index(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete indexed symbols for repo/snapshot.

        Note: This deletes the entire collection. For partial deletion,
        use filter-based deletion.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
        """
        try:
            await self.qdrant.delete_collection()
            logger.info(f"Deleted Qdrant index for {repo_id}:{snapshot_id}")
        except Exception as e:
            logger.error(f"Failed to delete Qdrant index: {e}")
            raise

    async def exists(self, repo_id: str, snapshot_id: str) -> bool:
        """
        Check if Qdrant index exists for repo/snapshot.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            True if index exists with data
        """
        try:
            count = await self.qdrant.count()
            return count > 0
        except Exception:
            return False
