"""
Foundation DI Registration

Registers foundation components:
- Chunk storage (PostgreSQL + optional caching)
- Pyright semantic analysis (RFC-023)
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.chunk.store import PostgresChunkStore
    from src.contexts.code_foundation.infrastructure.ir.external_analyzers import (
        PyrightSemanticDaemon,
        SemanticSnapshotStore,
    )
    from src.contexts.code_foundation.infrastructure.semantic_ir import DefaultSemanticIrBuilder
from src.common.observability import get_logger

logger = get_logger(__name__)


class FoundationContainer:
    """
    Foundation components container.

    Manages chunk storage and Pyright semantic analysis.
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
    # Chunk Storage
    # ========================================================================

    @cached_property
    def chunk_store(self) -> PostgresChunkStore:
        """Chunk storage (PostgreSQL with optional 3-tier caching)."""
        from src.contexts.code_foundation.infrastructure.chunk.store import PostgresChunkStore

        # PostgresStore 공유 (pool 자동 초기화)
        base_store = PostgresChunkStore(
            postgres_store=self._infra.postgres,
        )

        # 3-tier caching이 활성화되면 래핑
        if self._settings.cache.enable_three_tier:
            from src.contexts.code_foundation.infrastructure.chunk.cached_store import CachedChunkStore

            redis = self._infra.redis
            return CachedChunkStore(
                chunk_store=base_store,
                redis_client=redis.client if hasattr(redis, "client") else None,
                l1_maxsize=self._settings.cache.l1_chunk_maxsize,
                ttl=self._settings.cache.chunk_ttl,
            )

        return base_store

    @property
    def postgres_store(self):
        """PostgreSQL store (alias for infra.postgres)."""
        return self._infra.postgres

    # ========================================================================
    # RFC-023: Pyright Semantic Analysis
    # ========================================================================

    def create_semantic_ir_builder_with_pyright(self, project_root: str | Path) -> DefaultSemanticIrBuilder:
        """
        Create a Pyright-enabled semantic IR builder for a specific project.

        RFC-023 M0: Uses PyrightExternalAnalyzer (adapter over PyrightSemanticDaemon).

        This is a factory method (not cached) - creates a new instance per call.

        Args:
            project_root: Path to project root directory

        Returns:
            DefaultSemanticIrBuilder with PyrightExternalAnalyzer
        """
        from src.contexts.code_foundation.infrastructure.ir.external_analyzers import PyrightExternalAnalyzer
        from src.contexts.code_foundation.infrastructure.semantic_ir import DefaultSemanticIrBuilder
        from src.contexts.code_foundation.infrastructure.semantic_ir.expression.builder import ExpressionBuilder

        pyright = PyrightExternalAnalyzer(Path(project_root))
        expression_builder = ExpressionBuilder(external_analyzer=pyright)
        return DefaultSemanticIrBuilder(expression_builder=expression_builder)

    @cached_property
    def pyright_daemon(self) -> PyrightSemanticDaemon:
        """
        Global Pyright daemon (singleton).

        RFC-023 M0: Direct access to PyrightSemanticDaemon for snapshot management.
        Uses workspace root as project root. Automatically started on first access.
        """
        from src.contexts.code_foundation.infrastructure.ir.external_analyzers import PyrightSemanticDaemon

        project_root = Path.cwd()
        return PyrightSemanticDaemon(project_root)

    def create_pyright_daemon(self, project_root: str | Path) -> PyrightSemanticDaemon:
        """
        Create a Pyright daemon for a specific project.

        RFC-023 M0: Factory method - creates a new instance per call.

        Args:
            project_root: Path to project root directory

        Returns:
            PyrightSemanticDaemon instance
        """
        from src.contexts.code_foundation.infrastructure.ir.external_analyzers import PyrightSemanticDaemon

        return PyrightSemanticDaemon(Path(project_root))

    @cached_property
    def semantic_snapshot_store(self) -> SemanticSnapshotStore:
        """
        Semantic snapshot store.

        RFC-023 M1: PostgreSQL storage for Pyright semantic snapshots.
        """
        from src.contexts.code_foundation.infrastructure.ir.external_analyzers import SemanticSnapshotStore

        return SemanticSnapshotStore(self.postgres_store)

    def initialize_pyright_daemon(self) -> None:
        """
        Initialize Pyright daemon (starts pyright-langserver).

        Call during application startup to avoid first-use delay.
        """
        _ = self.pyright_daemon  # Access triggers initialization
