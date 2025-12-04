"""Search log data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class SearchLog(BaseModel):
    """검색 로그 스키마."""

    log_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Query context
    query: str
    intent: str | None = None
    repo_id: str
    user_id: str | None = None
    session_id: str | None = None

    # Retrieval details
    candidate_count: int | None = None
    fusion_strategy: str | None = None

    # Late Interaction
    late_interaction_enabled: bool = False
    max_sim_scores: list[float] | None = None

    # Results
    top_k: int | None = None
    result_chunk_ids: list[str] = Field(default_factory=list)
    result_scores: list[float] = Field(default_factory=list)

    # User feedback
    clicked_rank: int | None = None
    clicked_chunk_id: str | None = None
    dwell_time: float | None = None
    was_helpful: bool | None = None

    # Metadata
    metadata: dict | None = None
