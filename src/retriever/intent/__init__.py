"""
Intent Analysis Module

Provides query intent classification using LLM and rule-based fallback.
"""

from .models import IntentClassificationResult, IntentKind, QueryIntent
from .monitor import FallbackStats, IntentFallbackMonitor
from .prompts import INTENT_CLASSIFICATION_PROMPT, build_classification_prompt
from .rule_classifier import RuleBasedClassifier
from .service import IntentAnalyzer

__all__ = [
    # Models
    "IntentKind",
    "QueryIntent",
    "IntentClassificationResult",
    # Service
    "IntentAnalyzer",
    # Rule-based
    "RuleBasedClassifier",
    # Monitoring
    "IntentFallbackMonitor",
    "FallbackStats",
    # Prompts
    "build_classification_prompt",
    "INTENT_CLASSIFICATION_PROMPT",
]
