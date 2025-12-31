"""
Common ports (interfaces) used across layers.

Provides storage interfaces that foundation layer can depend on
without creating circular dependencies with infra layer.
"""

from typing import Any, Protocol


class PostgresStorePort(Protocol):
    """
    PostgreSQL storage port.

    Foundation layer components can depend on this interface
    instead of the concrete infra implementation.
    """

    async def execute(self, query: str, *args: Any) -> Any:
        """Execute a query"""
        ...

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Fetch single row"""
        ...

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Fetch all rows"""
        ...
