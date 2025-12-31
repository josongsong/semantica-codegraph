"""
V3 Search Types and Enums

SOTA-level type definitions for type safety and clarity.
"""

from enum import Enum


class SourceType(Enum):
    """Search result source types (internal logic)."""

    LEXICAL = "lexical"
    VECTOR = "vector"
    SYMBOL = "symbol"
    GRAPH = "graph"
    FUZZY = "fuzzy"
    DOMAIN = "domain"
    RUNTIME = "runtime"
    DOCSTRING = "docstring"


class IntentType(Enum):
    """Query intent types (internal logic)."""

    GENERAL = "general"
    SYMBOL = "symbol"
    FLOW = "flow"
    CONCEPT = "concept"
    DEFINITION = "definition"
    USAGE = "usage"
    DOCUMENTATION = "documentation"


class FusionStrategy(Enum):
    """Fusion strategy types."""

    RRF_V3 = "rrf_v3"
    WEIGHTED_SCORE = "weighted_score"
    CONSENSUS = "consensus"


class SearchMode(Enum):
    """Search execution modes."""

    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    ROUTING = "routing"


__all__ = [
    "SourceType",
    "IntentType",
    "FusionStrategy",
    "SearchMode",
]
