from fastapi import APIRouter, Query

from core.core.graph.call_graph import CallGraph
from core.core.schema.queries import CalleesQuery, CallersQuery
from core.core.store.factory import create_all_stores

router = APIRouter()

# 저장소 초기화
node_store, edge_store, vector_store = create_all_stores()
call_graph = CallGraph(node_store, edge_store)


@router.get("/callers")
async def get_callers(
    symbol_id: str = Query(..., description="심볼 ID"),
    depth: int = Query(1, ge=1, le=5),
):
    """호출자 조회"""
    query = CallersQuery(node_id=symbol_id, depth=depth)
    results = await call_graph.get_callers(query)
    return {"results": results}


@router.get("/callees")
async def get_callees(
    symbol_id: str = Query(..., description="심볼 ID"),
    depth: int = Query(1, ge=1, le=5),
):
    """호출 대상 조회"""
    query = CalleesQuery(node_id=symbol_id, depth=depth)
    results = await call_graph.get_callees(query)
    return {"results": results}
