"""Graph API Router - GraphRAG operations."""

from fastapi import APIRouter
from ..dependencies import GraphServiceDep

router = APIRouter()


@router.get("/neighbors/{node_id}")
async def get_neighbors(node_id: str, service: GraphServiceDep):
    """Get neighbors of a node."""
    # TODO: Implement
    raise NotImplementedError


@router.get("/callers/{symbol_id}")
async def get_callers(symbol_id: str, service: GraphServiceDep):
    """Get callers of a symbol."""
    # TODO: Implement
    raise NotImplementedError
