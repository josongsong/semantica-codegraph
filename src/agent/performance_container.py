"""
Performance-Optimized Agent Container

성능 최적화된 v7 Agent DI Container.

최적화:
- CachedLLMAdapter: LLM 응답 캐싱 (L1: Memory, L2: Redis)
- OptimizedLLMAdapter: Batch, Circuit Breaker, Rate Limiting
- ParallelOrchestrator: Analyze + Plan 병렬 실행

주의:
- Import는 cached_property 내부에서 lazy하게 수행 (순환 방지)
"""

import os
from functools import cached_property

# Type hints (runtime import 아님)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ports import (
        IGuardrailValidator,
        ILLMProvider,
        ISandboxExecutor,
        IVCSApplier,
        IWorkflowEngine,
    )


class PerformanceAgentContainer:
    """
    성능 최적화된 Agent DI Container.

    기능:
    - LLM 응답 캐싱 (Redis + In-memory)
    - 병렬 처리 (Analyze + Plan 동시 실행)
    - Batch 처리 (여러 요청 한 번에)
    - Circuit Breaker (장애 격리)
    - Rate Limiting (요청 속도 제한)
    """

    def __init__(self):
        """Initialize performance container"""
        pass

    # ========================================================================
    # Adapters (성능 최적화)
    # ========================================================================

    @cached_property
    def llm_provider(self):
        """
        LLM Provider (성능 최적화).

        구조:
        CachedLLMAdapter (L1: Memory, L2: Redis)
          └─ OptimizedLLMAdapter (Batch, Circuit Breaker, Rate Limiting)
             └─ LiteLLMProviderAdapter (실제 LLM API)
        """
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SEMANTICA_OPENAI_API_KEY")

        if not api_key:
            # Stub (API 키 없음)
            from src.agent.adapters.llm.litellm_adapter import StubLLMProvider

            return StubLLMProvider()

        # Base LLM
        from src.agent.adapters.llm.litellm_adapter import LiteLLMProviderAdapter

        base_llm = LiteLLMProviderAdapter(
            primary_model="gpt-4o-mini",
            fallback_models=["gpt-3.5-turbo"],
            api_key=api_key,
            timeout=120,
        )

        # OptimizedLLMAdapter
        from src.agent.adapters.llm.optimized_llm_adapter import OptimizedLLMAdapter

        optimized_llm = OptimizedLLMAdapter(
            base_llm=base_llm,
            rate_limit_per_second=10,
            circuit_breaker_threshold=5,
            enable_batch=True,
            enable_streaming=False,
        )

        # CachedLLMAdapter
        from src.agent.adapters.llm.cached_llm_adapter import CachedLLMAdapter

        # Redis (optional)
        redis_client = None
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))

        try:
            from src.infra.cache.redis import RedisAdapter

            redis_client = RedisAdapter(host=redis_host, port=redis_port)
        except Exception:
            # Redis 없으면 in-memory만 사용
            pass

        return CachedLLMAdapter(
            base_llm=optimized_llm,
            redis_client=redis_client,
            cache_ttl=3600,  # 1시간
            enable_cache=True,
            in_memory_cache_size=100,
        )

    @cached_property
    def sandbox_executor(self):
        """Sandbox Executor (E2B or Local)"""
        e2b_api_key = (
            os.getenv("SEMANTIC_E2B_API_KEY") or os.getenv("SEMANTICA_E2B_API_KEY") or os.getenv("E2B_API_KEY")
        )

        if e2b_api_key:
            from src.agent.adapters.sandbox.e2b_adapter import (
                E2BSandboxAdapter,
                E2BSandboxConfig,
            )

            config = E2BSandboxConfig(api_key=e2b_api_key)
            return E2BSandboxAdapter(config=config)
        else:
            from src.agent.adapters.sandbox.stub_sandbox import LocalSandboxAdapter

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
    # Orchestrator (병렬 처리)
    # ========================================================================

    @cached_property
    def agent_orchestrator(self):
        """
        Agent Orchestrator (병렬 처리).

        최적화:
        - Analyze + Plan 병렬 실행
        - Critic + Test 병렬 실행
        - 여러 파일 동시 생성
        """
        enable_parallel = os.getenv("AGENT_ENABLE_PARALLEL", "true").lower() == "true"

        if enable_parallel:
            from src.agent.orchestrator.parallel_orchestrator import (
                ParallelAgentOrchestrator,
            )

            return ParallelAgentOrchestrator(
                workflow_engine=self.workflow_engine,
                llm_provider=self.llm_provider,
                sandbox_executor=self.sandbox_executor,
                guardrail_validator=self.guardrail_validator,
                vcs_applier=self.vcs_applier,
            )
        else:
            from src.agent.orchestrator.v7_orchestrator import AgentOrchestrator

            return AgentOrchestrator(
                workflow_engine=self.workflow_engine,
                llm_provider=self.llm_provider,
                sandbox_executor=self.sandbox_executor,
                guardrail_validator=self.guardrail_validator,
                vcs_applier=self.vcs_applier,
            )


def get_performance_container() -> PerformanceAgentContainer:
    """성능 최적화된 Container 가져오기"""
    return PerformanceAgentContainer()
