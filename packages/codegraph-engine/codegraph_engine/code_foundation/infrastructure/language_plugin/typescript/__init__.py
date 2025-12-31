"""
TypeScript Language Plugin

Provides TypeScript-specific components for multi-language support.

Components:
- TypeScriptPlugin: Main plugin class (ILanguagePlugin implementation)

Usage:
    from codegraph_engine.code_foundation.infrastructure.language_plugin.typescript import TypeScriptPlugin

    plugin = TypeScriptPlugin()
    generator = plugin.create_structural_generator("my-repo")
"""

from codegraph_engine.code_foundation.infrastructure.language_plugin.typescript.plugin import (
    TypeScriptPlugin,
)

__all__ = [
    "TypeScriptPlugin",
]
