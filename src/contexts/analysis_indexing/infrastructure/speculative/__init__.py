"""
Speculative Graph Execution

Pre-calculates graph changes before applying AI agent patches.
"""

from .executor import SpeculativeExecutor
from .models import (
    GraphDelta,
    PatchType,
    RiskLevel,
    SpeculativePatch,
    SpeculativeResult,
)
from .risk_analyzer import RiskAnalyzer
from .simulator import GraphSimulator

__all__ = [
    "SpeculativePatch",
    "PatchType",
    "SpeculativeResult",
    "GraphDelta",
    "RiskLevel",
    "GraphSimulator",
    "SpeculativeExecutor",
    "RiskAnalyzer",
]
