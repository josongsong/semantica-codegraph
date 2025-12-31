"""
Java Language Plugin

Provides Java-specific components for multi-language support.

Components:
- JavaPlugin: Main plugin class (ILanguagePlugin implementation)

Usage:
    from codegraph_engine.code_foundation.infrastructure.language_plugin.java import JavaPlugin

    plugin = JavaPlugin()
    generator = plugin.create_structural_generator("my-repo")
"""

from codegraph_engine.code_foundation.infrastructure.language_plugin.java.plugin import (
    JavaPlugin,
)

__all__ = [
    "JavaPlugin",
]
