"""
Lexical Search Port

Abstract interface for lexical/keyword search.
Implementations: Meilisearch, Elasticsearch, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class LexicalSearchPort(ABC):
    """
    Port for lexical/keyword search operations.

    Responsibilities:
    - Index documents for text search
    - Perform keyword search
    - Filter and rank results
    """

    @abstractmethod
    async def index_documents(
        self,
        index_name: str,
        documents: List[Dict[str, Any]],
    ) -> None:
        """
        Index documents for search.

        Args:
            index_name: Name of the index
            documents: List of documents to index
        """
        pass

    @abstractmethod
    async def search(
        self,
        index_name: str,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword search.

        Args:
            index_name: Index to search in
            query: Search query
            filters: Optional filters
            limit: Maximum results
            offset: Result offset for pagination

        Returns:
            List of search results
        """
        pass

    @abstractmethod
    async def delete_by_filter(
        self,
        index_name: str,
        filters: Dict[str, Any],
    ) -> int:
        """
        Delete documents matching filters.

        Args:
            index_name: Index to delete from
            filters: Filter criteria

        Returns:
            Number of deleted documents
        """
        pass

    @abstractmethod
    async def create_index(
        self,
        index_name: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Create a new search index.

        Args:
            index_name: Name for the new index
            schema: Optional index schema/settings
        """
        pass

    @abstractmethod
    async def index_exists(self, index_name: str) -> bool:
        """Check if an index exists."""
        pass

    @abstractmethod
    async def update_settings(
        self,
        index_name: str,
        settings: Dict[str, Any],
    ) -> None:
        """
        Update index settings.

        Args:
            index_name: Index to update
            settings: New settings
        """
        pass
