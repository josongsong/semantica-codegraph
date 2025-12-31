"""
Graph Expansion Client for Flow Tracing

BFS-based call graph expansion for tracing execution flows.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

if TYPE_CHECKING:
    from codegraph_search.infrastructure.scope.models import ScopeResult
    from codegraph_shared.ports import SymbolIndexPort

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.types import TraversalDirection

logger = get_logger(__name__)


@dataclass
class GraphExpansionConfig:
    """Configuration for graph expansion."""

    max_depth: int = 3
    """Maximum BFS depth"""

    max_nodes: int = 40
    """Maximum total nodes to expand"""

    prefer_non_test: bool = True
    """Prefer non-test paths in expansion"""

    prefer_non_mock: bool = True
    """Prefer non-mock implementations"""


@dataclass
class ExpansionNode:
    """Node in expansion graph."""

    symbol_id: str
    chunk_id: str
    depth: int
    parent_id: str | None = None
    metadata: dict = field(default_factory=dict)


class GraphExpansionClient:
    """
    Graph-based flow expansion client.

    Expands call graph using BFS to trace execution flows.
    Separated from SymbolIndexClient:
    - SymbolIndexClient: Static structure (definitions, references, imports)
    - GraphExpansionClient: Dynamic flow (call chains, multi-hop expansion)
    """

    def __init__(
        self,
        symbol_index: "SymbolIndexPort",
        config: GraphExpansionConfig | None = None,
    ):
        """
        Initialize graph expansion client.

        Args:
            symbol_index: Symbol index port for graph queries
            config: Expansion configuration
        """
        self.symbol_index = symbol_index
        self.config = config or GraphExpansionConfig()

    async def expand_flow(
        self,
        start_symbol_ids: list[str],
        direction: TraversalDirection = TraversalDirection.FORWARD,
        scope: "ScopeResult | None" = None,
    ) -> list[SearchHit]:
        """
        Expand call graph from starting symbols.

        Args:
            start_symbol_ids: Starting symbol IDs
            direction: Expansion direction (TraversalDirection.FORWARD or BACKWARD)
            scope: Scope result for filtering

        Returns:
            List of SearchHit for expanded nodes
        """
        if not start_symbol_ids:
            return []

        # BFS expansion
        visited: set[str] = set()
        expansion_nodes: list[ExpansionNode] = []
        queue = deque()

        # Initialize queue with start symbols
        for symbol_id in start_symbol_ids:
            queue.append(ExpansionNode(symbol_id=symbol_id, chunk_id="", depth=0))
            visited.add(symbol_id)

        # BFS
        while queue and len(expansion_nodes) < self.config.max_nodes:
            current = queue.popleft()

            # Stop at max depth
            if current.depth >= self.config.max_depth:
                continue

            # Get neighbors based on direction
            if direction == TraversalDirection.FORWARD:
                neighbors = await self.symbol_index.get_callees(current.symbol_id)
            else:
                neighbors = await self.symbol_index.get_callers(current.symbol_id)

            # Process neighbors
            for neighbor in neighbors:
                neighbor_id = neighbor.get("symbol_id", "")
                if not neighbor_id or neighbor_id in visited:
                    continue

                # Apply filters
                if not self._should_expand(neighbor):
                    continue

                visited.add(neighbor_id)

                # Create expansion node
                exp_node = ExpansionNode(
                    symbol_id=neighbor_id,
                    chunk_id=neighbor.get("chunk_id", ""),
                    depth=current.depth + 1,
                    parent_id=current.symbol_id,
                    metadata=neighbor,
                )

                expansion_nodes.append(exp_node)
                queue.append(exp_node)

                # Check node limit
                if len(expansion_nodes) >= self.config.max_nodes:
                    logger.debug(f"Reached max nodes limit: {self.config.max_nodes}")
                    break

        # Convert to SearchHits
        hits = self._nodes_to_hits(expansion_nodes, scope)

        logger.info(
            f"Graph expansion: {len(start_symbol_ids)} start nodes → "
            f"{len(hits)} expanded nodes "
            f"(direction={direction}, max_depth={self.config.max_depth})"
        )

        return hits

    def _should_expand(self, neighbor: dict) -> bool:
        """
        Determine if neighbor should be expanded.

        Applies filtering heuristics (non-test, non-mock preference).

        Args:
            neighbor: Neighbor node metadata

        Returns:
            True if should expand
        """
        # Prefer non-test nodes
        if self.config.prefer_non_test:
            is_test = neighbor.get("is_test", False)
            if is_test:
                # Allow test nodes but with lower priority
                # For now, we'll allow them but this could be enhanced
                # in Phase 2 with priority scoring
                pass

        # Prefer non-mock nodes
        if self.config.prefer_non_mock:
            chunk_id = neighbor.get("chunk_id", "")
            if "mock" in chunk_id.lower():
                return False

        return True

    def _nodes_to_hits(
        self,
        nodes: list[ExpansionNode],
        scope: "ScopeResult | None",
    ) -> list[SearchHit]:
        """
        Convert expansion nodes to SearchHits.

        Args:
            nodes: Expansion nodes
            scope: Scope for filtering

        Returns:
            List of SearchHit
        """
        hits = []

        for node in nodes:
            # Apply scope filter if provided
            if scope and scope.is_focused:
                if node.chunk_id not in scope.chunk_ids:
                    continue

            # Calculate score based on depth (closer = higher score)
            # Depth 1: 1.0, Depth 2: 0.7, Depth 3: 0.5
            score = 1.0 - (node.depth * 0.15)
            score = max(score, 0.3)  # Minimum score

            hit = SearchHit(
                chunk_id=node.chunk_id,
                file_path=node.metadata.get("file_path"),
                symbol_id=node.symbol_id,
                score=score,
                source="symbol",  # Graph expansion uses symbol index
                metadata={
                    "expansion_depth": node.depth,
                    "parent_symbol_id": node.parent_id,
                    "is_test": node.metadata.get("is_test", False),
                },
            )

            hits.append(hit)

        return hits
