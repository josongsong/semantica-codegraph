"""
Meilisearch Lexical Search Adapter

Implements LexicalSearchPort using Meilisearch.
"""

from typing import Any, Optional

from ...core.ports.lexical_search_port import LexicalSearchPort


class MeilisearchAdapter(LexicalSearchPort):
    """
    Meilisearch implementation of LexicalSearchPort.
    """

    def __init__(self, host: str = "http://localhost:7700", api_key: Optional[str] = None):
        """Initialize Meilisearch client."""
        self.host = host
        self.api_key = api_key
        # TODO: Initialize meilisearch client

    async def index_documents(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> None:
        """Index documents."""
        # TODO: Implement
        raise NotImplementedError

    async def search(
        self,
        index_name: str,
        query: str,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Perform search."""
        # TODO: Implement
        raise NotImplementedError

    async def delete_by_filter(
        self,
        index_name: str,
        filters: dict[str, Any],
    ) -> int:
        """Delete documents by filter."""
        # TODO: Implement
        raise NotImplementedError

    async def create_index(
        self,
        index_name: str,
        schema: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create index."""
        # TODO: Implement
        raise NotImplementedError

    async def index_exists(self, index_name: str) -> bool:
        """Check if index exists."""
        # TODO: Implement
        raise NotImplementedError

    async def update_settings(
        self,
        index_name: str,
        settings: dict[str, Any],
    ) -> None:
        """Update index settings."""
        # TODO: Implement
        raise NotImplementedError
