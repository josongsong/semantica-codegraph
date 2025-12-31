"""
Graph Semantics API (RFC-SEM-022)

차별화 핵심 기능:
- graph.slice: 의미적 최소 코드 추출
- graph.dataflow: 값 흐름 증명
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/graph", tags=["Graph Semantics"])


# ============================================================
# Request/Response Models
# ============================================================


class SliceRequest(BaseModel):
    """Slice 요청."""

    anchor: str = Field(..., description="앵커 심볼 (변수/함수/클래스)")
    direction: Literal["backward", "forward", "both"] = Field("backward", description="슬라이스 방향")
    max_depth: int = Field(5, ge=1, le=20, description="최대 탐색 깊이")
    max_lines: int = Field(100, ge=10, le=500, description="최대 라인 수")


class CodeFragment(BaseModel):
    """코드 조각."""

    file_path: str
    start_line: int
    end_line: int
    code: str
    relevance: float = Field(1.0, ge=0.0, le=1.0)


class SliceResponse(BaseModel):
    """Slice 응답."""

    anchor: str
    direction: str
    fragments: list[CodeFragment]
    total_lines: int
    total_nodes: int
    metadata: dict


class DataflowRequest(BaseModel):
    """Dataflow 요청."""

    source: str = Field(..., description="소스 심볼")
    sink: str = Field(..., description="싱크 심볼")
    policy: str | None = Field(None, description="정책 (sql_injection, xss 등)")


class DataflowPath(BaseModel):
    """Dataflow 경로 노드."""

    node_id: str
    name: str
    file_path: str
    line: int
    kind: str


class DataflowResponse(BaseModel):
    """Dataflow 응답."""

    source: str
    sink: str
    reachable: bool
    paths: list[list[DataflowPath]]
    sanitizers: list[str]
    metadata: dict


# ============================================================
# Endpoints
# ============================================================


@router.post("/slice", response_model=SliceResponse)
async def graph_slice(request: SliceRequest):
    """
    Semantic Slicing - 버그/이슈의 Root Cause만 최소 단위로 추출.

    RFC-SEM-022:
    - "코드 전체"가 아니라 의미적으로 필요한 최소 코드만 반환
    - Agent가 "이 버그에 관련된 코드만 보여줘" 요청 가능
    """
    try:
        from codegraph_engine.reasoning_engine.adapters.slicer_adapter import SlicerAdapter

        # TODO: DI container에서 graph 가져오기
        # 현재는 graceful fallback
        try:
            from codegraph_shared.container import container

            graph = container.graph_index()
            slicer = SlicerAdapter(graph)

            if request.direction == "backward":
                result = slicer.backward_slice(request.anchor, request.max_depth)
            elif request.direction == "forward":
                result = slicer.forward_slice(request.anchor, request.max_depth)
            else:
                # both
                backward = slicer.backward_slice(request.anchor, request.max_depth)
                forward = slicer.forward_slice(request.anchor, request.max_depth)
                # Merge
                result = backward
                result.slice_nodes = result.slice_nodes | forward.slice_nodes
                result.code_fragments = backward.code_fragments + forward.code_fragments

            fragments = [
                CodeFragment(
                    file_path=f.file_path,
                    start_line=f.start_line,
                    end_line=f.end_line,
                    code=f.code,
                    relevance=1.0,
                )
                for f in result.code_fragments[: request.max_lines // 10]
            ]

            return SliceResponse(
                anchor=request.anchor,
                direction=request.direction,
                fragments=fragments,
                total_lines=sum(f.end_line - f.start_line + 1 for f in fragments),
                total_nodes=len(result.slice_nodes),
                metadata=result.metadata,
            )

        except ImportError as e:
            # 의존성 누락: 명시적 에러
            raise HTTPException(
                status_code=503,
                detail=f"Graph index not available: {e}. Run indexing first.",
            )
        except Exception as e:
            # 분석 실패: 에러 정보 포함
            import os

            if os.environ.get("SEMANTICA_STRICT_MODE", "").lower() == "true":
                raise HTTPException(status_code=500, detail=str(e))

            # Development: fallback 허용
            return SliceResponse(
                anchor=request.anchor,
                direction=request.direction,
                fragments=[],
                total_lines=0,
                total_nodes=0,
                metadata={"error": str(e), "fallback": True, "warning": "Set SEMANTICA_STRICT_MODE=true in production"},
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slice")
async def graph_slice_get(
    anchor: str = Query(..., description="앵커 심볼"),
    direction: Literal["backward", "forward", "both"] = Query("backward"),
    max_depth: int = Query(5, ge=1, le=20),
    max_lines: int = Query(100, ge=10, le=500),
):
    """GET 버전 Semantic Slicing."""
    request = SliceRequest(anchor=anchor, direction=direction, max_depth=max_depth, max_lines=max_lines)
    return await graph_slice(request)


@router.post("/dataflow", response_model=DataflowResponse)
async def graph_dataflow(request: DataflowRequest):
    """
    Dataflow Analysis - 값이 source → sink로 도달함을 증명.

    RFC-SEM-022:
    - 경로 노드/엣지 시퀀스
    - 전파 이유
    - 차단 가능한 지점 후보
    """
    try:
        from codegraph_engine.code_foundation.domain.taint.taint_engine import TaintEngine

        try:
            from codegraph_shared.container import container

            engine = container.taint_engine()

            # Taint 분석으로 dataflow 확인
            # TODO: source/sink 기반 분석 구현
            paths: list[list[DataflowPath]] = []
            reachable = False
            sanitizers: list[str] = []

            return DataflowResponse(
                source=request.source,
                sink=request.sink,
                reachable=reachable,
                paths=paths,
                sanitizers=sanitizers,
                metadata={"policy": request.policy},
            )

        except ImportError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Taint engine not available: {e}. Run indexing first.",
            )
        except Exception as e:
            import os

            if os.environ.get("SEMANTICA_STRICT_MODE", "").lower() == "true":
                raise HTTPException(status_code=500, detail=str(e))

            return DataflowResponse(
                source=request.source,
                sink=request.sink,
                reachable=False,
                paths=[],
                sanitizers=[],
                metadata={"error": str(e), "fallback": True, "warning": "Set SEMANTICA_STRICT_MODE=true in production"},
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dataflow")
async def graph_dataflow_get(
    source: str = Query(..., description="소스 심볼"),
    sink: str = Query(..., description="싱크 심볼"),
    policy: str | None = Query(None, description="정책"),
):
    """GET 버전 Dataflow Analysis."""
    request = DataflowRequest(source=source, sink=sink, policy=policy)
    return await graph_dataflow(request)
