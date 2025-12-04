"""
Execute Agent UseCase

에이전트 실행
"""

from collections.abc import Callable

from ..domain.models import AgentResult
from ..domain.ports import AgentOrchestratorPort


class ExecuteAgentUseCase:
    """에이전트 실행 UseCase"""

    def __init__(self, orchestrator: AgentOrchestratorPort):
        """
        초기화

        Args:
            orchestrator: 에이전트 오케스트레이터
        """
        self.orchestrator = orchestrator

    async def execute(
        self,
        repo_id: str,
        prompt: str,
        mode: str = "implement",
        step_callback: Callable[[str], None] | None = None,
    ) -> AgentResult:
        """
        에이전트 실행

        Args:
            repo_id: 리포지토리 ID
            prompt: 프롬프트
            mode: 에이전트 모드
            step_callback: 스텝 콜백

        Returns:
            실행 결과
        """
        result = await self.orchestrator.run_session(
            repo_id=repo_id,
            prompt=prompt,
            mode=mode,
            step_callback=step_callback,
        )

        return result
