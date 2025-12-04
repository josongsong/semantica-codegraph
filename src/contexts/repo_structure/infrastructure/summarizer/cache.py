"""
Summary Cache

Content-hash based caching to avoid regenerating summaries
for unchanged code.
"""

from typing import Protocol


class SummaryCache(Protocol):
    """
    Protocol for summary caching.

    Implementations:
    - InMemorySummaryCache: For testing and single-process use
    - RedisSummaryCache: For production (future)
    """

    def get(self, content_hash: str) -> str | None:
        """
        Get cached summary by content hash.

        Args:
            content_hash: Content hash of the code

        Returns:
            Cached summary or None if not found
        """
        ...

    def set(self, content_hash: str, summary: str) -> None:
        """
        Cache a summary.

        Args:
            content_hash: Content hash of the code
            summary: Generated summary
        """
        ...

    def clear(self) -> None:
        """Clear all cached summaries."""
        ...


class InMemorySummaryCache:
    """In-memory implementation of SummaryCache."""

    def __init__(self):
        self._cache: dict[str, str] = {}

    def get(self, content_hash: str) -> str | None:
        """Get cached summary."""
        return self._cache.get(content_hash)

    def set(self, content_hash: str, summary: str) -> None:
        """Cache a summary."""
        self._cache[content_hash] = summary

    def clear(self) -> None:
        """Clear cache."""
        self._cache.clear()

    def size(self) -> int:
        """Get cache size."""
        return len(self._cache)
