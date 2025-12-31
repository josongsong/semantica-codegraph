"""
Revision Generator

위반 사항을 자동으로 수정.
"""

import logging
from collections.abc import Callable

from .constitutional_models import ConstitutionalConfig, ConstitutionalResult, RuleViolation
from .safety_checker import SafetyChecker

logger = logging.getLogger(__name__)


class RevisionGenerator:
    """수정 생성기"""

    def __init__(
        self,
        config: ConstitutionalConfig,
        safety_checker: SafetyChecker,
    ):
        self.config = config
        self.safety_checker = safety_checker

    def revise(
        self,
        content: str,
        violations: list[RuleViolation],
        revise_fn: Callable[[str, list[RuleViolation]], str],
    ) -> ConstitutionalResult:
        """
        위반 사항 수정

        Args:
            content: 원본 콘텐츠
            violations: 위반 리스트
            revise_fn: 수정 함수 (LLM)

        Returns:
            수정 결과
        """
        revised_content = content
        all_violations = violations[:]
        attempts = 0

        # 자동 수정 시도
        if self.config.auto_revise and violations:
            for attempt in range(self.config.max_revision_attempts):
                attempts += 1
                logger.info(f"Revision attempt {attempt + 1}/{self.config.max_revision_attempts}")

                try:
                    # LLM으로 수정
                    revised_content = revise_fn(revised_content, all_violations)

                    # 재검사
                    new_violations = self.safety_checker.check(revised_content)

                    if not new_violations:
                        logger.info(f"Revision successful after {attempts} attempts")
                        all_violations = []
                        break

                    all_violations = new_violations

                except Exception as e:
                    logger.warning(f"Revision attempt {attempt + 1} failed: {e}")
                    continue

        # 결과 생성
        result = ConstitutionalResult(
            original_content=content,
            violations=all_violations,
            revised_content=revised_content if attempts > 0 else "",
            revision_attempted=attempts > 0,
            is_safe=not any(v.severity.value in ["critical", "error"] for v in all_violations),
            is_compliant=len(all_violations) == 0,
            total_violations=len(all_violations),
            critical_violations=sum(1 for v in all_violations if v.severity.value == "critical"),
            revision_attempts=attempts,
        )

        logger.info(
            f"Revision completed: {len(all_violations)} violations remaining, "
            f"is_safe={result.is_safe}, is_compliant={result.is_compliant}"
        )

        return result
