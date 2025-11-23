import json

from core.core.mcp.services import MCPGraphService


async def get_callees(service: MCPGraphService, arguments: dict) -> str:
    """호출 대상 조회 핸들러"""
    symbol_id = arguments.get("symbol_id", "")
    depth = arguments.get("depth", 1)

    result = await service.get_callees(symbol_id, depth)
    return json.dumps(result.to_dict(), ensure_ascii=False)
