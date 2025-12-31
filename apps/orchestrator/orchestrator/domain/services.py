"""
Agent Domain Services (Stub 구현)

Phase 1에서는 Stub으로 시작, 나중에 실제 LLM 연동
"""

from dataclasses import dataclass
from pathlib import Path

from apps.orchestrator.orchestrator.domain.models import AgentTask, ChangeType, CodeChange


@dataclass
class AnalysisResult:
    """분석 결과"""

    impacted_files: list[str]
    complexity: int
    requires_clarification: bool
    summary: str


@dataclass
class PlanResult:
    """계획 결과"""

    steps: list[str]
    estimated_changes: int
    rationale: str


class StubAnalyzeService:
    """
    Analyze Service Stub.

    실제 구현(Phase 2+):
    - LLM으로 코드 분석
    - 영향받는 파일 식별
    - 복잡도 추정
    """

    async def analyze_task(self, task: AgentTask) -> AnalysisResult:
        """
        Task 분석 (Stub).

        실제로는 LLM + Context를 사용하여 분석.
        현재는 하드코딩된 결과 반환.
        """
        # Stub: 간단한 휴리스틱
        if "utils.py" in task.description:
            return AnalysisResult(
                impacted_files=["utils.py", "test_utils.py"],
                complexity=3,
                requires_clarification=False,
                summary="calculate_total 함수의 할인율 계산 로직 수정 필요",
            )

        # 기본값
        return AnalysisResult(
            impacted_files=task.context_files,
            complexity=task.estimate_complexity(),
            requires_clarification=task.requires_clarification(),
            summary="일반적인 코드 수정 작업",
        )


class StubPlanService:
    """
    Plan Service Stub.

    실제 구현(Phase 2+):
    - LLM으로 변경 계획 생성
    - Step-by-step 전략 수립
    """

    async def create_plan(self, task: AgentTask, analysis: AnalysisResult) -> PlanResult:
        """
        변경 계획 생성 (Stub).

        실제로는 LLM이 계획 생성.
        """
        if "calculate_total" in task.description:
            return PlanResult(
                steps=[
                    "1. utils.py의 calculate_total 함수 열기",
                    "2. discount 계산 로직 수정 (discount_rate 그대로 빼는 버그 수정)",
                    "3. test_utils.py 실행하여 검증",
                ],
                estimated_changes=1,
                rationale="할인율 계산 로직을 수정하여 테스트 통과하도록 함",
            )

        # 기본값
        return PlanResult(
            steps=["1. 파일 분석", "2. 코드 수정", "3. 테스트 실행"],
            estimated_changes=len(analysis.impacted_files),
            rationale="기본 변경 계획",
        )


class StubGenerateService:
    """
    Generate Service Stub.

    실제 구현(Phase 2+):
    - LLM으로 코드 생성
    - Diff 생성
    """

    async def generate_code(self, task: AgentTask, plan: dict | None) -> list[CodeChange]:
        """Alias for generate_changes (Protocol interface)"""
        return await self.generate_changes(task, plan)

    async def generate_changes(self, task: AgentTask, plan: PlanResult) -> list[CodeChange]:
        """
        코드 변경 생성 (Stub).

        실제로는 LLM이 코드 생성.
        현재는 하드코딩된 수정 반환.
        """
        if "calculate_total" in task.description:
            # 올바른 수정
            return [
                CodeChange(
                    file_path="test_fixtures/scenario1/utils.py",
                    change_type=ChangeType.MODIFY,
                    original_lines=[
                        "    # 🐛 버그: discount_rate를 그대로 빼면 안 됨",
                        "    return price - discount_rate  # 잘못된 계산!",
                    ],
                    new_lines=[
                        "    # ✅ 수정: 할인율을 올바르게 적용",
                        "    discount = price * discount_rate",
                        "    return price - discount",
                    ],
                    start_line=22,
                    end_line=23,
                    rationale="할인율 계산 로직 수정: discount = price * discount_rate로 계산 후 차감",
                )
            ]

        # 기본값
        return []


class StubCriticService:
    """
    Critic Service Stub.

    실제 구현(Phase 2+):
    - LLM으로 코드 리뷰
    - 잠재적 문제 탐지
    """

    async def review_code(self, changes: list[CodeChange]) -> list[str]:
        """Alias for critique_changes (Protocol interface)"""
        return await self.critique_changes(changes)

    async def critique_changes(self, changes: list[CodeChange]) -> list[str]:
        """
        코드 리뷰 (Stub).

        실제로는 LLM이 리뷰.
        현재는 간단한 검증만.
        """
        errors = []

        for change in changes:
            # 변경 내용 검증
            if not change.new_lines:
                errors.append(f"{change.file_path}: 변경 내용이 비어있음")

            # 파일 존재 검증
            if not Path(change.file_path).exists():
                errors.append(f"{change.file_path}: 파일이 존재하지 않음")

        return errors
