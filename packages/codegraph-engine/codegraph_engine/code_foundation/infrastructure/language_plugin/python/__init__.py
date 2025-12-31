"""
Python Language Plugin

Provides Python-specific components for multi-language support.

Components:
- PythonPlugin: Main plugin class (ILanguagePlugin implementation)

Usage:
    from codegraph_engine.code_foundation.infrastructure.language_plugin.python import PythonPlugin

    plugin = PythonPlugin()
    generator = plugin.create_structural_generator("my-repo")
"""

from codegraph_engine.code_foundation.infrastructure.language_plugin.python.plugin import (
    PythonPlugin,
)

__all__ = [
    "PythonPlugin",
]
