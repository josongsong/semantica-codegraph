"""
Multi-index Search Orchestrator

Coordinates parallel searches across multiple indexes (Lexical, Vector, Symbol, Graph).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.index.common.documents import SearchHit
from src.retriever.intent.models import IntentKind, QueryIntent

if TYPE_CHECKING:
    from src.retriever.graph_runtime_expansion.flow_expander import GraphExpansionClient
    from src.retriever.scope.models import ScopeResult

    from .lexical_client import LexicalIndexClient
    from .symbol_client import SymbolIndexClient
    from .vector_client import VectorIndexClient

logger = logging.getLogger(__name__)


@dataclass
class MultiIndexResult:
    """
    Result from multi-index search.

    Attributes:
        lexical_hits: Hits from lexical index
        vector_hits: Hits from vector index
        symbol_hits: Hits from symbol index
        graph_hits: Hits from graph expansion
        errors: Errors from failed searches
    """

    lexical_hits: list[SearchHit] = field(default_factory=list)
    vector_hits: list[SearchHit] = field(default_factory=list)
    symbol_hits: list[SearchHit] = field(default_factory=list)
    graph_hits: list[SearchHit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total_hits(self) -> int:
        """Total number of hits across all indexes."""
        return (
            len(self.lexical_hits)
            + len(self.vector_hits)
            + len(self.symbol_hits)
            + len(self.graph_hits)
        )

    def get_all_hits(self) -> list[SearchHit]:
        """Get all hits as a single list."""
        return self.lexical_hits + self.vector_hits + self.symbol_hits + self.graph_hits


class MultiIndexOrchestrator:
    """
    Orchestrates parallel searches across multiple indexes.

    Determines which indexes to query based on intent and executes
    searches in parallel.
    """

    def __init__(
        self,
        lexical_client: "LexicalIndexClient",
        vector_client: "VectorIndexClient",
        symbol_client: "SymbolIndexClient",
        graph_client: "GraphExpansionClient",
    ):
        """
        Initialize multi-index orchestrator.

        Args:
            lexical_client: Lexical search client
            vector_client: Vector search client
            symbol_client: Symbol search client
            graph_client: Graph expansion client
        """
        self.lexical_client = lexical_client
        self.vector_client = vector_client
        self.symbol_client = symbol_client
        self.graph_client = graph_client

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        intent: QueryIntent,
        scope: "ScopeResult | None" = None,
        llm_requested_indices: list[str] | None = None,
        limit: int = 50,
    ) -> MultiIndexResult:
        """
        Execute multi-index search in parallel.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query
            intent: Query intent
            scope: Scope result for filtering
            llm_requested_indices: Explicitly requested indexes by LLM
            limit: Maximum results per index

        Returns:
            MultiIndexResult with hits from all queried indexes
        """
        # Determine which indexes to query
        tasks = []

        if llm_requested_indices:
            # LLM explicitly requested specific indexes
            logger.debug(f"Using LLM-requested indexes: {llm_requested_indices}")
            indices_to_query = set(llm_requested_indices)
        else:
            # Use intent-based strategy
            indices_to_query = self._get_indices_for_intent(intent.kind)
            logger.debug(
                f"Using intent-based indexes for {intent.kind.value}: {indices_to_query}"
            )

        # Build tasks for parallel execution
        if "lexical" in indices_to_query:
            tasks.append(
                self._safe_search(
                    "lexical",
                    self.lexical_client.search(repo_id, snapshot_id, query, scope, limit),
                )
            )

        if "vector" in indices_to_query:
            tasks.append(
                self._safe_search(
                    "vector", self.vector_client.search(repo_id, snapshot_id, query, scope, limit)
                )
            )

        if "symbol" in indices_to_query:
            tasks.append(
                self._safe_search(
                    "symbol", self.symbol_client.search(repo_id, snapshot_id, query, scope, limit)
                )
            )

        # Graph expansion is special - only for flow_trace intent
        if "graph" in indices_to_query or intent.kind == IntentKind.FLOW_TRACE:
            # For now, skip graph expansion if no symbol names
            # In a real implementation, we'd extract symbols from the query
            if intent.symbol_names:
                tasks.append(
                    self._safe_search(
                        "graph",
                        self.graph_client.expand_flow(
                            intent.symbol_names,  # Simplified - would need symbol IDs
                            direction="forward",
                            scope=scope,
                        ),
                    )
                )

        # Execute all searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        multi_result = MultiIndexResult()

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Search error: {result}")
                continue

            index_name, hits = result

            if index_name == "lexical":
                multi_result.lexical_hits = hits
            elif index_name == "vector":
                multi_result.vector_hits = hits
            elif index_name == "symbol":
                multi_result.symbol_hits = hits
            elif index_name == "graph":
                multi_result.graph_hits = hits

        logger.info(
            f"Multi-index search completed: "
            f"lexical={len(multi_result.lexical_hits)}, "
            f"vector={len(multi_result.vector_hits)}, "
            f"symbol={len(multi_result.symbol_hits)}, "
            f"graph={len(multi_result.graph_hits)}"
        )

        return multi_result

    def _get_indices_for_intent(self, intent_kind: IntentKind) -> set[str]:
        """
        Get default indexes to query for a given intent.

        Args:
            intent_kind: Query intent kind

        Returns:
            Set of index names to query
        """
        if intent_kind in [IntentKind.CODE_SEARCH, IntentKind.CONCEPT_SEARCH]:
            # Code/concept search: lexical + vector
            return {"lexical", "vector"}

        if intent_kind == IntentKind.SYMBOL_NAV:
            # Symbol navigation: symbol + lexical
            return {"symbol", "lexical"}

        if intent_kind == IntentKind.FLOW_TRACE:
            # Flow trace: graph + symbol
            return {"graph", "symbol"}

        if intent_kind == IntentKind.REPO_OVERVIEW:
            # Repository overview: vector + lexical
            return {"vector", "lexical"}

        # Default: lexical + vector
        return {"lexical", "vector"}

    async def _safe_search(self, index_name: str, coro) -> tuple[str, list[SearchHit]]:
        """
        Execute search with error handling.

        Args:
            index_name: Name of the index
            coro: Coroutine to execute

        Returns:
            Tuple of (index_name, hits)
        """
        try:
            hits = await coro
            return index_name, hits
        except Exception as e:
            logger.error(f"Error searching {index_name} index: {e}")
            return index_name, []
