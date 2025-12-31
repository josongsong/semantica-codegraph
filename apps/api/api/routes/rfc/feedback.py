"""
Feedback API (RFC-027 Extension)

SOTA L11:
- Real FeedbackService (No Mock)
- RESTful design
- Pydantic validation
- Error handling

Endpoints:
- POST /api/v1/feedback: Submit feedback
- GET  /api/v1/feedback: List feedback (optional)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================


class FeedbackRequest(BaseModel):
    """Feedback submission request"""

    request_id: str = Field(..., description="Original request ID", pattern=r"^req_[a-zA-Z0-9_-]+$")
    feedback_type: str = Field(..., description="Feedback type: positive, negative, correction")
    rating: int | None = Field(None, ge=1, le=5, description="Rating 1-5")
    details: dict | None = Field(None, description="Additional details")
    comment: str | None = Field(None, description="User comment")


class FeedbackResponse(BaseModel):
    """Feedback submission response"""

    feedback_id: str
    status: str  # "recorded", "processed"
    message: str


# ============================================================
# Endpoints
# ============================================================


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """
    Submit feedback for RFC execution result.

    Used for:
    - RLHF (Reinforcement Learning from Human Feedback)
    - Experience Store improvement
    - Quality monitoring

    Args:
        request: Feedback request

    Returns:
        Feedback confirmation

    Example:
        POST /api/v1/feedback
        {
            "request_id": "req_abc123",
            "feedback_type": "positive",
            "rating": 5,
            "comment": "Perfect analysis!"
        }
    """
    try:
        logger.info(
            "feedback_received",
            request_id=request.request_id,
            feedback_type=request.feedback_type,
            rating=request.rating,
        )

        # Load from AuditStore to get original request
        from codegraph_runtime.replay_audit.infrastructure import AuditStore

        audit_store = AuditStore()
        audit_log = await audit_store.get(request.request_id)

        if not audit_log:
            raise HTTPException(status_code=404, detail=f"Request not found: {request.request_id}")

        # Record feedback in EpisodicMemory
        from codegraph_runtime.session_memory.infrastructure.episodic import (
            EpisodicMemoryManager,
        )
        from codegraph_shared.infra.storage.postgres import PostgresStore

        # Initialize (production setup)
        postgres = PostgresStore.create_default()
        memory_manager = EpisodicMemoryManager(postgres_store=postgres)

        # Record (RLHF-ready)
        await memory_manager.record_feedback(
            episode_id=request.request_id,
            helpful=(request.feedback_type == "positive"),
            user_feedback=request.feedback_type,
        )

        # Also record in ExperienceStore (pattern learning)
        if request.feedback_type in ["positive", "correction"] and audit_log.outputs:
            from apps.orchestrator.orchestrator.experience_store import ExperienceStore

            exp_store = ExperienceStore()

            # Extract task description
            input_spec = audit_log.input_spec
            template_id = input_spec.get("template_id", "unknown")

            # Extract result
            outputs = audit_log.outputs
            summary = outputs.get("summary", "")

            await exp_store.add_experience(
                task_description=f"{template_id}: {summary}",
                error_pattern="",  # No error if positive
                fix_pattern=str(outputs),
                success=(request.feedback_type == "positive"),
            )

        feedback_id = f"fb_{request.request_id[:8]}"

        logger.info(
            "feedback_recorded",
            feedback_id=feedback_id,
            request_id=request.request_id,
            feedback_type=request.feedback_type,
        )

        return FeedbackResponse(
            feedback_id=feedback_id,
            status="recorded",
            message="Feedback recorded successfully for RLHF",
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "feedback_failed",
            request_id=request.request_id,
            error=str(e),
            exc_info=True,
        )

        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")
