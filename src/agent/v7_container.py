"""
v7 Agent Container

v7 Agent 전용 DI Container.
기존 src/container.py와 독립적으로 동작.

나중에 src/container.py와 통합 가능.
"""

import os
from functools import cached_property


class V7AgentContainer:
    """
    v7 Agent DI Container.

    Port/Adapter 기반 의존성 주입.
    """

    def __init__(self):
        """Initialize v7 container"""
        pass

    # ========================================================================
    # Adapters (Port 구현체)
    # ========================================================================

    @cached_property
    def llm_provider(self):
        """LLM Provider (LiteLLM)"""
        from src.agent.adapters.llm.litellm_adapter import (
            LiteLLMProviderAdapter,
            StubLLMProvider,
        )

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SEMANTICA_OPENAI_API_KEY")

        if api_key:
            return LiteLLMProviderAdapter(
                primary_model="gpt-4o-mini",
                fallback_models=["gpt-3.5-turbo"],
                api_key=api_key,
                timeout=120,
            )
        else:
            return StubLLMProvider()

    @cached_property
    def sandbox_executor(self):
        """Sandbox Executor (E2B or Local fallback)"""
        import os

        # E2B API 키 확인 (SEMANTIC_E2B_API_KEY, SEMANTICA_E2B_API_KEY, E2B_API_KEY)
        e2b_api_key = (
            os.getenv("SEMANTIC_E2B_API_KEY") or os.getenv("SEMANTICA_E2B_API_KEY") or os.getenv("E2B_API_KEY")
        )

        if e2b_api_key:
            # E2B Sandbox (실제 클라우드 샌드박스)
            import logging

            from src.agent.adapters.sandbox.e2b_adapter import (
                E2BSandboxAdapter,
                E2BSandboxConfig,
            )

            logger = logging.getLogger(__name__)
            logger.info(f"Using E2B Sandbox (API key: {e2b_api_key[:8]}...)")

            config = E2BSandboxConfig(api_key=e2b_api_key)
            return E2BSandboxAdapter(config=config)
        else:
            # Local Sandbox (fallback)
            import logging

            from src.agent.adapters.sandbox.stub_sandbox import LocalSandboxAdapter

            logger = logging.getLogger(__name__)
            logger.warning("E2B_API_KEY not found, using LocalSandboxAdapter")

            return LocalSandboxAdapter()

    @cached_property
    def guardrail_validator(self):
        """Guardrail Validator (Pydantic)"""
        from src.agent.adapters.guardrail.pydantic_validator import (
            PydanticValidatorAdapter,
        )

        return PydanticValidatorAdapter()

    @cached_property
    def vcs_applier(self):
        """VCS Applier (GitPython)"""
        from src.agent.adapters.vcs.gitpython_adapter import GitPythonVCSAdapter

        return GitPythonVCSAdapter(".")

    @cached_property
    def workflow_engine(self):
        """Workflow Engine (LangGraph)"""
        from src.agent.adapters.workflow.langgraph_adapter import (
            LangGraphWorkflowAdapter,
        )

        return LangGraphWorkflowAdapter()

    # ========================================================================
    # Managers
    # ========================================================================

    @cached_property
    def context_manager(self):
        """Context Manager"""
        from src.agent.context_manager import ContextManager

        return ContextManager()

    @cached_property
    def experience_store(self):
        """Experience Store"""
        from src.agent.experience_store import ExperienceStore

        return ExperienceStore()

    # ========================================================================
    # Services (Domain Services)
    # ========================================================================

    @cached_property
    def analyze_service(self):
        """Analyze Service (Real LLM)"""
        from src.agent.domain.real_services import RealAnalyzeService

        return RealAnalyzeService(self.llm_provider)

    @cached_property
    def plan_service(self):
        """Plan Service (Real LLM)"""
        from src.agent.domain.real_services import RealPlanService

        return RealPlanService(self.llm_provider)

    @cached_property
    def generate_service(self):
        """Generate Service (Real LLM + Experience)"""
        from src.agent.experience_store import ExperienceEnhancedGenerateService

        return ExperienceEnhancedGenerateService(self.llm_provider, self.experience_store)

    @cached_property
    def critic_service(self):
        """Critic Service (Real LLM)"""
        from src.agent.domain.real_services import RealCriticService

        return RealCriticService(self.llm_provider)

    @cached_property
    def test_service(self):
        """Test Service (Sandbox)"""
        from src.agent.domain.real_services import RealTestService

        return RealTestService(self.sandbox_executor)

    @cached_property
    def heal_service(self):
        """Heal Service (Real LLM)"""
        from src.agent.domain.real_services import RealHealService

        return RealHealService(self.llm_provider)

    # ========================================================================
    # Orchestrator
    # ========================================================================

    @cached_property
    def agent_orchestrator(self):
        """v7 Agent Orchestrator"""
        from src.agent.orchestrator.v7_orchestrator import AgentOrchestrator

        return AgentOrchestrator(
            workflow_engine=self.workflow_engine,
            llm_provider=self.llm_provider,
            sandbox_executor=self.sandbox_executor,
            guardrail_validator=self.guardrail_validator,
            vcs_applier=self.vcs_applier,
        )


# Singleton instance (NOTE: Reload로 인한 캐시 문제 주의)
# 개발 중에는 매번 새로 생성하는 것이 안전
# v7_container = V7AgentContainer()


# Factory function (캐시 문제 회피)
def get_v7_container() -> V7AgentContainer:
    """V7 Agent Container 가져오기 (캐시 회피)"""
    return V7AgentContainer()
