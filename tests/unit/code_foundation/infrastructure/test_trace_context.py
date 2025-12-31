"""
Trace Context Unit Tests (SOTA)

RFC-052: MCP Service Layer Architecture
Tests for trace context propagation.

Test Coverage:
- Context propagation
- Context manager
- Decorator
- Clear/Reset
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.monitoring import (
    TraceContext,
    TraceContextManager,
    clear_trace_context,
    get_trace_context,
    set_trace_context,
    traced,
)


class TestTraceContext:
    """TraceContext model tests"""

    def test_create_trace_context(self):
        """Create trace context with auto-generated ID"""
        ctx = TraceContext()

        assert ctx.trace_id.startswith("trace_")
        assert len(ctx.trace_id) > 10

    def test_trace_context_with_data(self):
        """Create trace context with all fields"""
        ctx = TraceContext(
            trace_id="trace_abc123",
            plan_hash="plan_def456",
            snapshot_id="snap_001",
            session_id="session_001",
        )

        assert ctx.trace_id == "trace_abc123"
        assert ctx.plan_hash == "plan_def456"
        assert ctx.snapshot_id == "snap_001"
        assert ctx.session_id == "session_001"

    def test_trace_context_to_dict(self):
        """Serialize trace context"""
        ctx = TraceContext(
            trace_id="trace_test",
            snapshot_id="snap_001",
        )

        data = ctx.to_dict()

        assert data["trace_id"] == "trace_test"
        assert data["snapshot_id"] == "snap_001"


class TestTraceContextPropagation:
    """Context propagation tests"""

    def setup_method(self):
        """Clear context before each test"""
        clear_trace_context()

    def test_set_and_get_context(self):
        """Set and get trace context"""
        ctx = TraceContext(trace_id="trace_test")

        set_trace_context(ctx)

        retrieved = get_trace_context()
        assert retrieved.trace_id == "trace_test"

    def test_clear_context(self):
        """Clear trace context"""
        ctx = TraceContext(trace_id="trace_test")
        set_trace_context(ctx)

        clear_trace_context()

        # Should create new trace_id
        retrieved = get_trace_context()
        assert retrieved.trace_id != "trace_test"


class TestTraceContextManager:
    """Context manager tests"""

    def setup_method(self):
        """Clear context before each test"""
        clear_trace_context()

    def test_context_manager_sets_context(self):
        """Context manager sets trace context"""
        with TraceContextManager(trace_id="trace_cm_test") as ctx:
            # Inside context
            current = get_trace_context()
            assert current.trace_id == "trace_cm_test"

        # Outside context - should be cleared
        # (Note: context vars are scoped to async context)

    def test_context_manager_with_all_fields(self):
        """Context manager with all fields"""
        with TraceContextManager(
            trace_id="trace_test",
            plan_hash="plan_test",
            snapshot_id="snap_test",
            session_id="session_test",
        ) as ctx:
            current = get_trace_context()

            assert current.trace_id == "trace_test"
            assert current.plan_hash == "plan_test"
            assert current.snapshot_id == "snap_test"
            assert current.session_id == "session_test"

    def test_context_manager_auto_generates_trace_id(self):
        """Context manager auto-generates trace_id if not provided"""
        with TraceContextManager() as ctx:
            assert ctx.trace_id.startswith("trace_")


class TestTracedDecorator:
    """Traced decorator tests"""

    def setup_method(self):
        """Clear context before each test"""
        clear_trace_context()

    @pytest.mark.asyncio
    async def test_traced_decorator(self):
        """Traced decorator sets context"""

        @traced
        async def my_function(value: int):
            ctx = get_trace_context()
            return ctx.trace_id, value

        trace_id, result = await my_function(42)

        assert trace_id.startswith("trace_")
        assert result == 42
