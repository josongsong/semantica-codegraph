import json
from typing import Dict

from core.core.mcp.services import MCPSearchService


async def get_chunk(service: MCPSearchService, arguments: Dict) -> str:
    """청크 조회 핸들러"""
    chunk_id = arguments.get("chunk_id", "")

    result = await service.get_chunk(chunk_id)
    return json.dumps(result.to_dict(), ensure_ascii=False)

