import json
from typing import Dict

from core.core.mcp.services import MCPGraphService


async def get_callers(service: MCPGraphService, arguments: Dict) -> str:
    """호출자 조회 핸들러"""
    symbol_id = arguments.get("symbol_id", "")
    depth = arguments.get("depth", 1)

    result = await service.get_callers(symbol_id, depth)
    return json.dumps(result.to_dict(), ensure_ascii=False)

