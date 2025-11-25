"""
Vector Index Client

Wrapper for Qdrant-based vector search with scope filtering.
"""

import logging
from typing import TYPE_CHECKING

from src.index.common.documents import SearchHit

if TYPE_CHECKING:
    from src.ports import VectorIndexPort
    from src.retriever.scope.models import ScopeResult

logger = logging.getLogger(__name__)


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
        Search using vector index.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            scope: Scope result for filtering (optional)
            limit: Maximum results

        Returns:
            List of SearchHit from vector index
        """
        # For now, we query the vector index directly
        # In Phase 2, we'll add scope-based filtering at the Qdrant level
        raw_hits = await self.vector_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=limit * 2,  # Request more since we'll filter
        )

        # Apply scope filter if provided
        if scope and scope.is_focused:
            filtered_hits = [hit for hit in raw_hits if hit.chunk_id in scope.chunk_ids]
            logger.debug(
                f"Vector scope filter: {len(raw_hits)} → {len(filtered_hits)} hits "
                f"(scope size: {scope.chunk_count})"
            )
        else:
            filtered_hits = raw_hits

        # Limit to requested size
        result_hits = filtered_hits[:limit]

        logger.info(
            f"Vector search: query='{query[:50]}...' → {len(result_hits)} hits "
            f"(scope={'focused' if scope and scope.is_focused else 'full'})"
        )

        return result_hits
