"""
Edge Cost Model for Graph Traversal.

Defines traversal costs for different edge types to enable
cost-aware graph expansion (Dijkstra's algorithm instead of BFS).

Edge costs reflect:
1. Semantic relevance (direct calls vs indirect references)
2. Context quality (production code vs test/mock)
3. Cross-boundary penalties (cross-module imports)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdgeKind


class EdgeCostCategory(str, Enum):
    """Edge cost categories for cost tuning."""

    DIRECT_CALL = "direct_call"  # Direct function/method calls
    INDIRECT_REF = "indirect_ref"  # Indirect references (type refs, symbol refs)
    STRUCTURAL = "structural"  # Structural relationships (contains, imports)
    DATA_FLOW = "data_flow"  # Data flow edges (reads, writes)
    CONTROL_FLOW = "control_flow"  # Control flow edges
    FRAMEWORK = "framework"  # Framework/architecture edges


@dataclass
class EdgeCostConfig:
    """
    Configuration for edge costs.

    Lower cost = more preferred path.
    Costs are used in Dijkstra's algorithm for graph expansion.
    """

    # Base costs by edge kind
    base_costs: dict[str, float] = field(default_factory=dict)

    # Multipliers for context
    test_path_multiplier: float = 5.0  # Heavily penalize test paths
    mock_path_multiplier: float = 8.0  # Even more penalty for mocks
    cross_module_multiplier: float = 1.5  # Slight penalty for cross-module
    external_module_multiplier: float = 3.0  # External dependencies cost more

    # Maximum total cost for a path
    max_path_cost: float = 50.0

    def __post_init__(self):
        """Initialize default base costs if not provided."""
        if not self.base_costs:
            self.base_costs = DEFAULT_EDGE_COSTS.copy()


# Default edge costs by GraphEdgeKind
# Lower = more preferred
DEFAULT_EDGE_COSTS: dict[str, float] = {
    # Direct calls - lowest cost (most valuable for flow tracing)
    GraphEdgeKind.CALLS.value: 1.0,
    GraphEdgeKind.ROUTE_HANDLER.value: 1.0,
    GraphEdgeKind.HANDLES_REQUEST.value: 1.2,
    GraphEdgeKind.USES_REPOSITORY.value: 1.2,
    # Structural - low cost
    GraphEdgeKind.CONTAINS.value: 0.5,  # Parent-child is cheap to traverse
    GraphEdgeKind.INHERITS.value: 1.5,
    GraphEdgeKind.IMPLEMENTS.value: 1.5,
    # Imports - medium cost
    GraphEdgeKind.IMPORTS.value: 2.0,
    # References - medium cost
    GraphEdgeKind.REFERENCES_TYPE.value: 2.5,
    GraphEdgeKind.REFERENCES_SYMBOL.value: 2.5,
    # Data flow - medium-high cost
    GraphEdgeKind.READS.value: 3.0,
    GraphEdgeKind.WRITES.value: 3.0,
    # Control flow - high cost (less relevant for semantic search)
    GraphEdgeKind.CFG_NEXT.value: 4.0,
    GraphEdgeKind.CFG_BRANCH.value: 4.0,
    GraphEdgeKind.CFG_LOOP.value: 4.5,
    GraphEdgeKind.CFG_HANDLER.value: 4.5,
    # Decorator - medium cost
    GraphEdgeKind.DECORATES.value: 2.0,
    GraphEdgeKind.INSTANTIATES.value: 2.0,
    # Documentation - higher cost
    GraphEdgeKind.DOCUMENTS.value: 5.0,
    GraphEdgeKind.REFERENCES_CODE.value: 5.0,
    GraphEdgeKind.DOCUMENTED_IN.value: 5.0,
    # Middleware - medium cost
    GraphEdgeKind.MIDDLEWARE_NEXT.value: 2.0,
}


@dataclass
class EdgeCostCalculator:
    """
    Calculates traversal costs for graph edges.

    Combines base edge costs with contextual multipliers.
    """

    config: EdgeCostConfig = field(default_factory=EdgeCostConfig)

    def calculate_cost(
        self,
        edge_kind: str,
        source_attrs: dict[str, Any] | None = None,
        target_attrs: dict[str, Any] | None = None,
        edge_attrs: dict[str, Any] | None = None,
    ) -> float:
        """
        Calculate traversal cost for an edge.

        Args:
            edge_kind: GraphEdgeKind value
            source_attrs: Source node attributes
            target_attrs: Target node attributes
            edge_attrs: Edge attributes

        Returns:
            Traversal cost (lower = more preferred)
        """
        source_attrs = source_attrs or {}
        target_attrs = target_attrs or {}
        edge_attrs = edge_attrs or {}

        # Base cost
        base_cost = self.config.base_costs.get(edge_kind, 5.0)

        # Apply contextual multipliers
        multiplier = 1.0

        # Test path penalty
        if self._is_test_path(target_attrs):
            multiplier *= self.config.test_path_multiplier

        # Mock path penalty
        if self._is_mock_path(target_attrs):
            multiplier *= self.config.mock_path_multiplier

        # Cross-module penalty
        if self._is_cross_module(source_attrs, target_attrs):
            multiplier *= self.config.cross_module_multiplier

        # External module penalty
        if self._is_external(target_attrs):
            multiplier *= self.config.external_module_multiplier

        # Edge-specific adjustments
        adjusted_cost = base_cost * multiplier

        # Apply edge attribute bonuses/penalties
        adjusted_cost = self._apply_edge_adjustments(adjusted_cost, edge_kind, edge_attrs)

        return min(adjusted_cost, self.config.max_path_cost)

    def _is_test_path(self, attrs: dict[str, Any]) -> bool:
        """Check if target is in test code."""
        path = attrs.get("path", "") or attrs.get("file_path", "") or ""
        is_test = attrs.get("is_test", False)

        if is_test:
            return True

        path_lower = path.lower()
        return any(
            indicator in path_lower for indicator in ["test_", "_test", "/tests/", "/test/", "conftest", "fixture"]
        )

    def _is_mock_path(self, attrs: dict[str, Any]) -> bool:
        """Check if target is mock code."""
        path = attrs.get("path", "") or attrs.get("file_path", "") or ""
        name = attrs.get("name", "") or ""

        path_lower = path.lower()
        name_lower = name.lower()

        return any(indicator in path_lower or indicator in name_lower for indicator in ["mock", "fake", "stub", "spy"])

    def _is_cross_module(
        self,
        source_attrs: dict[str, Any],
        target_attrs: dict[str, Any],
    ) -> bool:
        """Check if edge crosses module boundaries."""
        source_path = source_attrs.get("path", "") or ""
        target_path = target_attrs.get("path", "") or ""

        if not source_path or not target_path:
            return False

        # Extract module (first directory component after src/)
        source_module = self._extract_module(source_path)
        target_module = self._extract_module(target_path)

        return source_module != target_module and source_module and target_module

    def _extract_module(self, path: str) -> str:
        """Extract top-level module from path."""
        parts = path.replace("\\", "/").split("/")

        # Find 'src' and get next component
        try:
            src_idx = parts.index("src")
            if src_idx + 1 < len(parts):
                return parts[src_idx + 1]
        except ValueError:
            pass

        # Fallback: first non-empty component
        for part in parts:
            if part and part not in (".", ".."):
                return part

        return ""

    def _is_external(self, attrs: dict[str, Any]) -> bool:
        """Check if target is external code."""
        kind = attrs.get("kind", "")
        is_external = attrs.get("is_external", False)

        return is_external or kind.startswith("External")

    def _apply_edge_adjustments(
        self,
        base_cost: float,
        edge_kind: str,
        edge_attrs: dict[str, Any],
    ) -> float:
        """Apply edge-specific cost adjustments."""
        cost = base_cost

        # CALLS edge adjustments
        if edge_kind == GraphEdgeKind.CALLS.value:
            # Async calls slightly cheaper (often main flow)
            if edge_attrs.get("is_async", False):
                cost *= 0.9

            # Constructor calls cheaper (object creation is important)
            if edge_attrs.get("is_constructor", False):
                cost *= 0.8

            # Conditional calls more expensive (might not execute)
            if edge_attrs.get("is_conditional", False):
                cost *= 1.3

            # Loop calls more expensive (repeated, less specific)
            if edge_attrs.get("is_in_loop", False):
                cost *= 1.2

        # IMPORTS edge adjustments
        elif edge_kind == GraphEdgeKind.IMPORTS.value:
            # Relative imports cheaper (same package)
            level = edge_attrs.get("level", 0)
            if level > 0:
                cost *= 0.8

            # Wildcard imports more expensive (less specific)
            if edge_attrs.get("is_wildcard", False):
                cost *= 1.5

        return cost

    def get_intent_adjusted_costs(self, intent: str) -> dict[str, float]:
        """
        Get edge costs adjusted for query intent.

        Args:
            intent: Query intent (symbol, flow, concept, code, balanced)

        Returns:
            Adjusted cost dictionary
        """
        base = self.config.base_costs.copy()

        if intent == "flow":
            # Boost call edges for flow tracing
            base[GraphEdgeKind.CALLS.value] *= 0.7
            base[GraphEdgeKind.ROUTE_HANDLER.value] *= 0.7
            base[GraphEdgeKind.HANDLES_REQUEST.value] *= 0.8
            # Reduce data flow importance
            base[GraphEdgeKind.READS.value] *= 1.5
            base[GraphEdgeKind.WRITES.value] *= 1.5

        elif intent == "symbol":
            # Structural edges more important
            base[GraphEdgeKind.CONTAINS.value] *= 0.5
            base[GraphEdgeKind.INHERITS.value] *= 0.7
            base[GraphEdgeKind.IMPLEMENTS.value] *= 0.7
            # Type references important
            base[GraphEdgeKind.REFERENCES_TYPE.value] *= 0.8

        elif intent == "concept":
            # Documentation edges cheaper
            base[GraphEdgeKind.DOCUMENTS.value] *= 0.5
            base[GraphEdgeKind.REFERENCES_CODE.value] *= 0.5
            # Structural overview important
            base[GraphEdgeKind.CONTAINS.value] *= 0.7

        return base


# Singleton default calculator
DEFAULT_EDGE_COST_CALCULATOR = EdgeCostCalculator()
