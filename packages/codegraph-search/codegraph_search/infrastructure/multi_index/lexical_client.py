"""
Lexical Index Client

Wrapper for Tantivy-based lexical search with chunk mapping.
"""

from typing import TYPE_CHECKING

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

if TYPE_CHECKING:
    from codegraph_search.infrastructure.scope.models import ScopeResult
    from codegraph_shared.ports import LexicalIndexPort
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class LexicalIndexClient:
    """
    Lexical search client with chunk mapping.

    Queries Tantivy for file/line matches and maps results to chunks.
    """

    def __init__(self, lexical_index: "LexicalIndexPort"):
        """
        Initialize lexical index client.

        Args:
            lexical_index: Lexical index port (Tantivy adapter)
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
        Search using lexical index with optimized filtering.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query (text/regex/identifier)
            scope: Scope result for filtering (optional)
            limit: Maximum results

        Returns:
            List of SearchHit from lexical index
        """
        # Request more results for filtering if scoped
        request_limit = limit * 3 if scope and scope.is_focused else limit

        # Query Tantivy
        raw_hits = await self.lexical_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=request_limit,
        )

        # Apply scope filter if provided
        if scope and scope.is_focused:
            # Convert to set for O(1) lookup
            allowed_chunks = scope.chunk_ids
            filtered_hits = [
                hit
                for hit in raw_hits
                if hit.chunk_id in allowed_chunks or not hit.chunk_id  # Keep unmapped hits
            ]
            logger.debug(
                f"Lexical scope filter: {len(raw_hits)} → {len(filtered_hits)} hits (scope size: {scope.chunk_count})"
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
