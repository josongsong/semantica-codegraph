"""
PostgreSQL Relational Store Adapter (stub)

Implements the shape expected by the DI container. Replace with real SQLAlchemy
implementation when wiring persistence.
"""

from typing import Any, Iterable, Optional


class PostgresAdapter:
    """Placeholder adapter for relational storage."""

    def __init__(self, connection_string: str) -> None:
        self.connection_string = connection_string

    async def bulk_create(self, records: Iterable[Any]) -> None:
        raise NotImplementedError("PostgresAdapter.bulk_create is not implemented yet")

    async def fetch_one(self, query: str, *params: Any) -> Optional[dict[str, Any]]:
        raise NotImplementedError("PostgresAdapter.fetch_one is not implemented yet")

    async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
        raise NotImplementedError("PostgresAdapter.fetch_all is not implemented yet")

    async def execute(self, query: str, *params: Any) -> None:
        raise NotImplementedError("PostgresAdapter.execute is not implemented yet")
