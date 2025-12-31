"""
Agent Container - Dependency Injection for Agent System

Extracted from codegraph-shared container.py to reduce coupling.
All agent-related factory methods (v7, v8, v9, cascade, safety).
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_shared.infra.di import InfraContainer

logger = get_logger(__name__)


class AgentContainer:
    """
    Agent System Dependency Injection Container.

    Provides lazy singleton instances of all agent components:
    - v7: Port/Adapter architecture agents
    - v8: Deep reasoning with ToT/Reflection
    - v9: LATS (Language Agent Tree Search)
    - CASCADE: Deep Context & Self-Correcting
    - Safety: Guardrails & Governance
    """

    def __init__(self, infra, domain):
        """
        Initialize AgentContainer.

        Args:
            infra: InfraContainer (redis, postgres, etc.)
            domain: Container (domain services like foundation, index, memory)
        """
        self.infra = infra
        self.domain = domain

    # ========================================================================
    # v7 Agent System (Port/Adapter 기반)
    # ========================================================================

    @cached_property
    def v7_llm_provider(self):
        """v7 LLM Provider (LiteLLM)"""
        import os

        from apps.orchestrator.orchestrator.adapters.llm.litellm_adapter import LiteLLMProviderAdapter

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SEMANTICA_OPENAI_API_KEY")
        return LiteLLMProviderAdapter(
            primary_model="gpt-4o-mini",
            fallback_models=["gpt-3.5-turbo"],
            api_key=api_key,
        )

    @cached_property
    def v7_sandbox_executor(self):
        """v7 Sandbox Executor (E2B or Local)"""
        import os

        e2b_api_key = os.getenv("E2B_API_KEY")

        if e2b_api_key:
            # E2B Sandbox (SOTA)
            from apps.orchestrator.orchestrator.adapters.sandbox.e2b_adapter import E2BSandboxAdapter, E2BSandboxConfig
            from apps.orchestrator.orchestrator.adapters.sandbox.security import SecurityLevel, SecurityPolicy

            config = E2BSandboxConfig(
                api_key=e2b_api_key,
                security_policy=SecurityPolicy.for_level(SecurityLevel.MEDIUM),
                timeout_sec=30,
            )
            return E2BSandboxAdapter(config=config)
        else:
            # Fallback: Local Sandbox
            from apps.orchestrator.orchestrator.adapters.sandbox.stub_sandbox import LocalSandboxAdapter

            logger.warning("E2B_API_KEY not found, using LocalSandboxAdapter")
            # CASCADE 통합: Process Manager 주입
            return LocalSandboxAdapter(process_manager=self.cascade_process_manager)

    @cached_property
    def v7_guardrail_validator(self):
        """v7 Guardrail Validator (Pydantic)"""
        from apps.orchestrator.orchestrator.adapters.guardrail.pydantic_validator import PydanticValidatorAdapter

        return PydanticValidatorAdapter()

    @cached_property
    def v7_vcs_applier(self):
        """v7 VCS Applier (GitPython)"""
        from apps.orchestrator.orchestrator.adapters.vcs.gitpython_adapter import GitPythonVCSAdapter

        return GitPythonVCSAdapter(".")

    @cached_property
    def v7_workflow_engine(self):
        """v7 Workflow Engine (LangGraph)"""
        from apps.orchestrator.orchestrator.adapters.workflow.langgraph_adapter import LangGraphWorkflowAdapter

        return LangGraphWorkflowAdapter()

    @cached_property
    def v7_context_manager(self):
        """v7 Context Manager"""
        from apps.orchestrator.orchestrator.context_manager import ContextManager

        return ContextManager()

    @cached_property
    def v7_experience_store(self):
        """v7 Experience Store"""
        from apps.orchestrator.orchestrator.experience_store import ExperienceStore

        return ExperienceStore()

    @cached_property
    def v7_incremental_workflow(self):
        """v7 Incremental Workflow Manager (SOTA급 - 기존 인프라 활용)"""
        from apps.orchestrator.orchestrator.domain.incremental_workflow import IncrementalCache, IncrementalWorkflow

        return IncrementalWorkflow(
            change_detector=self.domain.change_detector,  # ✅ 기존 SOTA
            graph_impact_analyzer=self._graph_impact_analyzer,  # ✅ 기존 SOTA
            graph_store=self.domain.graph_store,  # ✅ Memgraph
            cache=IncrementalCache(redis_client=self.infra.redis),  # ✅ Redis 캐시
        )

    @cached_property
    def _graph_impact_analyzer(self):
        """Graph Impact Analyzer (기존 SOTA 인프라)"""
        try:
            from codegraph_engine.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer

            return GraphImpactAnalyzer(
                max_depth=5,
                max_affected=1000,
                include_test_files=False,
            )
        except ImportError:
            # Fallback: None (IncrementalWorkflow가 간단한 방법 사용)
            return None

    @cached_property
    def v7_diff_manager(self):
        """v7 Diff Manager (Git diff 생성/파싱)"""
        from apps.orchestrator.orchestrator.domain.diff_manager import DiffManager

        return DiffManager(context_lines=3)

    @cached_property
    def v7_approval_manager(self):
        """v7 Approval Manager (Human-in-the-loop)"""
        from apps.orchestrator.orchestrator.domain.approval_manager import (
            ApprovalCriteria,
            ApprovalManager,
            CLIApprovalAdapter,
        )

        # 자동 승인 규칙
        criteria = ApprovalCriteria(
            auto_approve_tests=True,  # 테스트 파일 자동 승인
            auto_approve_docs=True,  # 문서 파일 자동 승인
            max_lines_auto=20,  # 20줄 이하 자동 승인
        )

        # CLI Adapter
        ui_adapter = CLIApprovalAdapter(colorize=True)

        return ApprovalManager(
            ui_adapter=ui_adapter,
            criteria=criteria,
        )

    @cached_property
    def v7_partial_committer(self):
        """v7 Partial Committer (부분 커밋)"""
        from apps.orchestrator.orchestrator.infrastructure.git_repository_impl import GitRepositoryImpl

        # CASCADE 통합: Fuzzy Patcher 주입
        return GitRepositoryImpl(repo_path=".", fuzzy_patcher=self.cascade_fuzzy_patcher)

    # ======================================================================
    # v8.1 Components (Dynamic Reasoning)
    # ======================================================================

    @cached_property
    def v8_complexity_analyzer(self):
        """v8 Complexity Analyzer (Adapter)"""
        from apps.orchestrator.orchestrator.adapters.reasoning import RadonComplexityAnalyzer

        return RadonComplexityAnalyzer()

    @cached_property
    def v8_risk_assessor(self):
        """v8 Risk Assessor (Adapter)"""
        from apps.orchestrator.orchestrator.adapters.reasoning import HistoricalRiskAssessor

        return HistoricalRiskAssessor(experience_store=None)  # TODO: Phase 3에서 Experience Store v2 연동

    @cached_property
    def v8_reasoning_router(self):
        """v8 Dynamic Reasoning Router (Domain Service)"""
        from apps.orchestrator.orchestrator.shared.reasoning import DynamicReasoningRouter

        return DynamicReasoningRouter(
            complexity_analyzer=self.v8_complexity_analyzer,
            risk_assessor=self.v8_risk_assessor,
        )

    @cached_property
    def v8_decide_reasoning_path(self):
        """v8 Decide Reasoning Path UseCase (Application Layer)"""
        from apps.orchestrator.orchestrator.application.use_cases import DecideReasoningPathUseCase

        return DecideReasoningPathUseCase(
            router=self.v8_reasoning_router,
            complexity_analyzer=self.v8_complexity_analyzer,
            risk_assessor=self.v8_risk_assessor,
        )

    @cached_property
    def v8_tot_scorer(self):
        """v8 ToT Scoring Engine (Domain Service)"""
        from apps.orchestrator.orchestrator.shared.reasoning import ToTScoringEngine

        return ToTScoringEngine()

    @cached_property
    def v8_sandbox_executor(self):
        """v8 Sandbox Executor (Subprocess, 로컬)"""
        from apps.orchestrator.orchestrator.adapters.reasoning import SubprocessSandbox

        return SubprocessSandbox()

    @cached_property
    def v8_strategy_generator(self):
        """v8 Strategy Generator (LLM)"""
        from apps.orchestrator.orchestrator.adapters.llm.strategy_generator import StrategyGeneratorFactory

        # OpenAI API Key 있으면 LLM 사용
        return StrategyGeneratorFactory.create(use_llm=True)

    @cached_property
    def v8_tot_executor(self):
        """v8 ToT Executor (LangGraph + LLM)"""
        from apps.orchestrator.orchestrator.adapters.reasoning import LangGraphToTExecutor

        return LangGraphToTExecutor(
            llm_provider=self.v8_strategy_generator,  # LLM 연동!
            sandbox_executor=self.v8_sandbox_executor,
            max_strategies=5,
            use_langgraph=True,  # LangGraph 활성화
        )

    @cached_property
    def v8_execute_tot(self):
        """v8 Execute ToT UseCase (Application Layer)"""
        from apps.orchestrator.orchestrator.application.use_cases import ExecuteToTUseCase

        return ExecuteToTUseCase(
            tot_executor=self.v8_tot_executor,
            tot_scorer=self.v8_tot_scorer,
        )

    @cached_property
    def v8_graph_analyzer(self):
        """v8 Graph Analyzer (Adapter)"""
        from apps.orchestrator.orchestrator.adapters.reasoning import SimpleGraphAnalyzer

        return SimpleGraphAnalyzer()

    @cached_property
    def v8_reflection_judge(self):
        """v8 Self-Reflection Judge (Domain Service)"""
        from apps.orchestrator.orchestrator.shared.reasoning import SelfReflectionJudge

        return SelfReflectionJudge()

    @cached_property
    def v8_experience_repository(self):
        """
        v8 Experience Repository (SOTA: Unified Session Memory)

        SOTA: contexts/session_memory 통합!
        - Episode 저장
        - Bug pattern 학습
        - Code pattern 추출
        - Project knowledge 축적
        """
        import os

        # SOTA: Try contexts/session_memory first!
        try:
            # Direct access to consolidation service
            consolidation = self.domain._memory.consolidation_service
            logger.info("using_session_memory_consolidation_service")
            return consolidation
        except Exception as e:
            logger.warning(f"Session memory not available: {e}, falling back to simple experience store")

        # Fallback: agent/experience (기존 호환성)
        profile = os.getenv("SEMANTICA_PROFILE", "local")

        if profile in ["prod", "production", "cloud"]:
            try:
                from apps.orchestrator.orchestrator.infrastructure.experience_repository import ExperienceRepository

                db_session = self.infra.postgres if hasattr(self.infra, "postgres") else None
                return ExperienceRepository(db_session=db_session)
            except Exception as e2:
                logger.warning(f"PostgreSQL failed: {e2}")

        # Final fallback: SQLite
        from apps.orchestrator.orchestrator.infrastructure.experience_repository_sqlite import (
            ExperienceRepositorySQLite,
        )

        return ExperienceRepositorySQLite()

    @cached_property
    def v8_fail_safe(self):
        """v8 Fail-Safe Layer"""
        from apps.orchestrator.orchestrator.reasoning.fail_safe import FailSafeLayer

        return FailSafeLayer()

    # ===== Safety & Governance =====
    @cached_property
    def safety_secret_scrubber(self):
        from apps.orchestrator.orchestrator.adapters.safety import SecretScrubberAdapter
        from apps.orchestrator.orchestrator.domain.safety import ScrubberConfig

        return SecretScrubberAdapter(ScrubberConfig())

    @cached_property
    def safety_license_checker(self):
        from apps.orchestrator.orchestrator.adapters.safety import LicenseComplianceCheckerAdapter
        from apps.orchestrator.orchestrator.domain.safety import LicensePolicy

        return LicenseComplianceCheckerAdapter(LicensePolicy())

    @cached_property
    def safety_action_gate(self):
        from apps.orchestrator.orchestrator.adapters.safety import DangerousActionGateAdapter
        from apps.orchestrator.orchestrator.domain.safety import GateConfig

        return DangerousActionGateAdapter(GateConfig())

    @cached_property
    def safety_orchestrator(self):
        from apps.orchestrator.orchestrator.domain.safety import SafetyConfig, SafetyOrchestrator

        # DIP: Inject Ports (Adapters implement Ports)
        return SafetyOrchestrator(
            config=SafetyConfig(),
            secret_scanner=self.safety_secret_scrubber,
            license_checker=self.safety_license_checker,
            action_gate=self.safety_action_gate,
        )

    # ========================================================================
    # v9: LATS (Language Agent Tree Search)
    # ========================================================================

    @cached_property
    def v9_lats_thought_evaluator(self):
        """v9 LATS Thought Evaluator (Heuristic + LLM)"""
        from apps.orchestrator.orchestrator.shared.reasoning.lats_thought_evaluator import LATSThoughtEvaluator

        return LATSThoughtEvaluator(llm=self.llm_provider)

    @cached_property
    def v9_lats_config(self):
        """v9 LATS Config (MCTS 설정)"""
        from apps.orchestrator.orchestrator.shared.reasoning.lats_models import MCTSConfig

        return MCTSConfig(
            max_iterations=100,
            max_depth=5,
            exploration_constant=1.4,
            # Dynamic Temperature
            temperature_expansion=0.8,
            temperature_evaluation=0.2,
            temperature_simulation=0.0,
            temperature_final=0.3,
            # Budget
            max_total_tokens=50_000,
            max_cost_usd=5.0,
            enable_budget_limit=True,
            # Cross-Model
            generator_model="gpt-4o",
            verifier_model="claude-3.5-sonnet",
            enable_cross_model=False,  # 기본 비활성 (비용 고려)
            # Optimization
            enable_prompt_caching=True,
            enable_semantic_dedup=True,
        )

    @cached_property
    def v9_lats_executor(self):
        """v9 LATS Executor (Adapter)"""
        from apps.orchestrator.orchestrator.adapters.reasoning.lats_executor import LATSExecutor

        return LATSExecutor(
            llm=self.llm_provider,
            sandbox=self.v8_sandbox_executor,  # v8 Sandbox 재사용
            thought_evaluator=self.v9_lats_thought_evaluator,
            config=self.v9_lats_config,
        )

    @cached_property
    def v9_lats_search_engine(self):
        """v9 LATS Search Engine (Domain Service)"""
        from apps.orchestrator.orchestrator.shared.reasoning.lats_search import LATSSearchEngine

        return LATSSearchEngine(
            executor=self.v9_lats_executor,
            config=self.v9_lats_config,
            on_event=None,  # TODO: Event handler 연결
            save_winning_paths=True,
            enable_reflexion=True,  # P2 Advanced
            experience_repository=self.v8_experience_repository,  # ✅ Experience Store 연동!
        )

    @cached_property
    def v9_lats_persistence(self):
        """v9 LATS Tree Persistence (P2 Advanced)"""
        from apps.orchestrator.orchestrator.shared.reasoning.lats_persistence import LATSTreePersistence

        return LATSTreePersistence()

    @cached_property
    def v9_lats_intent_predictor(self):
        """v9 LATS Intent Predictor (P2 Advanced)"""
        from apps.orchestrator.orchestrator.shared.reasoning.lats_intent_predictor import LATSIntentPredictor

        return LATSIntentPredictor(experience_repository=self.v8_experience_repository)

    @cached_property
    def v8_agent_orchestrator(self):
        """v8 Agent Orchestrator (SOTA: Dynamic Routing + ToT + Reflection + Code Context + Multi-LLM)"""
        import os

        from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import DeepReasoningOrchestrator

        # SOTA Features toggle (from env vars)
        enable_multi_llm = os.getenv("ENABLE_MULTI_LLM_ENSEMBLE", "true").lower() == "true"
        enable_alphacode = os.getenv("ENABLE_ALPHACODE_SAMPLING", "false").lower() == "true"

        return DeepReasoningOrchestrator(
            decide_reasoning_path=self.v8_decide_reasoning_path,
            execute_tot=self.v8_execute_tot,
            reflection_judge=self.v8_reflection_judge,
            fast_path_orchestrator=self.v7_agent_orchestrator,
            # Code Context Services (SOTA)
            ast_analyzer=self.domain.ast_analyzer,
            graph_builder=self.domain.dependency_graph_builder,
            embedding_service=self.domain.code_embedding_service,
            experience_repository=self.v8_experience_repository,
            llm_adapter=self.v7_llm_provider,
            # SOTA: Multi-LLM Ensemble (RFC-025)
            enable_multi_llm_ensemble=enable_multi_llm,
            ensemble_config=None,  # Use default config
            # SOTA: AlphaCode Sampling
            enable_alphacode_sampling=enable_alphacode,
            alphacode_sampler=None,  # Auto-create
        )

    # ========================================================================
    # Infrastructure Ports (Hexagonal Architecture 완벽 준수)
    # ========================================================================

    @cached_property
    def command_executor(self):
        """Infrastructure: Command Executor (subprocess 추상화)"""
        from apps.orchestrator.orchestrator.adapters.infrastructure import AsyncSubprocessAdapter

        return AsyncSubprocessAdapter()

    @cached_property
    def process_monitor(self):
        """Infrastructure: Process Monitor (psutil 추상화)"""
        from apps.orchestrator.orchestrator.adapters.infrastructure import PsutilAdapter

        return PsutilAdapter()

    @cached_property
    def filesystem(self):
        """Infrastructure: FileSystem (pathlib 추상화)"""
        from apps.orchestrator.orchestrator.adapters.infrastructure import PathlibAdapter

        return PathlibAdapter()

    # ========================================================================
    # CASCADE: Deep Context & Self-Correcting Agent (RFC-CASCADE-001)
    # Hexagonal Architecture 완벽 준수 (Infrastructure Port 주입)
    # ========================================================================

    @cached_property
    def cascade_fuzzy_patcher(self):
        """CASCADE: Smart Fuzzy Patcher (Hexagonal)"""
        from apps.orchestrator.orchestrator.adapters.cascade import FuzzyPatcherAdapter

        return FuzzyPatcherAdapter(
            command_executor=self.command_executor,  # Port 주입
            filesystem=self.filesystem,  # Port 주입
            whitespace_insensitive=True,
            min_confidence=0.8,
        )

    @cached_property
    def cascade_reproduction_engine(self):
        """CASCADE: Reproduction-First Engine (Hexagonal)"""
        from apps.orchestrator.orchestrator.adapters.cascade import ReproductionEngineAdapter

        return ReproductionEngineAdapter(
            llm=self.v7_llm_provider,
            command_executor=self.command_executor,  # Port 주입
            filesystem=self.filesystem,  # Port 주입
            default_timeout=30.0,
        )

    @cached_property
    def cascade_process_manager(self):
        """CASCADE: Zombie Process Killer (Hexagonal)"""
        from apps.orchestrator.orchestrator.adapters.cascade import ProcessManagerAdapter

        return ProcessManagerAdapter(
            process_monitor=self.process_monitor,
            zombie_threshold_sec=5.0,
            cpu_threshold=90.0,  # Port 주입
        )

    @cached_property
    def cascade_graph_pruner(self):
        """CASCADE: Graph RAG PageRank Pruner (토큰 최적화)"""
        from apps.orchestrator.orchestrator.adapters.cascade import GraphPrunerAdapter

        return GraphPrunerAdapter(tokens_per_char=0.25, signature_ratio=0.1)

    @cached_property
    def cascade_orchestrator(self):
        """CASCADE: 전체 오케스트레이터 (Reproduction-First TDD)"""
        from apps.orchestrator.orchestrator.adapters.cascade import CascadeOrchestratorAdapter

        return CascadeOrchestratorAdapter(
            fuzzy_patcher=self.cascade_fuzzy_patcher,
            reproduction_engine=self.cascade_reproduction_engine,
            process_manager=self.cascade_process_manager,
            graph_pruner=self.cascade_graph_pruner,
            code_generator=self.v8_agent_orchestrator,  # v8 사용
            sandbox_executor=self.v7_sandbox_executor,
        )

    @cached_property
    def v7_soft_lock_manager(self):
        """v7 Soft Lock Manager (Multi-Agent Lock 관리 + Deadlock 방지)"""
        from apps.orchestrator.orchestrator.domain.deadlock_detector import DeadlockDetector
        from apps.orchestrator.orchestrator.domain.soft_lock_manager import SoftLockManager
        from apps.orchestrator.orchestrator.infrastructure.sqlite_lock_store import create_lock_store

        # Deadlock Detector 생성 (SOTA)
        deadlock_detector = DeadlockDetector(
            enable_auto_break=True,
            max_cycle_length=10,
        )

        # 🔥 SQLite First Strategy (RFC-018)
        # Redis 있으면 Redis, 없으면 SQLite
        redis_client = None
        if self.domain._profile.should_use_redis():
            redis_client = self.infra.redis if hasattr(self.infra, "redis") else None

        # Lock Store (Auto-detect)
        lock_store = create_lock_store(
            mode="auto",
            redis_client=redis_client,
            sqlite_path="data/agent_locks.db",
        )

        return SoftLockManager(
            redis_client=lock_store,  # SQLite or Redis
            deadlock_detector=deadlock_detector,
        )

    @cached_property
    def v7_lock_keeper(self):
        """v7 Lock Keeper (Lock 자동 갱신)"""
        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        return LockKeeper(
            lock_manager=self.v7_soft_lock_manager,
            renewal_interval=300.0,  # 5분마다 갱신
            max_consecutive_failures=3,
        )

    @cached_property
    def v7_deadlock_detector(self):
        """v7 Deadlock Detector (Wait-for graph)"""
        # soft_lock_manager가 이미 갖고 있음
        return self.v7_soft_lock_manager.deadlock_detector

    @cached_property
    def v7_conflict_resolver(self):
        """v7 Conflict Resolver (Multi-Agent 충돌 해결)"""
        from apps.orchestrator.orchestrator.domain.conflict_resolver import ConflictResolver

        return ConflictResolver(
            vcs_applier=self.v7_vcs_applier,
        )

    @cached_property
    def v7_agent_coordinator(self):
        """v7 Agent Coordinator (Multi-Agent 조율)"""
        from apps.orchestrator.orchestrator.domain.agent_coordinator import AgentCoordinator

        return AgentCoordinator(
            lock_manager=self.v7_soft_lock_manager,
            conflict_resolver=self.v7_conflict_resolver,
            orchestrator_factory=lambda: self.v7_agent_orchestrator,
        )

    @cached_property
    def v7_metrics_collector(self):
        """v7 Metrics Collector (Prometheus)"""
        from apps.orchestrator.orchestrator.adapters.monitoring import PrometheusMetricsAdapter

        return PrometheusMetricsAdapter()  # Uses global collector

    @cached_property
    def v7_health_checker(self):
        """v7 Health Checker (시스템 컴포넌트 상태)"""
        from apps.orchestrator.orchestrator.adapters.monitoring import HealthCheckAdapter

        return HealthCheckAdapter(
            postgres_client=self.infra.postgres,
            redis_client=self.infra.redis,
            qdrant_client=self.infra.qdrant,
            memgraph_client=self.infra.memgraph,
            llm_provider=self.v7_llm_provider,
        )

    # ========================================================================
    # v7: Performance Optimization (SOTA급)
    # ========================================================================

    @cached_property
    def v7_optimized_llm_provider(self):
        """v7 Optimized LLM Provider (SOTA급 성능 최적화)"""
        from codegraph_shared.config import settings

        from apps.orchestrator.orchestrator.adapters.llm.optimized_llm_adapter import OptimizedLLMAdapter

        return OptimizedLLMAdapter(
            primary_model=settings.agent_llm_model if hasattr(settings, "agent_llm_model") else "gpt-4o-mini",
            fallback_models=["gpt-4o", "gpt-4"],
            timeout=60,
            max_requests_per_second=10.0,
            max_concurrent=5,
            enable_cache=True,
            cache_ttl=3600,
            redis_client=self.infra.redis,
        )

    @cached_property
    def v7_advanced_cache(self):
        """v7 Advanced Multi-tier Cache (L1: Local, L2: Redis)"""
        from apps.orchestrator.orchestrator.infrastructure.cache.advanced_cache import AdvancedCache

        return AdvancedCache(
            redis_client=self.infra.redis,
            local_max_size=1000,
            local_max_bytes=100 * 1024 * 1024,  # 100MB
            default_ttl=3600,
            compression_threshold=1024,  # 1KB
            enable_bloom_filter=True,
        )

    @cached_property
    def v7_performance_monitor(self):
        """v7 Performance Monitor (Request Tracing, Latency, Throughput)"""
        from apps.orchestrator.orchestrator.infrastructure.performance_monitor import PerformanceMonitor

        def alert_callback(message: str):
            logger.warning(f"Performance Alert: {message}")

        return PerformanceMonitor(
            slow_threshold=1.0,  # 1초
            histogram_window=1000,
            alert_callback=alert_callback,
        )

    @cached_property
    def v7_profiler(self):
        """v7 Profiler (CPU, Memory, Async)"""
        from apps.orchestrator.orchestrator.infrastructure.profiler import Profiler

        return Profiler(
            enable_cpu=True,
            enable_memory=True,
            enable_async=True,
        )

    @cached_property
    def v7_bottleneck_detector(self):
        """v7 Bottleneck Detector (자동 병목 감지)"""
        from apps.orchestrator.orchestrator.infrastructure.profiler import BottleneckDetector

        def alert_callback(message: str):
            logger.warning(f"Bottleneck Alert: {message}")

        return BottleneckDetector(
            time_threshold=1.0,  # 1초
            memory_threshold=100 * 1024 * 1024,  # 100MB
            alert_callback=alert_callback,
        )

    @cached_property
    def v7_agent_orchestrator(self):
        """v7 Agent Orchestrator (SOTA급 통합)"""
        from apps.orchestrator.orchestrator.orchestrator.fast_path_orchestrator import FastPathOrchestrator

        return FastPathOrchestrator(
            workflow_engine=self.v7_workflow_engine,
            llm_provider=self.v7_llm_provider,
            sandbox_executor=self.v7_sandbox_executor,
            guardrail_validator=self.v7_guardrail_validator,
            vcs_applier=self.v7_vcs_applier,
            # 기존 시스템 통합
            retriever_service=self.domain.retriever_service,
            chunk_store=self.domain.chunk_store,
            memory_system=self.domain.memory_system,
            # Incremental Execution
            incremental_workflow=self.v7_incremental_workflow,
            # Human-in-the-Loop
            approval_manager=self.v7_approval_manager,
            diff_manager=self.v7_diff_manager,
            partial_committer=self.v7_partial_committer,
            # CASCADE 통합
            reproduction_engine=self.cascade_reproduction_engine,
        )

    # Alias for compatibility
    @property
    def llm_provider(self):
        """Alias for v7_llm_provider"""
        return self.v7_llm_provider

    @cached_property
    def ast_analyzer(self):
        """Code Context: AST Analyzer (Domain Service)"""
        from apps.orchestrator.orchestrator.domain.code_context import ASTAnalyzer

        return ASTAnalyzer()

    @cached_property
    def dependency_graph_builder(self):
        """Code Context: Dependency Graph Builder (Domain Service)"""
        from apps.orchestrator.orchestrator.domain.code_context import DependencyGraphBuilder

        return DependencyGraphBuilder()

    @cached_property
    def code_embedding_service(self):
        """Code Context: Embedding Service (Infrastructure)"""
        from apps.orchestrator.orchestrator.infrastructure.code_analysis import CodeEmbeddingService

        # TF-IDF (no pretrained model)
        return CodeEmbeddingService(use_pretrained=False)
