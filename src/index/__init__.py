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
"""

from .common import IndexDocument, IndexDocumentTransformer, SearchHit
from .factory import (
    IndexingConfig,
    create_indexing_service,
    create_indexing_service_from_config,
    create_indexing_service_minimal,
    create_lexical_index_standalone,
    create_vector_index_standalone,
)
from .service import IndexingService
from .symbol import KuzuSymbolIndex, create_kuzu_symbol_index

__all__ = [
    # Common schemas
    "IndexDocument",
    "SearchHit",
    "IndexDocumentTransformer",
    # Service
    "IndexingService",
    # Factory functions
    "create_indexing_service",
    "create_indexing_service_minimal",
    "create_indexing_service_from_config",
    "create_vector_index_standalone",
    "create_lexical_index_standalone",
    "IndexingConfig",
    # Symbol Index
    "KuzuSymbolIndex",
    "create_kuzu_symbol_index",
]
