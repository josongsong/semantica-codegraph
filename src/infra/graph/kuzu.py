"""
Kùzu Graph Store Adapter (stub)

Provides the interface expected by the DI container. Replace with actual Kùzu
bindings when available.
"""

from typing import Any, Iterable


class KuzuGraphStore:
    """Placeholder adapter for graph persistence."""

    def __init__(self, db_path: str, buffer_pool_size: int = 1024) -> None:
        self.db_path = db_path
        self.buffer_pool_size = buffer_pool_size

    async def create_node(self, node: dict[str, Any]) -> None:
        raise NotImplementedError("KuzuGraphStore.create_node is not implemented yet")

    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError("KuzuGraphStore.create_relationship is not implemented yet")

    async def get_neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "outgoing",
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("KuzuGraphStore.get_neighbors is not implemented yet")

    async def query_path(self, start_id: str, end_id: str, max_depth: int = 5) -> list[list[str]]:
        raise NotImplementedError("KuzuGraphStore.query_path is not implemented yet")

    async def bulk_create(self, nodes: Iterable[dict[str, Any]]) -> None:
        raise NotImplementedError("KuzuGraphStore.bulk_create is not implemented yet")
