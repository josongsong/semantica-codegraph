"""
Indexing API Router

Endpoints for repository indexing operations.
"""

from fastapi import APIRouter, BackgroundTasks

from ..dependencies import IndexingServiceDep
from ..schemas.index_schema import IndexRequest, IndexResponse

router = APIRouter()


@router.post("/repository", response_model=IndexResponse)
async def index_repository(
    request: IndexRequest,
    background_tasks: BackgroundTasks,
    service: IndexingServiceDep,
):
    """
    Index a repository.

    Args:
        request: Index request with repo path and options
        background_tasks: FastAPI background tasks
        service: Indexing service

    Returns:
        Indexing job status
    """
    # TODO: Implement repository indexing
    raise NotImplementedError


@router.post("/reindex/{repo_id}")
async def reindex_repository(
    repo_id: str,
    background_tasks: BackgroundTasks,
    service: IndexingServiceDep,
):
    """
    Reindex an existing repository.

    Args:
        repo_id: Repository ID
        background_tasks: Background tasks
        service: Indexing service

    Returns:
        Reindexing job status
    """
    # TODO: Implement reindexing
    raise NotImplementedError
