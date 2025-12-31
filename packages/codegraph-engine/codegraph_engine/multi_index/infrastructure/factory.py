"""
Index Layer Factory

Provides factory functions for creating IndexingService with wired adapters.

Usage:
    # Async factory (recommended)
    service = await create_indexing_service(
        tantivy_index_path="./data/tantivy_index",
        qdrant_url="http://localhost:6333",
        chunk_store=chunk_store,
    )

    # Minimal setup (lexical + vector only)
    service = await create_indexing_service_minimal(chunk_store)
"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.chunk.store import ChunkStore
from codegraph_engine.multi_index.infrastructure.domain_meta.adapter_meta import DomainMetaIndex
from codegraph_engine.multi_index.infrastructure.lexical.tantivy import TantivyCodeIndex
from codegraph_engine.multi_index.infrastructure.service import IndexingService
from codegraph_engine.multi_index.infrastructure.vector.adapter_qdrant import (
    OpenAIEmbeddingProvider,
    QdrantVectorIndex,
)
from codegraph_shared.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)
# ============================================================
# Full Factory (All Adapters)
# ============================================================


async def create_indexing_service(
    chunk_store: ChunkStore,
    tantivy_index_path: str = "./data/tantivy_index",
    tantivy_heap_size_mb: int = 512,
    qdrant_url: str = "http://localhost:6333",
    qdrant_mode: str = "embedded",
    qdrant_storage_path: str = "./data/qdrant_storage",
    embedding_model: str = "text-embedding-3-small",
    enable_symbol: bool = False,
    enable_domain: bool = False,
    postgres_store: PostgresStore | None = None,
) -> IndexingService:
    """
    Create fully configured IndexingService with Tantivy

    Args:
        chunk_store: ChunkStore instance (required for Tantivy mapping)
        tantivy_index_path: Tantivy index directory
        tantivy_heap_size_mb: Tantivy writer heap size (MB)
        qdrant_url: Qdrant server URL (server 모드용)
        qdrant_mode: Qdrant 모드 - memory | embedded | server
        qdrant_storage_path: embedded 모드 저장 경로
        embedding_model: OpenAI embedding model name
        enable_symbol: Enable Symbol index - default False
        enable_domain: Enable Domain index
        postgres_store: PostgresStore instance (required for domain index)

    Returns:
        Configured IndexingService instance

    Example:
        from codegraph_engine.code_foundation.infrastructure.chunk.store import PostgresChunkStore

        chunk_store = await PostgresChunkStore.create(db_url)
        service = await create_indexing_service(
            chunk_store=chunk_store,
            tantivy_index_path="./data/tantivy_index",
        )
    """
    logger.info("Creating IndexingService with Tantivy")

    # ========================================
    # 1. Create Lexical Index (Tantivy)
    # ========================================
    lexical_index = TantivyCodeIndex(
        index_dir=tantivy_index_path,
        chunk_store=chunk_store,
        heap_size_mb=tantivy_heap_size_mb,
        num_threads=4,
    )
    logger.info(f"✓ Lexical Index: Tantivy @ {tantivy_index_path}")

    # ========================================
    # 2. Create Vector Index (Qdrant)
    # ========================================
    from codegraph_shared.infra.vector import create_qdrant_client

    qdrant_client = create_qdrant_client(
        mode=qdrant_mode,
        storage_path=qdrant_storage_path,
        url=qdrant_url,
    )
    embedding_provider = OpenAIEmbeddingProvider(model=embedding_model)
    vector_index = QdrantVectorIndex(
        client=qdrant_client,
        embedding_provider=embedding_provider,
    )
    logger.info(f"✓ Vector Index: Qdrant {qdrant_mode} mode, model={embedding_model}")

    # ========================================
    # 3. Create Symbol Index (Disabled)
    # ========================================
    symbol_index = None

    # ========================================
    # 4. Create Fuzzy Index (pg_trgm)
    # ========================================
    fuzzy_index = None
    if postgres_store is None:
        logger.warning("Fuzzy Index requires postgres_store, skipping")
    else:
        logger.info("✓ Fuzzy Index: PostgreSQL pg_trgm")

    # ========================================
    # 5. Create Domain Index (full-text search)
    # ========================================
    domain_index = None
    if enable_domain:
        if postgres_store is None:
            logger.warning("Domain Index requires postgres_store, skipping")
        else:
            domain_index = DomainMetaIndex(postgres_store=postgres_store)
            logger.info("✓ Domain Index: PostgreSQL full-text search")

    # ========================================
    # 6. Wire to IndexingService
    # ========================================
    service = IndexingService(
        lexical_index=lexical_index,
        vector_index=vector_index,
        symbol_index=symbol_index,
        fuzzy_index=fuzzy_index,
        domain_index=domain_index,
        runtime_index=None,  # Phase 3
    )

    logger.info("IndexingService created successfully")
    return service


# ============================================================
# Minimal Factory (Lexical + Vector Only)
# ============================================================


async def create_indexing_service_minimal(
    chunk_store: ChunkStore,
    tantivy_index_path: str = "./data/tantivy_index",
    qdrant_url: str = "http://localhost:6333",
) -> IndexingService:
    """
    Create minimal IndexingService with Lexical + Vector only.

    Faster startup, suitable for MVP and testing.

    Args:
        chunk_store: ChunkStore instance
        tantivy_index_path: Tantivy index directory
        qdrant_url: Qdrant server URL

    Returns:
        IndexingService with Lexical + Vector indexes only
    """
    return await create_indexing_service(
        chunk_store=chunk_store,
        tantivy_index_path=tantivy_index_path,
        qdrant_url=qdrant_url,
        enable_symbol=False,
        enable_domain=False,
    )


# ============================================================
# Vector-Only Factory (For Testing)
# ============================================================


async def create_vector_index_standalone(
    qdrant_url: str = "http://localhost:6333",
    qdrant_mode: str = "embedded",
    qdrant_storage_path: str = "./data/qdrant_storage",
    embedding_model: str = "text-embedding-3-small",
) -> QdrantVectorIndex:
    """
    Create standalone VectorIndex for testing.

    Args:
        qdrant_url: Qdrant server URL (server 모드용)
        qdrant_mode: Qdrant 모드 - memory | embedded | server
        qdrant_storage_path: embedded 모드 저장 경로
        embedding_model: OpenAI embedding model

    Returns:
        Configured QdrantVectorIndex
    """
    from codegraph_shared.infra.vector import create_qdrant_client

    client = create_qdrant_client(
        mode=qdrant_mode,
        storage_path=qdrant_storage_path,
        url=qdrant_url,
    )
    embedding_provider = OpenAIEmbeddingProvider(model=embedding_model)

    return QdrantVectorIndex(
        client=client,
        embedding_provider=embedding_provider,
    )


# ============================================================
# Configuration Presets
# ============================================================


class IndexingConfig:
    """Configuration presets for IndexingService."""

    # Development (local services)
    DEV = {
        "tantivy_index_path": "./data/tantivy_index",
        "qdrant_url": "http://localhost:6333",
        "embedding_model": "text-embedding-3-small",
        "enable_symbol": False,
    }

    # Production (docker-compose services)
    PROD = {
        "tantivy_index_path": "./data/tantivy_index",
        "qdrant_url": "http://qdrant:6333",
        "embedding_model": "text-embedding-3-small",
        "enable_symbol": False,
    }

    # Testing (mocked services)
    TEST = {
        "tantivy_index_path": "./data/tantivy_index",
        "qdrant_url": "http://localhost:6333",
        "embedding_model": "text-embedding-3-small",
        "enable_symbol": False,
    }


async def create_indexing_service_from_config(
    chunk_store: ChunkStore,
    config: dict[str, Any],
) -> IndexingService:
    """
    Create IndexingService from configuration dict.

    Args:
        chunk_store: ChunkStore instance
        config: Configuration dict (use IndexingConfig.DEV/PROD/TEST)

    Returns:
        Configured IndexingService

    Example:
        service = await create_indexing_service_from_config(
            chunk_store=chunk_store,
            config=IndexingConfig.DEV,
        )
    """
    return await create_indexing_service(
        chunk_store=chunk_store,
        tantivy_index_path=config.get("tantivy_index_path", "./data/tantivy_index"),
        qdrant_url=config.get("qdrant_url", "http://localhost:6333"),
        embedding_model=config.get("embedding_model", "text-embedding-3-small"),
        enable_symbol=False,
    )
