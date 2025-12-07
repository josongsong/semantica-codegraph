"""
Search API Routes

Provides unified search endpoints using the new Index Layer.

Architecture:
    FastAPI → IndexingService → (Zoekt + Qdrant + Kuzu) → SearchHit

Endpoints:
    GET /search              - Unified hybrid search (Lexical + Vector Fusion)
    GET /search/lexical      - Lexical search only (Zoekt)
    GET /search/vector       - Vector search only (Qdrant)
    GET /search/symbol       - Symbol search only (Kuzu) - Phase 3
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from src.foundation.chunk.store import PostgresChunkStore
from src.index import (
    IndexingService,
    create_indexing_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


# ============================================================
# Dependency Injection
# ============================================================


async def get_chunk_store() -> PostgresChunkStore:
    """
    Get ChunkStore instance.

    TODO: Replace with proper DI container (e.g., FastAPI Depends with lifespan).
    For now, creates new instance per request (not optimal).
    """
    db_url = "postgresql://postgres:postgres@localhost:5432/semantica"
    chunk_store = PostgresChunkStore(connection_string=db_url)
    return chunk_store


async def get_indexing_service(
    chunk_store: PostgresChunkStore = Depends(get_chunk_store),
) -> IndexingService:
    """
    Get IndexingService instance.

    TODO: Cache this as singleton in app.state for better performance.
    """
    service = await create_indexing_service(
        chunk_store=chunk_store,
        zoekt_host="localhost",
        zoekt_port=6070,
        qdrant_url="http://localhost:6333",
    )
    return service


# ============================================================
# Search Endpoints
# ============================================================


@router.get("/search")
async def search_unified(
    q: str = Query(..., description="검색 쿼리", min_length=1),
    repo_id: str = Query(..., description="리포지토리 ID"),
    snapshot_id: str = Query("HEAD", description="스냅샷 ID (기본값: HEAD)"),
    limit: int = Query(50, ge=1, le=200, description="최대 결과 수"),
    lexical_weight: float = Query(0.3, ge=0.0, le=1.0, description="Lexical 가중치"),
    vector_weight: float = Query(0.3, ge=0.0, le=1.0, description="Vector 가중치"),
    service: IndexingService = Depends(get_indexing_service),
):
    """
    통합 하이브리드 검색 (Lexical + Vector Fusion).

    Weighted fusion of Lexical (Zoekt) and Vector (Qdrant) search results.

    Args:
        q: Search query (text/identifier/natural language)
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier (default: "HEAD")
        limit: Maximum number of results
        lexical_weight: Weight for lexical search (0.0-1.0)
        vector_weight: Weight for vector search (0.0-1.0)

    Returns:
        {
            "query": str,
            "repo_id": str,
            "snapshot_id": str,
            "results": list[SearchHit],
            "total": int,
            "weights": dict,
        }
    """
    try:
        # Prepare weights
        weights = {
            "lexical": lexical_weight,
            "vector": vector_weight,
        }

        # Execute unified search
        results = await service.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=q,
            limit=limit,
            weights=weights,
        )

        return {
            "query": q,
            "repo_id": repo_id,
            "snapshot_id": snapshot_id,
            "results": results,
            "total": len(results),
            "weights": weights,
        }

    except Exception as e:
        logger.error(f"Unified search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@router.get("/search/lexical")
async def search_lexical(
    q: str = Query(..., description="검색 쿼리", min_length=1),
    repo_id: str = Query(..., description="리포지토리 ID"),
    snapshot_id: str = Query("HEAD", description="스냅샷 ID"),
    limit: int = Query(50, ge=1, le=200),
    service: IndexingService = Depends(get_indexing_service),
):
    """
    Lexical 검색 전용 (Zoekt).

    File-based text search using Zoekt with Chunk mapping.

    Args:
        q: Search query (text/regex/identifier)
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        limit: Maximum number of results

    Returns:
        {
            "query": str,
            "results": list[SearchHit with source="lexical"],
            "total": int,
        }
    """
    try:
        if not service.lexical_index:
            raise HTTPException(status_code=503, detail="Lexical index not available")

        results = await service.lexical_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=q,
            limit=limit,
        )

        return {
            "query": q,
            "repo_id": repo_id,
            "snapshot_id": snapshot_id,
            "results": results,
            "total": len(results),
            "source": "lexical",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lexical search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lexical search failed: {str(e)}") from e


@router.get("/search/vector")
async def search_vector(
    q: str = Query(..., description="검색 쿼리 (자연어)", min_length=1),
    repo_id: str = Query(..., description="리포지토리 ID"),
    snapshot_id: str = Query("HEAD", description="스냅샷 ID"),
    limit: int = Query(50, ge=1, le=200),
    service: IndexingService = Depends(get_indexing_service),
):
    """
    Vector 검색 전용 (Qdrant).

    Semantic search using embeddings and vector similarity.

    Args:
        q: Natural language query
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        limit: Maximum number of results

    Returns:
        {
            "query": str,
            "results": list[SearchHit with source="vector"],
            "total": int,
        }
    """
    try:
        if not service.vector_index:
            raise HTTPException(status_code=503, detail="Vector index not available")

        results = await service.vector_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=q,
            limit=limit,
        )

        return {
            "query": q,
            "repo_id": repo_id,
            "snapshot_id": snapshot_id,
            "results": results,
            "total": len(results),
            "source": "vector",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vector search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vector search failed: {str(e)}") from e


@router.get("/search/symbol")
async def search_symbol(
    q: str = Query(..., description="심볼 이름 또는 패턴", min_length=1),
    repo_id: str = Query(..., description="리포지토리 ID"),
    snapshot_id: str = Query("HEAD", description="스냅샷 ID"),
    limit: int = Query(50, ge=1, le=200),
    service: IndexingService = Depends(get_indexing_service),
):
    """
    Symbol 검색 (Kuzu Graph) - Phase 3.

    Graph-based symbol navigation (go-to-def, find-refs).

    Args:
        q: Symbol name or pattern
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        limit: Maximum number of results

    Returns:
        {
            "query": str,
            "results": list[SearchHit with source="symbol"],
            "total": int,
        }
    """
    try:
        if not service.symbol_index:
            raise HTTPException(
                status_code=501,
                detail="Symbol index not yet implemented (Phase 3)",
            )

        results = await service.symbol_index.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=q,
            limit=limit,
        )

        return {
            "query": q,
            "repo_id": repo_id,
            "snapshot_id": snapshot_id,
            "results": results,
            "total": len(results),
            "source": "symbol",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symbol search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Symbol search failed: {str(e)}") from e


# ============================================================
# Legacy Endpoints (Deprecated)
# ============================================================


@router.get("/chunks", deprecated=True)
async def search_chunks_legacy(
    q: str = Query(..., description="검색 쿼리"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    청크 검색 (Deprecated).

    Use /search/vector or /search instead.
    """
    raise HTTPException(
        status_code=410,
        detail="Endpoint deprecated. Use /search/vector or /search instead.",
    )


@router.get("/symbols", deprecated=True)
async def search_symbols_legacy(
    q: str = Query(..., description="검색 쿼리"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    심볼 검색 (Deprecated).

    Use /search/symbol instead.
    """
    raise HTTPException(
        status_code=410,
        detail="Endpoint deprecated. Use /search/symbol instead.",
    )
