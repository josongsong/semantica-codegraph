"""
Monitoring Ports

RFC-052: MCP Service Layer Architecture
Domain-defined interface for monitoring/observability.

Why Port?
- Monitoring is Infrastructure concern
- Application needs observability
- Port abstracts implementation (logs, metrics, traces)
"""

from typing import Any, Protocol


class TraceContextPort(Protocol):
    """
    Trace context provider port.

    Domain-defined interface for trace propagation.
    """

    @property
    def trace_id(self) -> str:
        """Current trace ID"""
        ...

    @property
    def session_id(self) -> str | None:
        """Current session ID"""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize trace context"""
        ...


class MonitoringPort(Protocol):
    """
    Monitoring service port.

    Provides observability without infrastructure coupling.
    """

    def get_trace_context(self) -> TraceContextPort:
        """Get current trace context"""
        ...

    def start_trace(
        self,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        Start trace scope (context manager).

        Returns:
            Context manager for trace scope
        """
        ...
