"""
Symbol Index Client

Wrapper for Kuzu Graph-based symbol search (go-to-def, find-refs).
"""

import logging
from typing import TYPE_CHECKING

from src.index.common.documents import SearchHit

if TYPE_CHECKING:
    from src.ports import SymbolIndexPort
    from src.retriever.scope.models import ScopeResult

logger = logging.getLogger(__name__)


class SymbolIndexClient:
    """
    Symbol search client for definitions and references.

    Queries Kuzu graph for symbol definitions, references, and imports.
    Phase 1: Python-focused, basic go-to-def and find-refs (1-hop).
    Phase 2: Cross-language support.
    """

    def __init__(self, symbol_index: "SymbolIndexPort"):
        """
        Initialize symbol index client.

        Args:
            symbol_index: Symbol index port (Kuzu adapter)
        """
        self.symbol_index = symbol_index

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        scope: "ScopeResult | None" = None,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        Search using symbol index (go-to-def, find-refs).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Symbol name or pattern
            scope: Scope result for filtering (optional)
            limit: Maximum results

        Returns:
            List of SearchHit from symbol index
        """
        # Query symbol index
        raw_hits = await self.symbol_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=limit * 2,
        )

        # Apply scope filter if provided
        if scope and scope.is_focused:
            filtered_hits = [hit for hit in raw_hits if hit.chunk_id in scope.chunk_ids]
            logger.debug(
                f"Symbol scope filter: {len(raw_hits)} → {len(filtered_hits)} hits "
                f"(scope size: {scope.chunk_count})"
            )
        else:
            filtered_hits = raw_hits

        # Limit to requested size
        result_hits = filtered_hits[:limit]

        logger.info(
            f"Symbol search: query='{query}' → {len(result_hits)} hits "
            f"(scope={'focused' if scope and scope.is_focused else 'full'})"
        )

        return result_hits

    async def find_definition(
        self,
        symbol_id: str,
        scope: "ScopeResult | None" = None,
    ) -> list[SearchHit]:
        """
        Find definition of a symbol.

        Args:
            symbol_id: Symbol identifier
            scope: Scope result for filtering

        Returns:
            List of SearchHit for definition(s)
        """
        # For Phase 1, this is a placeholder
        # Actual implementation depends on Kuzu graph schema
        logger.debug(f"Finding definition for symbol: {symbol_id}")
        return []

    async def find_references(
        self,
        symbol_id: str,
        scope: "ScopeResult | None" = None,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        Find references to a symbol.

        Args:
            symbol_id: Symbol identifier
            scope: Scope result for filtering
            limit: Maximum results

        Returns:
            List of SearchHit for references
        """
        # For Phase 1, this is a placeholder
        # Actual implementation depends on Kuzu graph schema
        logger.debug(f"Finding references for symbol: {symbol_id}")
        return []
