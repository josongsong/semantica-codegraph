"""
Cost-Aware Graph Expander.

Replaces BFS with Dijkstra's algorithm for graph expansion,
using edge costs to prioritize relevant paths.

Key improvements over BFS:
1. Edge costs: Different edge types have different traversal costs
2. Path costs: Tracks cumulative cost to each node
3. Cost-based pruning: Stops expansion when cost exceeds threshold
4. Intent-aware: Adjusts costs based on query intent
"""

import heapq
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.contexts.multi_index.infrastructure.common.documents import SearchHit
from src.contexts.retrieval_search.infrastructure.graph.edge_cost import (
    DEFAULT_EDGE_COST_CALCULATOR,
    EdgeCostCalculator,
    EdgeCostConfig,
)

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.scope.models import ScopeResult
    from src.ports import SymbolIndexPort
from src.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class CostAwareExpansionConfig:
    """Configuration for cost-aware graph expansion."""

    max_total_cost: float = 30.0
    """Maximum cumulative path cost"""

    max_nodes: int = 40
    """Maximum total nodes to expand"""

    max_depth: int = 5
    """Maximum traversal depth (safety limit)"""

    prefer_non_test: bool = True
    """Prefer non-test paths"""

    prefer_non_mock: bool = True
    """Prefer non-mock paths"""

    edge_cost_config: EdgeCostConfig = field(default_factory=EdgeCostConfig)
    """Edge cost configuration"""


@dataclass
class ExpansionPath:
    """Represents a path in the expansion graph."""

    symbol_id: str
    chunk_id: str
    total_cost: float
    depth: int
    parent_id: str | None = None
    edge_kind: str | None = None
    metadata: dict = field(default_factory=dict)

    def __lt__(self, other: "ExpansionPath"):
        """For heap comparison - lower cost is better."""
        return self.total_cost < other.total_cost


class CostAwareGraphExpander:
    """
    Cost-aware graph expansion using Dijkstra's algorithm.

    Expands call graph using edge costs to prioritize relevant paths.
    """

    def __init__(
        self,
        symbol_index: "SymbolIndexPort",
        config: CostAwareExpansionConfig | None = None,
        cost_calculator: EdgeCostCalculator | None = None,
    ):
        """
        Initialize cost-aware graph expander.

        Args:
            symbol_index: Symbol index port for graph queries
            config: Expansion configuration
            cost_calculator: Edge cost calculator
        """
        self.symbol_index = symbol_index
        self.config = config or CostAwareExpansionConfig()
        self.cost_calculator = cost_calculator or DEFAULT_EDGE_COST_CALCULATOR

    async def expand_flow(
        self,
        start_symbol_ids: list[str],
        direction: str = "forward",
        scope: "ScopeResult | None" = None,
        intent: str = "balanced",
    ) -> list[SearchHit]:
        """
        Expand call graph from starting symbols using Dijkstra's algorithm.

        Args:
            start_symbol_ids: Starting symbol IDs
            direction: Expansion direction ("forward" or "backward")
            scope: Scope result for filtering
            intent: Query intent for cost adjustment

        Returns:
            List of SearchHit for expanded nodes
        """
        if not start_symbol_ids:
            return []

        # Get intent-adjusted costs
        adjusted_costs = self.cost_calculator.get_intent_adjusted_costs(intent)

        # Priority queue: (total_cost, ExpansionPath)
        pq: list[ExpansionPath] = []
        visited: set[str] = set()
        expansion_results: list[ExpansionPath] = []

        # Initialize with start symbols (cost = 0)
        for symbol_id in start_symbol_ids:
            path = ExpansionPath(
                symbol_id=symbol_id,
                chunk_id="",
                total_cost=0.0,
                depth=0,
            )
            heapq.heappush(pq, path)
            visited.add(symbol_id)

        # Dijkstra's algorithm
        while pq and len(expansion_results) < self.config.max_nodes:
            current = heapq.heappop(pq)

            # Skip if exceeds max cost
            if current.total_cost > self.config.max_total_cost:
                logger.debug(f"Path cost exceeded threshold: {current.total_cost:.2f}")
                continue

            # Skip if exceeds max depth
            if current.depth >= self.config.max_depth:
                continue

            # Get neighbors based on direction
            neighbors = await self._get_neighbors(current.symbol_id, direction)

            for neighbor in neighbors:
                neighbor_id = neighbor.get("symbol_id", "")
                if not neighbor_id or neighbor_id in visited:
                    continue

                # Calculate edge cost
                edge_kind = neighbor.get("edge_kind", "CALLS")
                adjusted_costs.get(edge_kind, 5.0)

                # Apply contextual multipliers
                full_cost = self.cost_calculator.calculate_cost(
                    edge_kind=edge_kind,
                    source_attrs={"path": current.metadata.get("file_path", "")},
                    target_attrs=neighbor,
                    edge_attrs=neighbor.get("edge_attrs", {}),
                )

                # Total path cost
                new_total_cost = current.total_cost + full_cost

                # Skip if exceeds threshold
                if new_total_cost > self.config.max_total_cost:
                    continue

                visited.add(neighbor_id)

                # Create expansion path
                new_path = ExpansionPath(
                    symbol_id=neighbor_id,
                    chunk_id=neighbor.get("chunk_id", ""),
                    total_cost=new_total_cost,
                    depth=current.depth + 1,
                    parent_id=current.symbol_id,
                    edge_kind=edge_kind,
                    metadata=neighbor,
                )

                expansion_results.append(new_path)
                heapq.heappush(pq, new_path)

                if len(expansion_results) >= self.config.max_nodes:
                    logger.debug(f"Reached max nodes limit: {self.config.max_nodes}")
                    break

        # Convert to SearchHits
        hits = self._paths_to_hits(expansion_results, scope)

        logger.info(
            f"Cost-aware expansion: {len(start_symbol_ids)} start → "
            f"{len(hits)} expanded "
            f"(direction={direction}, intent={intent}, max_cost={self.config.max_total_cost})"
        )

        return hits

    async def _get_neighbors(self, symbol_id: str, direction: str) -> list[dict[str, Any]]:
        """Get neighbors with edge information."""
        if direction == "forward":
            raw_neighbors = await self.symbol_index.get_callees(symbol_id)
        else:
            raw_neighbors = await self.symbol_index.get_callers(symbol_id)

        # Enrich with edge kind if available
        neighbors = []
        for n in raw_neighbors:
            neighbor = dict(n)
            if "edge_kind" not in neighbor:
                neighbor["edge_kind"] = "CALLS"  # Default
            neighbors.append(neighbor)

        return neighbors

    def _paths_to_hits(
        self,
        paths: list[ExpansionPath],
        scope: "ScopeResult | None",
    ) -> list[SearchHit]:
        """Convert expansion paths to SearchHits."""
        hits = []

        # Sort by cost for ranking
        sorted_paths = sorted(paths, key=lambda p: p.total_cost)

        for rank, path in enumerate(sorted_paths):
            # Apply scope filter
            if scope and scope.is_focused:
                if path.chunk_id not in scope.chunk_ids:
                    continue

            # Calculate score: inverse of cost, normalized
            # Lower cost = higher score
            max_cost = self.config.max_total_cost
            score = max(0.1, 1.0 - (path.total_cost / max_cost))

            hit = SearchHit(
                chunk_id=path.chunk_id,
                file_path=path.metadata.get("file_path"),
                symbol_id=path.symbol_id,
                score=score,
                source="symbol",
                metadata={
                    "expansion_depth": path.depth,
                    "path_cost": path.total_cost,
                    "parent_symbol_id": path.parent_id,
                    "edge_kind": path.edge_kind,
                    "is_test": path.metadata.get("is_test", False),
                    "expansion_rank": rank,
                },
            )

            hits.append(hit)

        return hits

    async def expand_bidirectional(
        self,
        symbol_id: str,
        scope: "ScopeResult | None" = None,
        intent: str = "flow",
        forward_weight: float = 0.6,
    ) -> list[SearchHit]:
        """
        Expand in both directions with weighted combination.

        Args:
            symbol_id: Starting symbol ID
            scope: Scope result for filtering
            intent: Query intent
            forward_weight: Weight for forward results (0-1)

        Returns:
            Combined SearchHit list
        """
        # Expand both directions
        forward_hits = await self.expand_flow(
            start_symbol_ids=[symbol_id],
            direction="forward",
            scope=scope,
            intent=intent,
        )

        backward_hits = await self.expand_flow(
            start_symbol_ids=[symbol_id],
            direction="backward",
            scope=scope,
            intent=intent,
        )

        # Combine with weights
        backward_weight = 1.0 - forward_weight

        # Adjust scores
        for hit in forward_hits:
            hit.score *= forward_weight

        for hit in backward_hits:
            hit.score *= backward_weight

        # Merge and deduplicate
        seen_chunks: set[str] = set()
        combined: list[SearchHit] = []

        for hit in sorted(forward_hits + backward_hits, key=lambda h: h.score, reverse=True):
            if hit.chunk_id not in seen_chunks:
                seen_chunks.add(hit.chunk_id)
                combined.append(hit)

        return combined
