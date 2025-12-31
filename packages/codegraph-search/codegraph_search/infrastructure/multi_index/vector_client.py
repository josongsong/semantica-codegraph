"""
Vector Index Client

Wrapper for Qdrant-based vector search with scope filtering.
"""

from typing import TYPE_CHECKING

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

if TYPE_CHECKING:
    from codegraph_search.infrastructure.scope.models import ScopeResult
    from codegraph_shared.ports import VectorIndexPort
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class VectorIndexClient:
    """
    Vector search client with semantic matching.

    Queries Qdrant for semantically similar chunks.
    """

    def __init__(self, vector_index: "VectorIndexPort"):
        """
        Initialize vector index client.

        Args:
            vector_index: Vector index port (Qdrant adapter)
        """
        self.vector_index = vector_index

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        scope: "ScopeResult | None" = None,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        Search using vector index with DB-level filtering.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            scope: Scope result for filtering (optional)
            limit: Maximum results

        Returns:
            List of SearchHit from vector index
        """
        # Apply scope filtering at DB level (Qdrant)
        chunk_ids = None
        if scope and scope.is_focused:
            chunk_ids = list(scope.chunk_ids)
            logger.debug(f"Using DB-level filter for {len(chunk_ids)} chunks")

        # Search with filter
        result_hits = await self.vector_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=limit,
            chunk_ids=chunk_ids,
        )

        logger.info(
            f"Vector search: query='{query[:50]}...' → {len(result_hits)} hits "
            f"(scope={'focused' if scope and scope.is_focused else 'full'})"
        )

        return result_hits
