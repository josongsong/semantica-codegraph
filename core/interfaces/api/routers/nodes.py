"""Nodes API Router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/{node_id}")
async def get_node(node_id: str):
    """Get node by ID."""
    # TODO: Implement
    raise NotImplementedError
