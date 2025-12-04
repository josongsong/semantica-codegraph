"""
Index Layer Factory

Provides factory functions for creating IndexingService with wired adapters.

Usage:
    # Async factory (recommended)
    service = await create_indexing_service(
        zoekt_host="localhost",
        zoekt_port=6070,
        qdrant_url="http://localhost:6333",
        chunk_store=chunk_store,
    )

    # Minimal setup (lexical + vector only)
    service = await create_indexing_service_minimal(chunk_store)
"""

from typing import Any

from qdrant_client import AsyncQdrantClient

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.chunk.store import ChunkStore
from src.contexts.multi_index.infrastructure.domain_meta.adapter_meta import DomainMetaIndex
from src.contexts.multi_index.infrastructure.fuzzy.adapter_pgtrgm import PostgresFuzzyIndex
from src.contexts.multi_index.infrastructure.lexical.adapter_zoekt import (
    RepoPathResolver,
    ZoektLexicalIndex,
)
from src.contexts.multi_index.infrastructure.service import IndexingService
from src.contexts.multi_index.infrastructure.vector.adapter_qdrant import (
    OpenAIEmbeddingProvider,
    QdrantVectorIndex,
)
from src.infra.search.zoekt import ZoektAdapter
from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)
# ============================================================
# Full Factory (All Adapters)
# ============================================================


async def create_indexing_service(
    chunk_store: ChunkStore,
    zoekt_host: str = "localhost",
    zoekt_port: int = 6070,
    qdrant_url: str = "http://localhost:6333",
    embedding_model: str = "text-embedding-3-small",
    repos_root: str = "./repos",
    enable_symbol: bool = False,
    enable_fuzzy: bool = False,
    enable_domain: bool = False,
    postgres_store: PostgresStore | None = None,
) -> IndexingService:
    """
    Create fully configured IndexingService with all available adapters.

    Args:
        chunk_store: ChunkStore instance (required for Zoekt mapping)
        zoekt_host: Zoekt server host
        zoekt_port: Zoekt server port
        qdrant_url: Qdrant server URL
        embedding_model: OpenAI embedding model name
        repos_root: Root directory for repositories
        enable_symbol: Enable Symbol index - default False
        enable_fuzzy: Enable Fuzzy index (pg_trgm)
        enable_domain: Enable Domain index
        postgres_store: PostgresStore instance (required for fuzzy/domain indexes)

    Returns:
        Configured IndexingService instance

    Example:
        from src.contexts.code_foundation.infrastructure.chunk.store import PostgresChunkStore

        chunk_store = await PostgresChunkStore.create(db_url)
        service = await create_indexing_service(
            chunk_store=chunk_store,
            zoekt_host="localhost",
            zoekt_port=6070,
        )
    """
    logger.info("Creating IndexingService with full configuration")

    # ========================================
    # 1. Create Lexical Index (Zoekt)
    # ========================================
    zoekt_adapter = ZoektAdapter(host=zoekt_host, port=zoekt_port)
    repo_resolver = RepoPathResolver(repos_root=repos_root)
    lexical_index = ZoektLexicalIndex(
        zoekt_adapter=zoekt_adapter,
        chunk_store=chunk_store,
        repo_resolver=repo_resolver,
    )
    logger.info(f"✓ Lexical Index: Zoekt @ {zoekt_host}:{zoekt_port}, repos={repos_root}")

    # ========================================
    # 2. Create Vector Index (Qdrant)
    # ========================================
    qdrant_client = AsyncQdrantClient(url=qdrant_url)
    embedding_provider = OpenAIEmbeddingProvider(model=embedding_model)
    vector_index = QdrantVectorIndex(
        client=qdrant_client,
        embedding_provider=embedding_provider,
    )
    logger.info(f"✓ Vector Index: Qdrant @ {qdrant_url}, model={embedding_model}")

    # ========================================
    # 3. Create Symbol Index (Disabled)
    # ========================================
    symbol_index = None

    # ========================================
    # 4. Create Fuzzy Index (pg_trgm)
    # ========================================
    fuzzy_index = None
    if enable_fuzzy:
        if postgres_store is None:
            logger.warning("Fuzzy Index requires postgres_store, skipping")
        else:
            fuzzy_index = PostgresFuzzyIndex(postgres_store=postgres_store)
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
    zoekt_host: str = "localhost",
    zoekt_port: int = 6070,
    qdrant_url: str = "http://localhost:6333",
) -> IndexingService:
    """
    Create minimal IndexingService with Lexical + Vector only.

    Faster startup, suitable for MVP and testing.

    Args:
        chunk_store: ChunkStore instance
        zoekt_host: Zoekt server host
        zoekt_port: Zoekt server port
        qdrant_url: Qdrant server URL

    Returns:
        IndexingService with Lexical + Vector indexes only
    """
    return await create_indexing_service(
        chunk_store=chunk_store,
        zoekt_host=zoekt_host,
        zoekt_port=zoekt_port,
        qdrant_url=qdrant_url,
        enable_symbol=False,
        enable_fuzzy=False,
        enable_domain=False,
    )


# ============================================================
# Vector-Only Factory (For Testing)
# ============================================================


async def create_vector_index_standalone(
    qdrant_url: str = "http://localhost:6333",
    embedding_model: str = "text-embedding-3-small",
) -> QdrantVectorIndex:
    """
    Create standalone VectorIndex for testing.

    Args:
        qdrant_url: Qdrant server URL
        embedding_model: OpenAI embedding model

    Returns:
        Configured QdrantVectorIndex
    """
    client = AsyncQdrantClient(url=qdrant_url)
    embedding_provider = OpenAIEmbeddingProvider(model=embedding_model)

    return QdrantVectorIndex(
        client=client,
        embedding_provider=embedding_provider,
    )


# ============================================================
# Lexical-Only Factory (For Testing)
# ============================================================


def create_lexical_index_standalone(
    chunk_store: ChunkStore,
    zoekt_host: str = "localhost",
    zoekt_port: int = 6070,
    repos_root: str = "./repos",
) -> ZoektLexicalIndex:
    """
    Create standalone LexicalIndex for testing.

    Args:
        chunk_store: ChunkStore instance
        zoekt_host: Zoekt server host
        zoekt_port: Zoekt server port
        repos_root: Root directory for repositories

    Returns:
        Configured ZoektLexicalIndex
    """
    zoekt_adapter = ZoektAdapter(host=zoekt_host, port=zoekt_port)
    repo_resolver = RepoPathResolver(repos_root=repos_root)

    return ZoektLexicalIndex(
        zoekt_adapter=zoekt_adapter,
        chunk_store=chunk_store,
        repo_resolver=repo_resolver,
    )


# ============================================================
# Configuration Presets
# ============================================================


class IndexingConfig:
    """Configuration presets for IndexingService."""

    # Development (local services)
    DEV = {
        "zoekt_host": "localhost",
        "zoekt_port": 6070,
        "qdrant_url": "http://localhost:6333",
        "embedding_model": "text-embedding-3-small",
        "repos_root": "./repos",
        "enable_symbol": False,
    }

    # Production (docker-compose services)
    PROD = {
        "zoekt_host": "zoekt",
        "zoekt_port": 6070,
        "qdrant_url": "http://qdrant:6333",
        "embedding_model": "text-embedding-3-small",
        "repos_root": "/app/repos",
        "enable_symbol": False,
    }

    # Testing (mocked services)
    TEST = {
        "zoekt_host": "localhost",
        "zoekt_port": 6070,
        "qdrant_url": "http://localhost:6333",
        "embedding_model": "text-embedding-3-small",
        "repos_root": "./test-repos",
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
        zoekt_host=config.get("zoekt_host", "localhost"),
        zoekt_port=config.get("zoekt_port", 6070),
        qdrant_url=config.get("qdrant_url", "http://localhost:6333"),
        embedding_model=config.get("embedding_model", "text-embedding-3-small"),
        repos_root=config.get("repos_root", "./repos"),
        enable_symbol=False,
    )
