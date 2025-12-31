"""
이벤트 디바운서 - 파일 시스템 이벤트 배칭 및 디바운싱.

연속적인 파일 변경 이벤트를 효율적으로 처리하기 위해:
- 디바운싱: 300ms 내 동일 파일 이벤트 병합
- 배칭: 최대 5초 윈도우 내 이벤트 모음
- 최신 우선: 파일별 최신 이벤트만 유지
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeSet
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class FileEventType(Enum):
    """파일 이벤트 유형."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


@dataclass
class FileEvent:
    """단일 파일 이벤트."""

    event_type: FileEventType
    file_path: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    # moved 이벤트용
    dest_path: str | None = None


class EventDebouncer:
    """
    파일 이벤트 디바운서.

    기능:
    - 디바운싱: debounce_ms 내 동일 파일 이벤트 병합
    - 배칭: max_batch_window_ms 내 이벤트 모음
    - 콜백: 배치 준비 시 on_batch_ready 호출

    Thread-Safety:
    - Thread-safe queue for cross-thread push_event
    - Consumer loop runs in async context with proper locking

    사용 예:
        debouncer = EventDebouncer(
            debounce_ms=300,
            max_batch_window_ms=5000,
            on_batch_ready=handle_changes,
        )
        await debouncer.start()
        debouncer.push_event(FileEventType.MODIFIED, "src/main.py")  # Thread-safe
    """

    def __init__(
        self,
        debounce_ms: int = 300,
        max_batch_window_ms: int = 5000,
        on_batch_ready: Callable[[ChangeSet], Awaitable[None]] | None = None,
        max_queue_size: int = 10000,
    ):
        """
        Args:
            debounce_ms: 디바운스 시간 (ms). 이 시간 내 동일 파일 이벤트 병합.
            max_batch_window_ms: 최대 배치 윈도우 (ms). 이 시간 후 강제 플러시.
            on_batch_ready: 배치 준비 시 호출할 콜백.
            max_queue_size: 최대 큐 크기 (메모리 보호). Default: 10000
        """
        self.debounce_ms = debounce_ms
        self.max_batch_window_ms = max_batch_window_ms
        self.on_batch_ready = on_batch_ready
        self.max_queue_size = max_queue_size

        # Thread-safe queue for cross-thread communication
        self._queue: asyncio.Queue[FileEvent] = asyncio.Queue(maxsize=max_queue_size)

        # 이벤트 버퍼: file_path → FileEvent (최신만 유지)
        self._events: dict[str, FileEvent] = {}
        self._lock = asyncio.Lock()

        # 타이머
        self._debounce_task: asyncio.Task | None = None
        self._batch_window_task: asyncio.Task | None = None
        self._batch_start_time: datetime | None = None

        # 상태
        self._is_running = False
        self._consumer_task: asyncio.Task | None = None

    async def start(self):
        """디바운서 시작."""
        self._is_running = True

        # Consumer task 시작 (queue → events buffer)
        self._consumer_task = asyncio.create_task(self._consumer_loop())

        logger.info(
            "event_debouncer_started",
            debounce_ms=self.debounce_ms,
            max_batch_window_ms=self.max_batch_window_ms,
            max_queue_size=self.max_queue_size,
        )

    async def stop(self):
        """디바운서 중지 및 남은 이벤트 플러시."""
        self._is_running = False

        # Consumer task 취소
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # 타이머 취소
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        if self._batch_window_task and not self._batch_window_task.done():
            self._batch_window_task.cancel()

        # 남은 이벤트 플러시
        if self._events:
            await self._flush()

        logger.info("event_debouncer_stopped")

    def push_event(self, event_type: FileEventType, file_path: str, dest_path: str | None = None):
        """
        이벤트 추가 (Thread-safe).

        This method is thread-safe and can be called from Watchdog threads.
        Events are pushed to a queue and consumed by the consumer loop.

        Args:
            event_type: 이벤트 유형
            file_path: 파일 경로
            dest_path: 이동 대상 경로 (moved 이벤트용)
        """
        if not self._is_running:
            logger.warning("event_debouncer_not_running", file_path=file_path)
            return

        event = FileEvent(
            event_type=event_type,
            file_path=file_path,
            dest_path=dest_path,
        )

        # Thread-safe queue push (non-blocking)
        try:
            self._queue.put_nowait(event)
            logger.debug(
                "event_queued",
                event_type=event_type.value,
                file_path=file_path,
                queue_size=self._queue.qsize(),
            )
        except asyncio.QueueFull:
            logger.error(
                "event_queue_full",
                file_path=file_path,
                max_queue_size=self.max_queue_size,
            )
            # Drop event (prefer performance over completeness)

    async def _consumer_loop(self):
        """
        Consumer loop: queue → events buffer (async context).

        Runs in async context, consumes events from thread-safe queue.
        """
        while self._is_running:
            try:
                # Wait for event with timeout (check _is_running periodically)
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)

                # Process event in async context (thread-safe)
                async with self._lock:
                    # 이벤트 버퍼에 추가 (동일 파일은 최신으로 덮어쓰기)
                    self._events[event.file_path] = event

                    # moved 이벤트: dest_path도 추가 (created로)
                    if event.event_type == FileEventType.MOVED and event.dest_path:
                        self._events[event.dest_path] = FileEvent(
                            event_type=FileEventType.CREATED,
                            file_path=event.dest_path,
                        )

                    logger.debug(
                        "event_consumed",
                        event_type=event.event_type.value,
                        file_path=event.file_path,
                        buffer_size=len(self._events),
                    )

                    # 배치 윈도우 시작
                    if self._batch_start_time is None:
                        self._batch_start_time = datetime.now(timezone.utc)
                        self._start_batch_window_timer()

                    # 디바운스 타이머 리셋
                    self._reset_debounce_timer()

            except asyncio.TimeoutError:
                # No events, continue polling
                continue
            except asyncio.CancelledError:
                # Task cancelled during shutdown
                logger.info("consumer_loop_cancelled")
                break
            except Exception as e:
                logger.error(
                    "consumer_loop_error",
                    error=str(e),
                    exc_info=True,
                )

    def _reset_debounce_timer(self):
        """디바운스 타이머 리셋."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        self._debounce_task = asyncio.create_task(self._debounce_timer())

    async def _debounce_timer(self):
        """디바운스 타이머 - debounce_ms 후 플러시."""
        try:
            await asyncio.sleep(self.debounce_ms / 1000)
            await self._flush()
        except asyncio.CancelledError:
            pass  # 타이머 리셋됨

    def _start_batch_window_timer(self):
        """배치 윈도우 타이머 시작."""
        if self._batch_window_task and not self._batch_window_task.done():
            return  # 이미 실행 중

        self._batch_window_task = asyncio.create_task(self._batch_window_timer())

    async def _batch_window_timer(self):
        """배치 윈도우 타이머 - max_batch_window_ms 후 강제 플러시."""
        try:
            await asyncio.sleep(self.max_batch_window_ms / 1000)
            logger.info("batch_window_expired", forcing_flush=True)
            await self._flush()
        except asyncio.CancelledError:
            pass  # 플러시 완료로 취소됨

    async def _flush(self):
        """버퍼된 이벤트 플러시 및 콜백 호출."""
        async with self._lock:
            if not self._events:
                return

            # 이벤트 수집
            events = dict(self._events)
            self._events.clear()
            self._batch_start_time = None

            # 타이머 취소
            if self._batch_window_task and not self._batch_window_task.done():
                self._batch_window_task.cancel()

            # ChangeSet 생성
            change_set = self._build_change_set(events)

            logger.info(
                "events_flushed",
                added=len(change_set.added),
                modified=len(change_set.modified),
                deleted=len(change_set.deleted),
            )

            # 콜백 호출
            if self.on_batch_ready and not change_set.is_empty():
                try:
                    await self.on_batch_ready(change_set)
                except Exception as e:
                    logger.error("on_batch_ready_failed", error=str(e), exc_info=True)

    def _build_change_set(self, events: dict[str, FileEvent]) -> ChangeSet:
        """이벤트 맵 → ChangeSet 변환."""
        added: set[str] = set()
        modified: set[str] = set()
        deleted: set[str] = set()

        for file_path, event in events.items():
            if event.event_type == FileEventType.CREATED:
                added.add(file_path)
            elif event.event_type == FileEventType.MODIFIED:
                modified.add(file_path)
            elif event.event_type == FileEventType.DELETED:
                deleted.add(file_path)
            elif event.event_type == FileEventType.MOVED:
                # source는 deleted, dest는 이미 CREATED로 추가됨
                deleted.add(file_path)

        return ChangeSet(added=added, modified=modified, deleted=deleted)

    def get_pending_count(self) -> int:
        """대기 중인 이벤트 개수."""
        return len(self._events)

    def is_idle(self) -> bool:
        """버퍼가 비어있는지 확인."""
        return len(self._events) == 0
