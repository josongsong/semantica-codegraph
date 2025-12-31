"""
Intent Analysis Module

Provides query intent classification using LLM and rule-based fallback.
"""

from typing import TYPE_CHECKING

from codegraph_search.infrastructure.intent.models import (
    IntentClassificationResult,
    IntentKind,
    QueryIntent,
)
from codegraph_search.infrastructure.intent.monitor import FallbackStats, IntentFallbackMonitor
from codegraph_search.infrastructure.intent.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    build_classification_prompt,
)
from codegraph_search.infrastructure.intent.rule_classifier import RuleBasedClassifier

if TYPE_CHECKING:
    from codegraph_search.infrastructure.intent.service import IntentAnalyzer


def __getattr__(name: str):
    """Lazy import for heavy analyzer class."""
    if name == "IntentAnalyzer":
        from codegraph_search.infrastructure.intent.service import IntentAnalyzer

        return IntentAnalyzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "IntentKind",
    "QueryIntent",
    "IntentClassificationResult",
    # Service (LLM dependency - lazy import via TYPE_CHECKING)
    "IntentAnalyzer",
    # Rule-based (lightweight)
    "RuleBasedClassifier",
    # Monitoring (lightweight)
    "IntentFallbackMonitor",
    "FallbackStats",
    # Prompts (lightweight)
    "build_classification_prompt",
    "INTENT_CLASSIFICATION_PROMPT",
]
