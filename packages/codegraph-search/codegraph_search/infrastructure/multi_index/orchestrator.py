"""
Multi-index Search Orchestrator

Coordinates parallel searches across multiple indexes (Lexical, Vector, Symbol, Graph).
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.intent.models import IntentKind, QueryIntent

if TYPE_CHECKING:
    from codegraph_search.infrastructure.graph_runtime_expansion.flow_expander import GraphExpansionClient
    from codegraph_search.infrastructure.multi_index.docstring_client import DocstringIndexClient
    from codegraph_search.infrastructure.multi_index.lexical_client import LexicalIndexClient
    from codegraph_search.infrastructure.multi_index.symbol_client import SymbolIndexClient
    from codegraph_search.infrastructure.multi_index.vector_client import VectorIndexClient
    from codegraph_search.infrastructure.scope.models import ScopeResult

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.types import TraversalDirection

logger = get_logger(__name__)


@dataclass
class MultiIndexResult:
    """
    Result from multi-index search.

    Attributes:
        lexical_hits: Hits from lexical index
        vector_hits: Hits from vector index
        symbol_hits: Hits from symbol index
        graph_hits: Hits from graph expansion
        docstring_hits: Hits from docstring index (P0-1)
        errors: Errors from failed searches
    """

    lexical_hits: list[SearchHit] = field(default_factory=list)
    vector_hits: list[SearchHit] = field(default_factory=list)
    symbol_hits: list[SearchHit] = field(default_factory=list)
    graph_hits: list[SearchHit] = field(default_factory=list)
    docstring_hits: list[SearchHit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total_hits(self) -> int:
        """Total number of hits across all indexes."""
        return (
            len(self.lexical_hits)
            + len(self.vector_hits)
            + len(self.symbol_hits)
            + len(self.graph_hits)
            + len(self.docstring_hits)
        )

    def get_all_hits(self) -> list[SearchHit]:
        """Get all hits as a single list."""
        return self.lexical_hits + self.vector_hits + self.symbol_hits + self.graph_hits + self.docstring_hits


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
        docstring_client: "DocstringIndexClient | None" = None,
    ):
        """
        Initialize multi-index orchestrator.

        Args:
            lexical_client: Lexical search client
            vector_client: Vector search client
            symbol_client: Symbol search client
            graph_client: Graph expansion client
            docstring_client: Docstring search client (P0-1, optional)
        """
        self.lexical_client = lexical_client
        self.vector_client = vector_client
        self.symbol_client = symbol_client
        self.graph_client = graph_client
        self.docstring_client = docstring_client

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
        if llm_requested_indices:
            # LLM explicitly requested specific indexes
            logger.debug(f"Using LLM-requested indexes: {llm_requested_indices}")
            indices_to_query = set(llm_requested_indices)
        else:
            # Use intent-based strategy
            indices_to_query = self._get_indices_for_intent(intent.kind)
            logger.debug(f"Using intent-based indexes for {intent.kind.value}: {indices_to_query}")

        # Build tasks for parallel execution (track index names)
        tasks = []
        task_index_names = []

        if "lexical" in indices_to_query:
            tasks.append(
                self._safe_search(
                    "lexical",
                    self.lexical_client.search(repo_id, snapshot_id, query, scope, limit),
                )
            )
            task_index_names.append("lexical")

        if "vector" in indices_to_query:
            tasks.append(
                self._safe_search("vector", self.vector_client.search(repo_id, snapshot_id, query, scope, limit))
            )
            task_index_names.append("vector")

        if "symbol" in indices_to_query:
            tasks.append(
                self._safe_search("symbol", self.symbol_client.search(repo_id, snapshot_id, query, scope, limit))
            )
            task_index_names.append("symbol")

        # Docstring search (P0-1)
        if "docstring" in indices_to_query and self.docstring_client:
            tasks.append(
                self._safe_search("docstring", self.docstring_client.search(repo_id, snapshot_id, query, scope, limit))
            )
            task_index_names.append("docstring")

        # Graph expansion is special - only for flow_trace intent
        if "graph" in indices_to_query or intent.kind == IntentKind.FLOW_TRACE:
            # For now, skip graph expansion if no symbol names
            if intent.symbol_names:
                # Convert symbol names to IDs for graph expansion
                symbol_ids = await self._resolve_symbol_names_to_ids(
                    symbol_names=intent.symbol_names, repo_id=repo_id, snapshot_id=snapshot_id
                )

                if symbol_ids:
                    tasks.append(
                        self._safe_search(
                            "graph",
                            self.graph_client.expand_flow(
                                symbol_ids,  # Now using actual symbol IDs
                                direction=TraversalDirection.FORWARD,
                                scope=scope,
                            ),
                        )
                    )
                    task_index_names.append("graph")
                else:
                    logger.warning(f"Could not resolve symbol names to IDs: {intent.symbol_names}")

        # Execute all searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        multi_result = MultiIndexResult()

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Determine which index failed using task_index_names
                index_name = task_index_names[i] if i < len(task_index_names) else "unknown"
                error_msg = f"{type(result).__name__}: {str(result)}"
                multi_result.errors[index_name] = error_msg
                logger.error(f"{index_name} search failed: {error_msg}")
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
            elif index_name == "docstring":
                multi_result.docstring_hits = hits

        logger.info(
            f"Multi-index search completed: "
            f"lexical={len(multi_result.lexical_hits)}, "
            f"vector={len(multi_result.vector_hits)}, "
            f"symbol={len(multi_result.symbol_hits)}, "
            f"graph={len(multi_result.graph_hits)}, "
            f"docstring={len(multi_result.docstring_hits)}"
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

        if intent_kind == IntentKind.DOC_SEARCH:
            # Documentation search: docstring + vector (P0-1)
            return {"docstring", "vector"}

        # Default: lexical + vector
        return {"lexical", "vector"}

    async def _resolve_symbol_names_to_ids(self, symbol_names: list[str], repo_id: str, snapshot_id: str) -> list[str]:
        """
        Resolve symbol names to symbol IDs using symbol index.

        Args:
            symbol_names: List of symbol names (e.g., ["HybridRetriever", "search"])
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            List of resolved symbol IDs
        """
        import asyncio

        if not symbol_names:
            return []

        # Batch search: run all symbol searches in parallel (N+1 → 1 parallel batch)
        async def search_symbol(symbol_name: str) -> str | None:
            try:
                hits = await self.symbol_client.search(
                    repo_id=repo_id, snapshot_id=snapshot_id, query=symbol_name, scope=None, limit=5
                )
                for hit in hits:
                    if hit.symbol_id:
                        logger.debug(f"Resolved '{symbol_name}' → {hit.symbol_id}")
                        return hit.symbol_id
            except Exception as e:
                logger.warning(f"Failed to resolve symbol '{symbol_name}': {e}")
            return None

        # Execute all searches in parallel
        results = await asyncio.gather(*[search_symbol(name) for name in symbol_names])

        # Filter out None results
        return [sid for sid in results if sid is not None]

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
