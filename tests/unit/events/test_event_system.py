"""
E-2, E-4: Event System 테스트

E-2: Step 이벤트 순서 정확도
E-4: Cancellation 지원
"""

import asyncio

import pytest

from apps.orchestrator.orchestrator.events import AgentEvent, CancellationToken, EventBus, EventType


class TestEventOrder:
    """E-2: 이벤트 순서 테스트"""

    @pytest.mark.asyncio
    async def test_e2_1_correct_event_order(self):
        """E-2-1: Started → Running → Completed 순서 유지"""
        # Given
        bus = EventBus()

        # When
        await bus.emit(AgentEvent(type=EventType.STARTED, task_id="task1"))
        await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="task1"))
        await bus.emit(AgentEvent(type=EventType.COMPLETED, task_id="task1"))

        # Then
        order = bus.get_event_order()
        assert order == [EventType.STARTED, EventType.RUNNING, EventType.COMPLETED]

    @pytest.mark.asyncio
    async def test_e2_2_verify_order_method(self):
        """E-2-2: verify_order 메서드"""
        # Given
        bus = EventBus()
        await bus.emit(AgentEvent(type=EventType.STARTED, task_id="t1"))
        await bus.emit(AgentEvent(type=EventType.COMPLETED, task_id="t1"))

        # Then
        assert bus.verify_order([EventType.STARTED, EventType.COMPLETED])
        assert not bus.verify_order([EventType.COMPLETED, EventType.STARTED])  # 잘못된 순서

    @pytest.mark.asyncio
    async def test_e2_3_failed_event_order(self):
        """E-2-3: Started → Running → Failed 순서"""
        # Given
        bus = EventBus()

        # When
        await bus.emit(AgentEvent(type=EventType.STARTED, task_id="task1"))
        await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="task1"))
        await bus.emit(AgentEvent(type=EventType.FAILED, task_id="task1"))

        # Then
        assert bus.verify_order([EventType.STARTED, EventType.RUNNING, EventType.FAILED])

    @pytest.mark.asyncio
    async def test_e2_4_cancelled_event_order(self):
        """E-2-4: Started → Running → Cancelled 순서"""
        # Given
        bus = EventBus()

        # When
        await bus.emit(AgentEvent(type=EventType.STARTED, task_id="task1"))
        await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="task1"))
        await bus.emit(AgentEvent(type=EventType.CANCELLED, task_id="task1"))

        # Then
        assert bus.verify_order([EventType.STARTED, EventType.RUNNING, EventType.CANCELLED])

    @pytest.mark.asyncio
    async def test_e2_5_multiple_running_events(self):
        """E-2-5: 여러 RUNNING 이벤트 허용"""
        # Given
        bus = EventBus()

        # When
        await bus.emit(AgentEvent(type=EventType.STARTED, task_id="t1"))
        await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="t1", message="Step 1"))
        await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="t1", message="Step 2"))
        await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="t1", message="Step 3"))
        await bus.emit(AgentEvent(type=EventType.COMPLETED, task_id="t1"))

        # Then
        order = bus.get_event_order()
        assert order.count(EventType.RUNNING) == 3
        assert order[0] == EventType.STARTED
        assert order[-1] == EventType.COMPLETED


class TestCancellation:
    """E-4: Cancellation 테스트"""

    def test_e4_1_cancel_token_basic(self):
        """E-4-1: CancellationToken 기본 동작"""
        # Given
        token = CancellationToken()

        # When
        assert not token.is_cancelled()
        token.cancel()

        # Then
        assert token.is_cancelled()

    def test_e4_2_check_cancelled_raises_exception(self):
        """E-4-2: check_cancelled → 예외 발생"""
        # Given
        token = CancellationToken()
        token.cancel()

        # When/Then
        with pytest.raises(asyncio.CancelledError):
            token.check_cancelled()

    def test_e4_3_cancel_callback(self):
        """E-4-3: on_cancel 콜백 실행"""
        # Given
        token = CancellationToken()
        callback_called = []

        def on_cancel():
            callback_called.append(True)

        token.on_cancel(on_cancel)

        # When
        token.cancel()

        # Then
        assert callback_called == [True]

    def test_e4_4_multiple_callbacks(self):
        """E-4-4: 여러 콜백 등록"""
        # Given
        token = CancellationToken()
        calls = []

        token.on_cancel(lambda: calls.append("A"))
        token.on_cancel(lambda: calls.append("B"))
        token.on_cancel(lambda: calls.append("C"))

        # When
        token.cancel()

        # Then
        assert calls == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_e4_5_cancel_stops_execution(self):
        """E-4-5: Cancellation으로 실행 중단"""

        # Given
        token = CancellationToken()

        async def long_task():
            for i in range(100):
                token.check_cancelled()  # 취소 확인
                await asyncio.sleep(0.01)
            return "completed"

        # When: 중간에 취소
        task = asyncio.create_task(long_task())
        await asyncio.sleep(0.05)  # 일부 실행
        token.cancel()

        # Then: CancelledError 발생
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_e4_6_cancel_event_emitted(self):
        """E-4-6: 취소 시 CANCELLED 이벤트 발행"""
        # Given
        bus = EventBus()
        token = CancellationToken()

        await bus.emit(AgentEvent(type=EventType.STARTED, task_id="t1"))
        await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="t1"))

        # When: 취소
        token.cancel()
        await bus.emit(AgentEvent(type=EventType.CANCELLED, task_id="t1"))

        # Then
        assert bus.get_event_order()[-1] == EventType.CANCELLED


class TestEventStreaming:
    """이벤트 스트리밍 테스트"""

    @pytest.mark.asyncio
    async def test_stream_events(self):
        """이벤트 스트림 수신"""
        # Given
        bus = EventBus()

        # When: 백그라운드에서 이벤트 발행
        async def emit_events():
            await asyncio.sleep(0.01)
            await bus.emit(AgentEvent(type=EventType.STARTED, task_id="t1"))
            await asyncio.sleep(0.01)
            await bus.emit(AgentEvent(type=EventType.RUNNING, task_id="t1"))
            await asyncio.sleep(0.01)
            await bus.emit(AgentEvent(type=EventType.COMPLETED, task_id="t1"))

        emit_task = asyncio.create_task(emit_events())

        # Then: 스트림으로 수신
        events = []
        async for event in bus.stream():
            events.append(event.type)

        await emit_task

        assert events == [EventType.STARTED, EventType.RUNNING, EventType.COMPLETED]

    @pytest.mark.asyncio
    async def test_subscribe_callback(self):
        """구독자 콜백"""
        # Given
        bus = EventBus()
        received = []

        def handler(event: AgentEvent):
            received.append(event.type)

        bus.subscribe(handler)

        # When
        await bus.emit(AgentEvent(type=EventType.STARTED, task_id="t1"))
        await bus.emit(AgentEvent(type=EventType.COMPLETED, task_id="t1"))

        # Then
        assert received == [EventType.STARTED, EventType.COMPLETED]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
