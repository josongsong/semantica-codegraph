"""
Success Evaluator (SOTA급)

ExecutionResult를 기반으로 성공/실패를 intelligent하게 판단
"""

from dataclasses import dataclass
from typing import Literal

from src.agent.domain.reasoning.tot_models import ExecutionResult


@dataclass
class SuccessEvaluation:
    """성공 평가 결과"""

    success: bool
    confidence: float  # 0.0 ~ 1.0
    reason: str
    level: Literal["perfect", "good", "acceptable", "poor", "failed"]


class SuccessEvaluator:
    """
    Success Evaluator (SOTA급)

    단순 pass/fail이 아닌 다차원 평가:
    1. Compilation
    2. Tests (if available)
    3. Code Quality
    4. Security
    """

    def evaluate(self, result: ExecutionResult) -> SuccessEvaluation:
        """
        ExecutionResult를 평가

        SOTA: 컨텍스트 기반 intelligent 판단
        """
        # 1. Compilation 실패 → 무조건 실패
        if not result.compile_success:
            return SuccessEvaluation(success=False, confidence=1.0, reason="Compilation failed", level="failed")

        # 2. Tests가 실행된 경우 → Test 결과 우선
        if result.tests_run > 0:
            return self._evaluate_with_tests(result)

        # 3. Tests가 없는 경우 → Compilation + Quality 기반
        return self._evaluate_without_tests(result)

    def _evaluate_with_tests(self, result: ExecutionResult) -> SuccessEvaluation:
        """Tests가 실행된 경우의 평가"""

        # Perfect: 모든 테스트 통과 + 품질 좋음
        if result.tests_passed == result.tests_run and result.lint_errors == 0:
            return SuccessEvaluation(
                success=True,
                confidence=1.0,
                reason=f"All {result.tests_run} tests passed, no lint errors",
                level="perfect",
            )

        # Good: 대부분 테스트 통과
        if result.test_pass_rate >= 0.9:
            return SuccessEvaluation(
                success=True,
                confidence=0.9,
                reason=f"{result.tests_passed}/{result.tests_run} tests passed (90%+)",
                level="good",
            )

        # Acceptable: 과반수 테스트 통과
        if result.test_pass_rate >= 0.5:
            return SuccessEvaluation(
                success=True,
                confidence=0.7,
                reason=f"{result.tests_passed}/{result.tests_run} tests passed (50%+)",
                level="acceptable",
            )

        # Poor: 일부 테스트 통과
        if result.tests_passed > 0:
            return SuccessEvaluation(
                success=False,
                confidence=0.8,
                reason=f"Only {result.tests_passed}/{result.tests_run} tests passed",
                level="poor",
            )

        # Failed: 모든 테스트 실패
        return SuccessEvaluation(
            success=False, confidence=1.0, reason=f"All {result.tests_run} tests failed", level="failed"
        )

    def _evaluate_without_tests(self, result: ExecutionResult) -> SuccessEvaluation:
        """
        Tests가 없는 경우의 평가 (SOTA)

        Compilation + Code Quality + Security
        """
        score = 0.0
        reasons = []

        # Compilation success (baseline)
        score += 0.4
        reasons.append("compile success")

        # Code Quality
        if result.lint_errors == 0:
            score += 0.2
            reasons.append("no lint errors")
        elif result.lint_errors < 3:
            score += 0.1
            reasons.append(f"{result.lint_errors} lint errors")

        if result.lint_warnings < 5:
            score += 0.1
            reasons.append("few warnings")

        # Complexity (lower is better)
        if result.complexity_delta <= 0:
            score += 0.2
            reasons.append("complexity improved")
        elif result.complexity_delta < 5:
            score += 0.1
            reasons.append("complexity stable")

        # Security
        if result.security_severity in ["none", "low"]:
            score += 0.1
            reasons.append("no critical security issues")

        # 판단
        if score >= 0.8:
            return SuccessEvaluation(
                success=True,
                confidence=0.7,  # 테스트 없으므로 confidence 낮음
                reason=f"Compile + Quality ({', '.join(reasons)})",
                level="acceptable",
            )
        elif score >= 0.6:
            return SuccessEvaluation(
                success=True, confidence=0.5, reason=f"Compile + Basic Quality ({', '.join(reasons)})", level="poor"
            )
        else:
            return SuccessEvaluation(
                success=False,
                confidence=0.6,
                reason=f"Low quality score ({score:.1f}): {', '.join(reasons)}",
                level="failed",
            )


# Singleton
_evaluator = SuccessEvaluator()


def evaluate_success(result: ExecutionResult) -> SuccessEvaluation:
    """편의 함수"""
    return _evaluator.evaluate(result)
