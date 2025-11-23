import json

from core.core.mcp.services import MCPSearchService


async def get_symbol(service: MCPSearchService, arguments: dict) -> str:
    """심볼 조회 핸들러"""
    symbol_id = arguments.get("symbol_id", "")

    result = await service.get_symbol(symbol_id)
    return json.dumps(result.to_dict(), ensure_ascii=False)
