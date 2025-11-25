"""
DFG (Data Flow Graph) Layer

Data flow analysis on top of CFG.
"""

from .analyzers import PythonStatementAnalyzer
from .builder import DfgBuilder
from .models import DataFlowEdge, DfgSnapshot, VariableEntity, VariableEvent
from .resolver import DfgContext, VarResolverState, resolve_or_create_variable
from .statement_analyzer import AnalyzerRegistry, BaseStatementAnalyzer

__all__ = [
    # Builder
    "DfgBuilder",
    # Models
    "VariableEntity",
    "VariableEvent",
    "DataFlowEdge",
    "DfgSnapshot",
    # Resolver
    "VarResolverState",
    "DfgContext",
    "resolve_or_create_variable",
    # Analyzers
    "BaseStatementAnalyzer",
    "AnalyzerRegistry",
    "PythonStatementAnalyzer",
]
