"""
Reasoning Module

SOTA Reasoning Engines and Utilities
"""

# Import from existing modules
try:
    from .reflection.reflection_models import ReflectionVerdict
except ImportError:
    from ..shared.reasoning.reflection.reflection_models import ReflectionVerdict

# LATS
try:
    from .lats.lats_search import LATSSearchEngine
    from .lats.lats_thought_evaluator import LATSThoughtEvaluator
except ImportError:
    try:
        from ..shared.reasoning.lats.lats_search import LATSSearchEngine
        from ..shared.reasoning.lats.lats_thought_evaluator import LATSThoughtEvaluator
    except ImportError:
        LATSSearchEngine = None
        LATSThoughtEvaluator = None

# Base models
try:
    from .base.models import QueryFeatures
except ImportError:
    try:
        from ..shared.reasoning.base.models import QueryFeatures
    except ImportError:
        QueryFeatures = None

# Smart Pruner (TRAE-style)
# Pass@k Selector (TRAE-style)
from .passk_selector import PassKAttempt, PassKIntegration, PassKResult, PassKSelector
from .smart_pruner import ASTDeduplicator, PruningResult, RegressionFilter, SmartPruner

__all__ = [
    # Reflection
    "ReflectionVerdict",
    # LATS
    "LATSSearchEngine",
    "LATSThoughtEvaluator",
    # Base
    "QueryFeatures",
    # Smart Pruning
    "SmartPruner",
    "ASTDeduplicator",
    "RegressionFilter",
    "PruningResult",
    # Pass@k Selection
    "PassKSelector",
    "PassKIntegration",
    "PassKResult",
    "PassKAttempt",
]
