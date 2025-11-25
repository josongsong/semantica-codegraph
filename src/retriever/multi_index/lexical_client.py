"""
Lexical Index Client

Wrapper for Zoekt-based lexical search with chunk mapping.
"""

import logging
from typing import TYPE_CHECKING

from src.index.common.documents import SearchHit

if TYPE_CHECKING:
    from src.ports import LexicalIndexPort
    from src.retriever.scope.models import ScopeResult

logger = logging.getLogger(__name__)


class LexicalIndexClient:
    """
    Lexical search client with chunk mapping.

    Queries Zoekt for file/line matches and maps results to chunks.
    """

    def __init__(self, lexical_index: "LexicalIndexPort"):
        """
        Initialize lexical index client.

        Args:
            lexical_index: Lexical index port (Zoekt adapter)
        """
        self.lexical_index = lexical_index

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        scope: "ScopeResult | None" = None,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        Search using lexical index.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query (text/regex/identifier)
            scope: Scope result for filtering (optional)
            limit: Maximum results

        Returns:
            List of SearchHit from lexical index
        """
        # Query Zoekt
        raw_hits = await self.lexical_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=limit * 2,  # Request more since we'll filter
        )

        # Apply scope filter if provided
        if scope and scope.is_focused:
            filtered_hits = [
                hit
                for hit in raw_hits
                if hit.chunk_id in scope.chunk_ids or not hit.chunk_id  # Keep unmapped hits
            ]
            logger.debug(
                f"Lexical scope filter: {len(raw_hits)} → {len(filtered_hits)} hits "
                f"(scope size: {scope.chunk_count})"
            )
        else:
            filtered_hits = raw_hits

        # Limit to requested size
        result_hits = filtered_hits[:limit]

        logger.info(
            f"Lexical search: query='{query[:50]}...' → {len(result_hits)} hits "
            f"(scope={'focused' if scope and scope.is_focused else 'full'})"
        )

        return result_hits
