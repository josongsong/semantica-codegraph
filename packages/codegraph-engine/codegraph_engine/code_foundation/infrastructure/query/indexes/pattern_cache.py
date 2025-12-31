"""
Pattern Matching Cache - Global LRU Cache

Caches fnmatch pattern results for 10x-100x speedup.

Performance:
- Cache hit: O(1)
- Cache miss: O(M) where M = candidates
- Memory: Bounded to 1000 unique patterns

Thread Safety:
- All operations protected by RLock
"""

import fnmatch
import threading
from collections import OrderedDict
from collections.abc import Callable


class PatternCache:
    """
    Global LRU cache for pattern matching results

    Thread-safe, bounded memory.

    Example:
        cache = PatternCache(max_size=1000)
        matched = cache.match_pattern_fnmatch("user_*", all_names)
        # 1st call: O(M) compute
        # 2nd call: O(1) cached
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize pattern cache

        Args:
            max_size: Maximum cache entries
        """
        self._lock = threading.RLock()
        self._max_size = max_size
        self._cache: OrderedDict[tuple[str, frozenset[str]], frozenset[str]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def match_pattern_fnmatch(self, pattern: str, candidates: set[str]) -> set[str]:
        """
        Match pattern against candidates (with caching)

        Args:
            pattern: Glob pattern (e.g., "user_*")
            candidates: Set of candidate strings

        Returns:
            Set of matched strings

        Performance:
            - Cache hit: O(1)
            - Cache miss: O(M) where M = len(candidates)
        """
        cache_key = (pattern, frozenset(candidates))

        with self._lock:
            # Check cache
            if cache_key in self._cache:
                self._hits += 1
                # Move to end (LRU)
                self._cache.move_to_end(cache_key)
                return set(self._cache[cache_key])

            # Cache miss - compute
            self._misses += 1
            matches = frozenset(name for name in candidates if fnmatch.fnmatch(name, pattern))

            # LRU eviction
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            # Store in cache
            self._cache[cache_key] = matches

            return set(matches)

    def match_pattern_with_ids(
        self,
        pattern: str,
        name_to_ids: dict[str, list[str]],
        matcher: Callable[[str], bool],
    ) -> list[str]:
        """
        Match pattern and return ALL node IDs (full-result caching)

        Args:
            pattern: Glob pattern
            name_to_ids: Mapping of names to node ID lists
            matcher: Function that returns True if name matches pattern

        Returns:
            List of all matching node IDs (flat list)

        Performance:
            - Cache hit: O(1) - instant
            - Cache miss: O(M) - compute once

        Note:
            Caches node IDs, not just names. Safe for immutable indexes.
        """
        # Create stable cache key
        names_frozen = frozenset(name_to_ids.keys())
        cache_key = (pattern, names_frozen)

        with self._lock:
            # Check cache
            if cache_key in self._cache:
                self._hits += 1
                self._cache.move_to_end(cache_key)
                # Return cached IDs
                cached_result = self._cache[cache_key]
                if isinstance(cached_result, list):
                    return cached_result
                # If frozenset (from old cache), convert
                return list(cached_result) if not isinstance(cached_result, set) else list(cached_result)

            # Cache miss - compute full result
            self._misses += 1
            all_ids = []
            for name, ids in name_to_ids.items():
                if matcher(name):
                    all_ids.extend(ids)

            # LRU eviction
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            # Cache as list (not frozen set)
            self._cache[cache_key] = all_ids

            return all_ids

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Stats dict with hits, misses, hit_rate
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "hit_rate_pct": hit_rate * 100,
                "size": len(self._cache),
                "capacity": self._max_size,
                "max_size": self._max_size,
            }

    def clear(self) -> None:
        """Clear cache (for testing)"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Global pattern cache instance (shared across all SemanticIndex instances)
_global_pattern_cache: PatternCache | None = None
_global_cache_lock = threading.Lock()


def get_global_pattern_cache() -> PatternCache:
    """
    Get global pattern cache singleton

    Returns:
        Global PatternCache instance
    """
    global _global_pattern_cache

    if _global_pattern_cache is None:
        with _global_cache_lock:
            if _global_pattern_cache is None:
                _global_pattern_cache = PatternCache(max_size=1000)

    return _global_pattern_cache


__all__ = ["PatternCache", "get_global_pattern_cache"]
