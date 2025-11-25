"""
Fusion Weight Profiles

Defines scoring weights for different query intents.
"""

from src.retriever.intent.models import IntentKind

# Intent-specific weight profiles
# Format: { intent: { source: weight } }
WEIGHT_PROFILES = {
    IntentKind.CODE_SEARCH: {
        "lexical": 0.5,
        "vector": 0.3,
        "symbol": 0.15,
        "repomap": 0.05,
    },
    IntentKind.SYMBOL_NAV: {
        "symbol": 0.6,
        "lexical": 0.2,
        "vector": 0.15,
        "graph": 0.05,
    },
    IntentKind.CONCEPT_SEARCH: {
        "vector": 0.5,
        "lexical": 0.25,
        "repomap": 0.15,
        "symbol": 0.1,
    },
    IntentKind.FLOW_TRACE: {
        "graph": 0.6,
        "symbol": 0.25,
        "lexical": 0.15,
    },
    IntentKind.REPO_OVERVIEW: {
        "repomap": 0.5,
        "vector": 0.3,
        "lexical": 0.2,
    },
}

# Default weights (used when intent is unknown or for fallback)
DEFAULT_WEIGHTS = {
    "lexical": 0.4,
    "vector": 0.4,
    "symbol": 0.15,
    "graph": 0.05,
    "repomap": 0.0,
}


# PriorityScore formula weights
# PriorityScore = fused_score * PRIORITY_FUSED_WEIGHT
#               + repomap_importance * PRIORITY_REPOMAP_WEIGHT
#               + symbol_confidence * PRIORITY_SYMBOL_WEIGHT
PRIORITY_FUSED_WEIGHT = 0.55
PRIORITY_REPOMAP_WEIGHT = 0.30
PRIORITY_SYMBOL_WEIGHT = 0.15


def get_weights_for_intent(intent_kind: IntentKind) -> dict[str, float]:
    """
    Get fusion weights for a given intent.

    Args:
        intent_kind: Query intent kind

    Returns:
        Dict mapping source names to weights
    """
    return WEIGHT_PROFILES.get(intent_kind, DEFAULT_WEIGHTS)
