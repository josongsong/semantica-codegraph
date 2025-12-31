"""
Search Index Port (Interface)

Port for SearchIndex persistence and search operations.
Multiple adapters can implement this interface (Tantivy, Qdrant, PostgreSQL, etc.).
"""

from typing import Protocol

from codegraph_engine.code_foundation.infrastructure.search_index.models import SearchableSymbol, SearchIndex


class SearchIndexPort(Protocol):
    """
    Port (Interface) for SearchIndex storage and search.

    This interface defines how SearchIndex is persisted and queried.
    Multiple adapters can implement this:
    - TantivySearchAdapter (lexical search)
    - QdrantSearchAdapter (vector search)
    - PostgreSQLSearchAdapter (fuzzy/domain search)
    """

    def index_symbols(self, search_index: SearchIndex) -> None:
        """
        Index all symbols in the SearchIndex.

        Args:
            search_index: SearchIndex to be indexed
        """
        ...

    def search_fuzzy(self, query: str, repo_id: str, snapshot_id: str, limit: int = 10) -> list[SearchableSymbol]:
        """
        Fuzzy search for symbols by name.

        Args:
            query: Search query
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        ...

    def search_prefix(self, prefix: str, repo_id: str, snapshot_id: str, limit: int = 10) -> list[SearchableSymbol]:
        """
        Prefix search for symbols by name.

        Args:
            prefix: Name prefix
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        ...

    def search_signature(
        self, signature_pattern: str, repo_id: str, snapshot_id: str, limit: int = 10
    ) -> list[SearchableSymbol]:
        """
        Search for symbols by signature pattern.

        Args:
            signature_pattern: Signature pattern (e.g., "def foo(x: int)")
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        ...

    def delete_index(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete search index for a repository snapshot.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
        """
        ...

    def exists(self, repo_id: str, snapshot_id: str) -> bool:
        """
        Check if search index exists.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            True if index exists
        """
        ...
