"""모드 기반 인덱싱 통합 컨트롤러."""

from pathlib import Path

from codegraph_engine.analysis_indexing.infrastructure.background_scheduler import BackgroundScheduler, IdleDetector
from codegraph_engine.analysis_indexing.infrastructure.mode_manager import ModeManager
from codegraph_engine.analysis_indexing.infrastructure.models import IndexingMode
from codegraph_shared.infra.metadata.schema_version import SchemaVersionManager
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class ModeController:
    """모드 기반 인덱싱 통합 컨트롤러."""

    def __init__(
        self,
        orchestrator,
        mode_manager: ModeManager,
        schema_version_manager: SchemaVersionManager,
        background_scheduler: BackgroundScheduler | None = None,
    ):
        """
        Args:
            orchestrator: IndexingOrchestrator 인스턴스
            mode_manager: ModeManager 인스턴스
            schema_version_manager: SchemaVersionManager 인스턴스
            background_scheduler: 백그라운드 스케줄러 (선택)
        """
        self.orchestrator = orchestrator
        self.mode_manager = mode_manager
        self.schema_version_manager = schema_version_manager
        self.background_scheduler = background_scheduler
        self.idle_detector = IdleDetector()

    async def on_file_save(self, repo_id: str, repo_path: Path, file_path: str):
        """
        파일 저장 이벤트 처리 (Fast Mode).

        Args:
            repo_id: 레포지토리 ID
            repo_path: 레포지토리 경로
            file_path: 저장된 파일 경로
        """
        logger.info(f"File saved: {file_path}")
        self.idle_detector.mark_activity()

        # Fast Mode 실행
        result = await self.orchestrator.index_with_mode(
            repo_path=repo_path,
            repo_id=repo_id,
            mode=IndexingMode.FAST,
        )

        logger.info(f"Fast indexing completed in {result.total_duration_seconds:.2f}s")

        # Balanced 트리거 조건 확인
        if self._should_schedule_balanced(repo_id):
            await self._schedule_balanced(repo_id, repo_path)

    async def on_git_pull(self, repo_id: str, repo_path: Path):
        """
        git pull 이벤트 처리 (Fast → Balanced).

        Args:
            repo_id: 레포지토리 ID
            repo_path: 레포지토리 경로
        """
        logger.info("Git pull detected")
        self.idle_detector.mark_activity()

        # Fast Mode 먼저 실행 (변경 파일만)
        result = await self.orchestrator.index_with_mode(
            repo_path=repo_path,
            repo_id=repo_id,
            mode=IndexingMode.FAST,
        )

        logger.info(f"Fast indexing after pull: {result.total_duration_seconds:.2f}s")

        # Balanced 백그라운드 스케줄
        await self._schedule_balanced(repo_id, repo_path)

    async def on_idle(self, repo_id: str, repo_path: Path):
        """
        IDE idle 감지 시 처리 (Balanced 트리거).

        Args:
            repo_id: 레포지토리 ID
            repo_path: 레포지토리 경로
        """
        if not self.idle_detector.is_idle():
            return

        logger.info(f"IDE idle detected ({self.idle_detector.get_idle_minutes():.1f} min)")

        # Balanced 필요 여부 확인
        if self.mode_manager.should_transition_to_balanced(repo_id, self.idle_detector.get_idle_minutes()):
            await self._schedule_balanced(repo_id, repo_path)

    async def on_startup(self, repo_id: str, repo_path: Path):
        """
        앱 시작 시 처리 (버전 체크 + Repair).

        Args:
            repo_id: 레포지토리 ID
            repo_path: 레포지토리 경로
        """
        logger.info("App startup: checking schema version")

        # 버전 체크
        repair_needed, reason = self.schema_version_manager.check_and_repair(repo_id)

        if repair_needed:
            logger.warning(f"Repair needed: {reason}")

            # Repair Mode 실행
            result = await self.orchestrator.index_with_mode(
                repo_path=repo_path,
                repo_id=repo_id,
                mode=IndexingMode.REPAIR,
            )

            # 버전 업데이트
            self.schema_version_manager.mark_version_updated(repo_id)
            self.schema_version_manager.mark_repair_completed(repo_id)

            logger.info(f"Repair completed in {result.total_duration_seconds:.2f}s")
        else:
            logger.info("Schema version OK, no repair needed")

        # 무결성 체크
        is_valid, errors = self.schema_version_manager.check_integrity(repo_id)
        if not is_valid:
            logger.warning(f"Integrity check failed: {errors}")
            # 선택적으로 Repair 실행
            await self.orchestrator.index_with_mode(
                repo_path=repo_path,
                repo_id=repo_id,
                mode=IndexingMode.REPAIR,
            )

    async def request_deep_analysis(self, repo_id: str, repo_path: Path, query_files: set[str] | None = None):
        """
        고급 분석 요청 (on-demand Deep subset).

        Args:
            repo_id: 레포지토리 ID
            repo_path: 레포지토리 경로
            query_files: 분석할 파일들 (None이면 전체)
        """
        if query_files:
            logger.info(f"On-demand Deep analysis requested for {len(query_files)} files")
            # Subset Deep은 별도 구현 필요 (scope_expander.expand_from_query)
        else:
            logger.info("Full Deep analysis requested")

        result = await self.orchestrator.index_with_mode(
            repo_path=repo_path,
            repo_id=repo_id,
            mode=IndexingMode.DEEP,
        )

        logger.info(f"Deep analysis completed in {result.total_duration_seconds:.2f}s")
        return result

    async def _schedule_balanced(self, repo_id: str, repo_path: Path):
        """Balanced 모드 백그라운드 스케줄."""
        if not self.background_scheduler:
            logger.info("Background scheduler not available, running Balanced in foreground")
            await self.orchestrator.index_with_mode(
                repo_path=repo_path,
                repo_id=repo_id,
                mode=IndexingMode.BALANCED,
            )
            return

        logger.info("Scheduling Balanced mode in background")
        await self.background_scheduler.schedule(
            repo_id=repo_id,
            mode=IndexingMode.BALANCED,
        )

    def _should_schedule_balanced(self, repo_id: str) -> bool:
        """Balanced 스케줄 필요 여부 확인."""
        # 간단한 휴리스틱: idle 상태이고 마지막 Balanced 후 오래 지났으면
        if not self.idle_detector.is_idle():
            return False

        return self.mode_manager.should_transition_to_balanced(repo_id, self.idle_detector.get_idle_minutes())
