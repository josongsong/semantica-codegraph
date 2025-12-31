"""
RFC-037 Phase 1: Tier Planning

Automatic tier selection based on agent intent and query type.

Usage:
    from codegraph_engine.code_foundation.infrastructure.tier_planning import TierPlanner

    planner = TierPlanner()
    tier, options = planner.plan(
        intent=AgentIntent.EXTRACT_METHOD,
        query_type=QueryType.FLOW,
        scope=Scope.FUNCTION,
    )
    # → (SemanticTier.EXTENDED, {"dfg_threshold": 500})
"""

from codegraph_engine.code_foundation.infrastructure.tier_planning.enums import (
    AgentIntent,
    QueryType,
    Scope,
)
from codegraph_engine.code_foundation.infrastructure.tier_planning.planner import TierPlanner

__all__ = [
    "AgentIntent",
    "QueryType",
    "Scope",
    "TierPlanner",
]
