"""
Agent Modes

Specialized mode implementations for different development tasks.

Phase 0 (Core):
- Context Navigation: Code exploration
- Implementation: Code generation
- Debug: Error analysis
- Test: Test generation
- Documentation: Documentation generation

(Additional phases to be implemented)
"""

from src.agent.modes.base import BaseModeHandler
from src.agent.modes.context_nav import ContextNavigationMode, ContextNavigationModeSimple
from src.agent.modes.debug import DebugMode, DebugModeSimple
from src.agent.modes.documentation import DocumentationMode, DocumentationModeSimple
from src.agent.modes.implementation import ImplementationMode, ImplementationModeSimple
from src.agent.modes.test import TestMode, TestModeSimple

__all__ = [
    "BaseModeHandler",
    "ContextNavigationMode",
    "ContextNavigationModeSimple",
    "DebugMode",
    "DebugModeSimple",
    "DocumentationMode",
    "DocumentationModeSimple",
    "ImplementationMode",
    "ImplementationModeSimple",
    "TestMode",
    "TestModeSimple",
]
