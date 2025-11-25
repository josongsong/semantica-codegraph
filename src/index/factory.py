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

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient

from src.foundation.chunk.store import ChunkStore
from src.index.lexical.adapter_zoekt import (
    RepoPathResolver,
    ZoektLexicalIndex,
)
from src.index.service import IndexingService
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex
from src.index.vector.adapter_qdrant import (
    OpenAIEmbeddingProvider,
    QdrantVectorIndex,
)
from src.infra.search.zoekt import ZoektAdapter

logger = logging.getLogger(__name__)


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
    kuzu_db_path: str = "./kuzu_db",
    enable_symbol: bool = True,
    enable_fuzzy: bool = False,
    enable_domain: bool = False,
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
        kuzu_db_path: Kuzu database directory path
        enable_symbol: Enable Symbol index (Kuzu) - default True
        enable_fuzzy: Enable Fuzzy index (pg_trgm) - Phase 3
        enable_domain: Enable Domain index - Phase 3

    Returns:
        Configured IndexingService instance

    Example:
        from src.foundation.chunk.store import PostgresChunkStore

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
    # 3. Create Symbol Index (Kuzu Graph)
    # ========================================
    symbol_index = None
    if enable_symbol:
        symbol_index = KuzuSymbolIndex(db_path=kuzu_db_path)
        logger.info(f"✓ Symbol Index: Kuzu @ {kuzu_db_path}")

    # ========================================
    # 4. Create Fuzzy Index (Phase 3 - Optional)
    # ========================================
    fuzzy_index = None
    if enable_fuzzy:
        # TODO Phase 3: Implement PostgresFuzzyIndex
        logger.warning("Fuzzy Index not yet implemented (Phase 3)")

    # ========================================
    # 5. Create Domain Index (Phase 3 - Optional)
    # ========================================
    domain_index = None
    if enable_domain:
        # TODO Phase 3: Implement DomainMetaIndex
        logger.warning("Domain Index not yet implemented (Phase 3)")

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
        "kuzu_db_path": "./kuzu_db",
        "enable_symbol": True,
    }

    # Production (docker-compose services)
    PROD = {
        "zoekt_host": "zoekt",
        "zoekt_port": 6070,
        "qdrant_url": "http://qdrant:6333",
        "embedding_model": "text-embedding-3-small",
        "repos_root": "/app/repos",
        "kuzu_db_path": "/app/kuzu_db",
        "enable_symbol": True,
    }

    # Testing (mocked services)
    TEST = {
        "zoekt_host": "localhost",
        "zoekt_port": 6070,
        "qdrant_url": "http://localhost:6333",
        "embedding_model": "text-embedding-3-small",
        "repos_root": "./test-repos",
        "kuzu_db_path": "./test-kuzu_db",
        "enable_symbol": True,
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
        kuzu_db_path=config.get("kuzu_db_path", "./kuzu_db"),
        enable_symbol=config.get("enable_symbol", True),
    )
