"""
MCP Config Tests

RFC-052: MCP Service Layer Architecture
Tests for MCPConfig validation.

Test Coverage:
- Valid configuration
- Invalid budget progression
- Invalid TTL configuration
- Pool size bounds
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.config.mcp_config import MCPConfig


class TestMCPConfigValidation:
    """Config validation tests"""

    def test_valid_config(self):
        """Valid configuration passes validation"""
        config = MCPConfig()
        errors = config.validate()

        assert len(errors) == 0

    def test_invalid_budget_progression(self):
        """Budget progression validation"""
        config = MCPConfig(
            budget_light_max_depth=10,
            budget_default_max_depth=5,  # ❌ Should be > light
        )

        errors = config.validate()

        assert len(errors) > 0
        assert any("budget_light_max_depth" in e for e in errors)

    def test_invalid_ttl_configuration(self):
        """TTL configuration validation"""
        config = MCPConfig(
            evidence_min_session_ttl_days=60,
            evidence_ttl_days=30,  # ❌ Should be >= min
        )

        errors = config.validate()

        assert len(errors) > 0
        assert any("evidence_min_session_ttl_days" in e for e in errors)

    def test_pool_size_bounds(self):
        """Pool size should be reasonable for SQLite"""
        # Pydantic validates at construction time
        with pytest.raises(Exception):  # ValidationError
            config = MCPConfig(
                connection_pool_size=25,  # ❌ Too high (Pydantic rejects)
            )

    def test_default_values_are_valid(self):
        """Default configuration is valid"""
        config = MCPConfig.model_construct()  # Use defaults
        errors = config.validate()

        assert len(errors) == 0


class TestMCPConfigPaths:
    """Config path generation tests"""

    def test_evidence_db_path(self):
        """Evidence DB path is generated correctly"""
        config = MCPConfig()

        path = config.evidence_db_path

        assert path.name == "evidence.db"
        assert "mcp" in str(path)

    def test_session_db_path(self):
        """Session DB path is generated correctly"""
        config = MCPConfig()

        path = config.session_db_path

        assert path.name == "sessions.db"
        assert "mcp" in str(path)
