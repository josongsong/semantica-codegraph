"""
Python IR Generation - Specialized Builders

This package contains specialized builders for Python IR generation,
following the Strategy Pattern to separate concerns.

Components:
- signature_builder: Function/method signature analysis
- variable_analyzer: Variable and assignment tracking
- call_analyzer: Function call analysis and resolution

Note: NodeBuilder extraction is deferred to future refactoring.
"""

from .call_analyzer import PythonCallAnalyzer
from .signature_builder import PythonSignatureBuilder
from .variable_analyzer import PythonVariableAnalyzer

__all__ = [
    "PythonSignatureBuilder",
    "PythonVariableAnalyzer",
    "PythonCallAnalyzer",
]
