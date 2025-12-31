"""
Memory DI Container (SOTA Refactored)

Clean dependency injection following Hexagonal Architecture:
- All dependencies injected via ports (interfaces)
- No concrete implementations in application layer
- Lazy initialization with caching
- Thread-safe singleton management
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger

from .config import get_config

if TYPE_CHECKING:
    from codegraph_runtime.session_memory.application import (
        MemoryRetrievalService,
        SessionConsolidationService,
    )
    from codegraph_runtime.session_memory.domain.ports import (
        EmbeddingProviderPort,
        MemoryScorerPort,
    )
    from codegraph_runtime.session_memory.infrastructure.persistence import (
        EmbeddingMemoryStore,
        PostgresMemoryStore,
    )
    from codegraph_runtime.session_memory.infrastructure.production import ProductionMemorySystem
    from codegraph_runtime.session_memory.infrastructure.repositories import (
        BugPatternRepository,
        CodePatternRepository,
        CodeRuleRepository,
    )

logger = get_logger(__name__)


class MemoryContainer:
    """
    Memory system DI container.

    SOTA Features:
    - Lazy-loaded singletons via @cached_property
    - Configuration-driven initialization
    - Clean separation of ports and adapters
    - Support for both in-memory and production storage
    """

    def __init__(self, settings: Any = None, infra_container: Any = None):
        """
        Initialize memory container.

        Args:
            settings: Application settings (optional)
            infra_container: Infrastructure container for database access (optional)
        """
        self._settings = settings
        self._infra = infra_container
        self._config = get_config()

    # ========================================================================
    # Configuration
    # ========================================================================

    @property
    def config(self):
        """Get current configuration."""
        return self._config

    # ========================================================================
    # Embedding Provider (Port Implementation)
    # ========================================================================

    @cached_property
    def embedding_provider(self) -> EmbeddingProviderPort:
        """
        Embedding provider for memory system.

        Uses configuration to determine provider:
        - Production: Ollama bge-m3 (1024 dimensions)
        - Development: Mock provider

        Returns port interface, not concrete implementation.
        """
        if not self._config.episodic.enable_embeddings:
            from codegraph_runtime.session_memory.infrastructure.embeddings import (
                MockEmbeddingProvider,
            )

            return MockEmbeddingProvider(dimension=1024)

        try:
            from codegraph_runtime.session_memory.infrastructure.embeddings import (
                OllamaEmbeddingProvider,
            )

            if self._infra and hasattr(self._infra, "llm"):
                return OllamaEmbeddingProvider(adapter=self._infra.llm)
            else:
                # Standalone mode
                return OllamaEmbeddingProvider()
        except Exception as e:
            logger.warning(f"Failed to create Ollama embedding provider: {e}. Using mock.")
            from codegraph_runtime.session_memory.infrastructure.embeddings import (
                MockEmbeddingProvider,
            )

            return MockEmbeddingProvider(dimension=1024)

    # ========================================================================
    # Repositories (Port Implementations)
    # ========================================================================

    @cached_property
    def bug_pattern_repository(self) -> BugPatternRepository:
        """Repository for bug patterns."""
        from codegraph_runtime.session_memory.infrastructure.repositories import (
            BugPatternRepository,
        )

        return BugPatternRepository(max_patterns=self._config.semantic.max_bug_patterns)

    @cached_property
    def code_pattern_repository(self) -> CodePatternRepository:
        """Repository for code patterns."""
        from codegraph_runtime.session_memory.infrastructure.repositories import (
            CodePatternRepository,
        )

        return CodePatternRepository(max_patterns=self._config.semantic.max_code_patterns)

    @cached_property
    def code_rule_repository(self) -> CodeRuleRepository:
        """Repository for code rules."""
        from codegraph_runtime.session_memory.infrastructure.repositories import (
            CodeRuleRepository,
        )

        return CodeRuleRepository(
            max_rules=self._config.semantic.max_code_rules,
            min_confidence_threshold=self._config.semantic.min_pattern_confidence,
            promotion_threshold=self._config.semantic.pattern_promotion_threshold,
        )

    # ========================================================================
    # Scoring Engine
    # ========================================================================

    @cached_property
    def scorer(self) -> MemoryScorerPort:
        """Memory scoring engine (3-axis)."""
        from codegraph_runtime.session_memory.infrastructure.repositories.scoring import (
            MemoryScoringEngine,
        )

        return MemoryScoringEngine.from_config(self._config.retrieval)

    # ========================================================================
    # Storage Backends (for Production)
    # ========================================================================

    @cached_property
    def postgres_store(self) -> PostgresMemoryStore:
        """PostgreSQL memory store for structured data."""
        from codegraph_runtime.session_memory.infrastructure.persistence import (
            PostgresMemoryStore,
        )

        if self._infra and hasattr(self._infra, "postgres"):
            return PostgresMemoryStore(postgres_store=self._infra.postgres)
        else:
            raise ValueError("PostgreSQL store requires infra_container with postgres access")

    @cached_property
    def embedding_store(self) -> EmbeddingMemoryStore:
        """Qdrant embedding store for semantic search."""
        from codegraph_runtime.session_memory.infrastructure.persistence import (
            EmbeddingMemoryStore,
        )

        if self._infra and hasattr(self._infra, "qdrant"):
            return EmbeddingMemoryStore(
                qdrant_adapter=self._infra.qdrant,
                embedding_provider=self.embedding_provider,
                default_dimension=self.embedding_provider.dimension,
            )
        else:
            raise ValueError("Embedding store requires infra_container with qdrant access")

    # ========================================================================
    # Application Services
    # ========================================================================

    @cached_property
    def retrieval_service(self) -> MemoryRetrievalService:
        """
        Memory retrieval service.

        Orchestrates retrieval across all memory layers.
        """
        # Create episode repository adapter
        # (adapts postgres_store to EpisodeRepositoryPort)
        from codegraph_runtime.session_memory.adapters.postgres_adapters import (
            PostgresEpisodeRepository,
            PostgresProjectKnowledge,
        )
        from codegraph_runtime.session_memory.application import MemoryRetrievalService

        episode_repo = PostgresEpisodeRepository(self.postgres_store)

        project_knowledge = PostgresProjectKnowledge(self.postgres_store)

        return MemoryRetrievalService(
            episode_repository=episode_repo,
            bug_pattern_repository=self.bug_pattern_repository,
            code_rule_repository=self.code_rule_repository,
            project_knowledge=project_knowledge,
            embedding_provider=self.embedding_provider,
            scorer=self.scorer,
        )

    @cached_property
    def consolidation_service(self) -> SessionConsolidationService:
        """
        Session consolidation service.

        Handles working memory → long-term memory consolidation.
        """
        from codegraph_runtime.session_memory.adapters.postgres_adapters import (
            PostgresEpisodeRepository,
            PostgresProjectKnowledge,
        )
        from codegraph_runtime.session_memory.application import SessionConsolidationService

        episode_repo = PostgresEpisodeRepository(self.postgres_store)
        project_knowledge = PostgresProjectKnowledge(self.postgres_store)

        return SessionConsolidationService(
            episode_repository=episode_repo,
            bug_pattern_repository=self.bug_pattern_repository,
            code_rule_repository=self.code_rule_repository,
            project_knowledge=project_knowledge,
            embedding_provider=self.embedding_provider,
        )

    # ========================================================================
    # Production Memory System (Legacy Support)
    # ========================================================================

    @cached_property
    def system(self) -> ProductionMemorySystem:
        """
        Production memory system with all backends.

        Legacy interface for backwards compatibility.
        Prefer using retrieval_service and consolidation_service directly.
        """
        from codegraph_runtime.session_memory.infrastructure.production import (
            ProductionMemorySystem,
        )

        return ProductionMemorySystem(
            postgres_store=self.postgres_store,
            embedding_store=self.embedding_store,
        )

    # ========================================================================
    # Lifecycle Methods
    # ========================================================================

    async def initialize(self) -> None:
        """Initialize all storage backends."""
        if self._config.storage.storage_type == "postgres":
            await self.postgres_store.initialize()

        if self._config.episodic.enable_embeddings:
            try:
                await self.embedding_store.initialize()
            except Exception as e:
                logger.warning(f"Failed to initialize embedding store: {e}")

        logger.info(
            "Memory container initialized",
            storage_type=self._config.storage.storage_type,
            embeddings_enabled=self._config.episodic.enable_embeddings,
        )

    async def close(self) -> None:
        """Close all connections."""
        try:
            if hasattr(self, "_postgres_store"):
                await self.postgres_store.close()
            if hasattr(self, "_embedding_store"):
                await self.embedding_store.close()
        except Exception as e:
            logger.warning(f"Error closing memory container: {e}")

    def create_working_memory(self, session_id: str | None = None):
        """
        Create a new working memory for an agent session.

        Args:
            session_id: Optional session ID

        Returns:
            WorkingMemoryManager instance
        """
        from codegraph_runtime.session_memory.infrastructure.working import (
            WorkingMemoryManager,
        )

        return WorkingMemoryManager(
            session_id=session_id,
            config=self._config.working,
        )


# ========================================================================
# Factory Functions
# ========================================================================


def create_memory_container(
    settings: Any = None,
    infra_container: Any = None,
) -> MemoryContainer:
    """
    Factory function to create memory container.

    Args:
        settings: Application settings
        infra_container: Infrastructure container

    Returns:
        Configured MemoryContainer
    """
    return MemoryContainer(settings=settings, infra_container=infra_container)


def create_in_memory_container() -> MemoryContainer:
    """
    Create memory container with in-memory storage only.

    Useful for testing and development without external dependencies.
    """
    from .config import MemorySystemConfig, set_context_config

    # Set development config for this context
    config = MemorySystemConfig.for_development()
    set_context_config(config)

    return MemoryContainer()
