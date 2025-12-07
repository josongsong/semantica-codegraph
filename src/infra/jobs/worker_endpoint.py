"""
SemanticaTask Worker Endpoint.

SemanticaTask Daemon이 Job 실행 시 호출하는 HTTP endpoint.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.infra.jobs.handler import JobResult
from src.infra.jobs.semantica_adapter import SemanticaAdapter
from src.infra.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/worker", tags=["worker"])


class ExecuteJobRequest(BaseModel):
    """Job 실행 요청."""

    job_id: str
    job_type: str
    payload: dict[str, Any]


class ExecuteJobResponse(BaseModel):
    """Job 실행 응답."""

    job_id: str
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


# Global adapter (DI 컨테이너에서 주입)
_adapter: SemanticaAdapter | None = None


def set_adapter(adapter: SemanticaAdapter) -> None:
    """Adapter 설정 (앱 시작 시 호출)."""
    global _adapter
    _adapter = adapter


@router.post("/execute", response_model=ExecuteJobResponse)
async def execute_job(request: ExecuteJobRequest) -> ExecuteJobResponse:
    """
    Job 실행 (SemanticaTask Daemon이 호출).

    Flow:
    1. Daemon이 Job 실행 시점에 이 endpoint 호출
    2. Adapter가 Handler 찾아서 실행
    3. 결과 반환

    Example Request:
        POST /worker/execute
        {
            "job_id": "c4b2bb3a-...",
            "job_type": "INDEX_FILE",
            "payload": {"repo_path": "/path", "repo_id": "repo123"}
        }

    Example Response:
        {
            "job_id": "c4b2bb3a-...",
            "success": true,
            "data": {"files_processed": 42}
        }
    """
    if not _adapter:
        raise HTTPException(status_code=500, detail="Adapter not initialized")

    logger.info(
        "worker_execute_request",
        job_id=request.job_id,
        job_type=request.job_type,
    )

    result: JobResult = await _adapter.execute_handler(
        job_id=request.job_id,
        job_type=request.job_type,
        payload=request.payload,
    )

    return ExecuteJobResponse(
        job_id=request.job_id,
        success=result.success,
        data=result.data,
        error=result.error,
    )
