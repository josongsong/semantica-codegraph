"""
Language Plugin Registry

Central registry for language plugins.

Features:
- Plugin registration and lookup
- Extension-based language detection
- Thread-safe singleton pattern (optional)

Usage:
    registry = LanguagePluginRegistry()
    registry.register(PythonPlugin())
    registry.register(TypeScriptPlugin())

    # Lookup by language
    plugin = registry.get("python")

    # Lookup by file extension
    plugin = registry.get_by_extension(".py")

    # Check support
    if registry.supports("java"):
        ...
"""

import threading
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.language_plugin.protocols import (
        ILanguagePlugin,
    )

logger = get_logger(__name__)


class LanguagePluginRegistry:
    """
    Language plugin registry.

    Manages language-specific plugins for multi-language support.

    Thread Safety:
        This class is NOT thread-safe by default.
        For concurrent access, use get_global_registry() singleton.

    Attributes:
        _plugins: Dict mapping language → plugin
        _ext_map: Dict mapping extension → language

    Example:
        registry = LanguagePluginRegistry()
        registry.register(PythonPlugin())

        plugin = registry.get("python")
        generator = plugin.create_structural_generator("my-repo")
    """

    def __init__(self) -> None:
        """
        Initialize empty registry.

        Thread Safety:
            All mutations (register, unregister) are protected by a lock.
        """
        self._plugins: dict[str, ILanguagePlugin] = {}
        self._ext_map: dict[str, str] = {}  # extension → language
        self._lock = threading.RLock()  # Reentrant lock for nested calls

    def register(self, plugin: "ILanguagePlugin") -> None:
        """
        Register a language plugin.

        Thread Safety:
            Protected by internal lock. Safe for concurrent calls.

        Args:
            plugin: Plugin instance implementing ILanguagePlugin

        Raises:
            ValueError: If language already registered

        Side Effects:
            - Adds plugin to registry
            - Maps all extensions to language
            - Logs registration

        Example:
            registry.register(PythonPlugin())
        """
        lang = plugin.language

        with self._lock:
            if lang in self._plugins:
                raise ValueError(f"Language already registered: {lang}")

            self._plugins[lang] = plugin

            # Map extensions to language
            for ext in plugin.supported_extensions:
                if ext in self._ext_map:
                    logger.warning(
                        "extension_conflict",
                        extension=ext,
                        existing_lang=self._ext_map[ext],
                        new_lang=lang,
                    )
                self._ext_map[ext] = lang

        # Log outside lock (I/O operation)
        logger.info(
            "plugin_registered",
            language=lang,
            extensions=list(plugin.supported_extensions),
            typing_mode=plugin.typing_mode.value,
        )

    def unregister(self, language: str) -> bool:
        """
        Unregister a language plugin.

        Thread Safety:
            Protected by internal lock.

        Args:
            language: Language identifier

        Returns:
            True if plugin was removed, False if not found
        """
        with self._lock:
            if language not in self._plugins:
                return False

            plugin = self._plugins.pop(language)

            # Remove extension mappings
            for ext in plugin.supported_extensions:
                if self._ext_map.get(ext) == language:
                    del self._ext_map[ext]

        logger.info("plugin_unregistered", language=language)
        return True

    def get(self, language: str | None) -> "ILanguagePlugin | None":
        """
        Get plugin by language.

        Args:
            language: Language identifier (e.g., "python"), or None

        Returns:
            Plugin instance or None if not found

        Example:
            plugin = registry.get("python")
            if plugin:
                generator = plugin.create_structural_generator("repo")
        """
        if language is None:
            return None
        return self._plugins.get(language)

    def get_by_extension(self, extension: str | None) -> "ILanguagePlugin | None":
        """
        Get plugin by file extension.

        Args:
            extension: File extension including dot (e.g., ".py"), or None

        Returns:
            Plugin instance or None if not found

        Example:
            plugin = registry.get_by_extension(".py")
        """
        # Null safety
        if extension is None:
            return None

        # Normalize extension
        if not extension.startswith("."):
            extension = f".{extension}"

        lang = self._ext_map.get(extension)
        return self._plugins.get(lang) if lang else None

    def supports(self, language: str) -> bool:
        """
        Check if language is supported.

        Args:
            language: Language identifier

        Returns:
            True if language has registered plugin
        """
        return language in self._plugins

    def supports_extension(self, extension: str) -> bool:
        """
        Check if file extension is supported.

        Args:
            extension: File extension including dot

        Returns:
            True if extension has registered plugin
        """
        if not extension.startswith("."):
            extension = f".{extension}"
        return extension in self._ext_map

    @property
    def languages(self) -> list[str]:
        """
        Get list of supported languages.

        Returns:
            List of language identifiers
        """
        return list(self._plugins.keys())

    @property
    def extensions(self) -> list[str]:
        """
        Get list of supported extensions.

        Returns:
            List of file extensions
        """
        return list(self._ext_map.keys())

    @property
    def plugins(self) -> dict[str, "ILanguagePlugin"]:
        """
        Get all registered plugins.

        Returns:
            Dict mapping language → plugin
        """
        return self._plugins.copy()

    def __len__(self) -> int:
        """Return number of registered plugins."""
        return len(self._plugins)

    def __contains__(self, language: str) -> bool:
        """Check if language is registered."""
        return language in self._plugins

    def __repr__(self) -> str:
        """String representation."""
        return f"LanguagePluginRegistry(languages={self.languages})"


# ============================================================
# Global Singleton (Thread-Safe)
# ============================================================

_global_registry: LanguagePluginRegistry | None = None
_global_registry_lock = threading.Lock()


def get_global_registry() -> LanguagePluginRegistry:
    """
    Get global plugin registry singleton.

    Thread Safety:
        Uses double-checked locking pattern. Safe for concurrent calls.

    Returns:
        Shared LanguagePluginRegistry instance

    Example:
        registry = get_global_registry()
        registry.register(PythonPlugin())
    """
    global _global_registry

    # First check (fast path, no lock)
    if _global_registry is not None:
        return _global_registry

    # Slow path with lock
    with _global_registry_lock:
        # Double-check after acquiring lock
        if _global_registry is None:
            _global_registry = LanguagePluginRegistry()

    return _global_registry


def reset_global_registry() -> None:
    """
    Reset global registry (for testing).

    Warning:
        Only use in tests!
    """
    global _global_registry
    _global_registry = None
