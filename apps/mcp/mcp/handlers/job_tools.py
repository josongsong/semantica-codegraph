"""
Job Tools (RFC-SEM-022 SOTA MCP Protocol)

비동기 Job 관리 도구.
Heavy 분석을 비동기로 실행하고 폴링/스트리밍으로 결과 조회.

SOTA Features:
- SSE 기반 실시간 스트리밍 (job_streaming.py)
- Async Job 실행 + Progress 추적
- Cancellation 지원
- VerificationSnapshot 통합

Tools:
- job_submit: Job 제출
- job_status: Job 상태 조회
- job_result: Job 결과 조회
- job_cancel: Job 취소
- job_subscribe: Job 스트리밍 구독 (RFC-SEM-022)
"""

import json
from typing import Any

from apps.api.api.routes.rfc.job_streaming import get_job_manager
from apps.mcp.mcp.config import get_job_config
from codegraph_shared.common.observability import get_logger
from codegraph_shared.config import settings

logger = get_logger(__name__)

# Load configuration
JOB_CONFIG = get_job_config()


async def job_submit(arguments: dict[str, Any]) -> str:
    """
    Job 제출 (JobManager 통합)

    Args:
        arguments:
            - tool: 실행할 도구 이름 (analyze_taint, analyze_impact, etc.)
            - args: 도구 인자
            - priority: 우선순위 (low/medium/high/critical)
            - timeout_seconds: 타임아웃 (기본 300)

    Returns:
        JSON: {status, job_id, eta_hint, queue_position}
    """
    tool = arguments.get("tool")
    args = arguments.get("args", {})
    priority = arguments.get("priority", settings.DEFAULT_PRIORITY)
    timeout_seconds = arguments.get("timeout_seconds", settings.DEFAULT_JOB_TIMEOUT)

    if not tool:
        return json.dumps({"status": "error", "error": "tool is required"})

    try:
        manager = get_job_manager()

        # Build spec from tool + args
        spec = {"intent": "analyze", "template_id": tool, "priority": priority, **args}

        job = await manager.create_job(
            job_type="analysis",
            spec=spec,
            timeout_seconds=timeout_seconds,
        )

        logger.info("job_submitted", job_id=job.job_id, tool=tool, priority=priority)

        # Estimate ETA based on tool type
        eta_hint = _estimate_eta(tool)

        return json.dumps(
            {
                "status": "accepted",
                "job_id": job.job_id,
                "eta_hint": eta_hint,
                "queue_position": len(list(manager.list_jobs(status="queued"))),
                "stream_url": f"/api/v1/jobs/{job.job_id}/stream",
            }
        )

    except Exception as e:
        logger.error("job_submit_failed", error=str(e), exc_info=True)
        return json.dumps({"status": "error", "error": str(e)})


async def job_status(arguments: dict[str, Any]) -> str:
    """
    Job 상태 조회

    Args:
        arguments:
            - job_id: Job ID

    Returns:
        JSON: {status, progress, stage, logs_tail}
    """
    job_id = arguments.get("job_id")

    if not job_id:
        return json.dumps({"status": "error", "error": "job_id is required"})

    try:
        manager = get_job_manager()
        job = manager.get(job_id)

        if not job:
            return json.dumps({"status": "error", "error": f"Job not found: {job_id}"})

        return json.dumps(
            {
                "status": job.status,
                "progress": job.progress,
                "stage": _get_stage_from_progress(job.progress),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
        )
    except Exception as e:
        logger.error("job_status_failed", job_id=job_id, error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


async def job_result(arguments: dict[str, Any]) -> str:
    """
    Job 결과 조회

    Args:
        arguments:
            - job_id: Job ID
            - cursor: 페이지네이션 커서 (선택)

    Returns:
        JSON: {status, summary, data, next_cursor}
    """
    job_id = arguments.get("job_id")
    cursor = arguments.get("cursor")

    if not job_id:
        return json.dumps({"status": "error", "error": "job_id is required"})

    try:
        manager = get_job_manager()
        job = manager.get(job_id)

        if not job:
            return json.dumps({"status": "error", "error": f"Job not found: {job_id}"})

        if job.status == "running":
            return json.dumps(
                {
                    "status": "running",
                    "progress": job.progress,
                    "message": "Job still running. Poll again later.",
                }
            )

        if job.status == "failed":
            return json.dumps(
                {
                    "status": "failed",
                    "error": job.error or "Unknown error",
                }
            )

        if job.status == "completed":
            result = job.result or {}

            # Paginate if needed
            if cursor:
                result = _paginate_result(result, cursor)

            return json.dumps(
                {
                    "status": "ok",
                    "summary": result.get("summary", "Analysis completed") if isinstance(result, dict) else "Completed",
                    "data": result,
                    "next_cursor": result.get("next_cursor") if isinstance(result, dict) else None,
                }
            )

        return json.dumps({"status": job.status})

    except Exception as e:
        logger.error("job_result_failed", job_id=job_id, error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


async def job_cancel(arguments: dict[str, Any]) -> str:
    """
    Job 취소

    Args:
        arguments:
            - job_id: Job ID

    Returns:
        JSON: {status}
    """
    job_id = arguments.get("job_id")

    if not job_id:
        return json.dumps({"status": "error", "error": "job_id is required"})

    try:
        manager = get_job_manager()
        cancelled = await manager.cancel_job(job_id)

        if cancelled:
            logger.info("job_cancelled", job_id=job_id)
            return json.dumps({"status": "ok", "message": f"Job {job_id} cancelled"})
        else:
            job = manager.get(job_id)
            if not job:
                return json.dumps({"status": "error", "error": f"Job not found: {job_id}"})
            return json.dumps(
                {
                    "status": "error",
                    "error": f"Cannot cancel job in status: {job.status}",
                }
            )

    except Exception as e:
        logger.error("job_cancel_failed", job_id=job_id, error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


# ============================================================
# Internal helpers
# ============================================================


def _estimate_eta(tool: str) -> str:
    """Estimate ETA based on tool type"""
    heavy_tools = {"analyze_taint", "analyze_impact", "scan_repository", "analyze_slice"}
    medium_tools = {"analyze_cost", "analyze_race"}

    if tool in heavy_tools:
        return "30-120s"
    elif tool in medium_tools:
        return "10-30s"
    else:
        return "5-15s"


def _get_stage_from_progress(progress: float) -> str:
    """Get current execution stage from progress percentage"""
    if progress < 10:
        return "queued"
    elif progress < 30:
        return "initializing"
    elif progress < 50:
        return "loading_data"
    elif progress < 90:
        return "analyzing"
    else:
        return "finalizing"


def _paginate_result(result: dict, cursor: str) -> dict:
    """Paginate large result"""
    # Simple offset-based pagination
    from codegraph_engine.shared_kernel.contracts.pagination import decode_cursor

    try:
        offset, _ = decode_cursor(cursor)
    except ValueError:
        offset = 0

    limit = JOB_CONFIG.default_limit

    # Paginate paths/items if present
    for key in ("paths", "items", "slices", "affected_symbols"):
        if key in result and isinstance(result[key], list):
            items = result[key]
            result[key] = items[offset : offset + limit]

            if offset + limit < len(items):
                from codegraph_engine.shared_kernel.contracts.pagination import encode_cursor

                result["next_cursor"] = encode_cursor(offset + limit)

    return result


# ============================================================
# RFC-SEM-022 SOTA: Streaming Job Support
# ============================================================


async def job_subscribe(arguments: dict[str, Any]) -> str:
    """
    Job 스트리밍 구독 URL 반환 (RFC-SEM-022 SOTA)

    MCP Protocol: resources/subscribe

    Args:
        arguments:
            - job_type: 실행할 분석 타입
            - spec: 분석 스펙 (AnalyzeSpec, etc.)
            - timeout_seconds: 타임아웃

    Returns:
        JSON: {status, job_id, stream_url, message}

    Example:
        {
            "job_type": "analysis",
            "spec": {"intent": "analyze", "template_id": "security_audit", ...}
        }

        Response:
        {
            "status": "created",
            "job_id": "job_abc123",
            "stream_url": "/api/v1/jobs/job_abc123/stream",
            "message": "Subscribe to stream_url for real-time updates"
        }
    """
    job_type = arguments.get("job_type", "analysis")
    spec = arguments.get("spec", {})
    timeout_seconds = arguments.get("timeout_seconds", settings.DEFAULT_JOB_TIMEOUT)

    if not spec:
        return json.dumps({"status": "error", "error": "spec is required"})

    try:
        from apps.api.api.routes.rfc.job_streaming import get_job_manager

        manager = get_job_manager()

        job = await manager.create_job(
            job_type=job_type,
            spec=spec,
            timeout_seconds=timeout_seconds,
        )

        logger.info(
            "job_subscribe_created",
            job_id=job.job_id,
            job_type=job_type,
        )

        return json.dumps(
            {
                "status": "created",
                "job_id": job.job_id,
                "stream_url": f"/api/v1/jobs/{job.job_id}/stream",
                "polling_url": f"/api/v1/jobs/{job.job_id}/status",
                "message": "Subscribe to stream_url for SSE updates, or poll polling_url",
            }
        )

    except Exception as e:
        logger.error("job_subscribe_failed", error=str(e), exc_info=True)
        return json.dumps({"status": "error", "error": str(e)})


async def job_unsubscribe(arguments: dict[str, Any]) -> str:
    """
    Job 스트리밍 구독 해제 (RFC-SEM-022 SOTA)

    MCP Protocol: resources/unsubscribe

    Args:
        arguments:
            - job_id: Job ID

    Returns:
        JSON: {status}
    """
    job_id = arguments.get("job_id")

    if not job_id:
        return json.dumps({"status": "error", "error": "job_id is required"})

    try:
        from apps.api.api.routes.rfc.job_streaming import get_job_manager

        manager = get_job_manager()

        cancelled = await manager.cancel_job(job_id)

        if cancelled:
            return json.dumps({"status": "ok", "message": f"Job {job_id} cancelled"})
        else:
            job = manager.get(job_id)
            if not job:
                return json.dumps({"status": "error", "error": f"Job not found: {job_id}"})
            return json.dumps(
                {
                    "status": "error",
                    "error": f"Cannot cancel job in status: {job.status}",
                }
            )

    except Exception as e:
        logger.error("job_unsubscribe_failed", error=str(e), exc_info=True)
        return json.dumps({"status": "error", "error": str(e)})
