"""
Speculative Graph Execution

Pre-calculates graph changes before applying AI agent patches.
"""

from .models import (
    SpeculativePatch,
    PatchType,
    SpeculativeResult,
    GraphDelta,
    RiskLevel,
)
from .simulator import GraphSimulator
from .executor import SpeculativeExecutor
from .risk_analyzer import RiskAnalyzer

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

