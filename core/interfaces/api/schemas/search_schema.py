"""Search API schemas."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search request schema."""

    query: str = Field(..., description="Search query")
    limit: int = Field(10, ge=1, le=100, description="Max results")
    filters: Optional[dict[str, Any]] = Field(None, description="Metadata filters")
    use_hybrid: bool = Field(True, description="Use hybrid search")


class SearchResultItem(BaseModel):
    """Single search result."""

    chunk_id: str
    score: float
    content: str
    file_path: str
    uri: str
    language: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search response schema."""

    results: list[SearchResultItem]
    total: int
    query: str
