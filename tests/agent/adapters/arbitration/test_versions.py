"""
Tests for RFC Adapter Versions (RFC-027 Section 9)

Test Coverage:
- Version registry completeness
- Dynamic version lookup
- Semantic versioning format
"""

import pytest

from apps.orchestrator.orchestrator.adapters.rfc.versions import (
    ADAPTER_VERSIONS,
    COST_VERSION,
    REASONING_VERSION,
    RISK_VERSION,
    SCCP_VERSION,
    TAINT_VERSION,
    get_adapter_version,
    get_all_versions,
)

# ============================================================
# Base Cases
# ============================================================


def test_version_constants():
    """Test version constants are defined"""
    from apps.orchestrator.orchestrator.adapters.rfc.versions import DIFF_VERSION, RACE_VERSION

    assert TAINT_VERSION == "3.0.0"
    assert SCCP_VERSION == "2.0.0"
    assert COST_VERSION == "1.0.0"
    assert REASONING_VERSION == "1.0.0"
    assert RISK_VERSION == "1.0.0"
    assert DIFF_VERSION == "1.0.0"
    assert RACE_VERSION == "1.0.0"


def test_adapter_versions_registry():
    """Test adapter versions registry is complete"""
    assert "taint" in ADAPTER_VERSIONS
    assert "sccp" in ADAPTER_VERSIONS
    assert "cost" in ADAPTER_VERSIONS
    assert "reasoning" in ADAPTER_VERSIONS
    assert "risk" in ADAPTER_VERSIONS
    assert "diff" in ADAPTER_VERSIONS
    assert "race" in ADAPTER_VERSIONS


def test_get_adapter_version():
    """Test get_adapter_version() returns correct version"""
    assert get_adapter_version("taint") == "3.0.0"
    assert get_adapter_version("sccp") == "2.0.0"
    assert get_adapter_version("cost") == "1.0.0"


def test_get_all_versions():
    """Test get_all_versions() returns all versions"""
    versions = get_all_versions()

    assert isinstance(versions, dict)
    assert len(versions) == 7
    assert versions["taint"] == "3.0.0"
    assert versions["sccp"] == "2.0.0"
    assert versions["cost"] == "1.0.0"
    assert versions["reasoning"] == "1.0.0"
    assert versions["risk"] == "1.0.0"
    assert versions["diff"] == "1.0.0"
    assert versions["race"] == "1.0.0"


# ============================================================
# Edge Cases
# ============================================================


def test_get_adapter_version_unknown():
    """Test get_adapter_version() raises KeyError for unknown adapter"""
    with pytest.raises(KeyError):
        get_adapter_version("unknown_adapter")


def test_get_all_versions_returns_copy():
    """Test get_all_versions() returns a copy (not reference)"""
    versions1 = get_all_versions()
    versions2 = get_all_versions()

    # Modify one copy
    versions1["taint"] = "999.0.0"

    # Other copy should be unchanged
    assert versions2["taint"] == "3.0.0"

    # Original should be unchanged
    assert ADAPTER_VERSIONS["taint"] == "3.0.0"


# ============================================================
# Corner Cases
# ============================================================


def test_semantic_versioning_format():
    """Test all versions follow semantic versioning (MAJOR.MINOR.PATCH)"""
    import re

    semver_pattern = re.compile(r"^\d+\.\d+\.\d+$")

    for adapter, version in ADAPTER_VERSIONS.items():
        assert semver_pattern.match(version), f"{adapter} version '{version}' is not valid semver"


def test_version_consistency():
    """Test version constants match registry"""
    from apps.orchestrator.orchestrator.adapters.rfc.versions import DIFF_VERSION, RACE_VERSION

    assert ADAPTER_VERSIONS["taint"] == TAINT_VERSION
    assert ADAPTER_VERSIONS["sccp"] == SCCP_VERSION
    assert ADAPTER_VERSIONS["cost"] == COST_VERSION
    assert ADAPTER_VERSIONS["reasoning"] == REASONING_VERSION
    assert ADAPTER_VERSIONS["risk"] == RISK_VERSION
    assert ADAPTER_VERSIONS["diff"] == DIFF_VERSION
    assert ADAPTER_VERSIONS["race"] == RACE_VERSION


# ============================================================
# Integration Tests
# ============================================================


def test_versions_used_in_audit_log():
    """Test versions can be used in audit log (without full executor instantiation)"""
    # Verify versions are available and can be used for audit logging
    versions = get_all_versions()

    # All 7 adapters should have versions
    assert len(versions) == 7
    assert all(isinstance(v, str) for v in versions.values())

    # Verify audit log format compatibility
    audit_entry = {
        "timestamp": "2024-01-01T00:00:00Z",
        "adapter_versions": versions,
    }
    assert audit_entry["adapter_versions"]["taint"] == TAINT_VERSION
    assert audit_entry["adapter_versions"]["sccp"] == SCCP_VERSION
