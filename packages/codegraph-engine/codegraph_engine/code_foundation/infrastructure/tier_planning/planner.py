"""
RFC-037 Phase 1: Tier Planner

Automatic tier selection based on agent intent and query type.
"""

from dataclasses import dataclass
from typing import Any

from codegraph_shared.common.observability import get_logger, record_counter, record_histogram
from codegraph_engine.code_foundation.infrastructure.ir.build_config import SemanticTier
from codegraph_engine.code_foundation.infrastructure.tier_planning.enums import (
    AgentIntent,
    QueryType,
    Scope,
)

# SOTA: Constants (no magic numbers)
DEFAULT_DFG_THRESHOLD = 500  # Must match BuildConfig.dfg_function_loc_threshold default


@dataclass
class TierPlanResult:
    """
    Result of tier planning.

    Contains selected tier and additional options.
    """

    tier: SemanticTier
    options: dict[str, Any]
    reason: str  # Human-readable explanation


class TierPlanner:
    """
    RFC-037: Automatic tier selection based on agent intent.

    Determines the minimum required semantic tier for a given operation.

    Design Principles:
    1. Query-first: QueryType has highest priority
    2. Intent-aware: Intent refines tier selection
    3. Scope-aware: Large scope may upgrade tier
    4. Conservative: Default to BASE (fastest)

    Examples:
        planner = TierPlanner()

        # Simple rename
        result = planner.plan(
            intent=AgentIntent.RENAME,
            query_type=QueryType.REFERENCES,
        )
        # → BASE tier (Call Graph sufficient)

        # Extract method
        result = planner.plan(
            intent=AgentIntent.EXTRACT_METHOD,
            query_type=QueryType.FLOW,
        )
        # → EXTENDED tier (DFG needed)

        # Program slicing
        result = planner.plan(
            intent=AgentIntent.SLICE,
            query_type=QueryType.SLICE,
        )
        # → FULL tier (PDG needed)
    """

    def __init__(self):
        """Initialize TierPlanner."""
        self.logger = get_logger(__name__)
        record_counter("tier_planner_initialized_total")

    def plan(
        self,
        intent: AgentIntent | None = None,
        query_type: QueryType | None = None,
        scope: Scope | None = None,
    ) -> TierPlanResult:
        """
        Determine required semantic tier from agent request.

        Priority:
        1. QueryType (highest - determines minimum tier)
        2. AgentIntent (refines tier)
        3. Scope (may upgrade tier for large scope)

        Args:
            intent: Agent's intended action (optional)
            query_type: Type of query needed (optional)
            scope: Operation scope (optional)

        Returns:
            TierPlanResult with tier, options, and reason

        Examples:
            # Query-driven
            plan(query_type=QueryType.SLICE) → FULL
            plan(query_type=QueryType.FLOW) → EXTENDED
            plan(query_type=QueryType.CALLERS) → BASE

            # Intent-driven
            plan(intent=AgentIntent.EXTRACT_METHOD) → EXTENDED
            plan(intent=AgentIntent.RENAME) → BASE

            # Combined
            plan(intent=AgentIntent.RENAME, query_type=QueryType.FLOW) → EXTENDED
        """
        # SOTA: Validate inputs (no silent failures)
        if intent is None and query_type is None and scope is None:
            # No information, default to BASE
            self.logger.debug("RFC-037: No inputs provided, defaulting to BASE tier")
            return TierPlanResult(
                tier=SemanticTier.BASE,
                options={},
                reason="No inputs specified (default)",
            )

        # Priority 1: QueryType (determines minimum tier)
        if query_type is not None:
            tier_from_query = self._tier_from_query_type(query_type)
            if tier_from_query:
                # Record decision
                record_counter(
                    "tier_planner_decisions_total",
                    labels={"source": "query_type", "tier": tier_from_query.tier.value},
                )
                return tier_from_query

        # Priority 2: AgentIntent
        if intent is not None:
            tier_from_intent = self._tier_from_intent(intent)
            if tier_from_intent:
                # Record decision
                record_counter(
                    "tier_planner_decisions_total",
                    labels={"source": "intent", "tier": tier_from_intent.tier.value},
                )
                return tier_from_intent

        # Priority 3: Scope (upgrade tier for large scope)
        if scope is not None and scope in (Scope.REPO, Scope.PACKAGE):
            # Large scope may benefit from EXTENDED tier
            self.logger.debug(f"RFC-037: Large scope ({scope.value}), upgrading to EXTENDED")
            return TierPlanResult(
                tier=SemanticTier.EXTENDED,
                options={"dfg_threshold": DEFAULT_DFG_THRESHOLD},
                reason=f"Large scope ({scope.value})",
            )

        # Default: BASE tier (fastest)
        self.logger.debug("RFC-037: No specific requirements, defaulting to BASE tier")
        record_counter("tier_planner_decisions_total", labels={"source": "default", "tier": "base"})
        return TierPlanResult(
            tier=SemanticTier.BASE,
            options={},
            reason="Default (no specific requirements)",
        )

    def _tier_from_query_type(self, query_type: QueryType) -> TierPlanResult | None:
        """
        Determine tier from query type.

        Query type determines the MINIMUM required tier.

        Args:
            query_type: Type of query

        Returns:
            TierPlanResult or None if unknown

        Raises:
            ValueError: If query_type is unhandled (enum exhaustiveness check)
        """
        # FULL tier queries (require SSA/PDG)
        if query_type in (
            QueryType.SLICE,
            QueryType.PATH_SENSITIVE,
            QueryType.REACHING_DEFS,
            QueryType.DOMINANCE,
        ):
            return TierPlanResult(
                tier=SemanticTier.FULL,
                options={},
                reason=f"Query type '{query_type.value}' requires SSA/PDG",
            )

        # EXTENDED tier queries (require DFG)
        if query_type in (
            QueryType.FLOW,
            QueryType.DEPENDENCIES,
            QueryType.SIDE_EFFECTS,
            QueryType.VALUE_ORIGIN,
        ):
            # SOTA: Create new dict (avoid shared reference)
            return TierPlanResult(
                tier=SemanticTier.EXTENDED,
                options={"dfg_threshold": DEFAULT_DFG_THRESHOLD},
                reason=f"Query type '{query_type.value}' requires DFG",
            )

        # BASE tier queries (Call Graph sufficient)
        if query_type in (
            QueryType.CALLERS,
            QueryType.CALLEES,
            QueryType.REFERENCES,
            QueryType.DEFINITIONS,
        ):
            return TierPlanResult(
                tier=SemanticTier.BASE,
                options={},
                reason=f"Query type '{query_type.value}' uses Call Graph only",
            )

        # Unknown query type (explicit handling)
        if query_type == QueryType.UNKNOWN:
            return None

        # SOTA: Exhaustive enum handling - FAIL FAST on unhandled enum
        # This ensures new enum values are explicitly handled
        raise ValueError(
            f"RFC-037: Unhandled QueryType enum value: {query_type}. "
            f"All QueryType values must be explicitly handled in TierPlanner."
        )

    def _tier_from_intent(self, intent: AgentIntent) -> TierPlanResult | None:
        """
        Determine tier from agent intent.

        Intent provides a hint but query_type is more authoritative.

        Args:
            intent: Agent's intended action

        Returns:
            TierPlanResult or None if unknown

        Raises:
            ValueError: If intent is unhandled (enum exhaustiveness check)
        """
        # FULL tier intents (require SSA/PDG)
        if intent in (
            AgentIntent.SLICE,
            AgentIntent.TAINT,
            AgentIntent.PATH_ANALYSIS,
            AgentIntent.NULL_CHECK,
        ):
            return TierPlanResult(
                tier=SemanticTier.FULL,
                options={},
                reason=f"Intent '{intent.value}' requires SSA/PDG",
            )

        # EXTENDED tier intents (require DFG)
        if intent in (
            AgentIntent.EXTRACT_METHOD,
            AgentIntent.INLINE,
            AgentIntent.ADD_PARAMETER,
            AgentIntent.MOVE,
        ):
            return TierPlanResult(
                tier=SemanticTier.EXTENDED,
                options={"dfg_threshold": DEFAULT_DFG_THRESHOLD},
                reason=f"Intent '{intent.value}' requires DFG",
            )

        # BASE tier intents (Call Graph sufficient)
        if intent in (
            AgentIntent.UNDERSTAND,
            AgentIntent.FIND_CALLERS,
            AgentIntent.FIND_REFERENCES,
            AgentIntent.RENAME,  # Simple rename only needs references
        ):
            return TierPlanResult(
                tier=SemanticTier.BASE,
                options={},
                reason=f"Intent '{intent.value}' uses Call Graph only",
            )

        # Unknown intent (explicit handling)
        if intent == AgentIntent.UNKNOWN:
            return None

        # SOTA: Exhaustive enum handling - FAIL FAST on unhandled enum
        # This ensures new enum values are explicitly handled in TierPlanner
        raise ValueError(
            f"RFC-037: Unhandled AgentIntent enum value: {intent}. "
            f"All AgentIntent values must be explicitly handled in TierPlanner."
        )
