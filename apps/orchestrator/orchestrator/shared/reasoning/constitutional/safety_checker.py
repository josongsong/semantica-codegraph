"""
Safety Checker

규칙 기반 안전성 검사.
"""

import logging

from .constitution import Constitution
from .constitutional_models import RuleViolation

logger = logging.getLogger(__name__)


class SafetyChecker:
    """안전성 검사기"""

    def __init__(self, constitution: Constitution | None = None):
        self.constitution = constitution or Constitution()

    def check(self, content: str) -> list[RuleViolation]:
        """
        콘텐츠 검사

        Args:
            content: 검사할 콘텐츠

        Returns:
            위반 리스트
        """
        violations: list[RuleViolation] = []

        for rule in self.constitution.get_rules():
            try:
                # 규칙 검사
                is_violated = rule.check_fn(content)

                if is_violated:
                    violation = RuleViolation(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        description=rule.description,
                    )
                    violations.append(violation)

                    logger.debug(f"Rule violation: {rule.rule_id} - {rule.name} ({rule.severity})")

            except Exception as e:
                logger.warning(f"Failed to check rule {rule.rule_id}: {e}")
                continue

        logger.info(f"Safety check completed: {len(violations)} violations found")
        return violations

    def is_safe(self, content: str) -> bool:
        """
        안전한지 확인

        Args:
            content: 검사할 콘텐츠

        Returns:
            안전 여부
        """
        violations = self.check(content)

        # CRITICAL이나 ERROR 위반이 없으면 안전
        critical_or_error = any(v.severity.value in ["critical", "error"] for v in violations)

        return not critical_or_error
