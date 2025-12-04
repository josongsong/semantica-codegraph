"""
Agent Automation DI Container

에이전트 자동화 컨텍스트의 의존성 주입 컨테이너
"""

import os
from functools import cached_property

from .infrastructure.orchestrator_adapter import OrchestratorAdapter
from .usecase.execute_agent import ExecuteAgentUseCase


class AgentAutomationContainer:
    """Agent Automation BC의 DI Container"""

    def __init__(self, use_fake: bool = False):
        """
        초기화

        Args:
            use_fake: Fake 구현 사용 여부
        """
        self._use_fake = use_fake or os.getenv("USE_FAKE_STORES", "false").lower() == "true"

    @cached_property
    def orchestrator(self):
        """에이전트 오케스트레이터"""
        if self._use_fake:
            # Lazy import for fake orchestrator
            from .infrastructure.fake_orchestrator import FakeAgentOrchestrator

            return FakeAgentOrchestrator()

        # 실제 AgentOrchestrator 사용
        from src.container import container

        return OrchestratorAdapter(orchestrator=container.agent_orchestrator)

    @cached_property
    def execute_agent_usecase(self) -> ExecuteAgentUseCase:
        """에이전트 실행 UseCase"""
        return ExecuteAgentUseCase(
            orchestrator=self.orchestrator,
        )

    @cached_property
    def repo_registry(self):
        """Repository Registry for multi-repo support"""
        from .infrastructure.repo_registry import RepoRegistry

        return RepoRegistry()

    @cached_property
    def incremental_indexing_adapter(self):
        """증분 인덱싱 Adapter"""
        from src.container import container

        from .infrastructure.indexing_adapter import IncrementalIndexingAdapter

        return IncrementalIndexingAdapter(
            job_orchestrator=container.index_job_orchestrator,
            repo_registry=self.repo_registry,
        )


# 전역 싱글톤
agent_automation_container = AgentAutomationContainer()
