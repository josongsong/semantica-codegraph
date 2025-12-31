"""Integration tests for Python plugin system.

Tests that the new plugin architecture works correctly
with the consolidated codegraph-analysis package.
"""

import pytest

from codegraph_analysis.plugin import AnalysisPlugin, PluginRegistry


class MockCryptoPlugin(AnalysisPlugin):
    """Mock crypto plugin for testing."""

    def name(self) -> str:
        return "crypto"

    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ir_documents):
        """Detect weak crypto usage."""
        findings = []

        for doc in ir_documents:
            nodes = doc.get("nodes", [])
            for node in nodes:
                # Check for MD5 usage
                if node.get("kind") == "Call" and "md5" in node.get("name", "").lower():
                    findings.append(
                        {
                            "severity": "HIGH",
                            "category": "weak-crypto",
                            "message": f"Weak cryptographic hash MD5 detected: {node.get('name')}",
                            "location": node.get("location", {}),
                            "remediation": "Use SHA-256 or SHA-3 instead of MD5",
                        }
                    )

        return findings


class MockAuthPlugin(AnalysisPlugin):
    """Mock auth plugin for testing."""

    def name(self) -> str:
        return "auth"

    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ir_documents):
        """Detect missing authentication."""
        findings = []

        for doc in ir_documents:
            nodes = doc.get("nodes", [])
            # Simple check: look for functions without @login_required
            functions = [n for n in nodes if n.get("kind") == "Function"]

            for func in functions:
                # Mock check: if function name contains "api_", it should be protected
                if "api_" in func.get("name", ""):
                    findings.append(
                        {
                            "severity": "MEDIUM",
                            "category": "missing-auth",
                            "message": f"API endpoint may need authentication: {func.get('name')}",
                            "location": func.get("location", {}),
                            "remediation": "Add @login_required or similar decorator",
                        }
                    )

        return findings


def test_plugin_registry():
    """Test plugin registry works."""
    registry = PluginRegistry()

    # Register plugins
    crypto_plugin = MockCryptoPlugin()
    auth_plugin = MockAuthPlugin()

    registry.register(crypto_plugin)
    registry.register(auth_plugin)

    # Verify registration
    assert "crypto" in registry.list_plugins()
    assert "auth" in registry.list_plugins()
    assert len(registry.list_plugins()) == 2

    # Get plugins
    assert registry.get("crypto") == crypto_plugin
    assert registry.get("auth") == auth_plugin

    # Unregister
    registry.unregister("auth")
    assert "auth" not in registry.list_plugins()
    assert len(registry.list_plugins()) == 1


def test_crypto_plugin():
    """Test crypto plugin detects weak crypto."""
    plugin = MockCryptoPlugin()

    # Mock IR with MD5 usage
    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "hashlib.md5",
                    "location": {"file": "test.py", "line": 10, "column": 5},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 1
    assert findings[0]["severity"] == "HIGH"
    assert findings[0]["category"] == "weak-crypto"
    assert "md5" in findings[0]["message"].lower()
    assert "SHA-256" in findings[0]["remediation"]


def test_auth_plugin():
    """Test auth plugin detects missing authentication."""
    plugin = MockAuthPlugin()

    # Mock IR with API function
    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Function",
                    "name": "api_get_user",
                    "location": {"file": "views.py", "line": 20, "column": 0},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 1
    assert findings[0]["severity"] == "MEDIUM"
    assert findings[0]["category"] == "missing-auth"
    assert "api_get_user" in findings[0]["message"]


def test_registry_run_all():
    """Test running all plugins through registry."""
    registry = PluginRegistry()
    registry.register(MockCryptoPlugin())
    registry.register(MockAuthPlugin())

    # Mock IR with both issues
    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "hashlib.md5",
                    "location": {"file": "test.py", "line": 10},
                },
                {
                    "kind": "Function",
                    "name": "api_endpoint",
                    "location": {"file": "test.py", "line": 20},
                },
            ]
        }
    ]

    results = registry.run_all(ir_documents)

    assert "crypto" in results
    assert "auth" in results
    assert len(results["crypto"]) == 1
    assert len(results["auth"]) == 1


def test_plugin_error_handling():
    """Test that plugin errors are caught and reported."""

    class BrokenPlugin(AnalysisPlugin):
        def name(self):
            return "broken"

        def version(self):
            return "1.0.0"

        def analyze(self, ir_documents):
            raise ValueError("Plugin is broken!")

    registry = PluginRegistry()
    registry.register(BrokenPlugin())
    registry.register(MockCryptoPlugin())

    ir_documents = [{"nodes": []}]
    results = registry.run_all(ir_documents)

    # Broken plugin should return error finding
    assert "broken" in results
    assert len(results["broken"]) == 1
    assert results["broken"][0]["severity"] == "ERROR"
    assert "Plugin broken failed" in results["broken"][0]["message"]

    # Other plugins should still run
    assert "crypto" in results


def test_framework_adapters_import():
    """Test that framework adapters can be imported."""
    from codegraph_analysis.security import framework_adapters

    # Django
    assert hasattr(framework_adapters, "DJANGO_TAINT_SOURCES")
    assert hasattr(framework_adapters, "DJANGO_TAINT_SINKS")
    assert isinstance(framework_adapters.DJANGO_TAINT_SOURCES, list)

    # Flask
    assert hasattr(framework_adapters, "FLASK_TAINT_SOURCES")
    assert hasattr(framework_adapters, "FLASK_TAINT_SINKS")

    # FastAPI
    assert hasattr(framework_adapters, "FASTAPI_TAINT_SOURCES")
    assert hasattr(framework_adapters, "FASTAPI_TAINT_SINKS")


def test_framework_adapters_content():
    """Test framework adapters have expected content."""
    from codegraph_analysis.security.framework_adapters import (
        DJANGO_TAINT_SINKS,
        DJANGO_TAINT_SOURCES,
        FASTAPI_TAINT_SOURCES,
        FLASK_TAINT_SOURCES,
    )

    # Django sources should include common input points
    assert "request.GET" in DJANGO_TAINT_SOURCES
    assert "request.POST" in DJANGO_TAINT_SOURCES

    # Django sinks should include dangerous operations
    assert "cursor.execute" in DJANGO_TAINT_SINKS
    assert "os.system" in DJANGO_TAINT_SINKS

    # Flask sources
    assert "request.args" in FLASK_TAINT_SOURCES
    assert "request.form" in FLASK_TAINT_SOURCES

    # FastAPI sources
    assert "Query(...)" in FASTAPI_TAINT_SOURCES
    assert "Body(...)" in FASTAPI_TAINT_SOURCES


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
