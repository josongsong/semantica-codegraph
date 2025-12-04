"""
파일 감시 서비스 - FileWatcher와 BackgroundScheduler 통합.

이 서비스는 파일 변경 감지부터 인덱싱 실행까지 전체 플로우를 조율합니다.

파이프라인:
    FileWatcher (Watchdog)
        ↓
    EventDebouncer (300ms 디바운스)
        ↓
    ContentHashChecker (가짜 변경 필터링)
        ↓
    ScopeExpander (의존성 확장)
        ↓
    IndexJob 생성 (TriggerType.FS_EVENT)
        ↓
    BackgroundScheduler
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from src.contexts.analysis_indexing.infrastructure.background_scheduler import BackgroundScheduler, IdleDetector
from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeSet
from src.contexts.analysis_indexing.infrastructure.content_hash_checker import ContentHashChecker, HashStore
from src.contexts.analysis_indexing.infrastructure.file_watcher import MultiRepoFileWatcher
from src.contexts.analysis_indexing.infrastructure.models.job import TriggerType
from src.contexts.analysis_indexing.infrastructure.models.mode import IndexingMode
from src.contexts.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from src.infra.config.settings import settings
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.analysis_indexing.infrastructure.job_orchestrator import IndexJobOrchestrator

logger = get_logger(__name__)


class FileWatcherService:
    """
    파일 감시 서비스.

    FileWatcher → EventDebouncer → ContentHashChecker → ScopeExpander → IndexJob 플로우를 조율합니다.

    사용 예:
        service = FileWatcherService(
            job_orchestrator=orchestrator,
            scope_expander=expander,
            graph_store=graph_store,
        )
        await service.start()
        await service.watch_repo(Path("/path/to/repo"), "my-repo")
        # ... 애플리케이션 실행 ...
        await service.stop()
    """

    def __init__(
        self,
        job_orchestrator: "IndexJobOrchestrator | None" = None,
        scheduler: BackgroundScheduler | None = None,
        idle_detector: IdleDetector | None = None,
        scope_expander: ScopeExpander | None = None,
        hash_store: HashStore | None = None,
        enable_hash_check: bool = True,
        enable_scope_expansion: bool = True,
    ):
        """
        Args:
            job_orchestrator: 인덱싱 작업 오케스트레이터
            scheduler: 백그라운드 스케줄러 (None이면 새로 생성)
            idle_detector: Idle 감지기 (None이면 새로 생성)
            scope_expander: 의존성 범위 확장기 (None이면 비활성화)
            hash_store: 해시 저장소 (None이면 InMemoryHashStore 사용)
            enable_hash_check: 해시 체크 활성화 여부
            enable_scope_expansion: 의존성 확장 활성화 여부
        """
        self.job_orchestrator = job_orchestrator
        self.scheduler = scheduler
        self.idle_detector = idle_detector or IdleDetector()
        self.scope_expander = scope_expander
        self.hash_store = hash_store
        self.enable_hash_check = enable_hash_check
        self.enable_scope_expansion = enable_scope_expansion

        # 설정
        self._enabled = settings.file_watcher_enabled
        self._debounce_ms = settings.file_watcher_debounce_ms
        self._max_batch_window_ms = settings.file_watcher_max_batch_window_ms
        self._exclude_patterns = self._parse_patterns(settings.file_watcher_exclude_patterns)
        self._supported_extensions = self._parse_patterns(settings.file_watcher_supported_extensions)

        # 멀티 레포 감시자
        self._multi_watcher = MultiRepoFileWatcher(
            on_changes=self._on_repo_changes,
            debounce_ms=self._debounce_ms,
            max_batch_window_ms=self._max_batch_window_ms,
        )

        # 레포별 해시 체커
        self._hash_checkers: dict[str, ContentHashChecker] = {}

        # 레포별 경로 매핑
        self._repo_paths: dict[str, Path] = {}

        # 상태
        self._is_running = False

        # Idle 체크 타이머
        self._idle_check_task: asyncio.Task | None = None
        self._idle_check_interval_seconds = 60  # 1분마다 idle 체크
        self._idle_threshold_minutes = 5  # 5분 idle 시 Deep 인덱싱

        # Deep 인덱싱 스케줄 상태 (레포당 한번만)
        self._deep_scheduled_repos: set[str] = set()

    def _parse_patterns(self, patterns_str: str) -> list[str]:
        """쉼표 구분 문자열을 리스트로 변환."""
        return [p.strip() for p in patterns_str.split(",") if p.strip()]

    async def start(self):
        """서비스 시작."""
        if not self._enabled:
            logger.info("file_watcher_service_disabled")
            return

        if self._is_running:
            logger.warning("file_watcher_service_already_running")
            return

        self._is_running = True

        # Idle 체크 타이머 시작
        self._idle_check_task = asyncio.create_task(self._idle_check_loop())

        # BackgroundScheduler 시작 (있는 경우)
        if self.scheduler:
            asyncio.create_task(self.scheduler.start())

        logger.info(
            "file_watcher_service_started",
            debounce_ms=self._debounce_ms,
            max_batch_window_ms=self._max_batch_window_ms,
            idle_check_interval=self._idle_check_interval_seconds,
            idle_threshold_minutes=self._idle_threshold_minutes,
        )

    async def stop(self):
        """서비스 중지."""
        if not self._is_running:
            return

        # Idle 체크 타이머 중지
        if self._idle_check_task and not self._idle_check_task.done():
            self._idle_check_task.cancel()
            try:
                await self._idle_check_task
            except asyncio.CancelledError:
                pass

        # BackgroundScheduler 중지
        if self.scheduler:
            await self.scheduler.stop()

        await self._multi_watcher.stop_all()
        self._is_running = False
        logger.info("file_watcher_service_stopped")

    async def _idle_check_loop(self):
        """주기적으로 idle 상태를 체크하고 Deep 인덱싱 스케줄."""
        try:
            while self._is_running:
                await asyncio.sleep(self._idle_check_interval_seconds)

                if not self._is_running:
                    break

                # Idle 상태 체크
                if self.idle_detector.is_idle(self._idle_threshold_minutes):
                    await self._schedule_deep_indexing_if_needed()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("idle_check_loop_error", error=str(e), exc_info=True)

    async def _schedule_deep_indexing_if_needed(self):
        """Idle 상태일 때 Deep 인덱싱 스케줄."""
        watched_repos = self.get_watched_repos()

        for repo_id in watched_repos:
            # 이미 Deep 스케줄된 레포는 건너뜀
            if repo_id in self._deep_scheduled_repos:
                continue

            logger.info(
                "scheduling_deep_indexing",
                repo_id=repo_id,
                idle_minutes=self.idle_detector.get_idle_minutes(),
            )

            # BackgroundScheduler를 통해 Deep 인덱싱 스케줄
            if self.scheduler:
                await self.scheduler.schedule(
                    repo_id=repo_id,
                    mode=IndexingMode.DEEP,
                )
                self._deep_scheduled_repos.add(repo_id)

            # 또는 IndexJobOrchestrator를 통해 직접 Job 제출
            elif self.job_orchestrator:
                repo_path = self._repo_paths.get(repo_id)
                if repo_path:
                    try:
                        await self.job_orchestrator.submit_job(
                            repo_id=repo_id,
                            snapshot_id="deep",
                            repo_path=repo_path,
                            trigger_type=TriggerType.MANUAL,  # Idle-triggered deep indexing
                            trigger_metadata={
                                "trigger": "idle_deep_indexing",
                                "idle_minutes": self.idle_detector.get_idle_minutes(),
                            },
                        )
                        self._deep_scheduled_repos.add(repo_id)
                        logger.info(
                            "deep_indexing_job_submitted",
                            repo_id=repo_id,
                        )
                    except Exception as e:
                        logger.error(
                            "deep_indexing_job_failed",
                            repo_id=repo_id,
                            error=str(e),
                        )

    def reset_deep_schedule(self, repo_id: str | None = None):
        """
        Deep 인덱싱 스케줄 상태 초기화.

        다음 idle 시 다시 Deep 인덱싱이 트리거됩니다.

        Args:
            repo_id: 특정 레포만 초기화 (None이면 전체)
        """
        if repo_id:
            self._deep_scheduled_repos.discard(repo_id)
        else:
            self._deep_scheduled_repos.clear()

    async def watch_repo(
        self,
        repo_path: Path,
        repo_id: str,
        exclude_patterns: list[str] | None = None,
        supported_extensions: list[str] | None = None,
    ):
        """
        레포지토리 감시 시작.

        Args:
            repo_path: 레포지토리 경로
            repo_id: 레포지토리 ID
            exclude_patterns: 제외 패턴 (None이면 기본값 사용)
            supported_extensions: 지원 확장자 (None이면 기본값 사용)
        """
        if not self._enabled:
            logger.info("file_watcher_disabled_skipping_repo", repo_id=repo_id)
            return

        if not self._is_running:
            raise RuntimeError("FileWatcherService is not running. Call start() first.")

        repo_path = Path(repo_path).resolve()

        # 레포 경로 저장
        self._repo_paths[repo_id] = repo_path

        # 해시 체커 생성 (레포별)
        if self.enable_hash_check:
            self._hash_checkers[repo_id] = ContentHashChecker(
                repo_path=repo_path,
                repo_id=repo_id,
                hash_store=self.hash_store,
            )

        await self._multi_watcher.add_repo(
            repo_path=repo_path,
            repo_id=repo_id,
            exclude_patterns=exclude_patterns or self._exclude_patterns,
            supported_extensions=supported_extensions or self._supported_extensions,
        )

    async def unwatch_repo(self, repo_id: str):
        """레포지토리 감시 중지."""
        await self._multi_watcher.remove_repo(repo_id)

        # 해시 체커 정리
        if repo_id in self._hash_checkers:
            del self._hash_checkers[repo_id]

        # 경로 매핑 정리
        if repo_id in self._repo_paths:
            del self._repo_paths[repo_id]

    async def _on_repo_changes(self, repo_id: str, change_set: ChangeSet):
        """
        레포지토리 변경 감지 콜백.

        파이프라인:
        1. Idle 감지기 갱신
        2. ContentHashChecker로 가짜 변경 필터링
        3. ScopeExpander로 의존성 확장
        4. IndexJob 생성 및 제출
        """
        # 1. Idle 감지기 갱신 (사용자 활동)
        self.idle_detector.mark_activity()

        logger.info(
            "file_watcher_changes_detected",
            repo_id=repo_id,
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
        )

        if change_set.is_empty():
            return

        # 2. ContentHashChecker로 가짜 변경 필터링
        if self.enable_hash_check and repo_id in self._hash_checkers:
            hash_checker = self._hash_checkers[repo_id]
            filtered_set = hash_checker.filter_changes(change_set)

            if filtered_set.is_empty():
                logger.info(
                    "file_watcher_all_false_positives",
                    repo_id=repo_id,
                    original_count=change_set.total_count,
                )
                return

            change_set = filtered_set
            logger.info(
                "file_watcher_after_hash_check",
                repo_id=repo_id,
                added=len(change_set.added),
                modified=len(change_set.modified),
                deleted=len(change_set.deleted),
            )

        # 3. ScopeExpander로 의존성 확장 (1-hop)
        expanded_files = change_set.all_changed
        if self.enable_scope_expansion and self.scope_expander:
            expanded_files = await self.scope_expander.expand_scope(
                change_set=change_set,
                mode=IndexingMode.FAST,  # FileWatcher는 기본 FAST 모드
                repo_id=repo_id,
            )
            logger.info(
                "file_watcher_scope_expanded",
                repo_id=repo_id,
                original=len(change_set.all_changed),
                expanded=len(expanded_files),
            )

        # 4. IndexJob 생성 및 실행
        if self.job_orchestrator:
            try:
                changed_files = list(expanded_files)
                deleted_files = list(change_set.deleted)

                # Get repo_path from stored mapping
                repo_path = self._repo_paths.get(repo_id)
                if not repo_path:
                    logger.error(
                        "file_watcher_repo_path_not_found",
                        repo_id=repo_id,
                    )
                    return

                # Use "live" as snapshot_id for real-time file watching
                # This distinguishes from git-commit based indexing
                snapshot_id = "live"

                # Job 생성 및 제출
                job = await self.job_orchestrator.submit_job(
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    repo_path=repo_path,
                    scope_paths=changed_files,
                    trigger_type=TriggerType.FS_EVENT,
                    trigger_metadata={
                        "added": list(change_set.added),
                        "modified": list(change_set.modified),
                        "deleted": deleted_files,
                        "expanded_files": changed_files,
                        "expansion_enabled": self.enable_scope_expansion,
                    },
                )

                logger.info(
                    "file_watcher_job_submitted",
                    repo_id=repo_id,
                    job_id=job.id,
                    direct_changes=change_set.total_count,
                    expanded_files=len(changed_files),
                )

            except Exception as e:
                logger.error(
                    "file_watcher_job_submit_failed",
                    repo_id=repo_id,
                    error=str(e),
                    exc_info=True,
                )
        else:
            logger.warning(
                "file_watcher_no_orchestrator",
                repo_id=repo_id,
                message="Changes detected but no job orchestrator configured",
            )

    def get_watched_repos(self) -> list[str]:
        """감시 중인 레포지토리 목록."""
        return self._multi_watcher.get_watched_repos()

    def get_stats(self) -> dict:
        """서비스 통계."""
        # 해시 체커 통계 집계
        hash_checker_stats = {}
        for repo_id, checker in self._hash_checkers.items():
            hash_checker_stats[repo_id] = checker.get_stats()

        return {
            "enabled": self._enabled,
            "is_running": self._is_running,
            "debounce_ms": self._debounce_ms,
            "max_batch_window_ms": self._max_batch_window_ms,
            "enable_hash_check": self.enable_hash_check,
            "enable_scope_expansion": self.enable_scope_expansion,
            "idle_minutes": self.idle_detector.get_idle_minutes(),
            "watchers": self._multi_watcher.get_stats(),
            "hash_checker_stats": hash_checker_stats,
        }

    @property
    def is_running(self) -> bool:
        """서비스 실행 중인지 확인."""
        return self._is_running

    @property
    def is_enabled(self) -> bool:
        """서비스 활성화 여부."""
        return self._enabled


async def create_watcher_service(
    job_orchestrator: "IndexJobOrchestrator | None" = None,
    scope_expander: ScopeExpander | None = None,
    hash_store: HashStore | None = None,
    enable_hash_check: bool = True,
    enable_scope_expansion: bool = True,
) -> FileWatcherService:
    """
    FileWatcherService 팩토리 함수.

    Args:
        job_orchestrator: 인덱싱 작업 오케스트레이터
        scope_expander: 의존성 범위 확장기
        hash_store: 해시 저장소
        enable_hash_check: 해시 체크 활성화 여부
        enable_scope_expansion: 의존성 확장 활성화 여부

    Returns:
        구성된 FileWatcherService 인스턴스
    """
    service = FileWatcherService(
        job_orchestrator=job_orchestrator,
        scope_expander=scope_expander,
        hash_store=hash_store,
        enable_hash_check=enable_hash_check,
        enable_scope_expansion=enable_scope_expansion,
    )
    await service.start()
    return service
