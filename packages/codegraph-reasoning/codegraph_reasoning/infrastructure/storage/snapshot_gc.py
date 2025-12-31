"""
Snapshot Garbage Collector

Retention policy 기반 old snapshot 삭제.
"""

import time
from typing import Literal

from .snapshot_store import SnapshotStore


class SnapshotGC:
    """
    Snapshot 정리.

    Retention policy:
    - 최근 7일: 모두 보관
    - 7~30일: 매일 1개
    - 30~90일: 매주 1개
    - 90일 이후: 매월 1개
    """

    def __init__(self, snapshot_store: SnapshotStore):
        self.store = snapshot_store

    def collect_garbage(self, policy: Literal["aggressive", "moderate", "conservative"] = "moderate") -> dict:
        """
        GC 실행.

        Args:
            policy: 정리 정책
                - aggressive: 최근 3일만 보관
                - moderate: 기본 정책 (7-30-90)
                - conservative: 60일까지 모두 보관

        Returns:
            GC 통계 (deleted_count, freed_mb)
        """
        if policy == "aggressive":
            return self._gc_aggressive()
        elif policy == "moderate":
            return self._gc_moderate()
        else:  # conservative
            return self._gc_conservative()

    def _gc_aggressive(self) -> dict:
        """Aggressive GC: 최근 3일만 보관"""
        now = time.time()
        cutoff = now - (3 * 24 * 3600)

        snapshots = self.store.list_snapshots()

        deleted_count = 0
        freed_bytes = 0

        for snapshot in snapshots:
            if snapshot.timestamp < cutoff:
                freed_bytes += snapshot.compressed_size
                self.store.delete_snapshot(snapshot.version)
                deleted_count += 1

        return {
            "deleted_count": deleted_count,
            "freed_mb": freed_bytes / (1024 * 1024),
        }

    def _gc_moderate(self) -> dict:
        """Moderate GC: 7-30-90 정책"""
        now = time.time()

        # Time boundaries
        day_7 = now - (7 * 24 * 3600)
        day_30 = now - (30 * 24 * 3600)
        day_90 = now - (90 * 24 * 3600)

        snapshots = self.store.list_snapshots()

        deleted_count = 0
        freed_bytes = 0

        # Group snapshots by time range
        recent = []  # 0~7일
        week_old = []  # 7~30일
        month_old = []  # 30~90일
        very_old = []  # 90일+

        for snapshot in snapshots:
            ts = snapshot.timestamp
            if ts >= day_7:
                recent.append(snapshot)
            elif ts >= day_30:
                week_old.append(snapshot)
            elif ts >= day_90:
                month_old.append(snapshot)
            else:
                very_old.append(snapshot)

        # 최근 7일: 모두 보관
        # (아무것도 안 함)

        # 7~30일: 매일 1개만 보관
        deleted_count += self._keep_one_per_day(week_old, freed_bytes)

        # 30~90일: 매주 1개만 보관
        deleted_count += self._keep_one_per_week(month_old, freed_bytes)

        # 90일 이후: 매월 1개만 보관
        deleted_count += self._keep_one_per_month(very_old, freed_bytes)

        return {
            "deleted_count": deleted_count,
            "freed_mb": freed_bytes / (1024 * 1024),
        }

    def _gc_conservative(self) -> dict:
        """Conservative GC: 60일까지 모두 보관"""
        now = time.time()
        cutoff = now - (60 * 24 * 3600)

        snapshots = self.store.list_snapshots()

        deleted_count = 0
        freed_bytes = 0

        for snapshot in snapshots:
            if snapshot.timestamp < cutoff:
                freed_bytes += snapshot.compressed_size
                self.store.delete_snapshot(snapshot.version)
                deleted_count += 1

        return {
            "deleted_count": deleted_count,
            "freed_mb": freed_bytes / (1024 * 1024),
        }

    def _keep_one_per_day(self, snapshots: list, freed_bytes: int) -> int:
        """매일 1개만 보관 (나머지 삭제)"""
        # 날짜별 그룹화
        from collections import defaultdict

        by_day = defaultdict(list)

        for snapshot in snapshots:
            day = int(snapshot.timestamp // (24 * 3600))
            by_day[day].append(snapshot)

        deleted = 0

        for day_snapshots in by_day.values():
            # 각 날짜에서 최신 1개만 보관
            day_snapshots.sort(key=lambda s: s.timestamp, reverse=True)

            for snapshot in day_snapshots[1:]:
                freed_bytes += snapshot.compressed_size
                self.store.delete_snapshot(snapshot.version)
                deleted += 1

        return deleted

    def _keep_one_per_week(self, snapshots: list, freed_bytes: int) -> int:
        """매주 1개만 보관"""
        from collections import defaultdict

        by_week = defaultdict(list)

        for snapshot in snapshots:
            week = int(snapshot.timestamp // (7 * 24 * 3600))
            by_week[week].append(snapshot)

        deleted = 0

        for week_snapshots in by_week.values():
            week_snapshots.sort(key=lambda s: s.timestamp, reverse=True)

            for snapshot in week_snapshots[1:]:
                freed_bytes += snapshot.compressed_size
                self.store.delete_snapshot(snapshot.version)
                deleted += 1

        return deleted

    def _keep_one_per_month(self, snapshots: list, freed_bytes: int) -> int:
        """매월 1개만 보관"""
        from collections import defaultdict

        by_month = defaultdict(list)

        for snapshot in snapshots:
            month = int(snapshot.timestamp // (30 * 24 * 3600))
            by_month[month].append(snapshot)

        deleted = 0

        for month_snapshots in by_month.values():
            month_snapshots.sort(key=lambda s: s.timestamp, reverse=True)

            for snapshot in month_snapshots[1:]:
                freed_bytes += snapshot.compressed_size
                self.store.delete_snapshot(snapshot.version)
                deleted += 1

        return deleted
