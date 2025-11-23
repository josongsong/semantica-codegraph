"""Chunks API Router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/{chunk_id}")
async def get_chunk(chunk_id: str):
    """Get chunk by ID."""
    # TODO: Implement
    raise NotImplementedError
