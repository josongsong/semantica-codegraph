"""
Zoekt Search Adapter

Adapter for Zoekt lexical search engine.
Implements fuzzy search and prefix search using Zoekt's ctags-based indexing.
"""

from typing import TYPE_CHECKING

from .models import SearchableSymbol, SearchIndex

if TYPE_CHECKING:
    from src.infra.search.zoekt import ZoektStore


class ZoektSearchAdapter:
    """
    Zoekt implementation of SearchIndexPort (lexical search).

    Uses Zoekt for:
    - Fuzzy name search (trigram-based)
    - Prefix search (autocomplete)
    - Full-text search in code

    Note: Zoekt indexes are built externally via zoekt-index.
    This adapter only queries the index.
    """

    def __init__(self, zoekt_store: "ZoektStore"):
        """
        Initialize Zoekt adapter.

        Args:
            zoekt_store: ZoektStore instance for querying
        """
        self.zoekt = zoekt_store

    def index_symbols(self, search_index: SearchIndex) -> None:
        """
        Index symbols in Zoekt.

        Note: Zoekt indexing is done externally via zoekt-index CLI.
        This method is a no-op (or triggers external indexing).
        """
        # TODO: Trigger external zoekt-index process
        # For now, assume Zoekt index is built externally
        pass

    def search_fuzzy(
        self, query: str, repo_id: str, snapshot_id: str, limit: int = 10
    ) -> list[SearchableSymbol]:
        """
        Fuzzy search using Zoekt.

        Uses Zoekt's trigram-based fuzzy matching.

        Args:
            query: Fuzzy search query
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        # TODO: Implement using ZoektStore.search()
        # For now, return empty list
        return []

    def search_prefix(
        self, prefix: str, repo_id: str, snapshot_id: str, limit: int = 10
    ) -> list[SearchableSymbol]:
        """
        Prefix search using Zoekt.

        Uses Zoekt's prefix matching for autocomplete.

        Args:
            prefix: Name prefix
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        # TODO: Implement using ZoektStore.search() with prefix query
        # For now, return empty list
        return []

    def search_signature(
        self, signature_pattern: str, repo_id: str, snapshot_id: str, limit: int = 10
    ) -> list[SearchableSymbol]:
        """
        Signature search (not supported by Zoekt).

        Falls back to regex search in code.

        Args:
            signature_pattern: Signature pattern
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        # TODO: Implement using regex search via Zoekt
        # For now, return empty list
        return []

    def delete_index(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete Zoekt index.

        Note: Zoekt index deletion is done externally.
        """
        # TODO: Trigger external index deletion
        pass

    def exists(self, repo_id: str, snapshot_id: str) -> bool:
        """
        Check if Zoekt index exists.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            True if index exists
        """
        # TODO: Check Zoekt index existence
        return False
