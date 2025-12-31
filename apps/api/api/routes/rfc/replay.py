"""
RFC Replay API (RFC-SEM-022 SOTA)

결정론적 실행 재현 및 Regression Proof.

SOTA Features:
- VerificationSnapshot 기반 결정론 검증
- A/B 비교 (Patchset 적용)
- Regression Proof 통합

Endpoints:
- GET  /replay/{request_id}  - 요청 재현 정보 조회
- POST /replay/{execution_id}/rerun - 실행 재현
- POST /replay/{execution_id}/compare - A/B 비교
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from codegraph_runtime.replay_audit.infrastructure import AuditStore

router = APIRouter()  # No prefix (set by parent)


class ReplayResponse(BaseModel):
    """Replay response"""

    request_id: str
    input_spec: dict
    resolved_spec: dict
    engine_versions: dict
    index_digests: dict
    timestamp: str
    duration_ms: float
    user_id: str | None = None
    session_id: str | None = None


class RerunRequest(BaseModel):
    """Rerun 요청 (RFC-SEM-022)"""

    workspace_id: str | None = Field(None, description="다른 workspace에서 실행 (A/B 비교)")
    force_rerun: bool = Field(False, description="Snapshot 불일치 시에도 강제 실행")


class RerunResponse(BaseModel):
    """Rerun 응답 (RFC-SEM-022)"""

    replay_id: str
    original_execution_id: str
    status: str  # "identical" | "different" | "error"
    findings_diff: dict[str, Any]
    metrics_diff: dict[str, Any]
    new_execution_id: str | None = None
    error: str | None = None


class CompareRequest(BaseModel):
    """A/B 비교 요청 (RFC-SEM-022)"""

    patchset_id: str = Field(..., description="적용할 Patchset ID")


@router.get("/replay/{request_id}", response_model=ReplayResponse)
async def replay(request_id: str) -> ReplayResponse:
    """
    RFC 요청 재현 정보 조회.

    ## Parameters
    - request_id: 요청 ID

    ## Response
    원본 요청의 input_spec, engine_versions, index_digests 등 반환.

    ## Example
    ```
    GET /rfc/replay/req_abc123

    Response:
    {
      "request_id": "req_abc123",
      "input_spec": {...},
      "resolved_spec": {...},
      "engine_versions": {"sccp": "1.2.0"},
      "index_digests": {"chunk_index": "sha256:..."},
      "timestamp": "2025-12-16T10:30:00Z",
      "duration_ms": 234.5
    }
    ```
    """
    store = AuditStore()
    log = await store.get(request_id)

    if not log:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    return ReplayResponse(
        request_id=log.request_id,
        input_spec=log.input_spec,
        resolved_spec=log.resolved_spec,
        engine_versions=log.engine_versions,
        index_digests=log.index_digests,
        timestamp=log.timestamp.isoformat(),
        duration_ms=log.duration_ms,
        user_id=log.user_id,
        session_id=log.session_id,
    )


@router.get("/replay", response_model=list[ReplayResponse])
async def list_replays(limit: int = 100, offset: int = 0) -> list[ReplayResponse]:
    """
    최근 RFC 요청 목록 조회.

    ## Parameters
    - limit: 반환할 개수 (default: 100)
    - offset: 시작 offset (default: 0)

    ## Response
    최근 요청 목록 (timestamp 역순)
    """
    store = AuditStore()
    logs = await store.list(limit=limit, offset=offset)

    return [
        ReplayResponse(
            request_id=log.request_id,
            input_spec=log.input_spec,
            resolved_spec=log.resolved_spec,
            engine_versions=log.engine_versions,
            index_digests=log.index_digests,
            timestamp=log.timestamp.isoformat(),
            duration_ms=log.duration_ms,
            user_id=log.user_id,
            session_id=log.session_id,
        )
        for log in logs
    ]


# ============================================================
# RFC-SEM-022 SOTA: Deterministic Replay Endpoints
# ============================================================


@router.post("/replay/{execution_id}/rerun", response_model=RerunResponse)
async def rerun_execution(
    execution_id: str,
    request: RerunRequest,
) -> RerunResponse:
    """
    실행 재현 (RFC-SEM-022 SOTA).

    결정론적 실행을 보장하기 위해:
    1. 원본 Execution의 VerificationSnapshot 검증
    2. 동일 조건에서 재실행
    3. Regression Proof (Finding 비교)

    ## Parameters
    - execution_id: 재실행할 Execution ID
    - request: RerunRequest (workspace_id, force_rerun)

    ## Response
    - status: "identical" | "different" | "error"
    - findings_diff: 새로 발견/해결된 Finding

    ## Example
    ```
    POST /replay/exec_abc123/rerun
    {"workspace_id": null, "force_rerun": false}

    Response:
    {
      "replay_id": "replay_xyz789",
      "status": "identical",
      "findings_diff": {"new_findings": [], "removed_findings": []},
      ...
    }
    ```
    """
    from codegraph_runtime.replay_audit.application.replay_executor import (
        get_replay_executor,
    )

    executor = get_replay_executor()

    result = await executor.replay(
        execution_id=execution_id,
        workspace_id=request.workspace_id,
        force_rerun=request.force_rerun,
    )

    return RerunResponse(
        replay_id=result.replay_id,
        original_execution_id=result.original_execution_id,
        status=result.status,
        findings_diff=result.findings_diff,
        metrics_diff=result.metrics_diff,
        new_execution_id=result.new_execution_id,
        error=result.error,
    )


@router.post("/replay/{execution_id}/compare", response_model=RerunResponse)
async def compare_with_patch(
    execution_id: str,
    request: CompareRequest,
) -> RerunResponse:
    """
    A/B 비교 - Patchset 적용 후 비교 (RFC-SEM-022 SOTA).

    Agent Verification Loop의 핵심:
    1. Baseline Execution 로드
    2. Patchset 적용한 Workspace 생성
    3. 동일 분석 재실행
    4. Finding 비교 (Regression Proof)

    ## Parameters
    - execution_id: Baseline Execution ID
    - request: CompareRequest (patchset_id)

    ## Response
    - status: "identical" (no regression) | "different" (regression found)
    - findings_diff: 새로 발견/해결된 Finding

    ## Example
    ```
    POST /replay/exec_abc123/compare
    {"patchset_id": "ps_fix001"}

    Response:
    {
      "replay_id": "replay_xyz789",
      "status": "identical",  # No regression!
      "findings_diff": {
        "new_findings": [],
        "removed_findings": [{"type": "sql_injection", ...}]  # Fixed!
      },
      ...
    }
    ```
    """
    from codegraph_runtime.replay_audit.application.replay_executor import (
        get_replay_executor,
    )

    executor = get_replay_executor()

    result = await executor.replay_with_patch(
        execution_id=execution_id,
        patchset_id=request.patchset_id,
    )

    return RerunResponse(
        replay_id=result.replay_id,
        original_execution_id=result.original_execution_id,
        status=result.status,
        findings_diff=result.findings_diff,
        metrics_diff=result.metrics_diff,
        new_execution_id=result.new_execution_id,
        error=result.error,
    )
