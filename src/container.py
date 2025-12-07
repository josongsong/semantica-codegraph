"""
Dependency Injection Container

Provides lazy singleton instances of all adapters and services.
Follows Port/Adapter pattern with constructor injection.

Usage:
    from src.container import container

    # Access services
    result = container.indexing_service.index_repo_full(...)

    # Access adapters
    docs = container.qdrant.search(...)

    # V2: Access contexts
    usecase = container.contexts.analysis_indexing.index_full_usecase
"""

from functools import cached_property
from typing import TYPE_CHECKING

from src.common.factory import weak_cached_factory
from src.common.observability import get_logger
from src.common.types import GraphStoreFactory, RepoMapStoreFactory
from src.config import settings
from src.infra.config.profiles import get_profile_config

# Optional: agent_automation (v7로 대체됨)
try:
    from src.contexts.agent_automation.infrastructure.di import AgentContainer, IndexingContainerFactory

    HAS_AGENT_AUTOMATION = True
except ImportError:
    HAS_AGENT_AUTOMATION = False
    AgentContainer = None
    IndexingContainerFactory = None

from src.contexts.analysis_indexing.infrastructure.di import IndexingContainer
from src.contexts.code_foundation.infrastructure.di import FoundationContainer
from src.contexts.multi_index.infrastructure.di import IndexContainer
from src.contexts.retrieval_search.infrastructure.di import RetrieverContainer
from src.contexts.session_memory.infrastructure.di import MemoryContainer
from src.infra.di import InfraContainer

logger = get_logger(__name__)
if TYPE_CHECKING:
    try:
        from src.contexts.agent_automation.infrastructure.orchestrator import AgentOrchestrator
    except ImportError:
        AgentOrchestrator = None


class Container:
    """
    Application-wide dependency injection container.

    All dependencies are lazy-loaded as singletons using @cached_property.
    Container is the ONLY place where concrete implementations are created.

    Infrastructure adapters are delegated to InfraContainer.
    """

    def __init__(self):
        """Initialize container with sub-containers."""
        # 프로파일 설정 로드
        self._profile = get_profile_config()

        self._infra = InfraContainer(settings)
        self._foundation = FoundationContainer(settings, self._infra)
        self._index = IndexContainer(settings, self._infra, self._foundation)
        self._memory = MemoryContainer(settings, self._infra)

        # Lazy-initialized containers (no circular dependencies with factory pattern)
        self.__retriever: RetrieverContainer | None = None
        self.__indexing: IndexingContainer | None = None
        self.__agent: AgentContainer | None = None

    @property
    def _retriever(self) -> RetrieverContainer:
        """
        Lazy-initialized RetrieverContainer.

        Uses factory function for repomap_store to avoid circular dependency.
        Factory is safe: raises on failure, returns None on optional failure.
        """
        if self.__retriever is None:
            # Create weak + cached factory (no circular reference!)
            repomap_factory: RepoMapStoreFactory = weak_cached_factory(
                obj=self,
                accessor=lambda c: c.repomap_store,
                name="repomap_store",
            )

            self.__retriever = RetrieverContainer(
                settings=settings,
                infra_container=self._infra,
                index_container=self._index,
                foundation_container=self._foundation,
                repomap_store_factory=repomap_factory,
            )
        return self.__retriever

    @property
    def _indexing(self) -> IndexingContainer:
        """
        Lazy-initialized IndexingContainer.

        Uses factory functions for graph_store and repomap_store to avoid circular dependency.
        No longer passes entire Container (self).
        Factories include error handling and validation.
        """
        if self.__indexing is None:
            # Create weak + cached factories (no circular reference!)
            graph_factory: GraphStoreFactory = weak_cached_factory(
                obj=self,
                accessor=lambda c: c.graph_store,
                name="graph_store",
            )

            repomap_factory: RepoMapStoreFactory = weak_cached_factory(
                obj=self,
                accessor=lambda c: c.repomap_store,
                name="repomap_store",
            )

            # Pyright factory는 파라미터가 필요하므로 일반 lambda
            # (각 호출마다 다른 root 전달)
            def pyright_factory(root):
                return self.create_pyright_daemon(root)

            self.__indexing = IndexingContainer(
                settings=settings,
                infra_container=self._infra,
                index_container=self._index,
                foundation_container=self._foundation,
                graph_store_factory=graph_factory,
                repomap_store_factory=repomap_factory,
                pyright_daemon_factory=pyright_factory,
            )
        return self.__indexing

    @property
    def _agent(self) -> AgentContainer:
        """
        Lazy-initialized AgentContainer (optional, legacy).

        Uses factory function for indexing_container to avoid circular dependency.
        Factory is optional and handles None gracefully.

        Note: v7 Agent는 v7_agent_orchestrator 사용 권장.
        """
        if not HAS_AGENT_AUTOMATION:
            logger.warning("AgentContainer not available. Use v7_agent_orchestrator instead.")
            return None

        if self.__agent is None:
            # Create weak + cached factory (no circular reference!)
            indexing_factory: IndexingContainerFactory = weak_cached_factory(
                obj=self,
                accessor=lambda c: c._indexing,
                name="indexing_container",
            )

            self.__agent = AgentContainer(
                settings=settings,
                infra_container=self._infra,
                index_container=self._index,
                memory_container=self._memory,
                indexing_container_factory=indexing_factory,
            )
        return self.__agent

    # ========================================================================
    # Infrastructure Adapters (delegated to InfraContainer)
    # ========================================================================

    @property
    def qdrant(self):
        """Qdrant vector store adapter."""
        return self._infra.qdrant

    @property
    def memgraph(self):
        """Memgraph graph database adapter."""
        return self._infra.memgraph

    @property
    def postgres(self):
        """PostgreSQL database adapter."""
        return self._infra.postgres

    @property
    def redis(self):
        """Redis cache adapter."""
        return self._infra.redis

    @property
    def llm(self):
        """LLM provider adapter (Ollama)."""
        return self._infra.llm

    @property
    def ollama(self):
        """Ollama adapter (alias for llm)."""
        return self._infra.ollama

    @property
    def qdrant_async(self):
        """Async Qdrant client for vector operations."""
        return self._infra.qdrant_async

    @cached_property
    def graph_store(self):
        """Graph store (Memgraph with optional 3-tier caching)."""
        base_store = self.memgraph

        # 3-tier caching이 활성화되면 래핑
        if settings.cache.enable_three_tier:
            from src.infra.graph.cached_store import CachedGraphStore

            return CachedGraphStore(
                graph_store=base_store,
                redis_client=self.redis,  # Pass RedisAdapter directly (has async get/set)
                l1_node_maxsize=settings.cache.l1_graph_node_maxsize,
                l1_relation_maxsize=settings.cache.l1_graph_relation_maxsize,
                ttl=settings.cache.graph_ttl,
            )

        return base_store

    # ========================================================================
    # Index Adapters (delegated to IndexContainer)
    # ========================================================================

    @property
    def lexical_index(self):
        """Lexical search index (Zoekt)."""
        return self._index.lexical_index

    @property
    def vector_index(self):
        """Vector search index (Qdrant)."""
        return self._index.vector_index

    @property
    def symbol_index(self):
        """Symbol search index (Memgraph)."""
        return self._index.symbol_index

    @property
    def fuzzy_index(self):
        """Fuzzy search index (PostgreSQL trigram)."""
        return self._index.fuzzy_index

    @property
    def domain_index(self):
        """Domain/documentation search index."""
        return self._index.domain_index

    @property
    def indexing_service(self):
        """Indexing service orchestrating all index types."""
        service = self._index.indexing_service

        # Lazy 주입: IndexingOrchestrator (순환 참조 방지)
        if service.indexing_orchestrator is None:
            try:
                service.set_indexing_orchestrator(self.indexing_orchestrator)
            except Exception as e:
                logger.debug(f"IndexingOrchestrator not available: {e}")

        return service

    @property
    def search_service(self):
        """Unified search service (alias for indexing_service)."""
        return self._index.search_service

    # ========================================================================
    # Retriever Components (delegated to RetrieverContainer)
    # ========================================================================

    @property
    def retriever_v3_orchestrator(self):
        """Retriever V3 orchestrator with async parallel search."""
        return self._retriever.v3_orchestrator

    @property
    def retriever_v3_service(self):
        """Retriever V3 service with L2 Redis caching."""
        return self._retriever.v3_service

    @property
    def retriever_service(self):
        """Retriever service coordinating complete retrieval pipeline."""
        return self._retriever.service

    @property
    def intent_analyzer(self):
        """Intent analyzer for query classification."""
        return self._retriever.intent_analyzer

    @property
    def scope_selector(self):
        """Scope selector for RepoMap-based search scoping."""
        return self._retriever.scope_selector

    @property
    def multi_index_orchestrator(self):
        """Multi-index search orchestrator."""
        return self._retriever.multi_index_orchestrator

    @property
    def fusion_engine(self):
        """Fusion engine for multi-index result combination."""
        return self._retriever.fusion_engine

    @property
    def context_builder(self):
        """Context builder for LLM context generation."""
        return self._retriever.context_builder

    @property
    def lexical_client(self):
        """Lexical index client wrapper."""
        return self._retriever.lexical_client

    @property
    def vector_client(self):
        """Vector index client wrapper."""
        return self._retriever.vector_client

    @property
    def symbol_client(self):
        """Symbol index client wrapper."""
        return self._retriever.symbol_client

    @property
    def graph_expansion_client(self):
        """Graph expansion client for flow tracing."""
        return self._retriever.graph_expansion_client

    @property
    def search_logger(self):
        """Search logger for ML tuning."""
        return self._retriever.search_logger

    # ========================================================================
    # RepoMap Components
    # ========================================================================

    @cached_property
    def repomap_store(self):
        """RepoMap persistent storage (JSON file with in-memory cache)."""
        from src.contexts.repo_structure.infrastructure.storage_json import JsonFileRepoMapStore

        return JsonFileRepoMapStore(
            base_dir=settings.repomap_storage_dir,
        )

    @cached_property
    def repomap_builder(self):
        """RepoMap builder service."""
        from src.contexts.repo_structure.infrastructure.builder import RepoMapBuilder

        return RepoMapBuilder(
            store=self.repomap_store,
            llm=self.llm,
            chunk_store=self.chunk_store,
        )

    # ========================================================================
    # Foundation Components (delegated to FoundationContainer)
    # ========================================================================

    @property
    def chunk_store(self):
        """Chunk storage (PostgreSQL with optional 3-tier caching)."""
        return self._foundation.chunk_store

    @cached_property
    def overlay_chunk_store(self):
        """Overlay chunk store (in-memory, IDE integration)."""
        from src.contexts.code_foundation.infrastructure.chunk.overlay_store import OverlayChunkStore

        return OverlayChunkStore()

    @cached_property
    def chunk_merger(self):
        """Chunk merger (overlay + base)."""
        from src.contexts.code_foundation.infrastructure.chunk.merger import ChunkMerger

        return ChunkMerger()

    @property
    def postgres_store(self):
        """PostgreSQL store (alias for postgres)."""
        return self._foundation.postgres_store

    @property
    def pyright_daemon(self):
        """Global Pyright daemon (singleton)."""
        return self._foundation.pyright_daemon

    @property
    def semantic_snapshot_store(self):
        """Semantic snapshot store (RFC-023)."""
        return self._foundation.semantic_snapshot_store

    def create_semantic_ir_builder_with_pyright(self, project_root):
        """Create a Pyright-enabled semantic IR builder for a specific project."""
        return self._foundation.create_semantic_ir_builder_with_pyright(project_root)

    def create_pyright_daemon(self, project_root):
        """Create a Pyright daemon for a specific project."""
        return self._foundation.create_pyright_daemon(project_root)

    # ========================================================================
    # Agent System (Legacy - delegated to AgentContainer)
    # ========================================================================

    @property
    def agent_orchestrator(self):
        """
        Singleton AgentOrchestrator (legacy, for backward compatibility).

        Note: v7_agent_orchestrator 사용 권장.
        """
        if not HAS_AGENT_AUTOMATION:
            logger.warning("Legacy agent_orchestrator not available. Use v7_agent_orchestrator instead.")
            return None
        return self._agent.orchestrator

    def create_agent_orchestrator(
        self, project_id: str = "default", repo_id: str = "default", snapshot_id: str | None = None
    ) -> "AgentOrchestrator":
        """
        Create a new AgentOrchestrator instance (legacy factory method).

        Note: v7_agent_orchestrator 사용 권장.
        """
        if not HAS_AGENT_AUTOMATION:
            logger.warning("Legacy create_agent_orchestrator not available. Use v7_agent_orchestrator instead.")
            return None
        return self._agent.create_orchestrator(project_id=project_id, repo_id=repo_id, snapshot_id=snapshot_id)

    # ========================================================================
    # v7 Agent System (Port/Adapter 기반)
    # ========================================================================

    @cached_property
    def v7_llm_provider(self):
        """v7 LLM Provider (LiteLLM)"""
        import os

        from src.agent.adapters.llm.litellm_adapter import LiteLLMProviderAdapter

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
            from src.agent.adapters.sandbox.e2b_adapter import E2BSandboxAdapter, E2BSandboxConfig
            from src.agent.adapters.sandbox.security import SecurityLevel, SecurityPolicy

            config = E2BSandboxConfig(
                api_key=e2b_api_key,
                security_policy=SecurityPolicy.for_level(SecurityLevel.MEDIUM),
                timeout_sec=30,
            )
            return E2BSandboxAdapter(config=config)
        else:
            # Fallback: Local Sandbox
            from src.agent.adapters.sandbox.stub_sandbox import LocalSandboxAdapter

            logger.warning("E2B_API_KEY not found, using LocalSandboxAdapter")
            return LocalSandboxAdapter()

    @cached_property
    def v7_guardrail_validator(self):
        """v7 Guardrail Validator (Pydantic)"""
        from src.agent.adapters.guardrail.pydantic_validator import PydanticValidatorAdapter

        return PydanticValidatorAdapter()

    @cached_property
    def v7_vcs_applier(self):
        """v7 VCS Applier (GitPython)"""
        from src.agent.adapters.vcs.gitpython_adapter import GitPythonVCSAdapter

        return GitPythonVCSAdapter(".")

    @cached_property
    def v7_workflow_engine(self):
        """v7 Workflow Engine (LangGraph)"""
        from src.agent.adapters.workflow.langgraph_adapter import LangGraphWorkflowAdapter

        return LangGraphWorkflowAdapter()

    @cached_property
    def v7_context_manager(self):
        """v7 Context Manager"""
        from src.agent.context_manager import ContextManager

        return ContextManager()

    @cached_property
    def v7_experience_store(self):
        """v7 Experience Store"""
        from src.agent.experience_store import ExperienceStore

        return ExperienceStore()

    @cached_property
    def v7_incremental_workflow(self):
        """v7 Incremental Workflow Manager (SOTA급 - 기존 인프라 활용)"""
        from src.agent.domain.incremental_workflow import IncrementalCache, IncrementalWorkflow

        return IncrementalWorkflow(
            change_detector=self.change_detector,  # ✅ 기존 SOTA
            graph_impact_analyzer=self._graph_impact_analyzer,  # ✅ 기존 SOTA
            graph_store=self.graph_store,  # ✅ Memgraph
            cache=IncrementalCache(redis_client=self.redis),  # ✅ Redis 캐시
        )

    @cached_property
    def _graph_impact_analyzer(self):
        """Graph Impact Analyzer (기존 SOTA 인프라)"""
        try:
            from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer

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
        from src.agent.domain.diff_manager import DiffManager

        return DiffManager(context_lines=3)

    @cached_property
    def v7_approval_manager(self):
        """v7 Approval Manager (Human-in-the-loop)"""
        from src.agent.domain.approval_manager import (
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
        from src.agent.domain.partial_committer import PartialCommitter

        return PartialCommitter(repo_path=".")

    # ======================================================================
    # v8.1 Components (Dynamic Reasoning)
    # ======================================================================

    @cached_property
    def v8_complexity_analyzer(self):
        """v8 Complexity Analyzer (Adapter)"""
        from src.agent.adapters.reasoning import RadonComplexityAnalyzer

        return RadonComplexityAnalyzer()

    @cached_property
    def v8_risk_assessor(self):
        """v8 Risk Assessor (Adapter)"""
        from src.agent.adapters.reasoning import HistoricalRiskAssessor

        return HistoricalRiskAssessor(
            experience_store=None  # TODO: Phase 3에서 Experience Store v2 연동
        )

    @cached_property
    def v8_reasoning_router(self):
        """v8 Dynamic Reasoning Router (Domain Service)"""
        from src.agent.domain.reasoning import DynamicReasoningRouter

        return DynamicReasoningRouter(
            complexity_analyzer=self.v8_complexity_analyzer,
            risk_assessor=self.v8_risk_assessor,
        )

    @cached_property
    def v8_decide_reasoning_path(self):
        """v8 Decide Reasoning Path UseCase (Application Layer)"""
        from src.agent.application.use_cases import DecideReasoningPathUseCase

        return DecideReasoningPathUseCase(
            router=self.v8_reasoning_router,
            complexity_analyzer=self.v8_complexity_analyzer,
            risk_assessor=self.v8_risk_assessor,
        )

    @cached_property
    def v8_tot_scorer(self):
        """v8 ToT Scoring Engine (Domain Service)"""
        from src.agent.domain.reasoning import ToTScoringEngine

        return ToTScoringEngine()

    @cached_property
    def v8_sandbox_executor(self):
        """v8 Sandbox Executor (Subprocess, 로컬)"""
        from src.agent.adapters.reasoning import SubprocessSandbox

        return SubprocessSandbox()

    @cached_property
    def v8_strategy_generator(self):
        """v8 Strategy Generator (LLM)"""
        from src.agent.adapters.llm.strategy_generator import StrategyGeneratorFactory

        # OpenAI API Key 있으면 LLM 사용
        return StrategyGeneratorFactory.create(use_llm=True)

    @cached_property
    def v8_tot_executor(self):
        """v8 ToT Executor (LangGraph + LLM)"""
        from src.agent.adapters.reasoning import LangGraphToTExecutor

        return LangGraphToTExecutor(
            llm_provider=self.v8_strategy_generator,  # LLM 연동!
            sandbox_executor=self.v8_sandbox_executor,
            max_strategies=5,
            use_langgraph=True,  # LangGraph 활성화
        )

    @cached_property
    def v8_execute_tot(self):
        """v8 Execute ToT UseCase (Application Layer)"""
        from src.agent.application.use_cases import ExecuteToTUseCase

        return ExecuteToTUseCase(
            tot_executor=self.v8_tot_executor,
            tot_scorer=self.v8_tot_scorer,
        )

    @cached_property
    def v8_graph_analyzer(self):
        """v8 Graph Analyzer (Adapter)"""
        from src.agent.adapters.reasoning import SimpleGraphAnalyzer

        return SimpleGraphAnalyzer()

    @cached_property
    def v8_reflection_judge(self):
        """v8 Self-Reflection Judge (Domain Service)"""
        from src.agent.domain.reasoning import SelfReflectionJudge

        return SelfReflectionJudge()

    @cached_property
    def v8_experience_repository(self):
        """v8 Experience Repository (SOTA: Multi-Backend)"""
        import os

        # Profile에 따라 Backend 선택
        profile = os.getenv("SEMANTICA_PROFILE", "local")

        if profile in ["prod", "production", "cloud"]:
            # Production: PostgreSQL
            try:
                from src.agent.infrastructure.experience_repository import ExperienceRepository

                db_session = self.postgres if hasattr(self, "postgres") else None
                return ExperienceRepository(db_session=db_session)
            except Exception as e:
                logger.warning(f"PostgreSQL failed, falling back to SQLite: {e}")

        # Local/Dev: SQLite (SOTA!)
        from src.agent.infrastructure.experience_repository_sqlite import ExperienceRepositorySQLite

        return ExperienceRepositorySQLite()

    @cached_property
    def v7_soft_lock_manager(self):
        """v7 Soft Lock Manager (Multi-Agent Lock 관리)"""
        from src.agent.domain.soft_lock_manager import SoftLockManager

        # 프로파일에 따라 Redis 사용 여부 결정
        redis_client = None
        if self._profile.should_use_redis():
            redis_client = self.redis if hasattr(self, "redis") else None

        return SoftLockManager(redis_client=redis_client)

    @cached_property
    def v7_conflict_resolver(self):
        """v7 Conflict Resolver (Multi-Agent 충돌 해결)"""
        from src.agent.domain.conflict_resolver import ConflictResolver

        return ConflictResolver(
            vcs_applier=self.v7_vcs_applier,
        )

    @cached_property
    def v7_agent_coordinator(self):
        """v7 Agent Coordinator (Multi-Agent 조율)"""
        from src.agent.domain.agent_coordinator import AgentCoordinator

        return AgentCoordinator(
            lock_manager=self.v7_soft_lock_manager,
            conflict_resolver=self.v7_conflict_resolver,
            orchestrator_factory=lambda: self.v7_agent_orchestrator,
        )

    @cached_property
    def v7_metrics_collector(self):
        """v7 Metrics Collector (Prometheus)"""
        from src.agent.adapters.monitoring import PrometheusMetricsAdapter

        return PrometheusMetricsAdapter()  # Uses global collector

    @cached_property
    def v7_health_checker(self):
        """v7 Health Checker (시스템 컴포넌트 상태)"""
        from src.agent.adapters.monitoring import HealthCheckAdapter

        return HealthCheckAdapter(
            postgres_client=self.postgres,
            redis_client=self.redis,
            qdrant_client=self.qdrant,
            memgraph_client=self.memgraph,
            llm_provider=self.v7_llm_provider,
        )

    # ========================================================================
    # v7: Performance Optimization (SOTA급)
    # ========================================================================

    @cached_property
    def v7_optimized_llm_provider(self):
        """v7 Optimized LLM Provider (SOTA급 성능 최적화)"""
        from src.agent.adapters.llm.optimized_llm_adapter import OptimizedLLMAdapter

        return OptimizedLLMAdapter(
            primary_model=settings.agent_llm_model if hasattr(settings, "agent_llm_model") else "gpt-4o-mini",
            fallback_models=["gpt-4o", "gpt-4"],
            timeout=60,
            max_requests_per_second=10.0,
            max_concurrent=5,
            enable_cache=True,
            cache_ttl=3600,
            redis_client=self.redis,
        )

    @cached_property
    def v7_advanced_cache(self):
        """v7 Advanced Multi-tier Cache (L1: Local, L2: Redis)"""
        from src.agent.infrastructure.cache.advanced_cache import AdvancedCache

        return AdvancedCache(
            redis_client=self.redis,
            local_max_size=1000,
            local_max_bytes=100 * 1024 * 1024,  # 100MB
            default_ttl=3600,
            compression_threshold=1024,  # 1KB
            enable_bloom_filter=True,
        )

    @cached_property
    def v7_performance_monitor(self):
        """v7 Performance Monitor (Request Tracing, Latency, Throughput)"""
        from src.agent.infrastructure.performance_monitor import PerformanceMonitor

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
        from src.agent.infrastructure.profiler import Profiler

        return Profiler(
            enable_cpu=True,
            enable_memory=True,
            enable_async=True,
        )

    @cached_property
    def v7_bottleneck_detector(self):
        """v7 Bottleneck Detector (자동 병목 감지)"""
        from src.agent.infrastructure.profiler import BottleneckDetector

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
        from src.agent.orchestrator.v7_orchestrator import AgentOrchestrator as V7Orchestrator

        return V7Orchestrator(
            workflow_engine=self.v7_workflow_engine,
            llm_provider=self.v7_llm_provider,
            sandbox_executor=self.v7_sandbox_executor,
            guardrail_validator=self.v7_guardrail_validator,
            vcs_applier=self.v7_vcs_applier,
            # 기존 시스템 통합
            retriever_service=self.retriever_service,
            chunk_store=self.chunk_store,
            memory_system=self.memory_system,
            # Incremental Execution
            incremental_workflow=self.v7_incremental_workflow,
            # Human-in-the-Loop
            approval_manager=self.v7_approval_manager,
            diff_manager=self.v7_diff_manager,
            partial_committer=self.v7_partial_committer,
        )

    # ========================================================================
    # Indexing System (delegated to IndexingContainer)
    # ========================================================================

    @property
    def file_hash_store(self):
        """File hash store for incremental change detection."""
        return self._indexing.file_hash_store

    @property
    def indexing_metadata_store(self):
        """Indexing metadata store for mode tracking."""
        return self._indexing.metadata_store

    @property
    def snapshot_gc(self):
        """Snapshot garbage collector."""
        return self._indexing.snapshot_gc

    @property
    def change_detector(self):
        """Change detector for incremental indexing."""
        return self._indexing.change_detector

    @property
    def scope_expander(self):
        """Scope expander for mode-based file selection."""
        return self._indexing.scope_expander

    @property
    def mode_manager(self):
        """Mode manager for indexing mode selection."""
        return self._indexing.mode_manager

    @property
    def mode_controller(self):
        """Mode controller for event-driven indexing."""
        return self._indexing.mode_controller

    @property
    def background_scheduler(self):
        """Background scheduler for idle-triggered deep indexing."""
        return self._indexing.background_scheduler

    @property
    def file_watcher_service(self):
        """File watcher service for real-time file system monitoring."""
        return self._indexing.file_watcher_service

    @property
    def schema_version_manager(self):
        """Schema version manager for repair mode."""
        return self._indexing.schema_version_manager

    @property
    def index_job_orchestrator(self):
        """Job-based indexing orchestrator with distributed locking."""
        return self._indexing.job_orchestrator

    @cached_property
    def incremental_indexing_service(self):
        """
        증분 인덱싱 서비스 (Agent → Indexing 연결).

        Note: PostgresStore는 사용 전에 초기화 필요:
            await container.postgres_store.initialize()
        """
        return self.contexts.agent_automation.incremental_indexing_adapter

    @cached_property
    def repo_registry(self):
        """Repository Registry (Multi-repo 지원)"""
        return self.contexts.agent_automation.repo_registry

    @property
    def indexing_orchestrator_new(self):
        """IndexingOrchestrator with all required dependencies."""
        return self._indexing.orchestrator

    @property
    def indexing_orchestrator(self):
        """Alias for indexing_orchestrator_new for backward compatibility."""
        return self._indexing.orchestrator

    # ========================================================================
    # Memory System (delegated to MemoryContainer)
    # ========================================================================

    @property
    def memory_embedding_provider(self):
        """Embedding provider for memory system."""
        return self._memory.embedding_provider

    @property
    def memory_postgres_store(self):
        """PostgreSQL memory store for structured data."""
        return self._memory.postgres_store

    @property
    def memory_embedding_store(self):
        """Qdrant embedding store for semantic search."""
        return self._memory.embedding_store

    @property
    def memory_system(self):
        """Production memory system with all backends."""
        return self._memory.system

    async def initialize_memory_system(self) -> None:
        """Initialize memory system (create tables, collections)."""
        await self._memory.initialize()

    def initialize_pyright_daemon(self) -> None:
        """Initialize Pyright daemon (starts pyright-langserver)."""
        self._foundation.initialize_pyright_daemon()

    def create_working_memory(self, session_id: str | None = None):
        """Create a new working memory for an agent session."""
        return self._memory.create_working_memory(session_id=session_id)

    # ========================================================================
    # Lifecycle Management
    # ========================================================================

    async def startup(self) -> None:
        """
        Initialize all infrastructure adapters.

        This should be called during application startup (e.g., FastAPI lifespan).

        Initializes:
        - PostgreSQL connection pool
        - Redis connection
        - Qdrant client
        - Memgraph connection

        Usage:
            container = Container()
            await container.startup()
        """
        logger.info("Initializing container infrastructure...")

        try:
            # Initialize PostgreSQL pool
            await self.postgres.initialize()
            logger.info("PostgreSQL pool initialized")

            # Initialize Redis (if it has initialization)
            if hasattr(self.redis, "initialize"):
                await self.redis.initialize()
                logger.info("Redis initialized")

            # Qdrant and Memgraph are lazy-initialized, no explicit startup needed

            logger.info("Container startup complete")
        except Exception as e:
            logger.error(f"Container startup failed: {e}", exc_info=True)
            raise

    async def shutdown(self) -> None:
        """
        Clean shutdown of all infrastructure adapters.

        This should be called during application shutdown (e.g., FastAPI lifespan).

        Closes:
        - PostgreSQL connection pool
        - Redis connection
        - Qdrant client
        - Memgraph connection

        Usage:
            await container.shutdown()
        """
        logger.info("Shutting down container infrastructure...")

        try:
            # Close PostgreSQL pool (if initialized)
            if "postgres" in self._infra.__dict__:
                await self.postgres.close()
                logger.info("PostgreSQL pool closed")

            # Close Redis (if initialized and has close method)
            if "redis" in self._infra.__dict__ and hasattr(self.redis, "close"):
                await self.redis.close()
                logger.info("Redis closed")

            # Close Qdrant (if initialized and has close method)
            if "qdrant" in self._infra.__dict__ and hasattr(self.qdrant, "close"):
                await self.qdrant.close()
                logger.info("Qdrant closed")

            # Close Memgraph (if initialized and has close method)
            if "memgraph" in self._infra.__dict__ and hasattr(self.memgraph, "close"):
                self.memgraph.close()
                logger.info("Memgraph closed")

            # L10: Shutdown 백그라운드 태스크 정리
            if hasattr(self, "incremental_indexing_service"):
                try:
                    service = self.incremental_indexing_service
                    if hasattr(service, "cancel_all_tasks"):
                        cancelled = await service.cancel_all_tasks()
                        if cancelled > 0:
                            logger.info(f"Cancelled {cancelled} background indexing tasks")
                except Exception as e:
                    logger.warning(f"Failed to cancel background tasks: {e}")

            logger.info("Container shutdown complete")
        except Exception as e:
            logger.error(f"Container shutdown error: {e}", exc_info=True)
            # Don't raise - best effort shutdown

    async def health_check(self) -> dict[str, bool]:
        """
        Check health of all infrastructure components.

        Returns:
            Dict mapping component name to health status
        """
        health = {}

        # PostgreSQL
        try:
            health["postgres"] = await self.postgres.health_check()
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            health["postgres"] = False

        # Redis
        try:
            if hasattr(self.redis, "health_check"):
                health["redis"] = await self.redis.health_check()
            else:
                health["redis"] = True  # Assume healthy if no health check
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            health["redis"] = False

        # Qdrant
        try:
            if hasattr(self.qdrant, "health_check"):
                health["qdrant"] = await self.qdrant.health_check()
            else:
                health["qdrant"] = True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            health["qdrant"] = False

        # Memgraph
        try:
            if hasattr(self.memgraph, "health_check"):
                health["memgraph"] = self.memgraph.health_check()
            else:
                health["memgraph"] = True
        except Exception as e:
            logger.error(f"Memgraph health check failed: {e}")
            health["memgraph"] = False

        return health

    # ========================================================================
    # V2: Bounded Contexts (Hybrid Context Architecture)
    # ========================================================================

    @cached_property
    def contexts(self):
        """V2 Bounded Contexts Container"""

        class ContextsContainer:
            """모든 BC Container 접근 포인트"""

            @cached_property
            def code_foundation(self):
                from src.contexts.code_foundation.di import code_foundation_container

                return code_foundation_container

            @cached_property
            def analysis_indexing(self):
                from src.contexts.analysis_indexing.di import (
                    analysis_indexing_container,
                )

                return analysis_indexing_container

            @cached_property
            def retrieval_search(self):
                from src.contexts.retrieval_search.di import retrieval_search_container

                return retrieval_search_container

            @cached_property
            def agent_automation(self):
                from src.contexts.agent_automation.di import agent_automation_container

                return agent_automation_container

            @cached_property
            def multi_index(self):
                from src.contexts.multi_index.di import multi_index_container

                return multi_index_container

        return ContextsContainer()


# Module-level singleton (eager instantiation of container itself)
container = Container()
