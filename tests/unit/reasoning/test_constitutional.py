"""
Constitutional AI 테스트
"""

import pytest

from apps.orchestrator.orchestrator.shared.reasoning.constitutional import (
    Constitution,
    ConstitutionalConfig,
    ConstitutionalResult,
    RevisionGenerator,
    Rule,
    RuleSeverity,
    RuleViolation,
    SafetyChecker,
)


class TestConstitution:
    """Constitution 테스트"""

    def test_default_rules(self):
        """기본 규칙 존재"""
        constitution = Constitution()
        rules = constitution.get_rules()
        assert len(rules) > 0

    def test_add_custom_rule(self):
        """커스텀 규칙 추가"""
        constitution = Constitution()
        initial_count = len(constitution.get_rules())

        constitution.add_rule(
            Rule(
                rule_id="CUSTOM-001",
                name="Test rule",
                description="Test",
                severity=RuleSeverity.WARNING,
                check_fn=lambda content: "test" in content,
            )
        )

        assert len(constitution.get_rules()) == initial_count + 1

    def test_get_rules_by_severity(self):
        """심각도별 필터링"""
        constitution = Constitution()
        critical_rules = constitution.get_rules_by_severity(RuleSeverity.CRITICAL)
        assert all(r.severity == RuleSeverity.CRITICAL for r in critical_rules)


class TestSafetyChecker:
    """SafetyChecker 테스트"""

    def test_detect_hardcoded_password(self):
        """하드코딩된 비밀번호 탐지"""
        checker = SafetyChecker()
        code = 'password = "secret123"'

        violations = checker.check(code)
        assert len(violations) > 0
        assert any(v.rule_id == "SEC-001" for v in violations)
        assert not checker.is_safe(code)

    def test_detect_api_key(self):
        """하드코딩된 API 키 탐지"""
        checker = SafetyChecker()
        code = 'api_key = "sk-1234567890"'

        violations = checker.check(code)
        assert len(violations) > 0
        assert not checker.is_safe(code)

    def test_safe_code_passes(self):
        """안전한 코드는 통과"""
        checker = SafetyChecker()
        code = """
def add(a: int, b: int) -> int:
    return a + b
"""

        violations = checker.check(code)
        # 다른 경고는 있을 수 있지만 CRITICAL/ERROR는 없어야 함
        assert checker.is_safe(code)

    def test_detect_sql_injection(self):
        """SQL injection 취약점 탐지"""
        checker = SafetyChecker()
        code = "cursor.execute('SELECT * FROM users WHERE id=' + user_id)"

        violations = checker.check(code)
        # SQL injection 규칙 체크
        critical_violations = [v for v in violations if v.severity == RuleSeverity.CRITICAL]
        # 이 코드는 위험할 수 있음
        assert len(violations) > 0


class TestConstitutionalResult:
    """ConstitutionalResult 테스트"""

    def test_has_blocking_violations(self):
        """차단 위반 확인"""
        result = ConstitutionalResult(
            original_content="test",
            violations=[
                RuleViolation(
                    rule_id="SEC-001",
                    rule_name="Test",
                    severity=RuleSeverity.CRITICAL,
                    description="Critical issue",
                )
            ],
        )
        assert result.has_blocking_violations()

    def test_no_blocking_violations(self):
        """차단 위반 없음"""
        result = ConstitutionalResult(
            original_content="test",
            violations=[
                RuleViolation(
                    rule_id="INFO-001",
                    rule_name="Test",
                    severity=RuleSeverity.INFO,
                    description="Info",
                )
            ],
        )
        assert not result.has_blocking_violations()


class TestRevisionGenerator:
    """RevisionGenerator 테스트"""

    def test_no_auto_revise(self):
        """자동 수정 비활성화"""
        config = ConstitutionalConfig(auto_revise=False)
        checker = SafetyChecker()
        generator = RevisionGenerator(config, checker)

        violations = [RuleViolation("SEC-001", "Test", RuleSeverity.ERROR, "Error")]

        # revise_fn은 호출되지 않아야 함
        def revise_fn(content, violations):
            raise AssertionError("Should not be called")

        result = generator.revise("original", violations, revise_fn)
        assert not result.revision_attempted
        assert result.revised_content == ""
