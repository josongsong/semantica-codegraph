"""Repository API schemas."""

from typing import List
from pydantic import BaseModel, Field


class RepoSchema(BaseModel):
    """Placeholder for repository schemas."""
    pass


class RepoMapRequest(BaseModel):
    """Request schema for repository map generation."""
    token_budget: int = Field(
        default=8000,
        ge=1000,
        le=100000,
        description="Maximum token budget for the repository map"
    )


class RepoMapNodeSchema(BaseModel):
    """
    Repository map node schema.

    Represents a single node in the hierarchical repository structure.
    """
    node_id: str = Field(..., description="Unique node identifier")
    label: str = Field(..., description="Human-readable label")
    node_type: str = Field(..., description="Node type (repository, project, file, symbol, etc.)")
    importance_score: float = Field(..., description="Importance score (0-1)")
    token_estimate: int = Field(..., description="Estimated token count for this node")
    children: List["RepoMapNodeSchema"] = Field(
        default_factory=list,
        description="Child nodes in the hierarchy"
    )


class RepoMapResponse(BaseModel):
    """Response schema for repository map."""
    repo_id: str = Field(..., description="Repository identifier")
    root: RepoMapNodeSchema = Field(..., description="Root node of the repository map")
    total_tokens: int = Field(..., description="Total tokens in the map")
    nodes_included: int = Field(..., description="Number of nodes included in the map")
