"""
CWE Domain Layer

Pure domain logic with no infrastructure dependencies.
"""

from cwe.domain.ports import (
    AnalysisResult,
    ConfusionMatrix,
    SchemaValidator,
    TaintAnalyzer,
    TestCase,
)

__all__ = [
    "AnalysisResult",
    "ConfusionMatrix",
    "SchemaValidator",
    "TaintAnalyzer",
    "TestCase",
]
