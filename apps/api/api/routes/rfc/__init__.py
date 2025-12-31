"""
Analysis API Routes (RESTful Design)

Architecture:
- Resource-oriented (executions, validations, replays)
- Versioned (/api/v1)
- RESTful HTTP methods
- Clear hierarchy

Design Principles:
- SOLID: Single Responsibility per router
- RESTful: Resource-centric URLs
- Versioned: API version in path
- Consistent: Follows OpenAPI best practices

Routes:
- POST   /api/v1/executions/execute      - Execute analysis
- POST   /api/v1/validations/validate    - Validate spec
- POST   /api/v1/plans/plan              - Create plan
- POST   /api/v1/explanations/explain    - Generate explanation
- GET    /api/v1/executions/replay/{id}  - Replay execution
- POST   /api/v1/jobs                    - Submit job
- GET    /api/v1/jobs/{job_id}           - Get job status
- POST   /api/v1/sessions                - Create session
- GET    /api/v1/sessions/{session_id}   - Get session
"""

from fastapi import APIRouter

from .execute import router as execute_router
from .explain import router as explain_router
from .feedback import router as feedback_router
from .job_streaming import router as job_streaming_router
from .jobs import router as jobs_router
from .plan import router as plan_router
from .replay import router as replay_router
from .sessions import router as sessions_router
from .validate import router as validate_router

# ============================================================
# Modern Router - RESTful Design
# ============================================================

# Resource: Executions (통합 엔드포인트)
executions_router = APIRouter(prefix="/api/v1/executions", tags=["Executions (v2)"])

# Merge sub-routers with proper prefixes
executions_router.include_router(execute_router, prefix="", tags=["Executions"])  # POST /api/v1/executions
executions_router.include_router(replay_router, prefix="", tags=["Replays"])  # GET /api/v1/executions/{id}/replay

# Resource: Validations
validations_router = APIRouter(prefix="/api/v1/validations", tags=["Validations (v2)"])
validations_router.include_router(validate_router, prefix="", tags=["Validations"])

# Resource: Plans
plans_router = APIRouter(prefix="/api/v1/plans", tags=["Plans (v2)"])
plans_router.include_router(plan_router, prefix="", tags=["Plans"])

# Resource: Explanations
explanations_router = APIRouter(prefix="/api/v1/explanations", tags=["Explanations (v2)"])
explanations_router.include_router(explain_router, prefix="", tags=["Explanations"])

# Resource: Feedback (NEW)
feedback_router_v2 = APIRouter(prefix="/api/v1", tags=["Feedback (v2)"])
feedback_router_v2.include_router(feedback_router, prefix="", tags=["Feedback"])

# Resource: Sessions (NEW)
sessions_router_v2 = APIRouter(prefix="/api/v1", tags=["Sessions (v2)"])
sessions_router_v2.include_router(sessions_router, prefix="", tags=["Sessions"])

# Resource: Jobs (NEW)
jobs_router_v2 = APIRouter(prefix="/api/v1", tags=["Jobs (v2)"])
jobs_router_v2.include_router(jobs_router, prefix="", tags=["Jobs"])
jobs_router_v2.include_router(job_streaming_router, prefix="", tags=["Job Streaming"])


# ============================================================
# Combined Router
# ============================================================

router = APIRouter()

# Modern API
router.include_router(executions_router)
router.include_router(validations_router)
router.include_router(plans_router)
router.include_router(explanations_router)
router.include_router(feedback_router_v2)
router.include_router(sessions_router_v2)
router.include_router(jobs_router_v2)


__all__ = ["router", "executions_router"]
