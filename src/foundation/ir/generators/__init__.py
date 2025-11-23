"""
IR Generators

AST → IR converters for different languages.
"""

from .base import IRGenerator
from .python_generator import PythonIRGenerator
from .scope_stack import ScopeStack

__all__ = [
    "IRGenerator",
    "PythonIRGenerator",
    "ScopeStack",
]
