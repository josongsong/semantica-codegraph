"""
Distributed Tracing with OpenTelemetry

Provides tracing for tracking requests across system boundaries.
"""

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SpanKind(Enum):
    """Type of span."""

    SERVER = "server"  # Server-side request handling
    CLIENT = "client"  # Client-side request
    INTERNAL = "internal"  # Internal operation
    PRODUCER = "producer"  # Message producer
    CONSUMER = "consumer"  # Message consumer


class SpanStatus(Enum):
    """Span execution status."""

    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class Span:
    """
    Represents a single operation in a trace.

    A trace is composed of multiple spans forming a tree structure.
    """

    # Identification
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None

    # Naming
    name: str = "unnamed_operation"
    kind: SpanKind = SpanKind.INTERNAL

    # Timing
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    # Status
    status: SpanStatus = SpanStatus.UNSET
    status_description: str | None = None

    # Attributes (key-value pairs)
    attributes: dict[str, Any] = field(default_factory=dict)

    # Events (timestamped logs within the span)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float | None:
        """Calculate span duration in milliseconds."""
        if not self.end_time:
            return None
        delta = self.end_time - self.start_time
        return delta.total_seconds() * 1000

    def set_attribute(self, key: str, value: Any) -> None:
        """Add or update a span attribute."""
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add a timestamped event to the span."""
        self.events.append(
            {
                "name": name,
                "timestamp": datetime.now(),
                "attributes": attributes or {},
            }
        )

    def set_status(self, status: SpanStatus, description: str | None = None) -> None:
        """Set span status."""
        self.status = status
        self.status_description = description

    def end(self) -> None:
        """Mark span as ended."""
        if not self.end_time:
            self.end_time = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary for export."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "status_description": self.status_description,
            "attributes": self.attributes,
            "events": [
                {
                    **event,
                    "timestamp": event["timestamp"].isoformat(),
                }
                for event in self.events
            ],
        }


# Context variable for current span
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar("current_span", default=None)


class TracingContext:
    """
    Context manager for tracing spans.

    Automatically starts and ends spans, handles errors, and propagates context.

    Example:
        ```python
        with TracingContext("process_request", kind=SpanKind.SERVER) as span:
            span.set_attribute("user_id", 123)
            span.add_event("validation_complete")
            # ... do work ...
        ```
    """

    def __init__(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ):
        self.name = name
        self.kind = kind
        self.attributes = attributes or {}
        self.span: Span | None = None
        self.parent_span: Span | None = None
        self.token: contextvars.Token | None = None

    def __enter__(self) -> Span:
        # Get parent span from context
        self.parent_span = _current_span.get()

        # Create new span
        self.span = Span(name=self.name, kind=self.kind)

        # Inherit trace context from parent
        if self.parent_span:
            self.span.trace_id = self.parent_span.trace_id
            self.span.parent_span_id = self.parent_span.span_id

        # Set initial attributes
        for key, value in self.attributes.items():
            self.span.set_attribute(key, value)

        # Set as current span in context
        self.token = _current_span.set(self.span)

        return self.span

    def __exit__(self, exc_type, exc_val, _exc_tb):
        if not self.span:
            return False

        # Set status based on exception
        if exc_type is not None:
            self.span.set_status(SpanStatus.ERROR, f"{exc_type.__name__}: {exc_val}")
            self.span.add_event(
                "exception",
                attributes={
                    "exception.type": exc_type.__name__,
                    "exception.message": str(exc_val),
                },
            )
        else:
            self.span.set_status(SpanStatus.OK)

        # End span
        self.span.end()

        # Export span (in production, send to OpenTelemetry collector)
        _export_span(self.span)

        # Restore previous span context
        if self.token:
            _current_span.reset(self.token)

        return False  # Don't suppress exceptions


def start_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> TracingContext:
    """
    Start a new tracing span.

    Returns a context manager that should be used with 'with' statement.

    Args:
        name: Span name (e.g., "database_query", "http_request")
        kind: Span kind
        attributes: Initial attributes

    Example:
        ```python
        with start_span("fetch_user", attributes={"user_id": 123}):
            # ... operation ...
            pass
        ```
    """
    return TracingContext(name, kind, attributes)


def get_current_span() -> Span | None:
    """Get the current active span from context."""
    return _current_span.get()


def add_span_attribute(key: str, value: Any) -> None:
    """Add attribute to current span (if any)."""
    span = get_current_span()
    if span:
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add event to current span (if any)."""
    span = get_current_span()
    if span:
        span.add_event(name, attributes)


# Span storage for demo/testing (in production, send to OTLP endpoint)
_span_storage: list[Span] = []


def _export_span(span: Span) -> None:
    """
    Export span to storage/backend.

    In production, this would send to OpenTelemetry collector,
    which forwards to Jaeger, Zipkin, or cloud provider.
    """
    _span_storage.append(span)


def get_all_spans() -> list[Span]:
    """Get all recorded spans (for testing/debugging)."""
    return _span_storage.copy()


def clear_spans() -> None:
    """Clear span storage (for testing)."""
    _span_storage.clear()


# Decorators for automatic tracing
def trace_function(
    name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
):
    """
    Decorator to automatically trace a function.

    Args:
        name: Span name (defaults to function name)
        kind: Span kind

    Example:
        ```python
        @trace_function("process_data")
        def process_data(items: list):
            # ... processing ...
            return results
        ```
    """

    def decorator(func):
        span_name = name or func.__name__

        def wrapper(*args, **kwargs):
            with start_span(span_name, kind=kind) as span:
                # Add function info
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)

                # Call function
                result = func(*args, **kwargs)

                return result

        return wrapper

    return decorator


async def trace_async_function(
    name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
):
    """
    Decorator to automatically trace an async function.

    Example:
        ```python
        @trace_async_function("fetch_data")
        async def fetch_data(url: str):
            # ... async operation ...
            return data
        ```
    """

    def decorator(func):
        span_name = name or func.__name__

        async def wrapper(*args, **kwargs):
            with start_span(span_name, kind=kind) as span:
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)

                result = await func(*args, **kwargs)
                return result

        return wrapper

    return decorator


# Standard attribute names (OpenTelemetry semantic conventions)
class TraceAttributes:
    """Standard trace attribute names following OpenTelemetry conventions."""

    # HTTP attributes
    HTTP_METHOD = "http.method"
    HTTP_URL = "http.url"
    HTTP_STATUS_CODE = "http.status_code"
    HTTP_USER_AGENT = "http.user_agent"

    # Database attributes
    DB_SYSTEM = "db.system"  # e.g., "postgresql", "redis"
    DB_NAME = "db.name"
    DB_STATEMENT = "db.statement"
    DB_OPERATION = "db.operation"  # e.g., "SELECT", "INSERT"

    # Service attributes
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"

    # Custom attributes for Semantica
    QUERY_TYPE = "semantica.query.type"  # e.g., "find_definition", "find_usage"
    RETRIEVAL_RESULTS = "semantica.retrieval.results_count"
    INDEXING_FILES = "semantica.indexing.files_count"
    MEMORY_EPISODE_ID = "semantica.memory.episode_id"


def _example_usage():
    """Example demonstrating tracing usage."""

    # Example 1: Manual span management
    with start_span("process_request", kind=SpanKind.SERVER) as span:
        span.set_attribute(TraceAttributes.HTTP_METHOD, "GET")
        span.set_attribute("user_id", 123)

        # Nested span
        with start_span("database_query", kind=SpanKind.CLIENT) as db_span:
            db_span.set_attribute(TraceAttributes.DB_OPERATION, "SELECT")
            db_span.add_event("query_start")
            time.sleep(0.01)  # Simulate query
            db_span.add_event("query_complete", {"rows": 42})

        # Another nested span
        with start_span("cache_lookup") as cache_span:
            cache_span.set_attribute("cache.key", "user:123")
            cache_span.set_attribute("cache.hit", True)

    # Example 2: Function decorator
    @trace_function("calculate_score")
    def calculate_score(value: int) -> float:
        time.sleep(0.01)  # Simulate work
        return value * 1.5

    _ = calculate_score(100)

    # View all spans
    for span in get_all_spans():
        print(f"\nSpan: {span.name}")
        print(f"  Duration: {span.duration_ms:.2f}ms")
        print(f"  Trace ID: {span.trace_id}")
        print(f"  Parent: {span.parent_span_id}")
        print(f"  Status: {span.status.value}")
        print(f"  Attributes: {span.attributes}")


if __name__ == "__main__":
    _example_usage()
