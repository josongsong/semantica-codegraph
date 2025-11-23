#!/usr/bin/env python3
"""MCP 서버 엔트리포인트"""

import asyncio

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from apps.mcp_server.handlers import (
    get_callees,
    get_callers,
    get_chunk,
    get_symbol,
    search_chunks,
    search_symbols,
)
from core.core.graph.call_graph import CallGraph
from core.core.mcp.services import MCPGraphService, MCPSearchService
from core.core.search.chunk_retriever import create_chunk_retriever
from core.core.search.symbol_retriever import create_symbol_retriever
from core.core.store.factory import create_all_stores
from infra.config.logging import setup_logging

setup_logging()

# 저장소 및 서비스 초기화
node_store, edge_store, vector_store = create_all_stores()
chunk_retriever = create_chunk_retriever(vector_store, edge_store)
symbol_retriever = create_symbol_retriever(vector_store, edge_store)
call_graph = CallGraph(node_store, edge_store)

search_service = MCPSearchService(chunk_retriever, symbol_retriever, node_store)
graph_service = MCPGraphService(call_graph)

# MCP 서버 생성
server = Server("codegraph")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """도구 목록 반환"""
    return [
        Tool(
            name="search_chunks",
            description="코드 청크 검색",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "limit": {"type": "integer", "description": "결과 수", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_symbols",
            description="심볼 검색",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "limit": {"type": "integer", "description": "결과 수", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_chunk",
            description="청크 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string", "description": "청크 ID"},
                },
                "required": ["chunk_id"],
            },
        ),
        Tool(
            name="get_symbol",
            description="심볼 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "심볼 ID"},
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name="get_callers",
            description="호출자 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "심볼 ID"},
                    "depth": {"type": "integer", "description": "탐색 깊이", "default": 1},
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name="get_callees",
            description="호출 대상 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "심볼 ID"},
                    "depth": {"type": "integer", "description": "탐색 깊이", "default": 1},
                },
                "required": ["symbol_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> str:
    """도구 호출"""
    if name == "search_chunks":
        return await search_chunks(search_service, arguments)
    elif name == "search_symbols":
        return await search_symbols(search_service, arguments)
    elif name == "get_chunk":
        return await get_chunk(search_service, arguments)
    elif name == "get_symbol":
        return await get_symbol(search_service, arguments)
    elif name == "get_callers":
        return await get_callers(graph_service, arguments)
    elif name == "get_callees":
        return await get_callees(graph_service, arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """메인 함수"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(server_name="codegraph", server_version="0.1.0"),
        )


if __name__ == "__main__":
    asyncio.run(main())
