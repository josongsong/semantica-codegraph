import json

from core.core.mcp.services import MCPSearchService


async def search_symbols(service: MCPSearchService, arguments: dict) -> str:
    """심볼 검색 핸들러"""
    query = arguments.get("query", "")
    limit = arguments.get("limit", 10)

    results = await service.search_symbols(query, limit)
    return json.dumps([r.to_dict() for r in results], ensure_ascii=False)
