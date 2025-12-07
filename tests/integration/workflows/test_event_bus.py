"""
Event Bus Integration Tests

이벤트 버스 통합 테스트
"""

import pytest

from src.contexts.analysis_indexing.domain.events.file_indexed import FileIndexed
from src.contexts.analysis_indexing.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus


@pytest.mark.asyncio
class TestInMemoryEventBus:
    """InMemory 이벤트 버스 통합 테스트"""

    async def test_publish_and_handle(self):
        """이벤트 발행 및 처리"""
        bus = InMemoryEventBus()
        handled_events = []

        def handler(event):
            handled_events.append(event)

        bus.subscribe("FileIndexed", handler)

        event = FileIndexed(
            aggregate_id="session-1",
            file_path="/tmp/test.py",
            language="python",
        )

        await bus.publish(event)

        assert len(handled_events) == 1
        assert handled_events[0] == event

    async def test_multiple_handlers(self):
        """여러 핸들러 등록"""
        bus = InMemoryEventBus()
        handler1_calls = []
        handler2_calls = []

        def handler1(event):
            handler1_calls.append(event)

        def handler2(event):
            handler2_calls.append(event)

        bus.subscribe("FileIndexed", handler1)
        bus.subscribe("FileIndexed", handler2)

        event = FileIndexed(aggregate_id="session-1", file_path="/tmp/test.py")

        await bus.publish(event)

        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    async def test_publish_all(self):
        """여러 이벤트 발행"""
        bus = InMemoryEventBus()
        handled_events = []

        def handler(event):
            handled_events.append(event)

        bus.subscribe("FileIndexed", handler)

        events = [
            FileIndexed(aggregate_id="session-1", file_path="/tmp/test1.py"),
            FileIndexed(aggregate_id="session-1", file_path="/tmp/test2.py"),
        ]

        await bus.publish_all(events)

        assert len(handled_events) == 2
