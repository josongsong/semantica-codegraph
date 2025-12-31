"""
Security Rule Unit Tests

Tests for SecurityRule, TaintSource, TaintSink, TaintSanitizer, RuleRegistry.
"""

import pytest

from codegraph_analysis.security_analysis.domain.models.security_rule import (
    RuleRegistry,
    SecurityRule,
    TaintSanitizer,
    TaintSink,
    TaintSource,
    get_registry,
    register_rule,
    reset_registry,
    set_registry,
)
from codegraph_analysis.security_analysis.domain.models.vulnerability import CWE, Severity, Vulnerability


class TestTaintSource:
    """TaintSource dataclass tests"""

    def test_taint_source_basic(self):
        source = TaintSource(
            patterns=["request.args.get", "request.form"],
            description="HTTP request parameters",
        )
        assert len(source.patterns) == 2
        assert "request.args.get" in source.patterns
        assert source.confidence == 1.0

    def test_taint_source_with_confidence(self):
        source = TaintSource(
            patterns=["os.environ.get"],
            description="Environment variables",
            confidence=0.8,
        )
        assert source.confidence == 0.8


class TestTaintSink:
    """TaintSink dataclass tests"""

    def test_taint_sink_basic(self):
        sink = TaintSink(
            patterns=["cursor.execute", "db.execute"],
            description="Direct SQL execution",
        )
        assert len(sink.patterns) == 2
        assert sink.severity == Severity.HIGH

    def test_taint_sink_with_severity(self):
        sink = TaintSink(
            patterns=["os.system"],
            description="OS command execution",
            severity=Severity.CRITICAL,
        )
        assert sink.severity == Severity.CRITICAL


class TestTaintSanitizer:
    """TaintSanitizer dataclass tests"""

    def test_taint_sanitizer_basic(self):
        sanitizer = TaintSanitizer(
            patterns=["html.escape", "bleach.clean"],
            description="HTML sanitization",
        )
        assert len(sanitizer.patterns) == 2
        assert sanitizer.effectiveness == 1.0

    def test_taint_sanitizer_partial(self):
        sanitizer = TaintSanitizer(
            patterns=["strip"],
            description="Whitespace removal",
            effectiveness=0.3,
        )
        assert sanitizer.effectiveness == 0.3


class TestSecurityRule:
    """SecurityRule abstract class tests"""

    def test_cannot_instantiate_abstract(self):
        """Cannot instantiate SecurityRule directly"""
        with pytest.raises(TypeError):
            SecurityRule()

    def test_subclass_without_cwe_fails(self):
        """Subclass without CWE_ID should fail"""

        class BadRule(SecurityRule):
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        with pytest.raises(ValueError, match="must define CWE_ID"):
            BadRule()

    def test_subclass_without_severity_fails(self):
        """Subclass without SEVERITY should fail"""

        class BadRule(SecurityRule):
            CWE_ID = CWE.CWE_89

            def analyze(self, ir_document):
                return []

        with pytest.raises(ValueError, match="must define SEVERITY"):
            BadRule()

    def test_valid_subclass(self):
        """Valid subclass should work"""

        class ValidRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        rule = ValidRule()
        assert rule.CWE_ID == CWE.CWE_89
        assert rule.SEVERITY == Severity.HIGH

    def test_rule_get_name(self):
        """get_name returns class name"""

        class MyCustomRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        rule = MyCustomRule()
        assert rule.get_name() == "MyCustomRule"

    def test_rule_get_description(self):
        """get_description returns CWE info"""

        class TestRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        rule = TestRule()
        desc = rule.get_description()
        assert "SQL Injection" in desc
        assert "CWE-89" in desc

    def test_default_sources_sinks_sanitizers_are_tuples(self):
        """Default SOURCES, SINKS, SANITIZERS should be immutable tuples"""

        class TestRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        rule = TestRule()
        assert isinstance(rule.SOURCES, tuple)
        assert isinstance(rule.SINKS, tuple)
        assert isinstance(rule.SANITIZERS, tuple)

    def test_sources_sinks_with_tuples(self):
        """Rules can define SOURCES/SINKS as tuples"""

        class TestRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH
            SOURCES = (TaintSource(patterns=["request.args.get"], description="HTTP params"),)
            SINKS = (TaintSink(patterns=["cursor.execute"], description="SQL exec"),)

            def analyze(self, ir_document):
                return []

        rule = TestRule()
        assert len(rule.SOURCES) == 1
        assert len(rule.SINKS) == 1

    def test_calculate_confidence_short_path(self):
        """Short path gets bonus confidence"""

        class TestRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        rule = TestRule()
        # Short path (<=3): BASE(0.8) + BONUS(0.1) = 0.9
        conf = rule._calculate_confidence(None, None, [1, 2])
        assert conf == 0.9

    def test_calculate_confidence_long_path(self):
        """Long path gets penalty"""

        class TestRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        rule = TestRule()
        # Long path (>10): BASE(0.8) - PENALTY(0.1) = 0.7
        conf = rule._calculate_confidence(None, None, list(range(15)))
        assert conf == pytest.approx(0.7)

    def test_calculate_confidence_medium_path(self):
        """Medium path keeps base confidence"""

        class TestRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        rule = TestRule()
        # Medium path (4-10): BASE(0.8)
        conf = rule._calculate_confidence(None, None, list(range(5)))
        assert conf == 0.8

    def test_calculate_confidence_clamped(self):
        """Confidence is clamped to [0.0, 1.0]"""

        class TestRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            class ConfidenceSettings:
                BASE_CONFIDENCE = 0.95
                SHORT_PATH_BONUS = 0.2
                LONG_PATH_PENALTY = 0.1
                SHORT_PATH_THRESHOLD = 3
                LONG_PATH_THRESHOLD = 10

            def analyze(self, ir_document):
                return []

        rule = TestRule()
        # Would be 0.95 + 0.2 = 1.15, but clamped to 1.0
        conf = rule._calculate_confidence(None, None, [1])
        assert conf == 1.0


class TestRuleRegistry:
    """RuleRegistry tests"""

    @pytest.fixture
    def registry(self):
        """Fresh registry for each test"""
        return RuleRegistry()

    @pytest.fixture
    def sample_rule_class(self):
        """Sample rule class"""

        class SampleRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        return SampleRule

    def test_register_rule(self, registry, sample_rule_class):
        registry.register(sample_rule_class)
        assert "SampleRule" in registry
        assert len(registry) == 1

    def test_get_rule(self, registry, sample_rule_class):
        registry.register(sample_rule_class)
        rule = registry.get_rule("SampleRule")
        assert rule is not None
        assert isinstance(rule, SecurityRule)

    def test_get_rule_not_found(self, registry):
        assert registry.get_rule("NonExistent") is None

    def test_unregister_rule(self, registry, sample_rule_class):
        registry.register(sample_rule_class)
        assert registry.unregister("SampleRule") is True
        assert "SampleRule" not in registry

    def test_unregister_nonexistent(self, registry):
        assert registry.unregister("NonExistent") is False

    def test_get_all_rules(self, registry):
        class Rule1(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        class Rule2(SecurityRule):
            CWE_ID = CWE.CWE_78
            SEVERITY = Severity.CRITICAL

            def analyze(self, ir_document):
                return []

        registry.register(Rule1)
        registry.register(Rule2)

        rules = registry.get_all_rules()
        assert len(rules) == 2

    def test_get_rules_by_cwe(self, registry):
        class SQLi1(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        class SQLi2(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.CRITICAL

            def analyze(self, ir_document):
                return []

        class XSS(SecurityRule):
            CWE_ID = CWE.CWE_79
            SEVERITY = Severity.MEDIUM

            def analyze(self, ir_document):
                return []

        registry.register(SQLi1)
        registry.register(SQLi2)
        registry.register(XSS)

        sqli_rules = registry.get_rules_by_cwe(CWE.CWE_89)
        assert len(sqli_rules) == 2

        xss_rules = registry.get_rules_by_cwe(CWE.CWE_79)
        assert len(xss_rules) == 1

    def test_get_registered_names(self, registry, sample_rule_class):
        registry.register(sample_rule_class)
        names = registry.get_registered_names()
        assert "SampleRule" in names

    def test_clear(self, registry, sample_rule_class):
        registry.register(sample_rule_class)
        registry.clear()
        assert len(registry) == 0

    def test_caching(self, registry, sample_rule_class):
        """With caching enabled, same instance should be returned"""
        registry.register(sample_rule_class)
        rule1 = registry.get_rule("SampleRule")
        rule2 = registry.get_rule("SampleRule")
        assert rule1 is rule2

    def test_no_caching(self, sample_rule_class):
        """Without caching, new instances should be returned"""
        registry = RuleRegistry(use_cache=False)
        registry.register(sample_rule_class)
        rule1 = registry.get_rule("SampleRule")
        rule2 = registry.get_rule("SampleRule")
        assert rule1 is not rule2

    def test_contains(self, registry, sample_rule_class):
        registry.register(sample_rule_class)
        assert "SampleRule" in registry
        assert "NonExistent" not in registry

    def test_len(self, registry):
        assert len(registry) == 0

        class Rule1(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        registry.register(Rule1)
        assert len(registry) == 1


class TestGlobalRegistry:
    """Global registry singleton tests"""

    def setup_method(self):
        """Reset global registry before each test"""
        reset_registry()

    def teardown_method(self):
        """Reset global registry after each test"""
        reset_registry()

    def test_get_registry_singleton(self):
        """get_registry returns same instance"""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_set_registry(self):
        """set_registry replaces global registry"""
        custom = RuleRegistry()
        set_registry(custom)
        assert get_registry() is custom

    def test_reset_registry(self):
        """reset_registry creates new instance"""
        r1 = get_registry()
        reset_registry()
        r2 = get_registry()
        assert r1 is not r2


class TestRegisterRuleDecorator:
    """@register_rule decorator tests"""

    def setup_method(self):
        reset_registry()

    def teardown_method(self):
        reset_registry()

    def test_decorator_registers_rule(self):
        @register_rule
        class DecoratedRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.HIGH

            def analyze(self, ir_document):
                return []

        registry = get_registry()
        assert "DecoratedRule" in registry
        rule = registry.get_rule("DecoratedRule")
        assert rule is not None
