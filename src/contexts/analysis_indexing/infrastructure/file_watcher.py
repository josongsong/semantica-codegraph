"""
파일 감시자 - Watchdog 기반 실시간 파일 시스템 모니터링.

IDE/에디터에서 파일 변경 시 자동으로 증분 인덱싱을 트리거합니다.
"""

import asyncio
import fnmatch
from collections.abc import Awaitable, Callable
from pathlib import Path

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeSet
from src.contexts.analysis_indexing.infrastructure.watcher_debouncer import EventDebouncer, FileEventType
from src.infra.observability import get_logger

logger = get_logger(__name__)


# 기본 제외 패턴
DEFAULT_EXCLUDE_PATTERNS = [
    ".git",
    ".git/*",
    "**/.git/*",
    "node_modules",
    "node_modules/*",
    "**/node_modules/*",
    "__pycache__",
    "__pycache__/*",
    "**/__pycache__/*",
    ".venv",
    ".venv/*",
    "**/.venv/*",
    "venv",
    "venv/*",
    "**/venv/*",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".DS_Store",
    "*.swp",
    "*.swo",
    "*~",
    ".idea",
    ".idea/*",
    ".vscode",
    ".vscode/*",
    "*.log",
    "*.tmp",
    "*.temp",
    "dist",
    "dist/*",
    "build",
    "build/*",
    ".pytest_cache",
    ".pytest_cache/*",
    ".mypy_cache",
    ".mypy_cache/*",
    ".ruff_cache",
    ".ruff_cache/*",
    "*.egg-info",
    "*.egg-info/*",
]

# 지원 확장자
DEFAULT_SUPPORTED_EXTENSIONS = [
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".ex",
    ".exs",
]


class IndexingEventHandler(FileSystemEventHandler):
    """
    Watchdog 이벤트 핸들러.

    파일 시스템 이벤트를 필터링하고 EventDebouncer로 전달합니다.
    """

    def __init__(
        self,
        repo_path: Path,
        debouncer: EventDebouncer,
        exclude_patterns: list[str] | None = None,
        supported_extensions: list[str] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        """
        Args:
            repo_path: 감시 대상 레포지토리 경로
            debouncer: 이벤트 디바운서
            exclude_patterns: 제외할 경로 패턴 (glob)
            supported_extensions: 지원 확장자 목록
            loop: asyncio 이벤트 루프 (None이면 현재 루프 사용)
        """
        super().__init__()
        self.repo_path = repo_path
        self.debouncer = debouncer
        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS
        self.supported_extensions = supported_extensions or DEFAULT_SUPPORTED_EXTENSIONS
        self._loop = loop

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """이벤트 루프 반환."""
        if self._loop:
            return self._loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

    def _should_ignore(self, path: str) -> bool:
        """경로가 제외 대상인지 확인."""
        # 상대 경로로 변환
        try:
            rel_path = Path(path).relative_to(self.repo_path)
            rel_path_str = str(rel_path)
        except ValueError:
            rel_path_str = path

        # 제외 패턴 체크
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(rel_path_str, pattern):
                return True
            # 경로의 각 부분도 체크
            for part in Path(rel_path_str).parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

        return False

    def _is_supported_file(self, path: str) -> bool:
        """지원하는 파일 확장자인지 확인."""
        ext = Path(path).suffix.lower()
        return ext in self.supported_extensions

    def _get_relative_path(self, path: str) -> str:
        """상대 경로 반환."""
        try:
            return str(Path(path).relative_to(self.repo_path))
        except ValueError:
            return path

    def _push_event(self, event_type: FileEventType, file_path: str, dest_path: str | None = None):
        """이벤트를 디바운서에 전달 (스레드 안전)."""
        rel_path = self._get_relative_path(file_path)
        rel_dest = self._get_relative_path(dest_path) if dest_path else None

        # watchdog은 별도 스레드에서 실행되므로 thread-safe하게 처리
        loop = self._get_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(
                self.debouncer.push_event,
                event_type,
                rel_path,
                rel_dest,
            )
        else:
            self.debouncer.push_event(event_type, rel_path, rel_dest)

    def on_created(self, event: FileSystemEvent):
        """파일/디렉토리 생성 이벤트."""
        if isinstance(event, DirCreatedEvent):
            return  # 디렉토리는 무시

        if self._should_ignore(event.src_path):
            return

        if not self._is_supported_file(event.src_path):
            return

        logger.debug("file_created", path=event.src_path)
        self._push_event(FileEventType.CREATED, event.src_path)

    def on_modified(self, event: FileSystemEvent):
        """파일/디렉토리 수정 이벤트."""
        if isinstance(event, DirModifiedEvent):
            return  # 디렉토리는 무시

        if self._should_ignore(event.src_path):
            return

        if not self._is_supported_file(event.src_path):
            return

        logger.debug("file_modified", path=event.src_path)
        self._push_event(FileEventType.MODIFIED, event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        """파일/디렉토리 삭제 이벤트."""
        if isinstance(event, DirDeletedEvent):
            return  # 디렉토리는 무시

        if self._should_ignore(event.src_path):
            return

        # 삭제된 파일은 확장자 체크 생략 (이미 없으므로)
        # 하지만 이전에 인덱싱된 파일만 처리해야 함
        if not self._is_supported_file(event.src_path):
            return

        logger.debug("file_deleted", path=event.src_path)
        self._push_event(FileEventType.DELETED, event.src_path)

    def on_moved(self, event: FileSystemEvent):
        """파일/디렉토리 이동 이벤트."""
        if isinstance(event, DirMovedEvent):
            return  # 디렉토리는 무시

        src_ignored = self._should_ignore(event.src_path)
        dest_ignored = self._should_ignore(event.dest_path)

        # 둘 다 무시 대상
        if src_ignored and dest_ignored:
            return

        # src만 무시 → dest는 created
        if src_ignored and not dest_ignored:
            if self._is_supported_file(event.dest_path):
                logger.debug("file_moved_to_watched", dest=event.dest_path)
                self._push_event(FileEventType.CREATED, event.dest_path)
            return

        # dest만 무시 → src는 deleted
        if not src_ignored and dest_ignored:
            if self._is_supported_file(event.src_path):
                logger.debug("file_moved_from_watched", src=event.src_path)
                self._push_event(FileEventType.DELETED, event.src_path)
            return

        # 둘 다 감시 대상
        if self._is_supported_file(event.src_path) or self._is_supported_file(event.dest_path):
            logger.debug("file_moved", src=event.src_path, dest=event.dest_path)
            self._push_event(FileEventType.MOVED, event.src_path, event.dest_path)


class FileWatcher:
    """
    Watchdog 기반 파일 감시자.

    레포지토리 디렉토리를 감시하고 파일 변경 시 인덱싱을 트리거합니다.

    사용 예:
        async def handle_changes(change_set: ChangeSet):
            await indexer.index_incremental(change_set)

        watcher = FileWatcher(
            repo_path=Path("/path/to/repo"),
            repo_id="my-repo",
            on_changes=handle_changes,
        )
        await watcher.start()
        # ... 애플리케이션 실행 ...
        await watcher.stop()
    """

    def __init__(
        self,
        repo_path: Path,
        repo_id: str,
        on_changes: Callable[[ChangeSet], Awaitable[None]] | None = None,
        debounce_ms: int = 300,
        max_batch_window_ms: int = 5000,
        exclude_patterns: list[str] | None = None,
        supported_extensions: list[str] | None = None,
        recursive: bool = True,
    ):
        """
        Args:
            repo_path: 감시 대상 레포지토리 경로
            repo_id: 레포지토리 ID
            on_changes: 변경 감지 시 호출할 콜백
            debounce_ms: 디바운스 시간 (ms)
            max_batch_window_ms: 최대 배치 윈도우 (ms)
            exclude_patterns: 제외할 경로 패턴
            supported_extensions: 지원 확장자 목록
            recursive: 하위 디렉토리 재귀 감시 여부
        """
        self.repo_path = Path(repo_path).resolve()
        self.repo_id = repo_id
        self.on_changes = on_changes
        self.recursive = recursive

        # 디바운서 생성
        self.debouncer = EventDebouncer(
            debounce_ms=debounce_ms,
            max_batch_window_ms=max_batch_window_ms,
            on_batch_ready=self._on_batch_ready,
        )

        # Watchdog Observer
        self._observer: Observer | None = None
        self._event_handler: IndexingEventHandler | None = None
        self._exclude_patterns = exclude_patterns
        self._supported_extensions = supported_extensions

        # 상태
        self._is_running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self):
        """파일 감시 시작."""
        if self._is_running:
            logger.warning("file_watcher_already_running", repo_id=self.repo_id)
            return

        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repo_path}")

        self._loop = asyncio.get_running_loop()

        # 디바운서 시작
        await self.debouncer.start()

        # 이벤트 핸들러 생성
        self._event_handler = IndexingEventHandler(
            repo_path=self.repo_path,
            debouncer=self.debouncer,
            exclude_patterns=self._exclude_patterns,
            supported_extensions=self._supported_extensions,
            loop=self._loop,
        )

        # Observer 생성 및 시작
        self._observer = Observer()
        self._observer.schedule(
            self._event_handler,
            str(self.repo_path),
            recursive=self.recursive,
        )
        self._observer.start()

        self._is_running = True
        logger.info(
            "file_watcher_started",
            repo_id=self.repo_id,
            repo_path=str(self.repo_path),
            recursive=self.recursive,
        )

    async def stop(self):
        """파일 감시 중지."""
        if not self._is_running:
            return

        self._is_running = False

        # Observer 중지
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        # 디바운서 중지 (남은 이벤트 플러시)
        await self.debouncer.stop()

        logger.info("file_watcher_stopped", repo_id=self.repo_id)

    async def _on_batch_ready(self, change_set: ChangeSet):
        """배치 준비 완료 시 콜백."""
        logger.info(
            "file_watcher_batch_ready",
            repo_id=self.repo_id,
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
        )

        if self.on_changes:
            try:
                await self.on_changes(change_set)
            except Exception as e:
                logger.error(
                    "file_watcher_callback_failed",
                    repo_id=self.repo_id,
                    error=str(e),
                    exc_info=True,
                )

    @property
    def is_running(self) -> bool:
        """감시 중인지 확인."""
        return self._is_running

    def get_stats(self) -> dict:
        """감시 통계 반환."""
        return {
            "repo_id": self.repo_id,
            "repo_path": str(self.repo_path),
            "is_running": self._is_running,
            "pending_events": self.debouncer.get_pending_count(),
            "recursive": self.recursive,
        }


class MultiRepoFileWatcher:
    """
    멀티 레포지토리 파일 감시자.

    여러 레포지토리를 동시에 감시합니다.
    """

    def __init__(
        self,
        on_changes: Callable[[str, ChangeSet], Awaitable[None]] | None = None,
        debounce_ms: int = 300,
        max_batch_window_ms: int = 5000,
    ):
        """
        Args:
            on_changes: 변경 감지 시 호출할 콜백 (repo_id, change_set)
            debounce_ms: 디바운스 시간 (ms)
            max_batch_window_ms: 최대 배치 윈도우 (ms)
        """
        self._on_changes = on_changes
        self._debounce_ms = debounce_ms
        self._max_batch_window_ms = max_batch_window_ms
        self._watchers: dict[str, FileWatcher] = {}

    async def add_repo(
        self,
        repo_path: Path,
        repo_id: str,
        exclude_patterns: list[str] | None = None,
        supported_extensions: list[str] | None = None,
    ):
        """레포지토리 추가 및 감시 시작."""
        if repo_id in self._watchers:
            logger.warning("repo_already_watched", repo_id=repo_id)
            return

        async def on_repo_changes(change_set: ChangeSet):
            if self._on_changes:
                await self._on_changes(repo_id, change_set)

        watcher = FileWatcher(
            repo_path=repo_path,
            repo_id=repo_id,
            on_changes=on_repo_changes,
            debounce_ms=self._debounce_ms,
            max_batch_window_ms=self._max_batch_window_ms,
            exclude_patterns=exclude_patterns,
            supported_extensions=supported_extensions,
        )

        await watcher.start()
        self._watchers[repo_id] = watcher

        logger.info("repo_added_to_watcher", repo_id=repo_id)

    async def remove_repo(self, repo_id: str):
        """레포지토리 감시 중지 및 제거."""
        if repo_id not in self._watchers:
            return

        watcher = self._watchers.pop(repo_id)
        await watcher.stop()

        logger.info("repo_removed_from_watcher", repo_id=repo_id)

    async def stop_all(self):
        """모든 감시 중지."""
        for repo_id in list(self._watchers.keys()):
            await self.remove_repo(repo_id)

    def get_watched_repos(self) -> list[str]:
        """감시 중인 레포지토리 목록."""
        return list(self._watchers.keys())

    def get_stats(self) -> dict:
        """전체 통계."""
        return {
            "watched_repos": len(self._watchers),
            "repos": {repo_id: w.get_stats() for repo_id, w in self._watchers.items()},
        }
