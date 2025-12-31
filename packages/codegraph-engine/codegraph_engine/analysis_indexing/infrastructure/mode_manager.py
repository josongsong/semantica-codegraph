"""인덱싱 모드 관리자."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeDetector, ChangeSet
from codegraph_engine.analysis_indexing.infrastructure.models.mode import (
    MODE_LAYER_CONFIG,
    IndexingMode,
    Layer,
    ModeTransitionConfig,
)
from codegraph_engine.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class IndexingPlan:
    """인덱싱 실행 계획."""

    mode: IndexingMode
    layers: list[Layer]
    target_files: set[str]  # 빈 set = 전체
    change_set: ChangeSet
    is_incremental: bool
    estimated_duration_seconds: float | None = None


class ModeManager:
    """인덱싱 모드 관리 및 실행 계획 생성."""

    def __init__(
        self,
        change_detector: ChangeDetector,
        scope_expander: ScopeExpander,
        metadata_store=None,  # 마지막 실행 시간 등 저장
    ):
        """
        Args:
            change_detector: 변경 감지기
            scope_expander: 범위 확장기
            metadata_store: 메타데이터 저장소
        """
        self.change_detector = change_detector
        self.scope_expander = scope_expander
        self.metadata_store = metadata_store

    async def create_plan(
        self,
        repo_path: Path,
        repo_id: str,
        mode: IndexingMode | None = None,
        auto_mode: bool = True,
        total_files: int | None = None,
    ) -> IndexingPlan:
        """
        인덱싱 실행 계획 생성.

        Args:
            repo_path: 레포지토리 경로
            repo_id: 레포지토리 ID
            mode: 명시적 모드 (None이면 자동 선택)
            auto_mode: 자동 모드 선택 활성화
            total_files: 전체 파일 개수 (Deep subset 계산용)

        Returns:
            IndexingPlan
        """
        # 1. 변경 감지 (L0)
        change_set = self.change_detector.detect_changes(repo_path, repo_id)

        # 2. 모드 결정
        if mode is None and auto_mode:
            mode = self._auto_select_mode(repo_id, change_set, total_files)
        elif mode is None:
            mode = IndexingMode.FAST  # 기본값

        logger.info(
            "indexing_mode_selected",
            mode=mode.value,
            total_changes=change_set.total_count,
            repo_id=repo_id,
        )

        # 3. 레이어 결정
        layers = MODE_LAYER_CONFIG.get(mode, [Layer.L1, Layer.L2])

        # 4. 범위 확장
        target_files = await self.scope_expander.expand_scope(
            change_set=change_set,
            mode=mode,
            repo_id=repo_id,
            total_files=total_files,
        )

        # 5. 증분 여부
        is_incremental = mode != IndexingMode.BOOTSTRAP and not change_set.is_empty()

        # 6. 예상 소요 시간
        estimated_duration = self._estimate_duration(mode, len(target_files) if target_files else total_files)

        plan = IndexingPlan(
            mode=mode,
            layers=layers,
            target_files=target_files,
            change_set=change_set,
            is_incremental=is_incremental,
            estimated_duration_seconds=estimated_duration,
        )

        logger.info(
            "indexing_plan_created",
            mode=mode.value,
            layers_count=len(layers),
            target_files_count=len(target_files) if target_files else None,
            is_incremental=is_incremental,
            estimated_duration_seconds=estimated_duration,
        )

        return plan

    def _auto_select_mode(self, repo_id: str, change_set: ChangeSet, total_files: int | None) -> IndexingMode:
        """
        자동 모드 선택.

        로직:
        1. 변경 없음 → FAST (noop)
        2. 첫 인덱싱 → BOOTSTRAP
        3. 변경 > 10개 → BALANCED 고려
        4. 마지막 Balanced 후 24시간 경과 → BALANCED
        5. 기본 → FAST

        Args:
            repo_id: 레포지토리 ID
            change_set: 변경 파일
            total_files: 전체 파일 개수

        Returns:
            선택된 모드
        """
        # 첫 인덱싱 확인
        if self.metadata_store:
            last_indexed = self.metadata_store.get_last_indexed_time(repo_id)
            if last_indexed is None:
                logger.info(
                    "auto_mode_bootstrap",
                    reason="first_indexing",
                    repo_id=repo_id,
                )
                return IndexingMode.BOOTSTRAP

            # Balanced 마지막 실행 시간
            last_balanced = self.metadata_store.get_last_mode_time(repo_id, IndexingMode.BALANCED)
            if last_balanced:
                hours_since = (datetime.now(timezone.utc) - last_balanced).total_seconds() / 3600
                if hours_since > ModeTransitionConfig.FAST_TO_BALANCED_HOURS_SINCE_LAST:
                    logger.info(
                        "auto_mode_balanced",
                        reason="time_since_last_balanced",
                        hours_since=round(hours_since, 1),
                        repo_id=repo_id,
                    )
                    return IndexingMode.BALANCED

        # 변경 파일 개수 기반
        if change_set.total_count >= ModeTransitionConfig.FAST_TO_BALANCED_MIN_CHANGED_FILES:
            logger.info(
                "auto_mode_balanced",
                reason="many_changed_files",
                changed_files=change_set.total_count,
                repo_id=repo_id,
            )
            return IndexingMode.BALANCED

        # 기본값
        return IndexingMode.FAST

    def _estimate_duration(self, mode: IndexingMode, file_count: int | None) -> float | None:
        """
        예상 소요 시간 추정 (초).

        경험적 수치 (10K 파일 기준):
        - Fast: ~5초
        - Balanced: ~2분
        - Deep: ~30분
        - Bootstrap: ~10분

        Args:
            mode: 인덱싱 모드
            file_count: 처리할 파일 개수

        Returns:
            예상 시간 (초)
        """
        if file_count is None:
            file_count = 10000  # 기본값

        # 파일당 평균 처리 시간 (초)
        time_per_file = {
            IndexingMode.FAST: 0.0005,  # 5초 / 10K = 0.5ms
            IndexingMode.BALANCED: 0.012,  # 2분 / 10K = 12ms
            IndexingMode.DEEP: 0.18,  # 30분 / 10K = 180ms
            IndexingMode.BOOTSTRAP: 0.06,  # 10분 / 10K = 60ms
            IndexingMode.REPAIR: 0.0005,  # Fast와 동일
        }

        base_time = time_per_file.get(mode, 0.001) * file_count

        # 오버헤드 추가 (초기화, 커밋 등)
        overhead = {
            IndexingMode.FAST: 1,
            IndexingMode.BALANCED: 10,
            IndexingMode.DEEP: 60,
            IndexingMode.BOOTSTRAP: 30,
            IndexingMode.REPAIR: 5,
        }

        return base_time + overhead.get(mode, 0)

    def should_transition_to_balanced(self, repo_id: str, idle_minutes: float) -> bool:
        """
        Fast → Balanced 자동 전환 필요 여부.

        Args:
            repo_id: 레포지토리 ID
            idle_minutes: 현재 idle 시간 (분)

        Returns:
            Balanced 모드로 전환 필요 여부
        """
        if idle_minutes < ModeTransitionConfig.FAST_TO_BALANCED_IDLE_MINUTES:
            return False

        if not self.metadata_store:
            return False

        # 마지막 Balanced 실행 시간 확인
        last_balanced = self.metadata_store.get_last_mode_time(repo_id, IndexingMode.BALANCED)
        if last_balanced is None:
            return True

        hours_since = (datetime.now(timezone.utc) - last_balanced).total_seconds() / 3600
        return hours_since > ModeTransitionConfig.FAST_TO_BALANCED_HOURS_SINCE_LAST


# NOTE: IndexingMetadataStore moved to metadata_store.py
# Import from there instead:
#   from codegraph_engine.analysis_indexing.infrastructure.metadata_store import IndexingMetadataStore
