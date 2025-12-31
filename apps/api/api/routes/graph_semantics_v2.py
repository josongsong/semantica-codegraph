"""
Graph Semantics API V2 (RFC-052)

RFC-052: MCP Service Layer Architecture
API endpoints using Clean Architecture UseCases.

Changes from V1:
- ❌ Direct Infrastructure/Handler calls
- ✅ UseCase orchestration
- ✅ VerificationSnapshot in responses
- ✅ Evidence references

Endpoints:
- POST /graph/v2/slice
- POST /graph/v2/dataflow
"""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/graph/v2", tags=["Graph Semantics V2 (RFC-052)"])


# ============================================================
# Request/Response Models (API Layer)
# ============================================================


class SliceRequestAPI(BaseModel):
    """Slice API request (external boundary - strings)"""

    anchor: str = Field(..., description="앵커 심볼")
    direction: Literal["backward", "forward", "both"] = Field("backward")
    max_depth: int = Field(5, ge=1, le=20)
    max_lines: int = Field(100, ge=10, le=500)
    session_id: str | None = Field(None, description="세션 ID")
    repo_id: str = Field("default", description="리포지토리 ID")
    file_scope: str | None = Field(None, description="파일 제한")


class CodeFragmentAPI(BaseModel):
    """Code fragment (API response)"""

    file_path: str
    start_line: int
    end_line: int
    code: str


class VerificationSnapshotAPI(BaseModel):
    """Verification snapshot (API response)"""

    snapshot_id: str
    engine_version: str
    queryplan_hash: str
    executed_at: str


class EvidenceRefAPI(BaseModel):
    """Evidence reference (API response)"""

    evidence_id: str
    kind: str
    created_at: str


class SliceResponseAPI(BaseModel):
    """Slice API response"""

    verification: VerificationSnapshotAPI
    anchor: str
    direction: str
    fragments: list[CodeFragmentAPI]
    total_lines: int
    total_nodes: int
    evidence_ref: EvidenceRefAPI | None = None
    error: dict | None = None


class DataflowRequestAPI(BaseModel):
    """Dataflow API request"""

    source: str = Field(..., description="소스 심볼")
    sink: str = Field(..., description="싱크 심볼")
    policy: str | None = Field(None, description="정책")
    file_path: str | None = Field(None, description="파일 제한")
    session_id: str | None = None
    repo_id: str = Field("default")
    max_depth: int = Field(10, ge=1, le=20)


class DataflowResponseAPI(BaseModel):
    """Dataflow API response"""

    verification: VerificationSnapshotAPI
    source: str
    sink: str
    reachable: bool
    paths: list[dict]
    sanitizers: list[str]
    policy: str | None = None
    evidence_ref: EvidenceRefAPI | None = None
    error: dict | None = None


# ============================================================
# Endpoints
# ============================================================


@router.post("/slice", response_model=SliceResponseAPI)
async def slice_endpoint(request: SliceRequestAPI):
    """
    Semantic Slicing (RFC-052).

    Returns minimal code relevant to anchor point.
    Includes VerificationSnapshot for reproducibility.
    """
    try:
        from codegraph_shared.container import container
        from codegraph_engine.code_foundation.application.usecases import SliceRequest
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        # Convert API request to UseCase request
        usecase_request = SliceRequest(
            anchor=request.anchor,
            direction=request.direction,
            max_depth=request.max_depth,
            max_lines=request.max_lines,
            session_id=request.session_id,
            repo_id=request.repo_id,
            file_scope=request.file_scope,
        )

        # Get UseCase from container
        ir_doc = IRDocument(repo_id=request.repo_id, snapshot_id="temp")
        slice_usecase = container._foundation.create_slice_usecase(ir_doc)

        # Execute
        response = await slice_usecase.execute(usecase_request)

        # Convert to API response
        return SliceResponseAPI(
            verification=VerificationSnapshotAPI(**response.verification.to_dict()),
            anchor=response.anchor,
            direction=response.direction,
            fragments=[
                CodeFragmentAPI(
                    file_path=f.file_path,
                    start_line=f.start_line,
                    end_line=f.end_line,
                    code=f.code,
                )
                for f in (response.fragments or [])
            ],
            total_lines=response.total_lines,
            total_nodes=response.total_nodes,
            evidence_ref=EvidenceRefAPI(**response.evidence_ref.to_dict()) if response.evidence_ref else None,
            error=response.error.to_dict() if response.error else None,
        )

    except Exception as e:
        logger.error("slice_endpoint_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dataflow", response_model=DataflowResponseAPI)
async def dataflow_endpoint(request: DataflowRequestAPI):
    """
    Dataflow Analysis (RFC-052).

    Proves source → sink reachability.
    Includes VerificationSnapshot and Evidence.
    """
    try:
        from codegraph_shared.container import container
        from codegraph_engine.code_foundation.application.usecases import DataflowRequest
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        # Convert API request to UseCase request
        usecase_request = DataflowRequest(
            source=request.source,
            sink=request.sink,
            policy=request.policy,
            file_path=request.file_path,
            session_id=request.session_id,
            repo_id=request.repo_id,
            max_depth=request.max_depth,
        )

        # Get UseCase from container
        ir_doc = IRDocument(repo_id=request.repo_id, snapshot_id="temp")
        dataflow_usecase = container._foundation.create_dataflow_usecase(ir_doc)

        # Execute
        response = await dataflow_usecase.execute(usecase_request)

        # Convert to API response
        return DataflowResponseAPI(
            verification=VerificationSnapshotAPI(**response.verification.to_dict()),
            source=response.source,
            sink=response.sink,
            reachable=response.reachable,
            paths=[{"nodes": path.nodes} for path in (response.paths or [])],
            sanitizers=response.sanitizers or [],
            policy=response.policy,
            evidence_ref=EvidenceRefAPI(**response.evidence_ref.to_dict()) if response.evidence_ref else None,
            error=response.error.to_dict() if response.error else None,
        )

    except Exception as e:
        logger.error("dataflow_endpoint_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evidence/{evidence_id}")
async def get_evidence(evidence_id: str):
    """
    Get evidence by ID (RFC-052).

    Evidence retrieval endpoint for detailed analysis results.
    """
    try:
        from codegraph_shared.container import container

        repo = container._foundation.evidence_repository
        evidence = await repo.get_by_id(evidence_id)

        if not evidence:
            raise HTTPException(status_code=404, detail=f"Evidence {evidence_id} not found or expired")

        return evidence.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_evidence_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/snapshot")
async def get_session_snapshot(session_id: str):
    """
    Get snapshot for session (RFC-052).

    Shows which snapshot the session is locked to.
    """
    try:
        from codegraph_shared.container import container

        service = container._foundation.snapshot_session_service
        info = await service.get_snapshot_info(session_id)

        if not info:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        return info

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_session_snapshot_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
