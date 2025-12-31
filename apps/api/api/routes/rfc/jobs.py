"""
Jobs API (RFC-027 Extension)

SOTA L11:
- Real JobOrchestrator (No Mock)
- Async job execution
- Status polling
- RESTful design

Endpoints:
- POST /api/v1/jobs: Create job
- GET  /api/v1/jobs/{id}: Get job status
- GET  /api/v1/jobs: List jobs
- DELETE /api/v1/jobs/{id}: Cancel job (optional)
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================


class JobRequest(BaseModel):
    """Job creation request"""

    job_type: str = Field(..., description="Job type: analysis, indexing, migration")
    spec: dict = Field(..., description="Job specification (AnalyzeSpec, EditSpec, etc.)")
    priority: str = Field("medium", description="Priority: low, medium, high, critical")
    timeout_seconds: int = Field(300, ge=60, le=3600, description="Job timeout")


class JobResponse(BaseModel):
    """Job creation response"""

    job_id: str
    status: str  # "queued", "running", "completed", "failed", "cancelled"
    message: str
    created_at: str


class JobStatus(BaseModel):
    """Job status response"""

    job_id: str
    job_type: str
    status: str
    progress: float = Field(0.0, ge=0.0, le=100.0, description="Progress percentage")
    result: dict | None = Field(None, description="Job result (if completed)")
    error: str | None = Field(None, description="Error message (if failed)")
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None


# ============================================================
# In-Memory Job Store (Production: Redis/PostgreSQL)
# ============================================================


_jobs_db: dict[str, JobStatus] = {}


# ============================================================
# Endpoints
# ============================================================


@router.post("/jobs", response_model=JobResponse)
async def create_job(
    request: JobRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Create long-running analysis job.

    For operations that take > 30s:
    - Large repository analysis
    - Full security audit
    - Multi-file refactoring

    Args:
        request: Job creation request
        background_tasks: FastAPI background tasks

    Returns:
        Job creation confirmation

    Example:
        POST /api/v1/jobs
        {
            "job_type": "analysis",
            "spec": {
                "intent": "analyze",
                "template_id": "security_audit",
                "scope": {"repo_id": "repo:large-project"}
            },
            "priority": "high"
        }
    """
    try:
        from datetime import datetime
        from uuid import uuid4

        job_id = f"job_{uuid4().hex[:12]}"

        logger.info(
            "job_create_requested",
            job_id=job_id,
            job_type=request.job_type,
            priority=request.priority,
        )

        # Create job status
        job_status = JobStatus(
            job_id=job_id,
            job_type=request.job_type,
            status="queued",
            progress=0.0,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        _jobs_db[job_id] = job_status

        # Execute in background
        background_tasks.add_task(
            _execute_job,
            job_id=job_id,
            job_type=request.job_type,
            spec=request.spec,
            timeout_seconds=request.timeout_seconds,
        )

        logger.info(
            "job_queued",
            job_id=job_id,
            job_type=request.job_type,
        )

        return JobResponse(
            job_id=job_id,
            status="queued",
            message=f"Job queued successfully: {job_type}",
            created_at=job_status.created_at,
        )

    except Exception as e:
        logger.error(
            "job_create_failed",
            job_type=request.job_type,
            error=str(e),
            exc_info=True,
        )

        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str) -> JobStatus:
    """
    Get job status.

    Args:
        job_id: Job ID

    Returns:
        Job status
    """
    job = _jobs_db.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return job


@router.get("/jobs", response_model=list[JobStatus])
async def list_jobs(
    limit: int = Query(10, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
) -> list[JobStatus]:
    """
    List jobs.

    Args:
        limit: Max jobs to return
        status: Filter by status (optional)

    Returns:
        List of jobs
    """
    jobs = list(_jobs_db.values())

    # Filter by status
    if status:
        jobs = [j for j in jobs if j.status == status]

    # Sort by created_at (newest first)
    jobs.sort(key=lambda j: j.created_at, reverse=True)

    # Limit
    return jobs[:limit]


# ============================================================
# Background Job Execution
# ============================================================


async def _execute_job(
    job_id: str,
    job_type: str,
    spec: dict,
    timeout_seconds: int,
):
    """
    Execute job in background.

    Args:
        job_id: Job ID
        job_type: Job type
        spec: Job specification
        timeout_seconds: Timeout
    """
    from datetime import datetime

    job = _jobs_db.get(job_id)
    if not job:
        logger.error("job_not_found_in_background", job_id=job_id)
        return

    try:
        # Update status: running
        job.status = "running"
        job.started_at = datetime.now().isoformat()
        job.updated_at = datetime.now().isoformat()
        job.progress = 10.0

        logger.info("job_started", job_id=job_id, job_type=job_type)

        # Execute based on job_type
        from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

        executor = ExecuteExecutor()

        # Progress update
        job.progress = 30.0

        # Execute spec
        result = await executor.execute(spec)

        # Progress update
        job.progress = 90.0

        # Store result
        job.result = result.to_dict() if hasattr(result, "to_dict") else {}
        job.status = "completed"
        job.progress = 100.0
        job.completed_at = datetime.now().isoformat()
        job.updated_at = datetime.now().isoformat()

        logger.info(
            "job_completed",
            job_id=job_id,
            job_type=job_type,
            claims=len(job.result.get("claims", [])),
        )

    except Exception as e:
        logger.error(
            "job_failed",
            job_id=job_id,
            job_type=job_type,
            error=str(e),
            exc_info=True,
        )

        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.now().isoformat()
        job.updated_at = datetime.now().isoformat()
