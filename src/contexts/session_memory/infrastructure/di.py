"""
Memory DI Registration

Registers memory system components:
- Embedding provider (Ollama/Mock)
- PostgreSQL memory store
- Qdrant embedding store
- Production memory system
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from src.common.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.session_memory.infrastructure.persistence import EmbeddingMemoryStore, PostgresMemoryStore
    from src.contexts.session_memory.infrastructure.production import ProductionMemorySystem

logger = get_logger(__name__)


class MemoryContainer:
    """
    Memory system container.

    All components are lazy-loaded singletons via @cached_property.
    """

    def __init__(self, settings, infra_container):
        """
        Args:
            settings: Application settings
            infra_container: InfraContainer for database access
        """
        self._settings = settings
        self._infra = infra_container

    # ========================================================================
    # Embedding Provider
    # ========================================================================

    @cached_property
    def embedding_provider(self):
        """
        Embedding provider for memory system.

        Uses Ollama bge-m3 by default (1024 dimensions).
        Falls back to mock provider if Ollama unavailable.
        """
        try:
            from src.contexts.session_memory.infrastructure.embeddings import OllamaEmbeddingProvider

            return OllamaEmbeddingProvider(adapter=self._infra.llm)
        except Exception as e:
            logger.warning(f"Failed to create Ollama embedding provider: {e}. Using mock.")
            from src.contexts.session_memory.infrastructure.embeddings import MockEmbeddingProvider

            return MockEmbeddingProvider(dimension=1024)

    # ========================================================================
    # Storage Backends
    # ========================================================================

    @cached_property
    def postgres_store(self) -> PostgresMemoryStore:
        """PostgreSQL memory store for structured data."""
        from src.contexts.session_memory.infrastructure.persistence import PostgresMemoryStore

        return PostgresMemoryStore(postgres_store=self._infra.postgres)

    @cached_property
    def embedding_store(self) -> EmbeddingMemoryStore:
        """Qdrant embedding store for semantic search."""
        from src.contexts.session_memory.infrastructure.persistence import EmbeddingMemoryStore

        return EmbeddingMemoryStore(
            qdrant_adapter=self._infra.qdrant,
            embedding_provider=self.embedding_provider,
            default_dimension=self.embedding_provider.dimension,
        )

    # ========================================================================
    # Memory System
    # ========================================================================

    @cached_property
    def system(self) -> ProductionMemorySystem:
        """
        Production memory system with all backends.

        Provides:
        - Episodic memory (past task executions)
        - Semantic memory (learned patterns, project knowledge)
        - Graph memory (entity relationships)
        - Fact storage (Mem0-style)
        """
        from src.contexts.session_memory.infrastructure.production import ProductionMemorySystem

        return ProductionMemorySystem(
            postgres_store=self.postgres_store,
            embedding_store=self.embedding_store,
        )

    async def initialize(self) -> None:
        """Initialize memory system (create tables, collections)."""
        await self.system.initialize()

    def create_working_memory(self, session_id: str | None = None):
        """
        Create a new working memory for an agent session.

        Args:
            session_id: Optional session ID

        Returns:
            WorkingMemoryManager instance
        """
        return self.system.create_working_memory(session_id=session_id)
