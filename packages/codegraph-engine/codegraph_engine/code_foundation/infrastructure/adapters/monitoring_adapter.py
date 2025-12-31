"""
Monitoring Adapter

RFC-052: MCP Service Layer Architecture
Implements MonitoringPort using TraceContext.

Adapter Pattern:
- Port: MonitoringPort (Domain)
- Adapter: MonitoringAdapter (Infrastructure)
- Adaptee: TraceContext (Infrastructure)
"""

from typing import Any

from codegraph_engine.code_foundation.domain.ports.monitoring_ports import (
    MonitoringPort,
    TraceContextPort,
)
from codegraph_engine.code_foundation.infrastructure.monitoring import (
    TraceContext,
    TraceContextManager,
    get_trace_context,
)


class TraceContextAdapter:
    """Adapter for TraceContextPort"""

    def __init__(self, trace_context: TraceContext):
        self._trace = trace_context

    @property
    def trace_id(self) -> str:
        return self._trace.trace_id

    @property
    def session_id(self) -> str | None:
        return self._trace.session_id

    def to_dict(self) -> dict[str, Any]:
        return self._trace.to_dict()


class MonitoringAdapter:
    """
    Monitoring adapter for MonitoringPort.

    Bridges Domain (MonitoringPort) and Infrastructure (TraceContext).
    """

    def get_trace_context(self) -> TraceContextPort:
        """Get current trace context"""
        trace = get_trace_context()
        return TraceContextAdapter(trace)

    def start_trace(
        self,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        Start trace scope.

        Returns:
            TraceContextManager (context manager)
        """
        return TraceContextManager(session_id=session_id)
