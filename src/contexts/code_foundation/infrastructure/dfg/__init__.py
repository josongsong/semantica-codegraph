"""
DFG (Data Flow Graph) Layer

Data flow analysis on top of CFG.
"""

from src.contexts.code_foundation.infrastructure.dfg.analyzers import PythonStatementAnalyzer
from src.contexts.code_foundation.infrastructure.dfg.builder import DfgBuilder
from src.contexts.code_foundation.infrastructure.dfg.models import (
    DataFlowEdge,
    DfgSnapshot,
    VariableEntity,
    VariableEvent,
)
from src.contexts.code_foundation.infrastructure.dfg.resolver import (
    DfgContext,
    VarResolverState,
    resolve_or_create_variable,
)
from src.contexts.code_foundation.infrastructure.dfg.statement_analyzer import AnalyzerRegistry, BaseStatementAnalyzer

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
