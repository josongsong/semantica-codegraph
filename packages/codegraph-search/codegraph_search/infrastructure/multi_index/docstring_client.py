"""
Docstring Index Client

Searches only docstring chunks for documentation queries.
"""

from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.vector.qdrant_adapter import QdrantVectorAdapter
    from codegraph_search.infrastructure.scope.models import ScopeResult

logger = get_logger(__name__)


class DocstringIndexClient:
    """
    Client for searching docstring-only chunks.

    Uses vector search with filter: chunk.kind == "docstring"
    Optimized for natural language documentation queries.
    """

    def __init__(self, vector_adapter: "QdrantVectorAdapter"):
        """
        Initialize docstring index client.

        Args:
            vector_adapter: Qdrant vector adapter (shared with vector index)
        """
        self.vector_adapter = vector_adapter

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        scope: "ScopeResult | None" = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        """
        Search docstring chunks only.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            scope: Scope filter (optional)
            limit: Maximum results

        Returns:
            List of SearchHit from docstring chunks
        """
        try:
            # Use vector adapter with docstring filter
            hits = await self.vector_adapter.search(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query=query,
                limit=limit,
                # Filter: only docstring chunks
                filter_conditions={"must": [{"key": "kind", "match": {"value": "docstring"}}]},
            )

            # Mark source as "docstring" for fusion weights
            for hit in hits:
                hit.source = "docstring"
                hit.metadata["search_type"] = "docstring"

            logger.debug(f"Docstring search: {len(hits)} hits for query='{query[:50]}'")

            return hits

        except Exception as e:
            logger.error(f"Docstring search failed: {e}")
            return []

    async def search_by_symbol(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_fqn: str,
        limit: int = 5,
    ) -> list[SearchHit]:
        """
        Search docstrings for a specific symbol.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            symbol_fqn: Fully qualified name of symbol
            limit: Maximum results

        Returns:
            List of docstring hits for the symbol
        """
        try:
            # Query: "symbol_name documentation"
            # Filter: docstring chunks matching FQN pattern
            query = f"{symbol_fqn.split('.')[-1]} documentation"

            hits = await self.vector_adapter.search(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query=query,
                limit=limit,
                filter_conditions={
                    "must": [
                        {"key": "kind", "match": {"value": "docstring"}},
                        # Approximate FQN match (contains symbol name)
                        {"key": "fqn", "match": {"text": symbol_fqn}},
                    ]
                },
            )

            for hit in hits:
                hit.source = "docstring"

            return hits

        except Exception as e:
            logger.error(f"Docstring search by symbol failed: {e}")
            return []
