"""
Graph API Routes

Call graph 쿼리 엔드포인트.
CallGraphQueryBuilder 사용 (Memgraph 의존성 제거, graceful degradation).
"""

from fastapi import APIRouter, Query

from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

router = APIRouter()


def get_query_builder() -> CallGraphQueryBuilder:
    """Get CallGraphQueryBuilder (no external DB required)."""
    return CallGraphQueryBuilder()


@router.get("/callers")
async def get_callers(
    symbol_name: str = Query(..., description="심볼명"),
    repo_id: str = Query("default", description="저장소 ID"),
    snapshot_id: str = Query("latest", description="스냅샷 ID"),
    limit: int = Query(20, ge=1, le=100, description="최대 결과 수"),
):
    """호출자 조회 - 해당 심볼을 호출하는 심볼들을 조회"""
    builder = get_query_builder()
    callers = await builder.search_callers(repo_id, snapshot_id, symbol_name, limit)
    return {"results": callers, "count": len(callers)}


@router.get("/callees")
async def get_callees(
    symbol_name: str = Query(..., description="심볼명"),
    repo_id: str = Query("default", description="저장소 ID"),
    snapshot_id: str = Query("latest", description="스냅샷 ID"),
    limit: int = Query(20, ge=1, le=100, description="최대 결과 수"),
):
    """호출 대상 조회 - 해당 심볼이 호출하는 심볼들을 조회"""
    builder = get_query_builder()
    callees = await builder.search_callees(repo_id, snapshot_id, symbol_name, limit)
    return {"results": callees, "count": len(callees)}


@router.get("/references")
async def get_references(
    symbol_name: str = Query(..., description="심볼명"),
    repo_id: str = Query("default", description="저장소 ID"),
    snapshot_id: str = Query("latest", description="스냅샷 ID"),
    limit: int = Query(50, ge=1, le=200, description="최대 결과 수"),
):
    """참조 조회 - 해당 심볼을 참조하는 모든 노드들 조회"""
    builder = get_query_builder()
    refs = await builder.search_references(repo_id, snapshot_id, symbol_name, limit)
    return {"results": refs, "count": len(refs)}


@router.get("/imports")
async def get_imports(
    module_name: str = Query(..., description="모듈명"),
    repo_id: str = Query("default", description="저장소 ID"),
    snapshot_id: str = Query("latest", description="스냅샷 ID"),
    limit: int = Query(50, ge=1, le=200, description="최대 결과 수"),
):
    """Import 조회 - 해당 모듈을 import하는 파일들 조회"""
    builder = get_query_builder()
    imports = await builder.search_imports(repo_id, snapshot_id, module_name, limit)
    return {"results": imports, "count": len(imports)}
