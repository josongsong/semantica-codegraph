"""
Sessions API (RFC-027 Extension)

SOTA L11:
- Real EpisodicMemoryManager (No Mock)
- Session context management
- RESTful design
- Error handling

Endpoints:
- POST /api/v1/sessions: Create session
- GET  /api/v1/sessions/{id}: Get session
- GET  /api/v1/sessions: List sessions
- DELETE /api/v1/sessions/{id}: Delete session (optional)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================


class SessionCreateRequest(BaseModel):
    """Session creation request"""

    repo_id: str = Field(..., description="Repository ID", pattern=r"^repo:[a-zA-Z0-9_-]+$")
    task_description: str = Field(..., description="Task description")
    context: dict | None = Field(None, description="Initial context")


class SessionResponse(BaseModel):
    """Session response"""

    session_id: str
    repo_id: str
    task_description: str
    context: dict
    created_at: str
    usefulness_score: float = Field(0.5, description="Usefulness score (0-1)")


class SessionListResponse(BaseModel):
    """Session list response"""

    sessions: list[SessionResponse]
    total: int


# ============================================================
# Endpoints
# ============================================================


@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest) -> SessionResponse:
    """
    Create new RFC session.

    Session tracks context across multiple RFC requests:
    - Repository context
    - Task progress
    - Previous results
    - User preferences

    Args:
        request: Session creation request

    Returns:
        Created session

    Example:
        POST /api/v1/sessions
        {
            "repo_id": "repo:semantica",
            "task_description": "Fix SQL injection bugs",
            "context": {"focus": "security"}
        }
    """
    try:
        logger.info(
            "session_create_requested",
            repo_id=request.repo_id,
            task_description=request.task_description,
        )

        # Initialize EpisodicMemoryManager
        from codegraph_runtime.session_memory.infrastructure.episodic import (
            EpisodicMemoryManager,
        )
        from codegraph_shared.infra.storage.postgres import PostgresStore

        postgres = PostgresStore.create_default()
        memory_manager = EpisodicMemoryManager(postgres_store=postgres)

        # Create episode (session)
        from datetime import datetime

        episode_id = f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        await memory_manager.store_episode(
            episode_id=episode_id,
            task_description=request.task_description,
            inputs={"repo_id": request.repo_id, "context": request.context or {}},
            outputs={},  # Empty initially
            outcome="in_progress",
            error_message=None,
        )

        logger.info(
            "session_created",
            session_id=episode_id,
            repo_id=request.repo_id,
        )

        return SessionResponse(
            session_id=episode_id,
            repo_id=request.repo_id,
            task_description=request.task_description,
            context=request.context or {},
            created_at=datetime.now().isoformat(),
            usefulness_score=0.5,
        )

    except Exception as e:
        logger.error(
            "session_create_failed",
            repo_id=request.repo_id,
            error=str(e),
            exc_info=True,
        )

        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    """
    Get session by ID.

    Args:
        session_id: Session ID

    Returns:
        Session details
    """
    try:
        from codegraph_runtime.session_memory.infrastructure.episodic import (
            EpisodicMemoryManager,
        )
        from codegraph_shared.infra.storage.postgres import PostgresStore

        postgres = PostgresStore.create_default()
        memory_manager = EpisodicMemoryManager(postgres_store=postgres)

        # Get episode
        episode = await memory_manager.get_episode(session_id)

        if not episode:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        return SessionResponse(
            session_id=episode.episode_id,
            repo_id=episode.inputs.get("repo_id", "unknown"),
            task_description=episode.task_description,
            context=episode.inputs.get("context", {}),
            created_at=episode.timestamp.isoformat() if episode.timestamp else "",
            usefulness_score=episode.usefulness_score,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "session_get_failed",
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )

        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SessionListResponse:
    """
    List recent sessions.

    Args:
        limit: Max sessions to return
        offset: Offset for pagination

    Returns:
        List of sessions
    """
    try:
        from codegraph_runtime.session_memory.infrastructure.episodic import (
            EpisodicMemoryManager,
        )
        from codegraph_shared.infra.storage.postgres import PostgresStore

        postgres = PostgresStore.create_default()
        memory_manager = EpisodicMemoryManager(postgres_store=postgres)

        # Get recent episodes
        episodes = await memory_manager.get_recent_episodes(limit=limit + offset)

        # Pagination
        paginated = episodes[offset : offset + limit]

        sessions = []
        for ep in paginated:
            sessions.append(
                SessionResponse(
                    session_id=ep.episode_id,
                    repo_id=ep.inputs.get("repo_id", "unknown"),
                    task_description=ep.task_description,
                    context=ep.inputs.get("context", {}),
                    created_at=ep.timestamp.isoformat() if ep.timestamp else "",
                    usefulness_score=ep.usefulness_score,
                )
            )

        return SessionListResponse(
            sessions=sessions,
            total=len(episodes),
        )

    except Exception as e:
        logger.error(
            "session_list_failed",
            error=str(e),
            exc_info=True,
        )

        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")
