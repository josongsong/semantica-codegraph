"""Indexing API schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class IndexRequest(BaseModel):
    """Repository indexing request."""
    repo_path: str = Field(..., description="Path to repository")
    branch: Optional[str] = Field(None, description="Branch to index")
    force: bool = Field(False, description="Force reindex")


class IndexResponse(BaseModel):
    """Indexing response."""
    job_id: str
    status: str
    message: str
