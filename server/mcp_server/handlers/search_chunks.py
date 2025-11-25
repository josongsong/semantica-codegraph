import json

from src.core.mcp.services import MCPSearchService


async def search_chunks(service: MCPSearchService, arguments: dict) -> str:
    """청크 검색 핸들러"""
    query = arguments.get("query", "")
    limit = arguments.get("limit", 10)

    results = await service.search_chunks(query, limit)
    return json.dumps([r.to_dict() for r in results], ensure_ascii=False)
