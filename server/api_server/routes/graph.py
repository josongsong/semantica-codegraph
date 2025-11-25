from fastapi import APIRouter, Depends, Query

from src.container import Container
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex

router = APIRouter()


def get_container() -> Container:
    """Get application container instance."""
    from src.container import container

    return container


def get_symbol_index(
    container: Container = Depends(get_container),
) -> KuzuSymbolIndex:
    """Get symbol index from container."""
    return container.symbol_index


@router.get("/callers")
async def get_callers(
    symbol_id: str = Query(..., description="심볼 ID"),
    depth: int = Query(1, ge=1, le=5, description="탐색 깊이 (현재 미구현)"),
    symbol_index: KuzuSymbolIndex = Depends(get_symbol_index),
):
    """호출자 조회 - 해당 심볼을 호출하는 심볼들을 조회"""
    callers = await symbol_index.get_callers(symbol_id)
    # Note: depth parameter is not currently supported by KuzuSymbolIndex
    # TODO: Implement recursive caller traversal with depth
    return {"results": callers, "requested_depth": depth}


@router.get("/callees")
async def get_callees(
    symbol_id: str = Query(..., description="심볼 ID"),
    depth: int = Query(1, ge=1, le=5, description="탐색 깊이 (현재 미구현)"),
    symbol_index: KuzuSymbolIndex = Depends(get_symbol_index),
):
    """호출 대상 조회 - 해당 심볼이 호출하는 심볼들을 조회"""
    callees = await symbol_index.get_callees(symbol_id)
    # Note: depth parameter is not currently supported by KuzuSymbolIndex
    # TODO: Implement recursive callee traversal with depth
    return {"results": callees, "requested_depth": depth}
