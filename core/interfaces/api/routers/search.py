"""
Search API Router

Endpoints for code search operations.
"""

from typing import List, Optional
from fastapi import APIRouter, Query

from ..dependencies import SearchServiceDep
from ..schemas.search_schema import SearchRequest, SearchResponse

router = APIRouter()


@router.post("/", response_model=SearchResponse)
async def search_code(
    request: SearchRequest,
    service: SearchServiceDep,
):
    """
    Search code using hybrid search (semantic + lexical).

    Args:
        request: Search request with query and filters
        service: Search service dependency

    Returns:
        Search results with chunks and scores
    """
    # TODO: Implement search endpoint
    raise NotImplementedError


@router.get("/symbols")
async def search_symbols(
    query: str = Query(..., description="Symbol name query"),
    repo_id: Optional[str] = Query(None, description="Repository filter"),
    limit: int = Query(50, ge=1, le=100),
    service: SearchServiceDep = None,
):
    """
    Search for symbols by name.

    Args:
        query: Symbol name
        repo_id: Optional repository filter
        limit: Max results
        service: Search service

    Returns:
        List of matching symbols
    """
    # TODO: Implement symbol search
    raise NotImplementedError
