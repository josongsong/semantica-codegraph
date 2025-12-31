"""
Query Engine Unit Tests

Tests for QueryConfig, QueryEngine.
"""

import pytest

from codegraph_analysis.security_analysis.domain.models.security_rule import (
    RuleRegistry,
    SecurityRule,
)
from codegraph_analysis.security_analysis.domain.models.vulnerability import (
    CWE,
    Location,
    Severity,
    Vulnerability,
)
from codegraph_analysis.security_analysis.domain.services.query_engine import (
    QueryConfig,
    QueryEngine,
    create_query_engine,
)


class TestQueryConfig:
    """QueryConfig tests"""

    def test_default_config(self):
        config = QueryConfig()
        assert config.enabled_rules is None
        assert config.disabled_rules == []
        assert config.min_severity == Severity.INFO
        assert config.max_vulnerabilities == 1000
        assert config.timeout_ms == 300000
        assert config.parallel is False
        assert config.use_cache is True

    def test_custom_config(self):
        config = QueryConfig(
            enabled_rules=["SQLInjectionQuery"],
            min_severity=Severity.HIGH,
            max_vulnerabilities=100,
        )
        assert config.enabled_rules == ["SQLInjectionQuery"]
        assert config.min_severity == Severity.HIGH
        assert config.max_vulnerabilities == 100

    # === Validation Tests ===

    def test_max_vulnerabilities_too_low(self):
        """max_vulnerabilities below minimum should fail"""
        with pytest.raises(ValueError, match="max_vulnerabilities must be between"):
            QueryConfig(max_vulnerabilities=0)

    def test_max_vulnerabilities_too_high(self):
        """max_vulnerabilities above maximum should fail"""
        with pytest.raises(ValueError, match="max_vulnerabilities must be between"):
            QueryConfig(max_vulnerabilities=100001)

    def test_max_vulnerabilities_boundary_min(self):
        """Boundary: minimum allowed value"""
        config = QueryConfig(max_vulnerabilities=1)
        assert config.max_vulnerabilities == 1

    def test_max_vulnerabilities_boundary_max(self):
        """Boundary: maximum allowed value"""
        config = QueryConfig(max_vulnerabilities=100000)
        assert config.max_vulnerabilities == 100000

    def test_timeout_too_low(self):
        """timeout_ms below minimum should fail"""
        with pytest.raises(ValueError, match="timeout_ms must be between"):
            QueryConfig(timeout_ms=999)

    def test_timeout_too_high(self):
        """timeout_ms above maximum should fail"""
        with pytest.raises(ValueError, match="timeout_ms must be between"):
            QueryConfig(timeout_ms=3600001)

    def test_timeout_boundary_min(self):
        """Boundary: minimum allowed timeout"""
        config = QueryConfig(timeout_ms=1000)
        assert config.timeout_ms == 1000

    def test_timeout_boundary_max(self):
        """Boundary: maximum allowed timeout"""
        config = QueryConfig(timeout_ms=3600000)
        assert config.timeout_ms == 3600000

    def test_enabled_disabled_overlap(self):
        """Rules cannot be both enabled and disabled"""
        with pytest.raises(ValueError, match="cannot be both enabled and disabled"):
            QueryConfig(
                enabled_rules=["RuleA", "RuleB"],
                disabled_rules=["RuleB", "RuleC"],
            )

    def test_enabled_disabled_no_overlap(self):
        """Non-overlapping enabled/disabled is OK"""
        config = QueryConfig(
            enabled_rules=["RuleA", "RuleB"],
            disabled_rules=["RuleC", "RuleD"],
        )
        assert "RuleA" in config.enabled_rules
        assert "RuleC" in config.disabled_rules

    def test_combined_config(self):
        """Combined config with all options"""
        config = QueryConfig(
            enabled_rules=["SQLi", "XSS"],
            disabled_rules=["Info"],
            min_severity=Severity.HIGH,
            max_vulnerabilities=500,
            timeout_ms=60000,
            parallel=True,
            use_cache=False,
        )
        assert config.min_severity == Severity.HIGH
        assert config.max_vulnerabilities == 500
        assert config.parallel is True
        assert config.use_cache is False


class TestQueryEngine:
    """QueryEngine tests"""

    @pytest.fixture
    def empty_registry(self):
        return RuleRegistry()

    @pytest.fixture
    def registry_with_rules(self):
        registry = RuleRegistry()

        class TestRule1(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        class TestRule2(SecurityRule):
            CWE_ID = CWE.CWE_78
            SEVERITY = Severity.CRITICAL

            def analyze(self, ir_document):
                return []

        registry.register(TestRule1)
        registry.register(TestRule2)
        return registry

    def test_engine_init_default(self, empty_registry):
        engine = QueryEngine(registry=empty_registry)
        assert engine.config.min_severity == Severity.INFO
        assert len(engine.stats) == 4

    def test_engine_init_custom_config(self, empty_registry):
        config = QueryConfig(min_severity=Severity.HIGH)
        engine = QueryEngine(config=config, registry=empty_registry)
        assert engine.config.min_severity == Severity.HIGH

    def test_get_active_rules_all(self, registry_with_rules):
        engine = QueryEngine(registry=registry_with_rules)
        rules = engine._get_active_rules()
        assert len(rules) == 2

    def test_get_active_rules_enabled_only(self, registry_with_rules):
        config = QueryConfig(enabled_rules=["TestRule1"])
        engine = QueryEngine(config=config, registry=registry_with_rules)
        rules = engine._get_active_rules()
        assert len(rules) == 1
        assert rules[0].get_name() == "TestRule1"

    def test_get_active_rules_disabled(self, registry_with_rules):
        config = QueryConfig(disabled_rules=["TestRule1"])
        engine = QueryEngine(config=config, registry=registry_with_rules)
        rules = engine._get_active_rules()
        assert len(rules) == 1
        assert rules[0].get_name() == "TestRule2"

    def test_stats_initial(self, empty_registry):
        engine = QueryEngine(registry=empty_registry)
        stats = engine.get_stats()
        assert stats["files_scanned"] == 0
        assert stats["rules_executed"] == 0
        assert stats["vulnerabilities_found"] == 0
        assert stats["errors"] == 0

    def test_reset_stats(self, empty_registry):
        engine = QueryEngine(registry=empty_registry)
        engine.stats["files_scanned"] = 100
        engine.reset_stats()
        assert engine.stats["files_scanned"] == 0


class TestSeverityFilter:
    """Test _filter_by_severity method (bug fix verification)"""

    @pytest.fixture
    def sample_vulnerabilities(self):
        def make_vuln(severity):
            return Vulnerability(
                cwe=CWE.CWE_89,
                severity=severity,
                title="Test",
                description="",
                source_location=Location("a.py", 1, 1),
                sink_location=Location("a.py", 2, 2),
            )

        return [
            make_vuln(Severity.CRITICAL),
            make_vuln(Severity.HIGH),
            make_vuln(Severity.MEDIUM),
            make_vuln(Severity.LOW),
            make_vuln(Severity.INFO),
        ]

    def test_filter_info_includes_all(self, sample_vulnerabilities):
        """min_severity=INFO should include all"""
        config = QueryConfig(min_severity=Severity.INFO)
        engine = QueryEngine(config=config, registry=RuleRegistry())
        filtered = engine._filter_by_severity(sample_vulnerabilities)
        assert len(filtered) == 5

    def test_filter_low_includes_low_and_above(self, sample_vulnerabilities):
        """min_severity=LOW should include LOW, MEDIUM, HIGH, CRITICAL"""
        config = QueryConfig(min_severity=Severity.LOW)
        engine = QueryEngine(config=config, registry=RuleRegistry())
        filtered = engine._filter_by_severity(sample_vulnerabilities)
        assert len(filtered) == 4
        severities = {v.severity for v in filtered}
        assert Severity.INFO not in severities

    def test_filter_medium_includes_medium_and_above(self, sample_vulnerabilities):
        """min_severity=MEDIUM should include MEDIUM, HIGH, CRITICAL"""
        config = QueryConfig(min_severity=Severity.MEDIUM)
        engine = QueryEngine(config=config, registry=RuleRegistry())
        filtered = engine._filter_by_severity(sample_vulnerabilities)
        assert len(filtered) == 3
        severities = {v.severity for v in filtered}
        assert Severity.LOW not in severities
        assert Severity.INFO not in severities

    def test_filter_high_includes_high_and_above(self, sample_vulnerabilities):
        """min_severity=HIGH should include HIGH, CRITICAL"""
        config = QueryConfig(min_severity=Severity.HIGH)
        engine = QueryEngine(config=config, registry=RuleRegistry())
        filtered = engine._filter_by_severity(sample_vulnerabilities)
        assert len(filtered) == 2
        severities = {v.severity for v in filtered}
        assert severities == {Severity.HIGH, Severity.CRITICAL}

    def test_filter_critical_includes_critical_only(self, sample_vulnerabilities):
        """min_severity=CRITICAL should include only CRITICAL"""
        config = QueryConfig(min_severity=Severity.CRITICAL)
        engine = QueryEngine(config=config, registry=RuleRegistry())
        filtered = engine._filter_by_severity(sample_vulnerabilities)
        assert len(filtered) == 1
        assert filtered[0].severity == Severity.CRITICAL

    def test_filter_empty_list(self):
        """Empty input should return empty output"""
        config = QueryConfig(min_severity=Severity.HIGH)
        engine = QueryEngine(config=config, registry=RuleRegistry())
        filtered = engine._filter_by_severity([])
        assert filtered == []


class TestCreateQueryEngine:
    """Test convenience function"""

    def test_create_default(self):
        engine = create_query_engine()
        assert engine.config.min_severity == Severity.INFO

    def test_create_with_severity(self):
        engine = create_query_engine(min_severity=Severity.HIGH)
        assert engine.config.min_severity == Severity.HIGH

    def test_create_with_rules(self):
        engine = create_query_engine(enabled_rules=["TestRule"])
        assert engine.config.enabled_rules == ["TestRule"]
