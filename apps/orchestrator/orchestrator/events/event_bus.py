"""Event Bus 및 Cancellation Token"""

import asyncio
from collections.abc import AsyncIterator, Callable

from codegraph_shared.common.observability import get_logger

from .models import AgentEvent, EventType

logger = get_logger(__name__)


class CancellationToken:
    """취소 토큰 (E-4)"""

    def __init__(self):
        self._cancelled = False
        self._callbacks: list[Callable[[], None]] = []

    def cancel(self):
        """취소 요청"""
        if not self._cancelled:
            self._cancelled = True
            logger.info("Cancellation requested")

            # 콜백 실행
            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Cancellation callback error: {e}")

    def is_cancelled(self) -> bool:
        """취소 여부"""
        return self._cancelled

    def on_cancel(self, callback: Callable[[], None]):
        """취소 시 콜백 등록"""
        self._callbacks.append(callback)

    def check_cancelled(self):
        """취소 확인 (예외 발생)"""
        if self._cancelled:
            raise asyncio.CancelledError("Task was cancelled")


class EventBus:
    """이벤트 버스 (E-2)"""

    def __init__(self):
        self._events: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._subscribers: list[Callable[[AgentEvent], None]] = []
        self._event_order: list[EventType] = []

    async def emit(self, event: AgentEvent):
        """
        이벤트 발행

        Args:
            event: AgentEvent
        """
        # 순서 기록
        self._event_order.append(event.type)

        # Queue에 추가
        await self._events.put(event)

        # 구독자에게 알림
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")

        logger.debug(f"Event emitted: {event.type} for {event.task_id}")

    async def stream(self) -> AsyncIterator[AgentEvent]:
        """
        이벤트 스트리밍

        Yields:
            AgentEvent
        """
        while True:
            event = await self._events.get()
            yield event

            # Completed나 Failed면 종료
            if event.type in [EventType.COMPLETED, EventType.FAILED, EventType.CANCELLED]:
                break

    def subscribe(self, callback: Callable[[AgentEvent], None]):
        """
        이벤트 구독

        Args:
            callback: 이벤트 핸들러
        """
        self._subscribers.append(callback)

    def get_event_order(self) -> list[EventType]:
        """
        이벤트 순서 조회 (E-2 검증용)

        Returns:
            EventType 리스트
        """
        return self._event_order.copy()

    def verify_order(self, expected: list[EventType]) -> bool:
        """
        이벤트 순서 검증

        Args:
            expected: 예상 순서

        Returns:
            True if order matches
        """
        return self._event_order == expected
