"""
Symbol Index Client

Wrapper for Kuzu Graph-based symbol search (go-to-def, find-refs).
"""

from typing import TYPE_CHECKING

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

if TYPE_CHECKING:
    from codegraph_search.infrastructure.scope.models import ScopeResult
    from codegraph_shared.ports import SymbolIndexPort
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


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
        Search using symbol index with optimized filtering (consistent with vector/lexical).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Symbol name or pattern
            scope: Scope result for filtering (optional)
            limit: Maximum results

        Returns:
            List of SearchHit from symbol index
        """
        # Request more results for filtering if scoped
        request_limit = limit * 3 if scope and scope.is_focused else limit

        # Query symbol index
        raw_hits = await self.symbol_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=request_limit,
        )

        # Apply scope filter if provided
        if scope and scope.is_focused:
            # Convert to set for O(1) lookup (consistent with lexical client)
            allowed_chunks = scope.chunk_ids
            filtered_hits = [hit for hit in raw_hits if hit.chunk_id in allowed_chunks]
            logger.debug(
                f"Symbol scope filter: {len(raw_hits)} → {len(filtered_hits)} hits (scope size: {scope.chunk_count})"
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
        Find definition of a symbol using graph queries.

        Args:
            symbol_id: Symbol identifier
            scope: Scope result for filtering

        Returns:
            List of SearchHit for definition(s)
        """
        logger.debug(f"Finding definition for symbol: {symbol_id}")

        try:
            # Get symbol node from graph (definition is the node itself)
            node = await self.symbol_index.get_node_by_id(symbol_id)

            if not node:
                logger.warning(f"Symbol not found: {symbol_id}")
                return []

            # Create SearchHit from node
            hit = SearchHit(
                chunk_id=node.get("chunk_id", ""),
                file_path=node.get("path", ""),
                symbol_id=symbol_id,
                score=1.0,  # Exact definition
                source="symbol",
                metadata={
                    "kind": node.get("kind", ""),
                    "fqn": node.get("fqn", ""),
                    "name": node.get("name", ""),
                    "is_definition": True,
                },
            )

            # Apply scope filter
            if scope and scope.is_focused:
                if hit.chunk_id not in scope.chunk_ids:
                    return []

            return [hit]

        except Exception as e:
            logger.error(f"Failed to find definition for {symbol_id}: {e}")
            return []

    async def find_references(
        self,
        symbol_id: str,
        scope: "ScopeResult | None" = None,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        Find references to a symbol using REFERENCES edges in graph.

        Args:
            symbol_id: Symbol identifier
            scope: Scope result for filtering
            limit: Maximum results

        Returns:
            List of SearchHit for references
        """
        logger.debug(f"Finding references for symbol: {symbol_id}")

        try:
            # Query references using graph (nodes that REFERENCE this symbol)
            # This assumes REFERENCES edge exists in graph
            reference_nodes = await self.symbol_index.get_references(symbol_id)

            hits = []
            for ref_node in reference_nodes[:limit]:
                hit = SearchHit(
                    chunk_id=ref_node.get("chunk_id", ""),
                    file_path=ref_node.get("path", ""),
                    symbol_id=ref_node.get("node_id", ""),
                    score=0.9,  # Reference (slightly lower than definition)
                    source="symbol",
                    metadata={
                        "kind": ref_node.get("kind", ""),
                        "fqn": ref_node.get("fqn", ""),
                        "name": ref_node.get("name", ""),
                        "is_reference": True,
                        "referenced_symbol": symbol_id,
                    },
                )

                # Apply scope filter
                if scope and scope.is_focused:
                    if hit.chunk_id not in scope.chunk_ids:
                        continue

                hits.append(hit)

            logger.info(f"Found {len(hits)} references for symbol {symbol_id}")
            return hits

        except AttributeError as e:
            # get_references not implemented in symbol_index
            logger.warning(
                f"get_references not implemented in symbol index: {e}. Add 'get_references' method to SymbolIndexPort."
            )
            return []
        except Exception as e:
            logger.error(f"Failed to find references for {symbol_id}: {e}")
            return []
