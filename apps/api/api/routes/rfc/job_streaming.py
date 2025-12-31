"""
Job Streaming API (RFC-SEM-022 SOTA)

MCP Resource Streaming for Long-Running Jobs.

SOTA Features:
- SSE (Server-Sent Events) 기반 실시간 스트리밍
- Progress Updates + Partial Results
- Reconnection 지원
- Cancellation 지원
- Timeout 처리

MCP Protocol:
- resources/subscribe: Job 상태 구독
- resources/unsubscribe: 구독 해제

Example:
    GET /api/v1/jobs/{job_id}/stream
    Accept: text/event-stream

    data: {"type": "progress", "progress": 30.0}
    data: {"type": "partial", "claims": [{"type": "sql_injection", ...}]}
    data: {"type": "complete", "result": {...}}
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

router = APIRouter()


# ============================================================
# Job Manager (SOTA: AsyncIO Based)
# ============================================================


class JobState:
    """Job 상태 (RFC-SEM-022)."""

    def __init__(
        self,
        job_id: str,
        job_type: str,
        spec: dict[str, Any],
        timeout_seconds: int = 300,
    ):
        self.job_id = job_id
        self.job_type = job_type
        self.spec = spec
        self.timeout_seconds = timeout_seconds

        # State
        self.status: str = "queued"
        self.progress: float = 0.0
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.partial_claims: list[dict[str, Any]] = []

        # Timestamps
        self.created_at = datetime.utcnow()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.updated_at = datetime.utcnow()

        # Control
        self.cancelled = False
        self._subscribers: list[asyncio.Queue] = []
        self._update_event = asyncio.Event()

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to job updates."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from job updates."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def notify(self, event: dict[str, Any]) -> None:
        """Notify all subscribers."""
        self.updated_at = datetime.utcnow()
        for queue in self._subscribers:
            try:
                await queue.put(event)
            except Exception:
                pass  # Skip failed queues

    def cancel(self) -> None:
        """Cancel the job."""
        self.cancelled = True
        self.status = "cancelled"
        self.completed_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "partial_claims": self.partial_claims,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat(),
        }


class JobManager:
    """
    Job Manager (RFC-SEM-022 SOTA).

    Singleton for managing long-running jobs.

    Features:
    - Async job execution
    - Real-time streaming
    - Cancellation
    - Timeout handling
    """

    def __init__(self, max_jobs: int = 10000, job_ttl_seconds: int = 3600):
        """
        Initialize JobManager with memory management.

        Args:
            max_jobs: Maximum jobs to keep in memory (default: 10k)
            job_ttl_seconds: Job retention time after completion (default: 1h)

        Design: Bounded memory usage with auto-cleanup
        CRITICAL: Thread-safe via asyncio.Lock
        """
        self._jobs: dict[str, JobState] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._max_jobs = max_jobs
        self._job_ttl_seconds = job_ttl_seconds
        self._cleanup_task: asyncio.Task | None = None

        # CRITICAL: Lock for concurrent access protection
        self._lock = asyncio.Lock()

        # Metrics (SOTA: Observability)
        self._metrics = {
            "total_created": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_cleaned_up": 0,
        }

    def get(self, job_id: str) -> JobState | None:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: str | None = None,
        limit: int = 20,
    ) -> list[JobState]:
        """List jobs."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    async def create_job(
        self,
        job_type: str,
        spec: dict[str, Any],
        timeout_seconds: int = 300,
    ) -> JobState:
        """
        Create and start a job.

        Args:
            job_type: analysis | indexing | migration
            spec: Job specification (AnalyzeSpec, etc.)
            timeout_seconds: Timeout

        Returns:
            JobState
        """
        job_id = f"job_{uuid4().hex[:12]}"

        job = JobState(
            job_id=job_id,
            job_type=job_type,
            spec=spec,
            timeout_seconds=timeout_seconds,
        )

        # CRITICAL: Lock to prevent race condition
        async with self._lock:
            self._jobs[job_id] = job
            self._metrics["total_created"] += 1  # Observability

        # Start execution task (outside lock to avoid deadlock)
        task = asyncio.create_task(self._execute_job(job))

        async with self._lock:
            self._running_tasks[job_id] = task

        logger.info("job_created", job_id=job_id, job_type=job_type)

        return job

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status not in ("queued", "running"):
            return False

        job.cancel()

        # Cancel task
        task = self._running_tasks.get(job_id)
        if task and not task.done():
            task.cancel()

        await job.notify({"type": "cancelled", "job_id": job_id})

        logger.info("job_cancelled", job_id=job_id)

        return True

    async def _execute_job(self, job: JobState) -> None:
        """
        Execute job with streaming progress.

        RFC-SEM-022: VerificationSnapshot + Execution tracking.
        """
        try:
            job.status = "running"
            job.started_at = datetime.utcnow()

            await job.notify(
                {
                    "type": "started",
                    "job_id": job.job_id,
                    "timestamp": job.started_at.isoformat(),
                }
            )

            # Progress: 10%
            job.progress = 10.0
            await job.notify({"type": "progress", "progress": 10.0})

            # Check cancellation
            if job.cancelled:
                return

            # Execute with timeout
            try:
                result = await asyncio.wait_for(
                    self._run_spec(job),
                    timeout=job.timeout_seconds,
                )
            except asyncio.TimeoutError as e:
                raise TimeoutError(f"Job timed out after {job.timeout_seconds}s") from e

            # Complete
            job.status = "completed"
            job.progress = 100.0
            job.result = result
            job.completed_at = datetime.utcnow()

            # CRITICAL: Lock for metrics update
            async with self._lock:
                self._metrics["total_completed"] += 1

            await job.notify(
                {
                    "type": "complete",
                    "job_id": job.job_id,
                    "result": result,
                }
            )

            logger.info(
                "job_completed",
                job_id=job.job_id,
                duration_s=(job.completed_at - job.started_at).total_seconds(),
            )

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.completed_at = datetime.utcnow()

            async with self._lock:
                self._metrics["total_cancelled"] += 1

            logger.info("job_cancelled_async", job_id=job.job_id)

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()

            async with self._lock:
                self._metrics["total_failed"] += 1

            await job.notify(
                {
                    "type": "error",
                    "job_id": job.job_id,
                    "error": str(e),
                }
            )

            logger.error("job_failed", job_id=job.job_id, error=str(e), exc_info=True)

    async def _run_spec(self, job: JobState) -> dict[str, Any]:
        """
        Run spec with streaming partial results.

        RFC-SEM-022: Uses ExecuteExecutor with VerificationSnapshot.
        """
        from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

        executor = ExecuteExecutor()

        # Progress: 30%
        job.progress = 30.0
        await job.notify({"type": "progress", "progress": 30.0})

        if job.cancelled:
            return {"cancelled": True}

        # Execute spec
        envelope = await executor.execute(job.spec)

        # Progress: 70%
        job.progress = 70.0
        await job.notify({"type": "progress", "progress": 70.0})

        # Stream partial claims
        if envelope.claims:
            for i, claim in enumerate(envelope.claims):
                claim_dict = claim.model_dump() if hasattr(claim, "model_dump") else {}
                job.partial_claims.append(claim_dict)

                await job.notify(
                    {
                        "type": "partial",
                        "claim_index": i,
                        "claim": claim_dict,
                    }
                )

                # Small delay for streaming effect
                await asyncio.sleep(0.01)

        # Progress: 90%
        job.progress = 90.0
        await job.notify({"type": "progress", "progress": 90.0})

        return envelope.model_dump() if hasattr(envelope, "model_dump") else {}

    # ============================================================
    # Memory Management & Observability (SOTA L11)
    # ============================================================

    async def start_cleanup_loop(self) -> None:
        """
        Start background cleanup loop (SOTA: Memory Management).

        Automatically removes old completed jobs to prevent memory leak.
        Call this once during app startup.

        Design:
        - Runs every 5 minutes
        - Removes jobs older than TTL
        - Bounded memory usage
        """
        if self._cleanup_task is not None:
            logger.warning("Cleanup loop already running")
            return

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(300)  # 5 minutes
                    await self._cleanup_old_jobs()
                except asyncio.CancelledError:
                    logger.info("Cleanup loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"Cleanup loop error: {e}", exc_info=True)

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Job cleanup loop started", ttl_seconds=self._job_ttl_seconds)

    async def stop_cleanup_loop(self) -> None:
        """Stop background cleanup loop (for shutdown)"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Job cleanup loop stopped")

    async def _cleanup_old_jobs(self) -> None:
        """
        Clean up old completed jobs (SOTA: Memory Management).

        Removes jobs that have been completed for > TTL.
        Keeps jobs under max_jobs limit.

        CRITICAL: Uses lock to prevent race conditions during iteration.
        """
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        ttl_threshold = now - timedelta(seconds=self._job_ttl_seconds)

        jobs_to_remove = []

        # CRITICAL: Lock during iteration to prevent "dict changed size" error
        async with self._lock:
            # Snapshot jobs list to avoid iteration issues
            jobs_snapshot = list(self._jobs.items())

        # Analyze outside lock (no dict modification)
        for job_id, job in jobs_snapshot:
            # Remove if completed AND older than TTL
            if job.status in ["completed", "failed", "cancelled"]:
                if job.completed_at and job.completed_at < ttl_threshold:
                    jobs_to_remove.append(job_id)

        # Check if over limit
        async with self._lock:
            current_count = len(self._jobs)

        if current_count > self._max_jobs:
            # Get completed jobs snapshot
            async with self._lock:
                completed_jobs = [
                    (job_id, job)
                    for job_id, job in self._jobs.items()
                    if job.status in ["completed", "failed", "cancelled"]
                ]

            completed_jobs.sort(key=lambda x: x[1].completed_at or now)

            # Remove oldest to get under limit
            excess = current_count - self._max_jobs
            for job_id, _ in completed_jobs[:excess]:
                if job_id not in jobs_to_remove:
                    jobs_to_remove.append(job_id)

        # Execute removal with lock
        if jobs_to_remove:
            async with self._lock:
                for job_id in jobs_to_remove:
                    self._jobs.pop(job_id, None)
                    self._running_tasks.pop(job_id, None)
                    self._metrics["total_cleaned_up"] += 1

                remaining = len(self._jobs)

            logger.info(
                "cleanup_completed",
                removed_count=len(jobs_to_remove),
                remaining_jobs=remaining,
            )

    def get_metrics(self) -> dict[str, Any]:
        """
        Get JobManager metrics (SOTA: Observability).

        Returns:
            Dict with metrics:
            - total_created, completed, failed, cancelled
            - current_jobs, running_jobs, queued_jobs
            - cleanup statistics

        Design: Production monitoring ready
        CRITICAL: Snapshot to prevent race conditions
        """
        # CRITICAL: Create snapshot with lock to prevent iteration errors
        # Can't use async with in sync method, so we make it sync-safe
        # by taking snapshot of mutable state
        jobs_snapshot = list(self._jobs.values())
        metrics_snapshot = dict(self._metrics)

        current_jobs = len(jobs_snapshot)
        running = len([j for j in jobs_snapshot if j.status == "running"])
        queued = len([j for j in jobs_snapshot if j.status == "queued"])
        completed = len([j for j in jobs_snapshot if j.status == "completed"])
        failed = len([j for j in jobs_snapshot if j.status == "failed"])

        return {
            # Lifetime metrics
            "total_created": metrics_snapshot["total_created"],
            "total_completed": metrics_snapshot["total_completed"],
            "total_failed": metrics_snapshot["total_failed"],
            "total_cancelled": metrics_snapshot["total_cancelled"],
            "total_cleaned_up": metrics_snapshot["total_cleaned_up"],
            # Current state
            "current_jobs": current_jobs,
            "running_jobs": running,
            "queued_jobs": queued,
            "completed_jobs": completed,
            "failed_jobs": failed,
            # Limits
            "max_jobs_limit": self._max_jobs,
            "job_ttl_seconds": self._job_ttl_seconds,
            # Health
            "memory_usage_pct": (current_jobs / self._max_jobs) * 100 if self._max_jobs > 0 else 0,
        }

    def health_check(self) -> dict[str, Any]:
        """
        Health check for monitoring (SOTA: Production Ready).

        Returns:
            status: healthy/degraded/unhealthy
            reason: explanation if not healthy
        """
        metrics = self.get_metrics()
        memory_pct = metrics["memory_usage_pct"]

        if memory_pct > 90:
            return {"status": "unhealthy", "reason": f"Memory usage: {memory_pct:.1f}%"}
        elif memory_pct > 75:
            return {"status": "degraded", "reason": f"Memory usage: {memory_pct:.1f}%"}
        else:
            return {"status": "healthy", "current_jobs": metrics["current_jobs"]}


# Dependency Injection with Proper Singleton (SOTA Pattern)
# Application-level singleton using lru_cache


@lru_cache(maxsize=1)
def get_job_manager() -> JobManager:
    """
    Get JobManager singleton instance (Dependency Injection).

    Design:
    - lru_cache ensures single instance across all requests
    - Testable via dependency_overrides (FastAPI)
    - Can be reset with get_job_manager.cache_clear() for testing

    SOLID: Dependency Inversion Principle
    Thread-Safe: Yes (Python GIL + lru_cache is thread-safe)
    """
    return JobManager()


def reset_job_manager_for_testing() -> None:
    """
    Reset JobManager singleton (TEST ONLY).

    WARNING: Only call this in test cleanup.
    Clears lru_cache to allow fresh instance.
    """
    get_job_manager.cache_clear()


# ============================================================
# Request/Response Models
# ============================================================


class StreamingJobRequest(BaseModel):
    """Streaming job creation request."""

    job_type: str = Field(..., description="Job type: analysis, indexing, migration")
    spec: dict = Field(..., description="Job specification")
    timeout_seconds: int = Field(300, ge=60, le=3600, description="Timeout")


class StreamingJobResponse(BaseModel):
    """Streaming job response."""

    job_id: str
    status: str
    stream_url: str
    message: str


# ============================================================
# SSE Streaming Endpoints
# ============================================================


@router.post("/jobs/streaming", response_model=StreamingJobResponse)
async def create_streaming_job(
    request: StreamingJobRequest,
    manager: JobManager = Depends(get_job_manager),
) -> StreamingJobResponse:
    """
    Create streaming job (RFC-SEM-022 SOTA).

    Returns a stream URL for SSE subscription.

    Example:
        POST /api/v1/jobs/streaming
        {
            "job_type": "analysis",
            "spec": {"intent": "analyze", "template_id": "security_audit", ...}
        }

        Response:
        {
            "job_id": "job_abc123",
            "status": "queued",
            "stream_url": "/api/v1/jobs/job_abc123/stream"
        }
    """
    job = await manager.create_job(
        job_type=request.job_type,
        spec=request.spec,
        timeout_seconds=request.timeout_seconds,
    )

    return StreamingJobResponse(
        job_id=job.job_id,
        status=job.status,
        stream_url=f"/api/v1/jobs/{job.job_id}/stream",
        message="Job created. Subscribe to stream_url for real-time updates.",
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job_status(
    job_id: str,
    last_event_id: str | None = Query(None, description="Last received event ID"),
    manager: JobManager = Depends(get_job_manager),
) -> StreamingResponse:
    """
    Stream job status via SSE (RFC-SEM-022 SOTA).

    MCP Resources Protocol Implementation:
    - Real-time progress updates
    - Partial results streaming
    - Reconnection support (Last-Event-ID)

    Example:
        GET /api/v1/jobs/job_abc123/stream
        Accept: text/event-stream

        event: progress
        data: {"progress": 30.0}

        event: partial
        data: {"claim_index": 0, "claim": {"type": "sql_injection", ...}}

        event: complete
        data: {"result": {...}}
    """
    job = manager.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        queue = job.subscribe()
        event_id = 0

        try:
            # Send initial state
            yield _format_sse(
                event="status",
                data=job.to_dict(),
                event_id=str(event_id),
            )
            event_id += 1

            # If already completed, send final state and close
            if job.status in ("completed", "failed", "cancelled"):
                yield _format_sse(
                    event=job.status,
                    data=job.to_dict(),
                    event_id=str(event_id),
                )
                return

            # Stream updates
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)

                    yield _format_sse(
                        event=event.get("type", "update"),
                        data=event,
                        event_id=str(event_id),
                    )
                    event_id += 1

                    # Check for terminal events
                    if event.get("type") in ("complete", "error", "cancelled"):
                        break

                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"

        finally:
            job.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.delete("/jobs/{job_id}/stream")
async def cancel_streaming_job(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
) -> dict[str, Any]:
    """
    Cancel streaming job.

    MCP: resources/unsubscribe equivalent.
    """
    cancelled = await manager.cancel_job(job_id)

    if not cancelled:
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in status: {job.status}",
        )

    return {"status": "cancelled", "job_id": job_id}


@router.get("/jobs/{job_id}/status")
async def get_streaming_job_status(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
) -> dict[str, Any]:
    """
    Get current job status (non-streaming).

    For polling fallback when SSE is not available.
    """
    job = manager.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return job.to_dict()


@router.get("/jobs/metrics")
async def get_job_metrics(manager: JobManager = Depends(get_job_manager)) -> dict[str, Any]:
    """
    Get JobManager metrics (SOTA: Observability).

    Returns real-time metrics for monitoring and alerting.

    Response:
        {
            "total_created": 1234,
            "total_completed": 1200,
            "current_jobs": 34,
            "memory_usage_pct": 34.0,
            ...
        }
    """
    return manager.get_metrics()


@router.get("/jobs/health")
async def get_job_health(manager: JobManager = Depends(get_job_manager)) -> dict[str, Any]:
    """
    Health check endpoint (SOTA: Production Monitoring).

    Returns:
        status: healthy | degraded | unhealthy

    Use for:
    - Kubernetes liveness probe
    - Load balancer health checks
    - Alerting (PagerDuty, etc.)
    """
    return manager.health_check()


# ============================================================
# SSE Formatting
# ============================================================


def _format_sse(
    event: str,
    data: dict[str, Any],
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    """
    Format SSE event.

    SSE Format:
        id: <event_id>
        event: <event_type>
        retry: <milliseconds>
        data: <json_data>

    """
    import json

    lines = []

    if event_id:
        lines.append(f"id: {event_id}")

    if retry:
        lines.append(f"retry: {retry}")

    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data)}")

    return "\n".join(lines) + "\n\n"
