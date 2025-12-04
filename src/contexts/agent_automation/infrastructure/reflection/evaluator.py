"""
Criteria Evaluator - 다양한 평가 기준 적용

Mode별로 특화된 평가 기준을 적용하여 품질을 평가합니다.
"""

from typing import Any

from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task
from src.infra.observability import get_logger

logger = get_logger(__name__)


class CriteriaEvaluator:
    """
    Mode별 특화 평가 기준.

    각 모드의 특성에 맞는 평가 기준을 적용합니다.
    """

    def __init__(self):
        """평가 기준 초기화."""
        self.criteria_map = {
            AgentMode.IMPLEMENTATION: self._evaluate_implementation,
            AgentMode.DEBUG: self._evaluate_debug,
            AgentMode.TEST: self._evaluate_test,
            AgentMode.REFACTOR: self._evaluate_refactor,
            AgentMode.QA: self._evaluate_qa,
            AgentMode.DESIGN: self._evaluate_design,
        }

    def evaluate(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """
        Mode별 평가 수행.

        Args:
            result: 평가할 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            평가 결과 (score, issues, suggestions)
        """
        evaluator = self.criteria_map.get(result.mode, self._evaluate_generic)
        return evaluator(result, task, context)

    def _evaluate_implementation(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """Implementation mode 평가."""
        issues = []
        suggestions = []
        score = 1.0

        # 1. 변경사항 존재 여부
        if not context.pending_changes:
            issues.append("No code changes generated")
            score -= 0.3

        # 2. 에러 여부
        if context.errors:
            issues.append(f"Implementation produced {len(context.errors)} errors")
            score -= 0.2 * len(context.errors)

        # 3. 테스트 필요 여부
        if context.pending_changes and not any("test" in str(c).lower() for c in context.pending_changes):
            suggestions.append("Consider adding tests for new implementation")

        # 4. 문서화
        if context.pending_changes and len(context.pending_changes) > 5:
            suggestions.append("Document major changes for maintainability")

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }

    def _evaluate_debug(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """Debug mode 평가."""
        issues = []
        suggestions = []
        score = 1.0

        # 1. 에러 분석 여부
        if not result.data or not result.data.get("error_analysis"):
            issues.append("Missing error analysis")
            score -= 0.3

        # 2. 수정안 제시 여부
        if not result.data or not result.data.get("fix_proposal"):
            issues.append("No fix proposal provided")
            score -= 0.2

        # 3. Root cause 파악
        if result.data and result.data.get("root_cause"):
            suggestions.append("Root cause identified - good!")
        else:
            suggestions.append("Try to identify root cause, not just symptoms")

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }

    def _evaluate_test(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """Test mode 평가."""
        issues = []
        suggestions = []
        score = 1.0

        # 1. 테스트 실행 여부
        if not context.test_results:
            issues.append("No test results available")
            score -= 0.3

        # 2. 커버리지
        if context.test_results:
            coverage = context.test_results.get("coverage", 0)
            if coverage < 0.7:
                suggestions.append(f"Coverage is {coverage * 100:.0f}%, aim for 70%+")

        # 3. 테스트 통과율
        if context.test_results:
            total = context.test_results.get("total", 0)
            passed = context.test_results.get("passed", 0)
            if total > 0 and passed < total:
                issues.append(f"{total - passed} tests failing")
                score -= 0.1 * (total - passed) / total

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }

    def _evaluate_refactor(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """Refactor mode 평가."""
        issues = []
        suggestions = []
        score = 1.0

        # 1. Code smell 분석
        if result.data and not result.data.get("code_smells"):
            issues.append("No code smell analysis")
            score -= 0.2

        # 2. 안전성 평가
        if result.data:
            safety = result.data.get("safety_level")
            if safety == "unsafe":
                issues.append("Refactoring is marked as unsafe")
                score -= 0.3
            elif safety == "risky":
                suggestions.append("Risky refactoring - consider adding safety tests")

        # 3. 후방 호환성
        if result.data and not result.data.get("backward_compatible"):
            suggestions.append("Breaking changes detected - update documentation")

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }

    def _evaluate_qa(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """QA mode 평가."""
        issues = []
        suggestions = []
        score = 1.0

        # 1. 리뷰 완전성
        if not result.data or not result.data.get("review"):
            issues.append("Missing code review")
            score -= 0.4

        # 2. 품질 점수
        if result.data:
            quality_score = result.data.get("quality_score", 0)
            if quality_score < 70:
                issues.append(f"Low quality score: {quality_score}/100")
                score = quality_score / 100

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }

    def _evaluate_design(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """Design mode 평가."""
        issues = []
        suggestions = []
        score = 1.0

        # 1. 설계 문서 존재
        if not result.data or not result.data.get("design"):
            issues.append("No design document produced")
            score -= 0.3

        # 2. 구성요소 파악
        if result.data:
            components = result.data.get("components", [])
            if not components:
                suggestions.append("Identify key components and their responsibilities")

        # 3. 다이어그램
        if result.data and result.data.get("diagrams"):
            suggestions.append("Diagrams included - excellent!")

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }

    def _evaluate_generic(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """Generic fallback 평가."""
        issues = []
        suggestions = []
        score = 0.8  # 기본 점수

        # 기본적인 체크만 수행
        if not result.data:
            issues.append("Empty result data")
            score -= 0.2

        if context.errors:
            issues.append(f"{len(context.errors)} errors occurred")
            score -= 0.1 * len(context.errors)

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }
