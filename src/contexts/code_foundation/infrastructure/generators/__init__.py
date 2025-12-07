"""
IR Generators

AST → IR converters for different languages.
"""

from src.contexts.code_foundation.infrastructure.generators.base import IRGenerator
from src.contexts.code_foundation.infrastructure.generators.java_generator import JavaIRGenerator
from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from src.contexts.code_foundation.infrastructure.generators.typescript_generator import TypeScriptIRGenerator

__all__ = [
    "IRGenerator",
    "JavaIRGenerator",
    "PythonIRGenerator",
    "TypeScriptIRGenerator",
    "ScopeStack",
]
