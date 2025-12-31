"""
Pyright Result Cache

SOTA-grade caching layer for Pyright LSP results.
Eliminates redundant Pyright calls between Layer 3 (LSP Enrichment) and Layer 5 (Semantic IR).

Design:
    - Layer 3: Populates cache with hover/definition results
    - Layer 5: Reads from cache first, only calls Pyright on cache miss
    - Key: (file_path, content_hash, line, col)
    - TTL: Session-based (cleared on file change)

Performance Impact:
    - Before: Layer 3 + Layer 5 = 2x Pyright calls
    - After: Layer 3 populates, Layer 5 reads = 1x Pyright calls
    - Expected improvement: 50%+ reduction in Pyright overhead

RFC-029: Pyright Result Caching (Performance Optimization)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import threading


@dataclass
class HoverResult:
    """Cached hover result from Pyright."""

    type_str: str | None
    docs: str | None
    raw: dict | None = None

    def to_dict(self) -> dict | None:
        """Convert to dict format expected by ExpressionBuilder."""
        if self.type_str is None and self.docs is None:
            return None
        return {"type": self.type_str, "docs": self.docs}


@dataclass
class DefinitionResult:
    """Cached definition result from Pyright."""

    file_path: str | None
    line: int | None
    col: int | None
    raw: dict | None = None

    def to_dict(self) -> dict | None:
        """Convert to dict format."""
        if self.file_path is None:
            return None
        return {
            "file": self.file_path,
            "line": self.line,
            "col": self.col,
        }


@dataclass
class CacheKey:
    """Cache key for Pyright results."""

    file_path: str
    content_hash: str
    line: int
    col: int

    def __hash__(self) -> int:
        return hash((self.file_path, self.content_hash, self.line, self.col))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CacheKey):
            return False
        return (
            self.file_path == other.file_path
            and self.content_hash == other.content_hash
            and self.line == other.line
            and self.col == other.col
        )


@dataclass
class CacheEntry:
    """Cache entry with hover and definition results."""

    hover: HoverResult | None = None
    definition: DefinitionResult | None = None


class PyrightResultCache:
    """
    Thread-safe cache for Pyright LSP results.

    Usage:
        cache = PyrightResultCache()

        # Layer 3: Populate cache
        cache.put_hover(file_path, content, line, col, hover_result)

        # Layer 5: Read from cache
        cached = cache.get_hover(file_path, content, line, col)
        if cached is None:
            # Cache miss - call Pyright
            result = pyright.hover(...)
            cache.put_hover(file_path, content, line, col, result)

    Thread Safety:
        - Uses RLock for concurrent access
        - Safe for parallel file processing

    Memory Management:
        - Per-file content hash invalidation
        - Clear on file change
        - Max entries limit (default: 100,000)
    """

    def __init__(self, max_entries: int = 100_000):
        """
        Initialize cache.

        Args:
            max_entries: Maximum cache entries before LRU eviction
        """
        self._cache: dict[CacheKey, CacheEntry] = {}
        self._content_hashes: dict[str, str] = {}  # file_path -> content_hash
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    # ============================================================
    # Content Hash Management
    # ============================================================

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute content hash for cache key."""
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _get_content_hash(self, file_path: str | Path, content: str | None = None) -> str | None:
        """
        Get content hash for file.

        Args:
            file_path: File path
            content: File content (if available)

        Returns:
            Content hash or None if not available
        """
        file_key = str(file_path)

        if content is not None:
            content_hash = self.compute_hash(content)
            with self._lock:
                old_hash = self._content_hashes.get(file_key)
                if old_hash != content_hash:
                    # Content changed - invalidate all entries for this file
                    self._invalidate_file(file_key)
                self._content_hashes[file_key] = content_hash
            return content_hash

        with self._lock:
            return self._content_hashes.get(file_key)

    def _invalidate_file(self, file_path: str) -> int:
        """
        Invalidate all cache entries for a file.

        Args:
            file_path: File path to invalidate

        Returns:
            Number of entries removed
        """
        # Called with lock held
        keys_to_remove = [k for k in self._cache if k.file_path == file_path]
        for key in keys_to_remove:
            del self._cache[key]
        return len(keys_to_remove)

    # ============================================================
    # Hover Cache Operations
    # ============================================================

    def get_hover(
        self,
        file_path: str | Path,
        content: str | None,
        line: int,
        col: int,
    ) -> HoverResult | None:
        """
        Get cached hover result.

        Args:
            file_path: Source file path
            content: File content (for hash validation)
            line: Line number
            col: Column number

        Returns:
            Cached HoverResult or None on cache miss
        """
        content_hash = self._get_content_hash(file_path, content)
        if content_hash is None:
            self._misses += 1
            return None

        key = CacheKey(str(file_path), content_hash, line, col)

        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry.hover is not None:
                self._hits += 1
                return entry.hover

        self._misses += 1
        return None

    def put_hover(
        self,
        file_path: str | Path,
        content: str,
        line: int,
        col: int,
        result: dict | None,
    ) -> None:
        """
        Store hover result in cache.

        Args:
            file_path: Source file path
            content: File content
            line: Line number
            col: Column number
            result: Pyright hover result dict
        """
        content_hash = self._get_content_hash(file_path, content)
        if content_hash is None:
            return

        key = CacheKey(str(file_path), content_hash, line, col)
        hover = HoverResult(
            type_str=result.get("type") if result else None,
            docs=result.get("docs") if result else None,
            raw=result,
        )

        with self._lock:
            self._ensure_capacity()
            if key in self._cache:
                self._cache[key].hover = hover
            else:
                self._cache[key] = CacheEntry(hover=hover)

    # ============================================================
    # Definition Cache Operations
    # ============================================================

    def get_definition(
        self,
        file_path: str | Path,
        content: str | None,
        line: int,
        col: int,
    ) -> DefinitionResult | None:
        """
        Get cached definition result.

        Args:
            file_path: Source file path
            content: File content (for hash validation)
            line: Line number
            col: Column number

        Returns:
            Cached DefinitionResult or None on cache miss
        """
        content_hash = self._get_content_hash(file_path, content)
        if content_hash is None:
            self._misses += 1
            return None

        key = CacheKey(str(file_path), content_hash, line, col)

        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry.definition is not None:
                self._hits += 1
                return entry.definition

        self._misses += 1
        return None

    def put_definition(
        self,
        file_path: str | Path,
        content: str,
        line: int,
        col: int,
        result: dict | None,
    ) -> None:
        """
        Store definition result in cache.

        Args:
            file_path: Source file path
            content: File content
            line: Line number
            col: Column number
            result: Pyright definition result dict
        """
        content_hash = self._get_content_hash(file_path, content)
        if content_hash is None:
            return

        key = CacheKey(str(file_path), content_hash, line, col)
        definition = DefinitionResult(
            file_path=result.get("file") if result else None,
            line=result.get("line") if result else None,
            col=result.get("col") if result else None,
            raw=result,
        )

        with self._lock:
            self._ensure_capacity()
            if key in self._cache:
                self._cache[key].definition = definition
            else:
                self._cache[key] = CacheEntry(definition=definition)

    # ============================================================
    # Batch Operations (for Layer 3 bulk population)
    # ============================================================

    def put_batch(
        self,
        file_path: str | Path,
        content: str,
        results: list[tuple[int, int, dict | None, dict | None]],
    ) -> int:
        """
        Store multiple results in batch.

        Args:
            file_path: Source file path
            content: File content
            results: List of (line, col, hover_result, definition_result)

        Returns:
            Number of entries stored
        """
        content_hash = self._get_content_hash(file_path, content)
        if content_hash is None:
            return 0

        stored = 0
        file_key = str(file_path)

        with self._lock:
            self._ensure_capacity(len(results))

            for line, col, hover_dict, def_dict in results:
                key = CacheKey(file_key, content_hash, line, col)

                hover = None
                if hover_dict:
                    hover = HoverResult(
                        type_str=hover_dict.get("type"),
                        docs=hover_dict.get("docs"),
                        raw=hover_dict,
                    )

                definition = None
                if def_dict:
                    definition = DefinitionResult(
                        file_path=def_dict.get("file"),
                        line=def_dict.get("line"),
                        col=def_dict.get("col"),
                        raw=def_dict,
                    )

                if key in self._cache:
                    entry = self._cache[key]
                    if hover:
                        entry.hover = hover
                    if definition:
                        entry.definition = definition
                else:
                    self._cache[key] = CacheEntry(hover=hover, definition=definition)

                stored += 1

        return stored

    # ============================================================
    # Cache Management
    # ============================================================

    def _ensure_capacity(self, needed: int = 1) -> None:
        """Ensure cache has capacity for new entries (called with lock held)."""
        while len(self._cache) + needed > self._max_entries:
            # Simple FIFO eviction (Python dict maintains insertion order)
            if self._cache:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            else:
                break

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._content_hashes.clear()
            self._hits = 0
            self._misses = 0

    def clear_file(self, file_path: str | Path) -> int:
        """
        Clear cache entries for a specific file.

        Args:
            file_path: File path to clear

        Returns:
            Number of entries removed
        """
        file_key = str(file_path)
        with self._lock:
            if file_key in self._content_hashes:
                del self._content_hashes[file_key]
            return self._invalidate_file(file_key)

    # ============================================================
    # Statistics
    # ============================================================

    @property
    def size(self) -> int:
        """Number of cache entries."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def stats(self) -> dict:
        """Get cache statistics."""
        return {
            "entries": len(self._cache),
            "files": len(self._content_hashes),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "max_entries": self._max_entries,
        }

    def __repr__(self) -> str:
        return (
            f"PyrightResultCache(entries={len(self._cache)}, "
            f"files={len(self._content_hashes)}, "
            f"hit_rate={self.hit_rate:.1%})"
        )


# ============================================================
# Singleton for shared cache across layers
# ============================================================

_shared_cache: PyrightResultCache | None = None
_shared_cache_lock = threading.Lock()


def get_shared_cache() -> PyrightResultCache:
    """
    Get shared PyrightResultCache instance.

    Used by LayeredIRBuilder to share cache between Layer 3 and Layer 5.

    Returns:
        Shared PyrightResultCache instance
    """
    global _shared_cache
    if _shared_cache is None:
        with _shared_cache_lock:
            if _shared_cache is None:
                _shared_cache = PyrightResultCache()
    return _shared_cache


def clear_shared_cache() -> None:
    """Clear the shared cache."""
    global _shared_cache
    if _shared_cache is not None:
        _shared_cache.clear()
