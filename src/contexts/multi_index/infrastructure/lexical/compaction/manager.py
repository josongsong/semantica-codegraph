"""Compaction Manager - Two-Phase Base 재인덱싱."""

import asyncio
from typing import TYPE_CHECKING

from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.multi_index.infrastructure.lexical.adapter_zoekt import ZoektLexicalIndex
    from src.contexts.multi_index.infrastructure.lexical.compaction.freeze_buffer import FreezeBuffer
    from src.contexts.multi_index.infrastructure.lexical.delta.delta_index import DeltaLexicalIndex

logger = get_logger(__name__)


class CompactionManager:
    """Compaction Manager.

    Two-Phase Compaction으로 데이터 무손실 보장.

    Phase 1: Freeze (Delta snapshot + 새 Delta 생성)
    Phase 2: Rebuild (Base 재인덱싱, 비동기)
    Phase 3: Promote (Freeze buffer → Delta, 이전 Delta 삭제)
    """

    def __init__(
        self,
        base_index: "ZoektLexicalIndex",
        delta_index: "DeltaLexicalIndex",
        freeze_buffer: "FreezeBuffer",
        trigger_file_count: int = 200,
        trigger_age_hours: int = 24,
    ):
        """
        Args:
            base_index: Zoekt Base index
            delta_index: Delta index
            freeze_buffer: FreezeBuffer 인스턴스
            trigger_file_count: Compaction 트리거 (파일 수)
            trigger_age_hours: Compaction 트리거 (나이, 시간)
        """
        self.base = base_index
        self.delta = delta_index
        self.freeze_buffer = freeze_buffer
        self.trigger_file_count = trigger_file_count
        self.trigger_age_hours = trigger_age_hours

    async def should_compact(self, repo_id: str) -> bool:
        """Compaction 필요 여부.

        Trigger 조건:
        - Delta 파일 > 200개
        - Delta 나이 > 24시간

        Args:
            repo_id: 저장소 ID

        Returns:
            Compaction 필요 여부
        """
        delta_count = await self.delta.count(repo_id)

        # Phase 1 Day 11: Delta 나이 체크 (delta_lexical_stats 뷰 사용)
        age_hours = await self._get_delta_age_hours(repo_id)

        # Trigger 조건: 파일 수 또는 나이
        trigger_by_count = delta_count >= self.trigger_file_count
        trigger_by_age = age_hours >= self.trigger_age_hours if age_hours is not None else False

        should_compact = trigger_by_count or trigger_by_age

        if should_compact:
            logger.info(
                "compaction_triggered",
                repo_id=repo_id,
                delta_count=delta_count,
                age_hours=age_hours,
                trigger_by_count=trigger_by_count,
                trigger_by_age=trigger_by_age,
            )

        return should_compact

    async def _get_delta_age_hours(self, repo_id: str) -> float | None:
        """
        Delta 인덱스의 나이를 시간 단위로 반환.

        delta_lexical_stats 뷰를 사용하여 마지막 업데이트 시각 기준으로 나이를 계산.

        Args:
            repo_id: 저장소 ID

        Returns:
            Delta 나이 (시간), Delta가 없으면 None
        """
        # Delta index에 postgres_store (db) 속성 사용
        db = getattr(self.delta, "db", None)
        if not db:
            logger.warning("delta_db_not_available", repo_id=repo_id)
            return None

        try:
            query = """
                SELECT age_seconds
                FROM delta_lexical_stats
                WHERE repo_id = $1
                ORDER BY last_updated DESC
                LIMIT 1
            """

            pool = await db._ensure_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchrow(query, repo_id)

            if result and result["age_seconds"] is not None:
                age_hours = float(result["age_seconds"]) / 3600.0
                logger.debug(
                    "delta_age_calculated",
                    repo_id=repo_id,
                    age_hours=age_hours,
                )
                return age_hours

            logger.debug("no_delta_index_found", repo_id=repo_id)
            return None
        except Exception as e:
            logger.warning(
                "delta_age_check_failed",
                repo_id=repo_id,
                error=str(e),
            )
            return None

    async def compact(self, repo_id: str, snapshot_id: str) -> bool:
        """Two-Phase Compaction 실행.

        Args:
            repo_id: 저장소 ID
            snapshot_id: Snapshot ID

        Returns:
            성공 여부
        """
        logger.info(f"Starting Two-Phase Compaction: {repo_id}")

        try:
            # Phase 1: Freeze
            await self._phase1_freeze(repo_id)

            # Phase 2: Rebuild (비동기)
            rebuild_task = asyncio.create_task(self._phase2_rebuild(repo_id, snapshot_id))

            # Phase 3은 rebuild 완료 후
            success = await rebuild_task
            if success:
                await self._phase3_promote(repo_id)

            return success

        except Exception as e:
            logger.error(f"Compaction failed: {e}", exc_info=True)
            return False

    async def _phase1_freeze(self, repo_id: str) -> None:
        """Phase 1: Freeze Delta.

        Delta를 read-only로 전환하고
        새 write는 freeze buffer로 리다이렉트합니다.

        Args:
            repo_id: 저장소 ID
        """
        logger.info(f"Phase 1: Freezing Delta for {repo_id}")

        # Freeze 상태 설정
        await self.freeze_buffer.set_frozen(repo_id, True)

        logger.info(f"Phase 1 completed: Delta frozen for {repo_id}")

    async def _phase2_rebuild(self, repo_id: str, snapshot_id: str) -> bool:
        """Phase 2: Base 재인덱싱 (비동기).

        Base + Delta를 merge하여 새 Base 생성.

        Args:
            repo_id: 저장소 ID
            snapshot_id: Snapshot ID

        Returns:
            성공 여부
        """
        logger.info(f"Phase 2: Rebuilding Base for {repo_id}")

        try:
            # Base 재인덱싱 (Zoekt full reindex)
            await self.base.reindex_repo(repo_id, snapshot_id)

            logger.info(f"Phase 2 completed: Base rebuilt for {repo_id}")
            return True

        except Exception as e:
            logger.error(f"Phase 2 failed: {e}", exc_info=True)
            return False

    async def _phase3_promote(self, repo_id: str) -> None:
        """Phase 3: Freeze buffer replay & Delta 초기화.

        Args:
            repo_id: 저장소 ID
        """
        logger.info(f"Phase 3: Promoting freeze buffer for {repo_id}")

        # Freeze buffer에 있던 이벤트들을 Delta로 replay
        events = await self.freeze_buffer.replay(repo_id)

        for event in events:
            operation = event.get("operation")
            file_path = event.get("file_path")
            content = event.get("content")

            if operation == "index" and file_path and content:
                await self.delta.index_file(repo_id, file_path, content)
            elif operation == "delete" and file_path:
                await self.delta.delete_file(repo_id, file_path)

        # 이전 Delta 초기화
        await self.delta.clear(repo_id)

        # Freeze buffer 초기화
        await self.freeze_buffer.clear(repo_id)

        # Freeze 해제
        await self.freeze_buffer.set_frozen(repo_id, False)

        logger.info(
            f"Phase 3 completed: Promoted {len(events)} events, cleared Delta",
            extra={"repo_id": repo_id, "events": len(events)},
        )
