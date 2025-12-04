"""
Reflection Engine - 결과 평가 및 Self-Critique

Agent가 생성한 결과를 스스로 평가하고 개선점을 도출하는 엔진.
"""

from typing import TYPE_CHECKING, Any

from src.contexts.agent_automation.infrastructure.types import ModeContext, ReflectionOutput, Result, Task
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.infra.llm.base import BaseLLMClient

logger = get_logger(__name__)


class ReflectionEngine:
    """
    Reflection Engine - 자기 평가 및 개선 제안.

    Agent의 실행 결과를 평가하고 개선이 필요한지 판단합니다.
    """

    def __init__(
        self,
        llm_client: "BaseLLMClient | None" = None,
        quality_threshold: float = 0.7,
        max_iterations: int = 3,
    ):
        """
        Args:
            llm_client: LLM 클라이언트 (평가용)
            quality_threshold: 품질 임계값 (이하면 개선 필요)
            max_iterations: 최대 개선 반복 횟수
        """
        self.llm_client = llm_client
        self.quality_threshold = quality_threshold
        self.max_iterations = max_iterations

    async def reflect(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> ReflectionOutput:
        """
        결과에 대한 Reflection 수행.

        Args:
            result: 평가할 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            ReflectionOutput with evaluation
        """
        logger.info(f"Reflecting on {result.mode.value} result")

        # 1. 기본 품질 체크
        basic_checks = self._basic_quality_checks(result, task, context)

        # 2. LLM 기반 심층 평가 (optional)
        if self.llm_client:
            llm_evaluation = await self._llm_based_evaluation(result, task, context)
        else:
            llm_evaluation = {"score": 0.8, "issues": [], "suggestions": []}

        # 3. 종합 점수 계산
        quality_score = self._calculate_quality_score(basic_checks, llm_evaluation)

        # 4. 개선 필요 여부 판단
        needs_improvement = quality_score < self.quality_threshold

        # 5. 이슈 및 제안 수집
        issues = basic_checks.get("issues", []) + llm_evaluation.get("issues", [])
        suggestions = basic_checks.get("suggestions", []) + llm_evaluation.get("suggestions", [])
        strengths = basic_checks.get("strengths", []) + llm_evaluation.get("strengths", [])

        logger.info(
            f"Reflection complete: score={quality_score:.2f}, "
            f"needs_improvement={needs_improvement}, "
            f"issues={len(issues)}"
        )

        return ReflectionOutput(
            needs_improvement=needs_improvement,
            quality_score=quality_score,
            issues=issues,
            suggestions=suggestions,
            strengths=strengths,
            metadata={
                "basic_checks": basic_checks,
                "llm_evaluation": llm_evaluation,
                "mode": result.mode.value,
            },
        )

    def _basic_quality_checks(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """
        기본 품질 체크 (Rule-based).

        Args:
            result: 평가할 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            체크 결과
        """
        issues = []
        suggestions = []
        strengths = []

        # 1. 결과 데이터 존재 여부
        if not result.data:
            issues.append("Result data is empty")
            suggestions.append("Ensure mode produces meaningful output")

        # 2. 에러 발생 여부
        if context.errors:
            issues.append(f"Execution had {len(context.errors)} errors")
            suggestions.append("Review and fix errors before proceeding")

        # 3. Pending changes 품질
        if context.pending_changes:
            if len(context.pending_changes) > 50:
                issues.append("Too many pending changes (>50)")
                suggestions.append("Consider breaking into smaller subtasks")
            else:
                strengths.append(f"Manageable {len(context.pending_changes)} changes")

        # 4. 설명 품질
        if not result.explanation or len(result.explanation) < 10:
            issues.append("Insufficient explanation")
            suggestions.append("Provide detailed explanation of actions taken")
        else:
            strengths.append("Detailed explanation provided")

        # 5. Trigger 일관성
        if result.trigger and result.trigger not in ["success", "error", "approved", "completed"]:
            # Valid custom triggers are allowed
            strengths.append(f"Clear transition trigger: {result.trigger}")

        # 기본 점수 계산 (휴리스틱)
        base_score = 1.0
        if issues:
            base_score -= len(issues) * 0.1
        if context.errors:
            base_score -= len(context.errors) * 0.15

        base_score = max(0.0, min(1.0, base_score))

        return {
            "score": base_score,
            "issues": issues,
            "suggestions": suggestions,
            "strengths": strengths,
        }

    async def _llm_based_evaluation(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> dict[str, Any]:
        """
        LLM 기반 심층 평가.

        Args:
            result: 평가할 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            LLM 평가 결과
        """
        if not self.llm_client:
            return {"score": 0.8, "issues": [], "suggestions": [], "strengths": []}

        # LLM 프롬프트 구성
        prompt = self._build_evaluation_prompt(result, task, context)

        try:
            # LLM 호출
            response = await self.llm_client.generate(
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,  # 일관된 평가를 위해 낮은 temperature
            )

            # 응답 파싱 (간단한 구현)
            evaluation = self._parse_llm_response(response)
            return evaluation

        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}")
            # Fallback to basic evaluation
            return {"score": 0.75, "issues": [], "suggestions": [], "strengths": []}

    def _build_evaluation_prompt(
        self,
        result: Result,
        task: Task,
        context: ModeContext,
    ) -> str:
        """
        LLM 평가용 프롬프트 생성.

        Args:
            result: 평가할 결과
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            프롬프트 문자열
        """
        prompt = f"""You are a code quality critic evaluating an AI agent's work.

Task: {task.query}
Mode: {result.mode.value}
Explanation: {result.explanation}

Result Data Summary:
{str(result.data)[:500]}

Pending Changes: {len(context.pending_changes)}
Errors: {len(context.errors)}

Please evaluate the quality of this result on a scale of 0.0 to 1.0, and provide:
1. Issues found (if any)
2. Suggestions for improvement
3. Strengths of the approach

Format your response as:
SCORE: <0.0-1.0>
ISSUES:
- <issue 1>
- <issue 2>
SUGGESTIONS:
- <suggestion 1>
- <suggestion 2>
STRENGTHS:
- <strength 1>
- <strength 2>
"""
        return prompt

    def _parse_llm_response(self, response: str) -> dict[str, Any]:
        """
        LLM 응답 파싱.

        Args:
            response: LLM 응답 텍스트

        Returns:
            파싱된 평가 결과
        """
        lines = response.strip().split("\n")

        score = 0.75  # 기본값
        issues = []
        suggestions = []
        strengths = []

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
            elif line.startswith("SUGGESTIONS:"):
                current_section = "suggestions"
            elif line.startswith("STRENGTHS:"):
                current_section = "strengths"
            elif line.startswith("-") and current_section:
                content = line[1:].strip()
                if current_section == "issues":
                    issues.append(content)
                elif current_section == "suggestions":
                    suggestions.append(content)
                elif current_section == "strengths":
                    strengths.append(content)

        return {
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
            "strengths": strengths,
        }

    def _calculate_quality_score(
        self,
        basic_checks: dict[str, Any],
        llm_evaluation: dict[str, Any],
    ) -> float:
        """
        종합 품질 점수 계산.

        Args:
            basic_checks: 기본 체크 결과
            llm_evaluation: LLM 평가 결과

        Returns:
            0.0 ~ 1.0 품질 점수
        """
        # 가중 평균 (basic 30%, llm 70%)
        basic_score = basic_checks.get("score", 0.5)
        llm_score = llm_evaluation.get("score", 0.5)

        if self.llm_client:
            final_score = 0.3 * basic_score + 0.7 * llm_score
        else:
            final_score = basic_score

        return max(0.0, min(1.0, final_score))

    async def improve(
        self,
        result: Result,
        reflection: ReflectionOutput,
        task: Task,
        context: ModeContext,
    ) -> Result:
        """
        Reflection 기반 결과 개선 (간단한 구현).

        Args:
            result: 원본 결과
            reflection: Reflection 평가
            task: 원본 태스크
            context: 실행 컨텍스트

        Returns:
            개선된 Result (실제로는 mode handler가 재실행해야 함)
        """
        logger.info(f"Attempting to improve result (score: {reflection.quality_score:.2f})")

        # 개선 메타데이터 추가
        improved_result = Result(
            mode=result.mode,
            data=result.data,  # 실제로는 mode handler 재실행 필요
            trigger=result.trigger,
            explanation=f"{result.explanation}\n\n[Improved based on reflection]",
            requires_approval=result.requires_approval,
            metadata={
                **result.metadata,
                "reflection": {
                    "original_score": reflection.quality_score,
                    "issues_addressed": reflection.issues,
                    "suggestions_applied": reflection.suggestions,
                },
            },
        )

        return improved_result
