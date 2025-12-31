"""Base plugin interface for CodeGraph analysis plugins."""

from abc import ABC, abstractmethod
from typing import Any


class AnalysisPlugin(ABC):
    """Base class for all analysis plugins.

    Analysis plugins receive IR documents from the Rust engine and
    perform domain-specific analysis (security, patterns, etc.).
    """

    @abstractmethod
    def name(self) -> str:
        """Return plugin name.

        Returns:
            Unique identifier for this plugin (e.g., "crypto", "auth")
        """
        pass

    @abstractmethod
    def version(self) -> str:
        """Return plugin version.

        Returns:
            Semantic version string (e.g., "1.0.0")
        """
        pass

    @abstractmethod
    def analyze(self, ir_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Analyze IR documents and return findings.

        Args:
            ir_documents: List of IR documents from Rust engine.
                Each document contains:
                - nodes: List of AST nodes
                - edges: List of relationships
                - metadata: File path, language, etc.

        Returns:
            List of findings with format:
            {
                "severity": "HIGH" | "MEDIUM" | "LOW",
                "category": str,  # e.g., "weak-crypto", "missing-auth"
                "message": str,
                "location": {
                    "file": str,
                    "line": int,
                    "column": int,
                },
                "remediation": str,  # Optional fix suggestion
            }
        """
        pass


class PluginRegistry:
    """Registry for managing analysis plugins.

    Example:
        >>> registry = PluginRegistry()
        >>> registry.register(CryptoPlugin())
        >>> registry.register(AuthPlugin())
        >>> findings = registry.run_all(ir_documents)
    """

    def __init__(self):
        self.plugins: dict[str, AnalysisPlugin] = {}

    def register(self, plugin: AnalysisPlugin) -> None:
        """Register a plugin.

        Args:
            plugin: Plugin instance to register
        """
        self.plugins[plugin.name()] = plugin

    def unregister(self, plugin_name: str) -> None:
        """Unregister a plugin.

        Args:
            plugin_name: Name of plugin to remove
        """
        if plugin_name in self.plugins:
            del self.plugins[plugin_name]

    def get(self, plugin_name: str) -> AnalysisPlugin | None:
        """Get a plugin by name.

        Args:
            plugin_name: Name of plugin to retrieve

        Returns:
            Plugin instance or None if not found
        """
        return self.plugins.get(plugin_name)

    def list_plugins(self) -> list[str]:
        """List all registered plugin names.

        Returns:
            List of plugin names
        """
        return list(self.plugins.keys())

    def run_all(self, ir_documents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Run all registered plugins.

        Args:
            ir_documents: IR documents from Rust engine

        Returns:
            Dictionary mapping plugin names to their findings.
            Example:
            {
                "crypto": [{...}, {...}],
                "auth": [{...}],
            }
        """
        results = {}
        for name, plugin in self.plugins.items():
            try:
                findings = plugin.analyze(ir_documents)
                results[name] = findings
            except Exception as e:
                # Log error but continue with other plugins
                results[name] = [
                    {
                        "severity": "ERROR",
                        "category": "plugin-error",
                        "message": f"Plugin {name} failed: {str(e)}",
                        "location": {},
                        "remediation": f"Check plugin {name} implementation",
                    }
                ]
        return results
