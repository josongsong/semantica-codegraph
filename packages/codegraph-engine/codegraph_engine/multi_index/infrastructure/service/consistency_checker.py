"""
Cross-Index Consistency Checker

인덱스 간 일관성 검증 (Senior Review Recommendation).

Responsibilities:
- 모든 인덱스가 동일한 snapshot_id 기준인지 검증
- 인덱스별 문서 수 비교
- 누락된 chunk_id 탐지
- 일관성 리포트 생성
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.service.index_registry import IndexRegistry

logger = get_logger(__name__)


@dataclass
class IndexSnapshot:
    """인덱스별 스냅샷 정보"""

    name: str
    snapshot_id: str | None
    document_count: int
    chunk_ids: set[str] = field(default_factory=set)
    last_indexed_at: datetime | None = None
    error: str | None = None


@dataclass
class ConsistencyReport:
    """일관성 검증 리포트"""

    repo_id: str
    checked_at: datetime
    is_consistent: bool
    reference_snapshot_id: str | None  # 기준 snapshot_id (가장 많은 문서를 가진 인덱스)
    index_snapshots: list[IndexSnapshot]
    issues: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """간단한 요약"""
        status = "✅ CONSISTENT" if self.is_consistent else "❌ INCONSISTENT"
        return f"{status}: {len(self.index_snapshots)} indexes, {len(self.issues)} issues"


class ConsistencyChecker:
    """
    Cross-Index Consistency Checker.

    여러 인덱스(Vector, Lexical, Symbol, Fuzzy, Domain)가
    동일한 snapshot 기준으로 동기화되어 있는지 검증합니다.

    Usage:
        checker = ConsistencyChecker(registry)
        report = await checker.check(repo_id, snapshot_id)
        if not report.is_consistent:
            logger.warning(f"Inconsistency detected: {report.issues}")
    """

    def __init__(
        self,
        registry: IndexRegistry,
        tolerance_percentage: float = 5.0,
    ):
        """
        Args:
            registry: 인덱스 레지스트리
            tolerance_percentage: 문서 수 차이 허용 비율 (기본 5%)
        """
        self._registry = registry
        self._tolerance_percentage = tolerance_percentage

    async def check(
        self,
        repo_id: str,
        expected_snapshot_id: str | None = None,
    ) -> ConsistencyReport:
        """
        모든 인덱스의 일관성 검증.

        Args:
            repo_id: 저장소 ID
            expected_snapshot_id: 예상되는 snapshot_id (None이면 자동 탐지)

        Returns:
            ConsistencyReport
        """
        checked_at = datetime.now(timezone.utc)
        issues: list[str] = []
        index_snapshots: list[IndexSnapshot] = []

        # 각 인덱스의 상태 수집 (병렬)
        entries = self._registry.get_all()

        async def _get_snapshot(name: str, index: Any) -> IndexSnapshot:
            try:
                snapshot_info = await self._get_index_snapshot(name, index, repo_id)
                return snapshot_info
            except Exception as e:
                logger.error(f"consistency_check_failed: {name}", exc_info=True)
                return IndexSnapshot(
                    name=name,
                    snapshot_id=None,
                    document_count=0,
                    error=str(e),
                )

        tasks = [_get_snapshot(entry.name, entry.index) for entry in entries]
        index_snapshots = await asyncio.gather(*tasks)

        # 에러 발생한 인덱스 체크
        for snapshot in index_snapshots:
            if snapshot.error:
                issues.append(f"[{snapshot.name}] Error: {snapshot.error}")

        # 유효한 스냅샷만 필터
        valid_snapshots = [s for s in index_snapshots if s.error is None and s.snapshot_id]

        if not valid_snapshots:
            return ConsistencyReport(
                repo_id=repo_id,
                checked_at=checked_at,
                is_consistent=False,
                reference_snapshot_id=None,
                index_snapshots=list(index_snapshots),
                issues=["No valid index snapshots found"] + issues,
            )

        # 기준 snapshot_id 결정
        reference_snapshot_id = expected_snapshot_id
        if not reference_snapshot_id:
            # 가장 많은 문서를 가진 인덱스의 snapshot_id를 기준으로
            reference_snapshot_id = max(valid_snapshots, key=lambda s: s.document_count).snapshot_id

        # Snapshot ID 일치 검증
        snapshot_id_mismatches = [s for s in valid_snapshots if s.snapshot_id != reference_snapshot_id]
        for mismatch in snapshot_id_mismatches:
            issues.append(f"[{mismatch.name}] Snapshot mismatch: {mismatch.snapshot_id} != {reference_snapshot_id}")

        # 문서 수 검증 (허용 범위 내인지)
        max_count = max(s.document_count for s in valid_snapshots)
        if max_count > 0:
            for snapshot in valid_snapshots:
                diff_pct = abs(snapshot.document_count - max_count) / max_count * 100
                if diff_pct > self._tolerance_percentage:
                    issues.append(
                        f"[{snapshot.name}] Document count mismatch: {snapshot.document_count} "
                        f"(expected ~{max_count}, diff={diff_pct:.1f}%)"
                    )

        # Chunk ID 교차 검증 (샘플링)
        chunk_issues = self._check_chunk_overlap(valid_snapshots)
        issues.extend(chunk_issues)

        is_consistent = len(issues) == 0

        report = ConsistencyReport(
            repo_id=repo_id,
            checked_at=checked_at,
            is_consistent=is_consistent,
            reference_snapshot_id=reference_snapshot_id,
            index_snapshots=list(index_snapshots),
            issues=issues,
        )

        if is_consistent:
            logger.info(
                "consistency_check_passed",
                repo_id=repo_id,
                indexes=len(valid_snapshots),
            )
        else:
            logger.warning(
                "consistency_check_failed",
                repo_id=repo_id,
                issues=len(issues),
                details=issues[:5],  # 처음 5개만 로그
            )

        return report

    async def _get_index_snapshot(
        self,
        name: str,
        index: Any,
        repo_id: str,
    ) -> IndexSnapshot:
        """
        개별 인덱스의 스냅샷 정보 수집.

        각 인덱스 어댑터는 다른 인터페이스를 가지므로 이름 기반 분기.
        """
        snapshot_id: str | None = None
        document_count = 0
        chunk_ids: set[str] = set()

        # 인덱스별 메타데이터 조회 (어댑터마다 다른 방법 사용)
        if hasattr(index, "get_stats"):
            # 통합 stats 메서드가 있는 경우
            stats = await index.get_stats(repo_id)
            snapshot_id = stats.get("snapshot_id")
            document_count = stats.get("document_count", 0)
            chunk_ids = set(stats.get("chunk_ids", [])[:100])  # 샘플링

        elif hasattr(index, "count"):
            # count 메서드만 있는 경우
            document_count = await index.count(repo_id)

        elif name == "vector" and hasattr(index, "client"):
            # Qdrant Vector Index
            try:
                collection_info = await index.client.get_collection(f"{repo_id}_vectors")
                document_count = collection_info.points_count
                # snapshot_id는 별도 조회 필요
            except Exception:
                pass

        elif name == "lexical" and hasattr(index, "postgres"):
            # PostgreSQL Lexical Index
            try:
                async with index.postgres.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT snapshot_id, COUNT(*) as cnt FROM lexical_index "
                        "WHERE repo_id = $1 GROUP BY snapshot_id ORDER BY cnt DESC LIMIT 1",
                        repo_id,
                    )
                    if row:
                        snapshot_id = row["snapshot_id"]
                        document_count = row["cnt"]
            except Exception:
                pass

        elif name == "fuzzy" and hasattr(index, "postgres"):
            # PostgreSQL Fuzzy Index
            try:
                async with index.postgres.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT snapshot_id, COUNT(*) as cnt FROM fuzzy_identifiers "
                        "WHERE repo_id = $1 GROUP BY snapshot_id ORDER BY cnt DESC LIMIT 1",
                        repo_id,
                    )
                    if row:
                        snapshot_id = row["snapshot_id"]
                        document_count = row["cnt"]
            except Exception:
                pass

        elif name == "domain" and hasattr(index, "postgres"):
            # PostgreSQL Domain Index
            try:
                async with index.postgres.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT snapshot_id, COUNT(*) as cnt FROM domain_documents "
                        "WHERE repo_id = $1 GROUP BY snapshot_id ORDER BY cnt DESC LIMIT 1",
                        repo_id,
                    )
                    if row:
                        snapshot_id = row["snapshot_id"]
                        document_count = row["cnt"]
            except Exception:
                pass

        return IndexSnapshot(
            name=name,
            snapshot_id=snapshot_id,
            document_count=document_count,
            chunk_ids=chunk_ids,
        )

    def _check_chunk_overlap(
        self,
        snapshots: list[IndexSnapshot],
    ) -> list[str]:
        """
        Chunk ID 교차 검증.

        모든 인덱스에 공통으로 있어야 하는 chunk가 누락되었는지 확인.
        """
        issues: list[str] = []

        # chunk_ids가 있는 스냅샷만 필터
        snapshots_with_chunks = [s for s in snapshots if s.chunk_ids]

        if len(snapshots_with_chunks) < 2:
            return issues

        # 첫 번째를 기준으로 다른 인덱스와 비교
        reference = snapshots_with_chunks[0]

        for other in snapshots_with_chunks[1:]:
            missing_in_other = reference.chunk_ids - other.chunk_ids
            missing_in_reference = other.chunk_ids - reference.chunk_ids

            if missing_in_other:
                issues.append(f"[{other.name}] Missing {len(missing_in_other)} chunks present in [{reference.name}]")

            if missing_in_reference:
                issues.append(
                    f"[{reference.name}] Missing {len(missing_in_reference)} chunks present in [{other.name}]"
                )

        return issues

    async def repair(
        self,
        repo_id: str,
        report: ConsistencyReport,
    ) -> bool:
        """
        불일치 복구 (Future: 자동 재인덱싱 트리거).

        Args:
            repo_id: 저장소 ID
            report: 일관성 리포트

        Returns:
            복구 성공 여부
        """
        if report.is_consistent:
            return True

        logger.info(
            "consistency_repair_requested",
            repo_id=repo_id,
            issues=len(report.issues),
        )

        # TODO: 자동 재인덱싱 로직 구현
        # - snapshot_id가 다른 인덱스 재인덱싱
        # - 누락된 chunk 재인덱싱

        return False
