"""
Agent Orchestrator Adapter

실제 AgentOrchestrator 어댑터
"""

from collections.abc import Callable

from ..domain.models import AgentResult, AgentStep


class OrchestratorAdapter:
    """실제 AgentOrchestrator 어댑터"""

    def __init__(self, orchestrator):
        """
        초기화

        Args:
            orchestrator: AgentOrchestrator 인스턴스
        """
        self.orchestrator = orchestrator

    async def run_session(
        self,
        repo_id: str,
        prompt: str,
        mode: str,
        step_callback: Callable[[str], None] | None = None,
    ) -> AgentResult:
        """에이전트 세션 실행"""
        from uuid import uuid4

        session_id = str(uuid4())

        try:
            # 실제 orchestrator 호출 (기존 AgentOrchestrator의 메서드 확인 필요)
            # result = await self.orchestrator.run_session(...)

            # 임시: 콜백만 호출하고 성공 결과 반환
            if step_callback:
                step_callback(f"Processing: {prompt}")
                step_callback("Analyzing code...")
                step_callback("Generating solution...")

            steps = [
                AgentStep(step_number=1, description="Code analysis", completed=True),
                AgentStep(step_number=2, description="Solution generation", completed=True),
            ]

            return AgentResult(
                session_id=session_id,
                success=True,
                steps=steps,
                diff_summary="Generated patch",
            )

        except Exception as e:
            # 에러 발생 시 실패 결과 반환
            from src.common.observability import get_logger

            logger = get_logger(__name__)
            logger.error(f"Agent session failed: {e}", repo_id=repo_id, prompt=prompt)

            return AgentResult(
                session_id=session_id,
                success=False,
                steps=[],
                diff_summary="",
                error_message=str(e),
            )
