"""
Foundation Container Stub

Minimal stub for legacy code_foundation/infrastructure/di.py FoundationContainer.

This exists only to prevent import errors. All analysis logic has been moved to Rust.
DO NOT ADD NEW FEATURES HERE. Migrate callers to use Rust `import codegraph_ir` instead.

Migration Status (ADR-072 - Rust-only Architecture):
- ✅ Analysis logic → Rust (codegraph-ir)
- ⚠️ Python consumers still import FoundationContainer for chunk_store
- 🔧 TODO: Migrate chunk_store callers to Rust ChunkStore trait

Legacy Callers:
1. codegraph-search/infrastructure/di.py:212 (context_builder)
2. codegraph-engine/analysis_indexing/infrastructure/di.py:337, 359
"""

from functools import cached_property

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class FoundationContainer:
    """
    STUB: Foundation container for legacy compatibility.

    Provides minimal chunk_store implementation.
    All other analysis features have been removed (moved to Rust).

    DO NOT EXTEND THIS. Migrate callers to Rust codegraph_ir instead.
    """

    def __init__(self, settings, infra_container):
        """
        Initialize stub container.

        Args:
            settings: Application settings (unused, for compatibility)
            infra_container: Infrastructure container (unused, for compatibility)
        """
        self._settings = settings
        self._infra = infra_container
        logger.warning(
            "foundation_container_stub_initialized",
            message="Using FoundationContainer stub. Migrate to Rust codegraph_ir for analysis features.",
        )

    @cached_property
    def chunk_store(self):
        """
        In-memory chunk store (placeholder).

        Returns:
            InMemoryChunkStoreAdapter for testing/compatibility

        Migration Path:
            Use Rust ChunkStore trait via `import codegraph_ir`
            See: codegraph-ir/src/features/storage/
        """
        from codegraph_engine.code_foundation.infrastructure.adapters.foundation.chunk_store_adapter import (
            InMemoryChunkStoreAdapter,
        )

        logger.warning(
            "using_inmemory_chunk_store",
            message="Using in-memory chunk store stub. NOT for production. Migrate to Rust SqliteChunkStore.",
        )
        return InMemoryChunkStoreAdapter()
