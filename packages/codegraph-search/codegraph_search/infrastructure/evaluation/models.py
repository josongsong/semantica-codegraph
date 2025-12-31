"""
Evaluation Data Models

Models for golden set queries, feedback logs, and evaluation results.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    """Query intent categories for stratified evaluation."""

    FIND_DEFINITION = "find_definition"
    FIND_REFERENCES = "find_references"
    FIND_IMPLEMENTATIONS = "find_implementations"
    UNDERSTAND_FLOW = "understand_flow"
    FIND_RELATED = "find_related"
    EXPLORE_API = "explore_api"
    DEBUG_ISSUE = "debug_issue"
    REFACTOR_ANALYSIS = "refactor_analysis"


class QueryDifficulty(str, Enum):
    """Query difficulty levels."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class QuerySource(str, Enum):
    """How the query was created."""

    MANUAL = "manual"
    AUTO_GENERATED = "auto_generated"
    USER_FEEDBACK = "user_feedback"
    IR_BASED = "ir_based"
    GRAPH_BASED = "graph_based"


class AnnotationQuality(str, Enum):
    """Quality level of ground truth annotation."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    GOLD_STANDARD = "gold_standard"


class FeedbackAction(str, Enum):
    """User feedback actions."""

    CLICKED = "clicked"
    COPIED = "copied"
    DISMISSED = "dismissed"
    UPVOTED = "upvoted"
    DOWNVOTED = "downvoted"
    MARKED_RELEVANT = "marked_relevant"
    MARKED_IRRELEVANT = "marked_irrelevant"
    REPORTED_MISSING = "reported_missing"
    REPORTED_WRONG = "reported_wrong"


class GoldenSetQuery(BaseModel):
    """
    Golden set evaluation query with ground truth.

    Used for measuring retrieval quality (MRR, nDCG, P@5, R@20).
    """

    query_id: UUID = Field(default_factory=uuid4)
    query: str
    intent: QueryIntent
    relevant_chunk_ids: list[str]  # Ground truth chunk IDs

    # Metadata
    difficulty: QueryDifficulty = QueryDifficulty.MEDIUM
    source: QuerySource = QuerySource.MANUAL
    repo_id: str | None = None

    # Quality tracking
    annotation_quality: AnnotationQuality = AnnotationQuality.UNVERIFIED
    annotator_id: str | None = None
    review_notes: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Usage tracking
    evaluation_count: int = 0
    last_evaluated_at: datetime | None = None

    model_config = {"use_enum_values": True}


class FeedbackInput(BaseModel):
    """
    Input data for creating user feedback.

    Contains only user-provided fields. Auto-generated fields (feedback_id,
    timestamp, processed, golden_set_candidate) are handled by FeedbackLog.

    Usage:
        # Create input from individual params or request body
        feedback_input = FeedbackInput(
            query="...",
            retrieved_chunk_ids=[...],
            action=FeedbackAction.CLICKED,
            repo_id="...",
        )
        # Pass to service
        await service.log_feedback(feedback_input)
    """

    # Required fields
    query: str
    retrieved_chunk_ids: list[str]
    action: FeedbackAction
    repo_id: str

    # Optional user context
    user_id: str | None = None
    session_id: str | None = None

    # Optional query information
    query_intent: str | None = None

    # Optional retrieval details
    retrieval_scores: dict[str, float] | None = None  # chunk_id → score
    retrieval_metadata: dict[str, Any] | None = None

    # Optional feedback details
    target_chunk_ids: list[str] | None = None  # Which chunks feedback applies to
    feedback_text: str | None = None

    # Optional context
    file_context: str | None = None
    query_duration_ms: int | None = None

    model_config = {"use_enum_values": True}

    def to_feedback_log(self) -> "FeedbackLog":
        """Convert input to FeedbackLog with auto-generated fields."""
        return FeedbackLog(
            query=self.query,
            retrieved_chunk_ids=self.retrieved_chunk_ids,
            action=self.action,
            repo_id=self.repo_id,
            user_id=self.user_id,
            session_id=self.session_id,
            query_intent=self.query_intent,
            retrieval_scores=self.retrieval_scores,
            retrieval_metadata=self.retrieval_metadata,
            target_chunk_ids=self.target_chunk_ids,
            feedback_text=self.feedback_text,
            file_context=self.file_context,
            query_duration_ms=self.query_duration_ms,
        )


class FeedbackLog(BaseModel):
    """
    User feedback on retrieval results.

    Captures user interactions for continuous improvement and golden set generation.
    """

    feedback_id: UUID = Field(default_factory=uuid4)

    # User context
    user_id: str | None = None
    session_id: str | None = None

    # Query information
    query: str
    query_intent: str | None = None

    # Retrieved results
    retrieved_chunk_ids: list[str]
    retrieval_scores: dict[str, float] | None = None  # chunk_id → score
    retrieval_metadata: dict[str, Any] | None = None

    # User feedback
    action: FeedbackAction
    target_chunk_ids: list[str] | None = None  # Which chunks feedback applies to
    feedback_text: str | None = None

    # Context
    repo_id: str
    file_context: str | None = None

    # Timing
    timestamp: datetime = Field(default_factory=datetime.now)
    query_duration_ms: int | None = None

    # Processing status
    processed: bool = False
    processed_at: datetime | None = None
    golden_set_candidate: bool = False

    model_config = {"use_enum_values": True}


class EvaluationMetrics(BaseModel):
    """Evaluation metrics for a single query or aggregate."""

    mrr: float  # Mean Reciprocal Rank (target: > 0.8)
    ndcg: float  # Normalized Discounted Cumulative Gain
    precision_at_5: float  # Precision@5
    recall_at_20: float  # Recall@20

    # Optional per-query details
    rank_of_first_relevant: int | None = None  # For MRR
    num_relevant_retrieved: int | None = None  # For precision/recall
    total_relevant: int | None = None  # For recall


class EvaluationResult(BaseModel):
    """
    Evaluation result for tracking retriever performance over time.

    Stores aggregate metrics and per-query details.
    """

    eval_id: UUID = Field(default_factory=uuid4)

    # Evaluation metadata
    eval_name: str
    eval_timestamp: datetime = Field(default_factory=datetime.now)
    retriever_config: dict[str, Any]  # Retriever configuration tested

    # Query set metadata
    query_set_size: int
    query_intents: dict[str, int] | None = None  # Intent distribution

    # Aggregate metrics (Phase 1 targets)
    mrr: float
    ndcg: float
    precision_at_5: float
    recall_at_20: float

    # Stratified metrics
    metrics_by_intent: dict[str, dict[str, float]] | None = None
    metrics_by_difficulty: dict[str, dict[str, float]] | None = None

    # Per-query results (for debugging)
    detailed_results: list[dict[str, Any]] | None = None

    # Comparison
    baseline_eval_id: UUID | None = None
    improvement_summary: str | None = None

    # Status
    is_production: bool = False
    notes: str | None = None
