"""
RFC-039 P0.3: Global L1 Cache with Hierarchical Quota

SOTA 메모리 관리:
- Global shared L1 (process-wide)
- Project-level quota (fair sharing)
- Hierarchical LRU eviction
- Thread-safe

Architecture:
    Process
      │
      ├─ Global L1 Cache (512MB total)
      │   ├─ Project A quota (~100MB soft limit)
      │   ├─ Project B quota (~100MB soft limit)
      │   └─ Global LRU (hard limit)
      │
      └─ Multiple Builders share L1

Inspired by:
- Kubernetes resource quotas
- Linux cgroups memory limits
- nginx shared memory zones

Usage:
    from cache_global import get_global_l1_cache

    cache = get_global_l1_cache()
    cache.set(key, value, project_id="myproject")
"""

import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any

from codegraph_engine.code_foundation.infrastructure.ir.cache import CacheKey


@dataclass
class ProjectQuota:
    """
    프로젝트별 quota 추적.

    Soft limit: 프로젝트가 이 이상 사용 시 해당 프로젝트부터 evict
    Hard limit: 전체 캐시 limit (모든 프로젝트 합)
    """

    project_id: str
    current_bytes: int = 0
    entry_count: int = 0
    access_count: int = 0
    last_access: float = 0


class GlobalMemoryCache:
    """
    SOTA: Global L1 cache with hierarchical quota.

    Features:
    - Process-wide singleton
    - Project-level quota (soft limit)
    - Fair eviction (noisy neighbor prevention)
    - Thread-safe (threading.Lock)
    - O(1) LRU operations

    Memory Model:
        Total: 512MB (hard limit)
        Per-project: ~100MB (soft limit, elastic)

    Eviction Strategy:
        1. Project exceeds soft limit → Evict from that project
        2. Total exceeds hard limit → Global LRU
        3. Fairness: Prevent one project monopolizing

    Example:
        >>> cache = get_global_l1_cache()
        >>> cache.set(key, ir_doc, project_id="myproject")
        >>> result = cache.get(key)
    """

    def __init__(
        self,
        max_size: int = 5000,  # SOTA: 5K entries (vs 500)
        max_bytes: int = 4 * 1024 * 1024 * 1024,  # SOTA: 4GB (vs 512MB)
        project_soft_limit: int = 400 * 1024 * 1024,  # 400MB per project (10 projects = 4GB)
    ):
        """
        Initialize global memory cache.

        SOTA Configuration:
            max_size: 5000 entries (대형 프로젝트 지원)
            max_bytes: 4GB (현대 시스템 기준)
            project_soft_limit: 400MB (10 projects fair sharing)

        Memory Sizing Philosophy:
            - 16GB RAM 시스템: 4GB cache (25%)
            - 32GB RAM 시스템: 4GB cache (12.5%)
            - 64GB RAM 시스템: 4GB cache (6.25%)
            → 대부분 시스템에서 안전

        Args:
            max_size: Total max entries (hard limit)
            max_bytes: Total max bytes (hard limit)
            project_soft_limit: Per-project soft limit (elastic)
        """
        # Global cache (all projects)
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._max_bytes = max_bytes
        self._current_bytes = 0
        self._lock = threading.Lock()

        # Project-level tracking
        self._project_soft_limit = project_soft_limit
        self._projects: dict[str, ProjectQuota] = {}
        self._key_to_project: dict[str, str] = {}  # cache_key → project_id

        # Stats
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._project_evictions = defaultdict(int)

    def get(self, key: CacheKey) -> Any | None:
        """
        Get from cache (thread-safe, O(1)).

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        key_str = key.to_string()

        with self._lock:
            if key_str in self._cache:
                # LRU: Move to end
                self._cache.move_to_end(key_str)
                self._hits += 1

                # Update project stats
                project_id = self._key_to_project.get(key_str)
                if project_id and project_id in self._projects:
                    self._projects[project_id].access_count += 1
                    self._projects[project_id].last_access = time.time()

                return self._cache[key_str]

            self._misses += 1
            return None

    def set(self, key: CacheKey, value: Any, project_id: str = "default") -> None:
        """
        Set cache entry with project quota tracking.

        SOTA: Hierarchical eviction
        1. Check project soft limit → Evict from project
        2. Check global hard limit → Global LRU

        Args:
            key: Cache key
            value: Value to cache
            project_id: Project identifier for quota tracking
        """
        key_str = key.to_string()

        with self._lock:
            # Calculate size
            if hasattr(value, "estimated_size"):
                obj_size = value.estimated_size
            else:
                obj_size = len(getattr(value, "nodes", [])) * 200 + len(getattr(value, "edges", [])) * 100 + 1000

            # Initialize project quota if needed
            if project_id not in self._projects:
                self._projects[project_id] = ProjectQuota(project_id=project_id, last_access=time.time())

            # Update existing entry
            if key_str in self._cache:
                old_value = self._cache[key_str]
                old_size = getattr(old_value, "estimated_size", 1000)
                old_project = self._key_to_project.get(key_str, project_id)

                # Update sizes
                self._current_bytes -= old_size
                if old_project in self._projects:
                    self._projects[old_project].current_bytes -= old_size
                    self._projects[old_project].entry_count -= 1

                self._cache.move_to_end(key_str)
                self._cache[key_str] = value
                self._current_bytes += obj_size
                self._projects[project_id].current_bytes += obj_size
                self._projects[project_id].entry_count += 1
                self._key_to_project[key_str] = project_id
                return

            # SOTA: Hierarchical eviction
            # Step 1: Project soft limit exceeded?
            if self._projects[project_id].current_bytes + obj_size > self._project_soft_limit:
                # Evict from THIS project first (fairness)
                self._evict_from_project(project_id, obj_size)

            # Step 2: Global hard limit
            while self._current_bytes + obj_size > self._max_bytes and self._cache:
                self._evict_global_lru()

            while len(self._cache) >= self._max_size and self._cache:
                self._evict_global_lru()

            # Add new entry
            self._cache[key_str] = value
            self._current_bytes += obj_size
            self._projects[project_id].current_bytes += obj_size
            self._projects[project_id].entry_count += 1
            self._projects[project_id].last_access = time.time()
            self._key_to_project[key_str] = project_id

    def _evict_from_project(self, project_id: str, needed_bytes: int) -> None:
        """
        Evict entries from specific project (fairness).

        SOTA: Noisy neighbor prevention
        """
        evicted_bytes = 0

        # Find entries from this project (LRU order)
        to_evict = []
        for key_str in list(self._cache.keys()):
            if self._key_to_project.get(key_str) == project_id:
                to_evict.append(key_str)

                # Evict until enough space
                if evicted_bytes >= needed_bytes:
                    break

        # Evict
        for key_str in to_evict:
            value = self._cache.pop(key_str)
            size = getattr(value, "estimated_size", 1000)

            self._current_bytes -= size
            self._projects[project_id].current_bytes -= size
            self._projects[project_id].entry_count -= 1
            self._key_to_project.pop(key_str, None)

            evicted_bytes += size
            self._evictions += 1
            self._project_evictions[project_id] += 1

    def _evict_global_lru(self) -> None:
        """Global LRU eviction (oldest across all projects)."""
        if not self._cache:
            return

        # Evict oldest (LRU)
        key_str, value = self._cache.popitem(last=False)
        size = getattr(value, "estimated_size", 1000)

        project_id = self._key_to_project.pop(key_str, None)

        self._current_bytes -= size
        self._evictions += 1

        if project_id and project_id in self._projects:
            self._projects[project_id].current_bytes -= size
            self._projects[project_id].entry_count -= 1
            self._project_evictions[project_id] += 1

    def clear(self) -> None:
        """Clear entire cache (thread-safe)."""
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0
            self._projects.clear()
            self._key_to_project.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._project_evictions.clear()

    def stats(self) -> dict[str, Any]:
        """
        Get statistics (thread-safe).

        Returns detailed per-project stats.
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            # Per-project breakdown
            project_stats = {}
            for proj_id, quota in self._projects.items():
                project_stats[proj_id] = {
                    "bytes": quota.current_bytes,
                    "entries": quota.entry_count,
                    "accesses": quota.access_count,
                    "evictions": self._project_evictions[proj_id],
                    "last_access": quota.last_access,
                }

            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": len(self._cache),
                "current_bytes": self._current_bytes,
                "hit_rate": hit_rate,
                "projects": project_stats,
            }


# Global singleton
_global_l1_cache: GlobalMemoryCache | None = None
_global_l1_lock = threading.Lock()


def get_global_l1_cache() -> GlobalMemoryCache:
    """
    Get global L1 cache singleton (process-wide).

    SOTA: Thread-safe lazy initialization (double-check locking).

    Returns:
        Global L1 cache instance
    """
    global _global_l1_cache

    if _global_l1_cache is None:
        with _global_l1_lock:
            if _global_l1_cache is None:  # Double-check
                _global_l1_cache = GlobalMemoryCache(
                    max_size=5000,  # SOTA: 5K entries
                    max_bytes=4 * 1024 * 1024 * 1024,  # SOTA: 4GB
                    project_soft_limit=400 * 1024 * 1024,  # 400MB per project
                )

    return _global_l1_cache


def set_global_l1_cache(cache: GlobalMemoryCache) -> None:
    """
    Set global L1 cache (for testing).

    Args:
        cache: GlobalMemoryCache instance
    """
    global _global_l1_cache
    _global_l1_cache = cache
