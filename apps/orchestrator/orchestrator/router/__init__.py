from .confidence_scorer import ConfidenceScorer
from .models import Intent, IntentResult

# Lazy import to avoid heavy dependencies on module load
# IntentClassifier, Router는 필요할 때만 import

__all__ = [
    "Intent",
    "IntentResult",
    "ConfidenceScorer",
]


# For backward compatibility
def __getattr__(name):
    if name == "IntentClassifier":
        from .intent_classifier import IntentClassifier

        return IntentClassifier
    elif name == "Router":
        from .router import Router

        return Router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
