"""
Zoekt Lexical Search Adapter (stub)

Implements minimal API expected by DI container. Wire to real Zoekt HTTP/gRPC
client when available.
"""

from typing import Any


class ZoektAdapter:
    """Placeholder adapter for lexical search."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError("ZoektAdapter.search is not implemented yet")

    async def healthcheck(self) -> bool:
        raise NotImplementedError("ZoektAdapter.healthcheck is not implemented yet")
