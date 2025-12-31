"""
Indexing API Routes

Provides repository indexing endpoints using the Index Layer.

Architecture:
    FastAPI → Container → IndexingService → (Multi-Index Adapters)

Endpoints:
    POST /index/repo          - Full repository indexing
    POST /index/incremental   - Incremental indexing (changed files)
    DELETE /index/repo        - Delete repository index
    GET /index/status         - Get indexing status
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from codegraph_shared.container import Container
from codegraph_engine.multi_index.infrastructure.service.indexing_service import IndexingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Indexing"])


# ============================================================
# Request/Response Models
# ============================================================


class IndexRepoRequest(BaseModel):
    """Full repository indexing request."""

    repo_id: str = Field(..., description="Repository identifier")
    snapshot_id: str = Field(..., description="Git commit hash or snapshot ID")
    repo_path: str = Field(..., description="Local path to repository")
    force: bool = Field(False, description="Force re-index even if already indexed")


class IncrementalIndexRequest(BaseModel):
    """Incremental indexing request."""

    repo_id: str = Field(..., description="Repository identifier")
    snapshot_id: str = Field(..., description="Git commit hash or snapshot ID")
    changed_files: list[str] = Field(..., description="List of changed file paths")
    deleted_files: list[str] = Field(default_factory=list, description="List of deleted file paths")


class DeleteRepoRequest(BaseModel):
    """Delete repository index request."""

    repo_id: str = Field(..., description="Repository identifier")
    snapshot_id: str = Field(..., description="Snapshot ID to delete")


class IndexingResponse(BaseModel):
    """Generic indexing operation response."""

    success: bool
    repo_id: str
    snapshot_id: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Dependency Injection
# ============================================================


async def get_container(request: Request) -> Container:
    """Get Container from app state."""
    return request.app.state.container


async def get_indexing_service(container: Container = Depends(get_container)) -> IndexingService:
    """Get IndexingService from container."""
    return container.indexing_service


async def get_orchestrator(container: Container = Depends(get_container)):
    """Get IndexingOrchestrator from container."""
    return container.indexing_orchestrator


# ============================================================
# Indexing Endpoints
# ============================================================


@router.post("/repo", response_model=IndexingResponse)
async def index_repository(
    req: IndexRepoRequest,
    orchestrator=Depends(get_orchestrator),
):
    """
    Full repository indexing.

    Indexes entire repository across all available indexes:
    - Lexical (Zoekt)
    - Vector (Qdrant)
    - Symbol (Kuzu)
    - Fuzzy (PostgreSQL pg_trgm)
    - Domain (PostgreSQL FTS)

    Pipeline stages:
    1. File Discovery: Find all Python source files
    2. Parsing: Parse files to AST
    3. IR Generation: Generate intermediate representation
    4. Graph Building: Build call graph and relationships
    5. Chunk Creation: Create searchable code chunks
    6. Indexing: Index chunks into all available indexes

    Args:
        req: Indexing request with repo_id, snapshot_id, repo_path

    Returns:
        IndexingResponse with success status and details
    """
    logger.info(f"Starting full indexing for {req.repo_id}:{req.snapshot_id}")

    try:
        # Run full indexing pipeline
        result = await orchestrator.index_repository_full(
            repo_id=req.repo_id,
            snapshot_id=req.snapshot_id,
            repo_path=req.repo_path,
        )

        # Build response
        if result.success:
            message = f"Successfully indexed {result.files_processed} files, created {result.chunks_created} chunks"
        else:
            message = "Indexing completed with errors"

        return IndexingResponse(
            success=result.success,
            repo_id=result.repo_id,
            snapshot_id=result.snapshot_id,
            message=message,
            details={
                "files_processed": result.files_processed,
                "chunks_created": result.chunks_created,
                "chunks_indexed": result.chunks_indexed,
                "errors": result.errors,
                **result.details,
            },
        )

    except Exception as e:
        logger.error(f"Indexing failed for {req.repo_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}") from e


@router.post("/incremental", response_model=IndexingResponse)
async def index_incremental(
    req: IncrementalIndexRequest,
    orchestrator=Depends(get_orchestrator),
):
    """
    Incremental repository indexing.

    Updates only changed/deleted files without re-indexing entire repository.

    Pipeline stages:
    1. Parse changed files only
    2. Generate IR for changed files
    3. Update graph with new IR
    4. Create/update chunks for changed files
    5. Upsert chunks into indexes
    6. Delete chunks for deleted files

    Args:
        req: Incremental request with changed_files and deleted_files

    Returns:
        IndexingResponse with success status
    """
    logger.info(
        f"Starting incremental indexing for {req.repo_id}:{req.snapshot_id} "
        f"({len(req.changed_files)} changed, {len(req.deleted_files)} deleted)"
    )

    try:
        # Run incremental indexing pipeline
        result = await orchestrator.index_repository_incremental(
            repo_id=req.repo_id,
            snapshot_id=req.snapshot_id,
            changed_files=req.changed_files,
            deleted_files=req.deleted_files,
            old_snapshot_id=None,  # TODO: Get from request if available
        )

        # Build response
        if result.success:
            message = f"Successfully processed {result.files_processed} files, updated {result.chunks_indexed} chunks"
        else:
            message = "Incremental indexing completed with errors"

        return IndexingResponse(
            success=result.success,
            repo_id=result.repo_id,
            snapshot_id=result.snapshot_id,
            message=message,
            details={
                "files_processed": result.files_processed,
                "chunks_created": result.chunks_created,
                "chunks_indexed": result.chunks_indexed,
                "errors": result.errors,
                **result.details,
            },
        )

    except Exception as e:
        logger.error(f"Incremental indexing failed for {req.repo_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Incremental indexing failed: {str(e)}") from e


@router.delete("/repo", response_model=IndexingResponse)
async def delete_repository_index(
    req: DeleteRepoRequest,
    service: IndexingService = Depends(get_indexing_service),
):
    """
    Delete repository index.

    Removes all indexed data for a repository snapshot from all indexes.

    Args:
        req: Delete request with repo_id and snapshot_id

    Returns:
        IndexingResponse with success status
    """
    logger.info(f"Deleting index for {req.repo_id}:{req.snapshot_id}")

    try:
        # TODO: Implement index deletion
        # Call service methods to delete from all indexes

        return IndexingResponse(
            success=False,
            repo_id=req.repo_id,
            snapshot_id=req.snapshot_id,
            message="Index deletion not yet implemented",
        )

    except Exception as e:
        logger.error(f"Index deletion failed for {req.repo_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Index deletion failed: {str(e)}") from e


@router.get("/status/{repo_id}")
async def get_indexing_status(
    repo_id: str,
    snapshot_id: str | None = None,
):
    """
    Get indexing status for a repository.

    Returns information about which indexes are available and their status.

    Args:
        repo_id: Repository identifier
        snapshot_id: Optional snapshot ID (default: all snapshots)

    Returns:
        Indexing status with available indexes and metadata
    """
    logger.info(f"Getting indexing status for {repo_id}")

    try:
        # TODO: Query each index for status
        # Check if repo_id exists in each index

        return {
            "repo_id": repo_id,
            "snapshot_id": snapshot_id or "all",
            "indexes": {
                "lexical": {"available": False, "status": "not_implemented"},
                "vector": {"available": False, "status": "not_implemented"},
                "symbol": {"available": False, "status": "not_implemented"},
                "fuzzy": {"available": False, "status": "not_implemented"},
                "domain": {"available": False, "status": "not_implemented"},
            },
            "message": "Index status checking not yet implemented",
        }

    except Exception as e:
        logger.error(f"Status check failed for {repo_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}") from e


# ============================================================
# Health Check for Indexing Service
# ============================================================


@router.get("/health")
async def indexing_health_check(
    service: IndexingService = Depends(get_indexing_service),
):
    """
    Health check for indexing service and all index adapters.

    Returns:
        Health status for each index adapter
    """
    try:
        health_status = {
            "service": "indexing",
            "status": "healthy",
            "indexes": {},
        }

        # Check each index adapter
        if service.lexical_index:
            health_status["indexes"]["lexical"] = "available"
        else:
            health_status["indexes"]["lexical"] = "unavailable"

        if service.vector_index:
            health_status["indexes"]["vector"] = "available"
        else:
            health_status["indexes"]["vector"] = "unavailable"

        if service.symbol_index:
            health_status["indexes"]["symbol"] = "available"
        else:
            health_status["indexes"]["symbol"] = "unavailable"

        if service.fuzzy_index:
            health_status["indexes"]["fuzzy"] = "available"
        else:
            health_status["indexes"]["fuzzy"] = "unavailable"

        if service.domain_index:
            health_status["indexes"]["domain"] = "available"
        else:
            health_status["indexes"]["domain"] = "unavailable"

        return health_status

    except Exception as e:
        logger.error(f"Indexing health check failed: {e}", exc_info=True)
        return {
            "service": "indexing",
            "status": "unhealthy",
            "error": str(e),
        }
