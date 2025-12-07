"""
In-Memory Event Bus

메모리 기반 이벤트 버스
"""

from collections.abc import Callable
from typing import Any

from ...domain.events.base import DomainEvent


class InMemoryEventBus:
    """인메모리 이벤트 버스"""

    def __init__(self):
        """초기화"""
        self._handlers: dict[str, list[Callable[[DomainEvent], Any]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], Any]) -> None:
        """
        이벤트 핸들러 등록

        Args:
            event_type: 이벤트 타입 (클래스명)
            handler: 이벤트 핸들러
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """
        이벤트 발행

        Args:
            event: 도메인 이벤트
        """
        event_type = event.__class__.__name__
        handlers = self._handlers.get(event_type, [])

        for handler in handlers:
            try:
                if callable(handler):
                    result = handler(event)
                    # async handler 지원
                    if hasattr(result, "__await__"):
                        await result
            except Exception as e:
                # 이벤트 핸들러 실패해도 계속 진행
                print(f"[EventBus] Handler failed: {e}")

    async def publish_all(self, events: list[DomainEvent]) -> None:
        """
        여러 이벤트 발행

        Args:
            events: 도메인 이벤트 리스트
        """
        for event in events:
            await self.publish(event)

    def clear_handlers(self) -> None:
        """모든 핸들러 제거 (테스트용)"""
        self._handlers.clear()
