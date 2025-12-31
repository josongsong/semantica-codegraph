"""
Observability Infrastructure

P0-3 Implementation (IMPLEMENTATION_ROADMAP Phase 1)

Provides structured logging, metrics, tracing, alerting, and cost tracking
for production monitoring.
"""

from .alerting import (
    Alert,
    AlertChannel,
    AlertManager,
    AlertRule,
    AlertSeverity,
    get_standard_alert_rules,
)
from .cost_tracking import (
    CostCategory,
    CostTracker,
    get_cost_breakdown,
    get_cost_tracker,
    get_total_cost,
    record_embedding_cost,
    record_llm_cost,
    record_vector_search_cost,
)
from .logging import (
    LogPerformance,
    add_context,
    clear_context,
    get_logger,
    log_error,
    log_performance,
    setup_logging,
)
from .metrics import (
    MetricsCollector,
    OpenTelemetryExporter,
    RecordLatency,
    StandardMetrics,
    create_metrics_endpoint,
    get_metrics_collector,
    record_counter,
    record_gauge,
    record_histogram,
    record_metric,
)
from .tracing import (
    Span,
    SpanKind,
    SpanStatus,
    TraceAttributes,
    TracingContext,
    add_span_attribute,
    add_span_event,
    get_current_span,
    start_span,
    trace_function,
)

__all__ = [
    # Logging
    "get_logger",
    "setup_logging",
    "add_context",
    "clear_context",
    "log_error",
    "log_performance",
    "LogPerformance",
    # Metrics
    "MetricsCollector",
    "get_metrics_collector",
    "record_metric",
    "record_counter",
    "record_histogram",
    "record_gauge",
    "RecordLatency",
    "StandardMetrics",
    "OpenTelemetryExporter",
    "create_metrics_endpoint",
    # Tracing
    "TracingContext",
    "start_span",
    "get_current_span",
    "add_span_attribute",
    "add_span_event",
    "trace_function",
    "Span",
    "SpanKind",
    "SpanStatus",
    "TraceAttributes",
    # Alerting
    "AlertManager",
    "AlertRule",
    "AlertSeverity",
    "AlertChannel",
    "Alert",
    "get_standard_alert_rules",
    # Cost Tracking
    "CostTracker",
    "get_cost_tracker",
    "CostCategory",
    "record_llm_cost",
    "record_embedding_cost",
    "record_vector_search_cost",
    "get_total_cost",
    "get_cost_breakdown",
]
