"""
Python IR Generation - Specialized Builders

This package contains specialized builders for Python IR generation,
following the Strategy Pattern to separate concerns.

Components:
- signature_builder: Function/method signature analysis
- variable_analyzer: Variable and assignment tracking
- call_analyzer: Function call analysis and resolution
- lambda_analyzer: Lambda expression analysis

Note: NodeBuilder extraction is deferred to future refactoring.
"""

from codegraph_engine.code_foundation.infrastructure.generators.python.call_analyzer import PythonCallAnalyzer
from codegraph_engine.code_foundation.infrastructure.generators.python.lambda_analyzer import PythonLambdaAnalyzer
from codegraph_engine.code_foundation.infrastructure.generators.python.signature_builder import PythonSignatureBuilder
from codegraph_engine.code_foundation.infrastructure.generators.python.variable_analyzer import PythonVariableAnalyzer

__all__ = [
    "PythonSignatureBuilder",
    "PythonVariableAnalyzer",
    "PythonCallAnalyzer",
    "PythonLambdaAnalyzer",
]
