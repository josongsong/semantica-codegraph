"""
Semantic Diff Infrastructure

Effect System - 동작 변화 감지
"""

# New Effect System
from .effect_analyzer import EffectAnalyzer

try:
    # Legacy (if exists)
    from .semantic_differ import SemanticDiffer

    __all__ = ["EffectAnalyzer", "SemanticDiffer"]
except ImportError:
    __all__ = ["EffectAnalyzer"]
