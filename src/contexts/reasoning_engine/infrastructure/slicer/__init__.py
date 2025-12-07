"""
Program Slicer for LLM Context Optimization

PDG-based program slicing for minimal, relevant code extraction.
"""

from .budget_manager import BudgetConfig, BudgetManager, RelevanceScore
from .context_optimizer import ContextOptimizer, OptimizedContext
from .file_extractor import FileCodeExtractor, SourceCode
from .slicer import CodeFragment, ProgramSlicer, SliceConfig, SliceResult

__all__ = [
    "ProgramSlicer",
    "SliceResult",
    "SliceConfig",
    "CodeFragment",
    "BudgetManager",
    "BudgetConfig",
    "RelevanceScore",
    "ContextOptimizer",
    "OptimizedContext",
]
