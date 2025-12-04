"""
Index Layer

Normalizes Chunk/Graph structures into searchable indexes.

Components:
- Common: IndexDocument, SearchHit schemas and transformer
- Lexical (Zoekt): Full-text code search
- Vector (Qdrant): Semantic search
- Symbol (Kuzu): Graph-based symbol navigation
- Fuzzy (pg_trgm): Fuzzy identifier matching
- Domain (Qdrant): Documentation search
- Runtime (future): Execution trace analysis
- Service: Orchestrates all indexes

Note: Imports are lazy to avoid loading heavy dependencies (qdrant, numpy, kuzu)
when only lightweight components are needed.
"""

from typing import TYPE_CHECKING

from src.contexts.multi_index.infrastructure.common import IndexDocument, IndexDocumentTransformer, SearchHit

if TYPE_CHECKING:
    from src.contexts.multi_index.infrastructure.service import IndexingService


def __getattr__(name: str):
    """Lazy import to avoid loading heavy dependencies."""
    # Service (pulls in all indexes - lazy load)
    if name == "IndexingService":
        from src.contexts.multi_index.infrastructure.service import IndexingService

        return IndexingService

    # Factory functions (pull in all indexes including qdrant - lazy load)
    if name in (
        "IndexingConfig",
        "create_indexing_service",
        "create_indexing_service_from_config",
        "create_indexing_service_minimal",
        "create_lexical_index_standalone",
        "create_vector_index_standalone",
    ):
        from src.contexts.multi_index.infrastructure import factory

        return getattr(factory, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Common schemas (lightweight - direct import)
    "IndexDocument",
    "SearchHit",
    "IndexDocumentTransformer",
    # Service (heavy - lazy import)
    "IndexingService",
    # Factory functions (heavy - lazy import)
    "create_indexing_service",
    "create_indexing_service_minimal",
    "create_indexing_service_from_config",
    "create_vector_index_standalone",
    "create_lexical_index_standalone",
    "IndexingConfig",
]
