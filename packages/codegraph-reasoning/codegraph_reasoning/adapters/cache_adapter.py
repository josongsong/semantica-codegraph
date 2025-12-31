"""
Rebuild Cache Adapter

Infrastructure RebuildCache를 Port로 래핑
"""

from typing import Any

from ..infrastructure.cache.rebuild_cache import RebuildCache


class CacheAdapter:
    """
    RebuildCache Adapter

    Infrastructure → Port 브릿지
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 100):
        """
        Initialize adapter

        Args:
            ttl_seconds: Cache TTL in seconds
            max_entries: Maximum cache entries (LRU eviction)
        """
        self._cache = RebuildCache(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )

    def get(
        self,
        old_graph: Any,
        changes: dict[str, tuple[str, str]],
    ) -> Any | None:
        """캐시 조회 (Port 메서드)"""
        return self._cache.get(old_graph, changes)

    def set(
        self,
        old_graph: Any,
        changes: dict[str, tuple[str, str]],
        updated_graph: Any,
        plan_meta: dict[str, Any],
        stats: dict[str, Any],
    ) -> None:
        """캐시 저장 (Port 메서드)"""
        self._cache.set(old_graph, changes, updated_graph, plan_meta, stats)

    def invalidate(self, changes: dict[str, tuple[str, str]]) -> None:
        """캐시 무효화 (Port 메서드)"""
        self._cache.invalidate(changes)

    def get_metrics(self) -> dict[str, Any]:
        """캐시 메트릭 (Port 메서드)"""
        return self._cache.get_metrics()


# Type check
def _type_check() -> None:
    CacheAdapter()
