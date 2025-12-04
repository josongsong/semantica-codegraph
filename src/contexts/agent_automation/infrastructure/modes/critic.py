"""
Critic Mode - 독립 평가자 Agent

다른 Agent의 결과를 객관적으로 평가하고 승인/거부를 결정합니다.
Reflection과 달리 독립된 평가자로서 동작합니다.
"""

from typing import TYPE_CHECKING, Any

from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, CriticOutput, ModeContext, Result, Task
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.infra.llm.base import BaseLLMClient

logger = get_logger(__name__)


@mode_registry.register(AgentMode.CRITIC)
class CriticMode(BaseModeHandler):
    """
    Critic Agent - 독립 평가자.

    다른 Agent의 실행 결과를 다음 기준으로 평가:
    1. Correctness (정확성): 요구사항 충족 여부
    2. Completeness (완전성): 누락된 부분 없는지
    3. Safety (안전성): 버그나 보안 이슈 없는지
    4. Quality (품질): 코드 품질, 문서화 수준

    Usage:
        critic = CriticMode(AgentMode.CRITIC, llm_client=llm)
        result = await critic.execute(task, context)
        # result.data contains CriticOutput
    """

    APPROVAL_THRESHOLD = 0.7  # 승인 기준 점수

    def __init__(
        self,
        mode: AgentMode = AgentMode.CRITIC,
        llm_client: "BaseLLMClient | None" = None,
    ):
        """
        Args:
            mode: Agent mode (should be CRITIC)
            llm_client: LLM 클라이언트 (평가용)
        """
        super().__init__(mode)
        self.llm_client = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter critic mode."""
        await super().enter(context)
        self.logger.info(f"🎯 Critic mode: Evaluating {len(context.pending_changes)} changes")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute critic evaluation.

        Args:
            task: Evaluation task (should contain 'target_result' in context)
            context: Shared mode context

        Returns:
            Result with CriticOutput
        """
        self.logger.info(f"Evaluating: {task.query}")

        # 1. 평가 대상 추출
        target_result = task.context.get("target_result")
        target_mode = task.context.get("target_mode", "unknown")

        if not target_result and not context.pending_changes:
            return self._create_result(
                data=CriticOutput(
                    approved=False,
                    overall_score=0.0,
                    correctness_score=0.0,
                    completeness_score=0.0,
                    safety_score=0.0,
                    issues=["No result to evaluate"],
                    recommendations=[],
                    must_fix=[],
                ),
                trigger="no_target",
                explanation="No evaluation target provided",
            )

        # 2. 다차원 평가 수행
        correctness = await self._evaluate_correctness(target_result, task, context)
        completeness = await self._evaluate_completeness(target_result, task, context)
        safety = await self._evaluate_safety(target_result, task, context)

        # 3. 종합 점수 계산
        overall_score = self._calculate_overall_score(correctness, completeness, safety)

        # 4. 이슈 및 권장사항 수집
        issues = correctness.get("issues", []) + completeness.get("issues", []) + safety.get("issues", [])

        recommendations = (
            correctness.get("recommendations", [])
            + completeness.get("recommendations", [])
            + safety.get("recommendations", [])
        )

        must_fix = [issue for issue in issues if self._is_critical(issue)]

        # 5. 승인 여부 결정
        approved = overall_score >= self.APPROVAL_THRESHOLD and len(must_fix) == 0

        # 6. Trigger 결정
        if approved:
            trigger = "approved"
            explanation = f"Approved (score: {overall_score:.2f})"
        elif must_fix:
            trigger = "must_fix"
            explanation = f"Critical issues found ({len(must_fix)} must fix)"
        else:
            trigger = "improvements_needed"
            explanation = f"Improvements recommended (score: {overall_score:.2f})"

        self.logger.info(
            f"Evaluation complete: overall={overall_score:.2f}, "
            f"approved={approved}, issues={len(issues)}, must_fix={len(must_fix)}"
        )

        critic_output = CriticOutput(
            approved=approved,
            overall_score=overall_score,
            correctness_score=correctness["score"],
            completeness_score=completeness["score"],
            safety_score=safety["score"],
            issues=issues,
            recommendations=recommendations,
            must_fix=must_fix,
            metadata={
                "target_mode": target_mode,
                "evaluation_breakdown": {
                    "correctness": correctness,
                    "completeness": completeness,
                    "safety": safety,
                },
            },
        )

        return self._create_result(
            data=critic_output,
            trigger=trigger,
            explanation=explanation,
        )

    async def _evaluate_correctness(
        self,
        target_result: Any,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """
        정확성 평가: 요구사항을 올바르게 충족했는가?

        Args:
            target_result: 평가 대상 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            평가 결과
        """
        issues = []
        recommendations = []
        score = 1.0

        # 1. 요구사항 충족 여부
        if not target_result or (hasattr(target_result, "data") and not target_result.data):
            issues.append("No meaningful output produced")
            score -= 0.4

        # 2. 에러 발생 여부
        if context.errors:
            issues.append(f"Execution produced {len(context.errors)} errors")
            score -= 0.2 * min(len(context.errors), 2)

        # 3. LLM 기반 정확성 평가 (optional)
        if self.llm_client and target_result:
            llm_eval = await self._llm_evaluate_correctness(target_result, task)
            score = score * 0.5 + llm_eval["score"] * 0.5
            issues.extend(llm_eval.get("issues", []))
            recommendations.extend(llm_eval.get("recommendations", []))

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "recommendations": recommendations,
        }

    async def _evaluate_completeness(
        self,
        target_result: Any,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """
        완전성 평가: 누락된 부분이 없는가?

        Args:
            target_result: 평가 대상 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            평가 결과
        """
        issues = []
        recommendations = []
        score = 1.0

        # 1. 설명 완전성
        if hasattr(target_result, "explanation") and len(target_result.explanation) < 20:
            issues.append("Insufficient explanation")
            score -= 0.2

        # 2. 변경사항 문서화
        if context.pending_changes:
            undocumented = sum(1 for c in context.pending_changes if not c.get("description"))
            if undocumented > 0:
                recommendations.append(f"{undocumented} changes lack description")
                score -= 0.1

        # 3. 테스트 커버리지
        if context.pending_changes and not context.test_results:
            recommendations.append("No tests provided for changes")
            score -= 0.15

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "recommendations": recommendations,
        }

    async def _evaluate_safety(
        self,
        target_result: Any,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """
        안전성 평가: 위험한 변경은 없는가?

        Args:
            target_result: 평가 대상 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            평가 결과
        """
        issues = []
        recommendations = []
        score = 1.0

        # 1. 대량 변경 감지
        if len(context.pending_changes) > 100:
            issues.append(f"Large number of changes ({len(context.pending_changes)})")
            recommendations.append("Consider breaking into smaller increments")
            score -= 0.2

        # 2. 위험한 패턴 감지
        dangerous_patterns = ["eval(", "exec(", "os.system(", "subprocess.call("]
        for change in context.pending_changes:
            content = str(change.get("content", ""))
            for pattern in dangerous_patterns:
                if pattern in content:
                    issues.append(f"Dangerous pattern detected: {pattern}")
                    score -= 0.3
                    break

        # 3. 테스트 실패
        if context.test_results:
            if not context.test_results.get("all_passed", True):
                issues.append("Some tests are failing")
                score -= 0.3

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "recommendations": recommendations,
        }

    def _calculate_overall_score(
        self,
        correctness: dict[str, Any],
        completeness: dict[str, Any],
        safety: dict[str, Any],
    ) -> float:
        """
        종합 점수 계산.

        Args:
            correctness: 정확성 평가
            completeness: 완전성 평가
            safety: 안전성 평가

        Returns:
            0.0 ~ 1.0 종합 점수
        """
        # 가중 평균: Correctness 40%, Completeness 30%, Safety 30%
        overall = 0.4 * correctness["score"] + 0.3 * completeness["score"] + 0.3 * safety["score"]

        return max(0.0, min(1.0, overall))

    def _is_critical(self, issue: str) -> bool:
        """
        이슈가 critical한지 판단.

        Args:
            issue: 이슈 설명

        Returns:
            Critical 여부
        """
        critical_keywords = [
            "dangerous",
            "security",
            "failing",
            "error",
            "crash",
            "data loss",
        ]

        issue_lower = issue.lower()
        return any(keyword in issue_lower for keyword in critical_keywords)

    async def _llm_evaluate_correctness(
        self,
        target_result: Any,
        task: Task,
    ) -> dict[str, Any]:
        """
        LLM 기반 정확성 평가.

        Args:
            target_result: 평가 대상
            task: 원본 태스크

        Returns:
            평가 결과
        """
        if not self.llm_client:
            return {"score": 0.8, "issues": [], "recommendations": []}

        prompt = f"""You are an expert code critic. Evaluate the following result for CORRECTNESS.

Original Task: {task.query}
Result: {str(target_result)[:1000]}

Rate correctness on 0.0-1.0 scale and list any issues.

Format:
SCORE: <0.0-1.0>
ISSUES:
- <issue>
RECOMMENDATIONS:
- <recommendation>
"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                max_tokens=300,
                temperature=0.2,
            )

            # 간단한 파싱
            lines = response.strip().split("\n")
            score = 0.8
            issues = []
            recommendations = []

            current_section = None
            for line in lines:
                line = line.strip()
                if line.startswith("SCORE:"):
                    try:
                        score = float(line.split(":", 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("ISSUES:"):
                    current_section = "issues"
                elif line.startswith("RECOMMENDATIONS:"):
                    current_section = "recommendations"
                elif line.startswith("-") and current_section:
                    content = line[1:].strip()
                    if current_section == "issues":
                        issues.append(content)
                    elif current_section == "recommendations":
                        recommendations.append(content)

            return {"score": score, "issues": issues, "recommendations": recommendations}

        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}")
            return {"score": 0.75, "issues": [], "recommendations": []}
