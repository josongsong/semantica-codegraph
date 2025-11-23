from typing import List

from fastapi import APIRouter, Query

from core.core.schema.queries import SearchQuery, SearchType
from core.core.search.chunk_retriever import create_chunk_retriever
from core.core.search.symbol_retriever import create_symbol_retriever
from core.core.store.factory import create_all_stores

router = APIRouter()

# 저장소 초기화
node_store, edge_store, vector_store = create_all_stores()
chunk_retriever = create_chunk_retriever(vector_store, edge_store)
symbol_retriever = create_symbol_retriever(vector_store, edge_store)


@router.get("/chunks")
async def search_chunks(
    q: str = Query(..., description="검색 쿼리"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """청크 검색"""
    query = SearchQuery(query=q, search_type=SearchType.CHUNK, limit=limit, offset=offset)
    results = await chunk_retriever.search(query)
    return {"results": results, "total": len(results)}


@router.get("/symbols")
async def search_symbols(
    q: str = Query(..., description="검색 쿼리"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """심볼 검색"""
    query = SearchQuery(query=q, search_type=SearchType.SYMBOL, limit=limit, offset=offset)
    results = await symbol_retriever.search(query)
    return {"results": results, "total": len(results)}

