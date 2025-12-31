"""
Language Plugin Architecture

Multi-language support via plugin pattern.

Components:
- ILanguagePlugin: Language-specific component factory
- LanguagePluginRegistry: Plugin registration and lookup
- TypingMode: Language typing mode (STATIC, DYNAMIC, GRADUAL)

Usage:
    from codegraph_engine.code_foundation.infrastructure.language_plugin import (
        ILanguagePlugin,
        LanguagePluginRegistry,
        TypingMode,
    )
    from codegraph_engine.code_foundation.infrastructure.language_plugin.python import PythonPlugin

    registry = LanguagePluginRegistry()
    registry.register(PythonPlugin())

    plugin = registry.get("python")
    generator = plugin.create_structural_generator(repo_id="my-repo")
"""

from codegraph_engine.code_foundation.infrastructure.language_plugin.protocols import (
    ILanguagePlugin,
    TypingMode,
)
from codegraph_engine.code_foundation.infrastructure.language_plugin.registry import (
    LanguagePluginRegistry,
)

__all__ = [
    "ILanguagePlugin",
    "TypingMode",
    "LanguagePluginRegistry",
]
