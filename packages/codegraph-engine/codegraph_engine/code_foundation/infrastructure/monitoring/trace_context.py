"""
Trace Context for MCP Service Layer (SOTA)

RFC-052: MCP Service Layer Architecture
Lightweight distributed tracing with structured logging.

Design:
- trace_id: Request identifier
- plan_hash: QueryPlan identifier
- snapshot_id: Data version identifier
- Automatic propagation through call chain

Not OpenTelemetry (too heavy for this use case).
Simple structured logging with correlation IDs.
"""

import contextvars
import uuid
from dataclasses import dataclass, field
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Context variables for trace propagation
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_plan_hash: contextvars.ContextVar[str | None] = contextvars.ContextVar("plan_hash", default=None)
_snapshot_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("snapshot_id", default=None)
_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)


@dataclass
class TraceContext:
    """
    Trace context for request correlation.

    Propagated through async call chain via contextvars.
    """

    trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:12]}")
    plan_hash: str | None = None
    snapshot_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging"""
        return {
            "trace_id": self.trace_id,
            "plan_hash": self.plan_hash,
            "snapshot_id": self.snapshot_id,
            "session_id": self.session_id,
            **self.metadata,
        }


def get_trace_context() -> TraceContext:
    """
    Get current trace context.

    Returns:
        TraceContext with current values
    """
    return TraceContext(
        trace_id=_trace_id.get() or f"trace_{uuid.uuid4().hex[:12]}",
        plan_hash=_plan_hash.get(),
        snapshot_id=_snapshot_id.get(),
        session_id=_session_id.get(),
    )


def set_trace_context(context: TraceContext) -> None:
    """
    Set trace context.

    Args:
        context: TraceContext to set
    """
    _trace_id.set(context.trace_id)
    _plan_hash.set(context.plan_hash)
    _snapshot_id.set(context.snapshot_id)
    _session_id.set(context.session_id)


def clear_trace_context() -> None:
    """Clear trace context (for testing)"""
    _trace_id.set(None)
    _plan_hash.set(None)
    _snapshot_id.set(None)
    _session_id.set(None)


class TraceContextManager:
    """
    Context manager for trace scope.

    Usage:
        with TraceContextManager(trace_id="abc123"):
            # All logs in this scope include trace_id
            logger.info("processing", extra=get_trace_context().to_dict())
    """

    def __init__(
        self,
        trace_id: str | None = None,
        plan_hash: str | None = None,
        snapshot_id: str | None = None,
        session_id: str | None = None,
    ):
        """
        Initialize context manager.

        Args:
            trace_id: Trace ID (auto-generated if None)
            plan_hash: QueryPlan hash
            snapshot_id: Snapshot ID
            session_id: Session ID
        """
        self.context = TraceContext(
            trace_id=trace_id or f"trace_{uuid.uuid4().hex[:12]}",
            plan_hash=plan_hash,
            snapshot_id=snapshot_id,
            session_id=session_id,
        )
        self._tokens = []

    def __enter__(self):
        """Enter trace scope"""
        self._tokens = [
            _trace_id.set(self.context.trace_id),
            _plan_hash.set(self.context.plan_hash),
            _snapshot_id.set(self.context.snapshot_id),
            _session_id.set(self.context.session_id),
        ]

        logger.debug("trace_started", **self.context.to_dict())
        return self.context

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit trace scope"""
        # Reset context vars
        for token in self._tokens:
            try:
                if token is not None:
                    token.var.reset(token)
            except Exception:
                pass

        if exc_type:
            logger.error(
                "trace_failed",
                error=str(exc_val),
                **self.context.to_dict(),
            )
        else:
            logger.debug("trace_completed", **self.context.to_dict())


def traced(func):
    """
    Decorator for automatic trace context.

    Usage:
        @traced
        async def my_usecase(request):
            # Trace context automatically set
            ...
    """
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract trace info from args if available
        trace_id = None
        session_id = None

        if args and hasattr(args[0], "session_id"):
            session_id = args[0].session_id

        with TraceContextManager(trace_id=trace_id, session_id=session_id):
            return await func(*args, **kwargs)

    return wrapper
