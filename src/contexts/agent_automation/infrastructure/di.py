"""
Agent DI Registration

Registers agent system components:
- AgentFSM with mode handlers
- AgentOrchestrator (singleton and factory)
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cached_property
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.agent_automation.infrastructure.fsm import AgentFSM
    from src.contexts.agent_automation.infrastructure.orchestrator import AgentOrchestrator
    from src.contexts.analysis_indexing.infrastructure.di import IndexingContainer

from src.common.factory_helpers import safe_factory_call, validate_factory
from src.common.observability import get_logger

# Type alias for IndexingContainer factory
IndexingContainerFactory = Callable[[], "IndexingContainer"]

logger = get_logger(__name__)


class AgentContainer:
    """
    Agent system container.

    Manages AgentFSM and AgentOrchestrator creation.
    """

    def __init__(
        self,
        settings,
        infra_container,
        index_container,
        memory_container,
        indexing_container_factory: IndexingContainerFactory | None = None,
    ):
        """
        Args:
            settings: Application settings
            infra_container: InfraContainer for LLM, Memgraph
            index_container: IndexContainer for symbol_index
            memory_container: MemoryContainer for memory system
            indexing_container_factory: Factory function to get IndexingContainer (optional, lazy)

        Raises:
            TypeError: If factory function is not callable
        """
        # Validate factory (optional)
        validate_factory(indexing_container_factory, "indexing_container_factory", required=False)

        self._settings = settings
        self._infra = infra_container
        self._index = index_container
        self._memory = memory_container
        self._indexing_factory = indexing_container_factory

    # ========================================================================
    # Phase 0/1/2/3 Components
    # ========================================================================

    @cached_property
    def patch_store(self):
        """Patch store for patch queue (P0-2)."""
        from src.contexts.agent_automation.infrastructure.queue.store import PostgresPatchStore

        return PostgresPatchStore(db_pool=self._infra.postgres)

    @cached_property
    def patch_queue(self):
        """Patch queue for patch proposals (P0-2)."""
        from src.contexts.agent_automation.infrastructure.queue.patch_queue import PatchQueue

        return PatchQueue(store=self.patch_store)

    @cached_property
    def workspace_manager(self):
        """Workspace manager for git worktree isolation (P1-1)."""
        from pathlib import Path

        from src.contexts.agent_automation.infrastructure.workspace.manager import WorkspaceManager

        repo_path = Path(self._settings.workspace_path)
        return WorkspaceManager(
            repo_path=repo_path,
            max_sessions=10,
            session_ttl=3600,
        )

    @cached_property
    def apply_gateway(self):
        """Apply gateway for single writer pattern (P0-3)."""
        from pathlib import Path

        from src.contexts.agent_automation.infrastructure.apply_gateway.gateway import ApplyGateway

        return ApplyGateway(
            patch_queue=self.patch_queue,
            base_path=Path(self._settings.workspace_path),
            enable_formatting=True,
            enable_conflict_resolution=True,
            enable_testing=False,  # 기본 비활성화
            enable_lsp=False,  # 기본 비활성화
            enable_pre_commit=False,  # 기본 비활성화
            enable_approval=False,  # 기본 비활성화
            workspace_manager=self.workspace_manager,
        )

    @cached_property
    def rate_limiter(self):
        """Rate limiter for LLM API calls (P2-5)."""
        from src.contexts.agent_automation.infrastructure.rate_limit import ProviderQuota, RateLimiter

        # Default quota (Ollama)
        quota = ProviderQuota(
            provider="ollama",
            requests_per_minute=1000,
            concurrent_requests=5,
        )
        return RateLimiter(quota=quota)

    @cached_property
    def context_builder(self):
        """Automatic context builder (P3-1)."""
        from pathlib import Path

        from src.contexts.agent_automation.infrastructure.context.builder import AutoContextBuilder

        return AutoContextBuilder(
            project_root=Path(self._settings.workspace_path),
            max_tokens=100000,
            include_tests=True,
            include_docs=True,
        )

    @cached_property
    def prompt_cache(self):
        """Prompt cache for LLM responses (P3-2)."""
        from src.contexts.agent_automation.infrastructure.cache.prompt_cache import PromptCache
        from src.contexts.agent_automation.infrastructure.cache.store import RedisCacheStore

        cache_store = RedisCacheStore(
            redis_adapter=self._infra.redis,  # RedisAdapter 인스턴스
            ttl=3600,
        )
        return PromptCache(store=cache_store, enable_cache=True)

    @cached_property
    def repo_registry(self):
        """Repository registry for repo_id → path mapping."""
        from src.contexts.agent_automation.infrastructure.repo_registry import RepoRegistry

        # Default workspace path for backward compatibility (단일 repo)
        return RepoRegistry(default_workspace_path=self._settings.workspace_path)

    @cached_property
    def indexing_adapter(self):
        """Incremental indexing adapter for auto-reindexing."""
        from src.contexts.agent_automation.infrastructure.indexing_adapter import IncrementalIndexingAdapter

        if not self._indexing_factory:
            logger.debug("indexing_container_not_available")
            return None

        try:
            indexing_container = safe_factory_call(
                self._indexing_factory,
                factory_name="indexing_container_factory",
                default=None,
            )

            if indexing_container is None:
                logger.warning("indexing_container_factory returned None")
                return None

            return IncrementalIndexingAdapter(
                job_orchestrator=indexing_container.job_orchestrator,
                repo_registry=self.repo_registry,  # RepoRegistry 사용
            )
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"indexing_adapter_init_failed: {e}")
            return None

    # ========================================================================
    # Dependency Checking
    # ========================================================================

    def _check_dependencies(self) -> tuple[bool, bool]:
        """
        Check availability of agent dependencies.

        Returns:
            Tuple of (has_symbol_index, has_llm)
        """
        try:
            has_symbol_index = self._index.symbol_index is not None
        except (ConnectionError, TimeoutError, RuntimeError) as e:
            logger.debug(f"Symbol index not available: {e}")
            has_symbol_index = False

        try:
            has_llm = self._infra.llm is not None
        except (ConnectionError, TimeoutError, RuntimeError) as e:
            logger.debug(f"LLM not available: {e}")
            has_llm = False

        return has_symbol_index, has_llm

    # ========================================================================
    # FSM Creation
    # ========================================================================

    def _create_fsm(self, project_id: str = "default") -> AgentFSM:
        """
        Create and configure AgentFSM with mode handlers.

        Uses ModeRegistry for decoupled mode instantiation.

        Args:
            project_id: Project ID for memory operations

        Returns:
            Configured AgentFSM instance with memory system
        """
        from src.contexts.agent_automation.infrastructure.fsm import AgentFSM
        from src.contexts.agent_automation.infrastructure.modes import mode_registry
        from src.contexts.agent_automation.infrastructure.types import AgentMode

        # Create FSM with memory system
        try:
            memory = self._memory.system
        except (ConnectionError, TimeoutError, RuntimeError) as e:
            logger.debug(f"Memory system not available: {e}")
            memory = None

        fsm = AgentFSM(memory_system=memory, project_id=project_id)

        # Check dependencies
        has_symbol_index, has_llm = self._check_dependencies()

        # Prepare dependencies for mode creation
        deps = {
            "llm_client": self._infra.llm if has_llm else None,
            "graph_client": self._infra.memgraph,
            "symbol_index": self._index.symbol_index if has_symbol_index else None,
        }

        # Phase 0 modes (Core)
        phase0_modes = [
            AgentMode.CONTEXT_NAV,
            AgentMode.IMPLEMENTATION,
            AgentMode.DEBUG,
            AgentMode.TEST,
            AgentMode.DOCUMENTATION,
        ]

        use_simple = not (has_symbol_index and has_llm)
        for mode in phase0_modes:
            handler = mode_registry.create(mode, deps=deps, simple=use_simple)
            if handler:
                fsm.register(mode, handler)

        # Phase 1 modes (Advanced - require LLM)
        if has_llm:
            phase1_modes = [
                AgentMode.DESIGN,
                AgentMode.QA,
                AgentMode.REFACTOR,
                AgentMode.MULTI_FILE_EDITING,
                AgentMode.GIT_WORKFLOW,
                AgentMode.IMPACT_ANALYSIS,
            ]
            for mode in phase1_modes:
                handler = mode_registry.create(mode, deps=deps)
                if handler:
                    fsm.register(mode, handler)

        return fsm

    # ========================================================================
    # Orchestrator
    # ========================================================================

    @cached_property
    def orchestrator(self) -> AgentOrchestrator:
        """
        Singleton AgentOrchestrator (for backward compatibility).

        Note: For session-based usage, use create_orchestrator() instead.
        """
        from src.contexts.agent_automation.infrastructure.orchestrator import AgentOrchestrator

        fsm = self._create_fsm()

        return AgentOrchestrator(
            fsm=fsm,
            approval_callback=None,
            base_path=self._settings.workspace_path,
            auto_approve=self._settings.agent_enable_auto_approve,
            indexing_port=self.indexing_adapter,
        )

    def create_orchestrator(
        self, project_id: str = "default", repo_id: str = "default", snapshot_id: str | None = None
    ) -> AgentOrchestrator:
        """
        Create a new AgentOrchestrator instance (factory method).

        Creates a fresh instance every time. Use for session-based or
        request-based orchestrators to avoid state sharing.

        Args:
            project_id: Project ID for memory operations
            repo_id: Repository ID for indexing
            snapshot_id: Snapshot ID for indexing (branch/worktree)

        Returns:
            New AgentOrchestrator instance with fresh FSM and context
        """
        from src.contexts.agent_automation.infrastructure.orchestrator import AgentOrchestrator

        fsm = self._create_fsm(project_id=project_id)

        return AgentOrchestrator(
            fsm=fsm,
            approval_callback=None,
            base_path=self._settings.workspace_path,
            auto_approve=self._settings.agent_enable_auto_approve,
            indexing_port=self.indexing_adapter,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
        )
