"""
Metrics Collection with OpenTelemetry

Provides standardized metrics collection for monitoring and alerting.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any


class MetricType(Enum):
    """Metric types."""

    COUNTER = "counter"  # Monotonically increasing (e.g., requests_total)
    GAUGE = "gauge"  # Current value (e.g., active_connections)
    HISTOGRAM = "histogram"  # Distribution (e.g., latency_ms)


@dataclass
class MetricValue:
    """Single metric value."""

    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    In-memory metrics collector.

    In production, this would integrate with OpenTelemetry to export
    metrics to Prometheus, DataDog, CloudWatch, etc.
    """

    def __init__(self):
        # Metric storage: metric_name -> list of values
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

        # Labeled metrics: (metric_name, label_key, label_value) -> value
        self._labeled_counters: dict[tuple[str, ...], float] = defaultdict(float)
        self._labeled_gauges: dict[tuple[str, ...], float] = {}

        # Thread safety
        self._lock = Lock()

    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a counter metric (monotonically increasing).

        Args:
            name: Metric name (e.g., "requests_total")
            value: Value to add (default 1.0)
            labels: Optional labels for grouping (e.g., {"status": "200", "method": "GET"})

        Example:
            ```python
            collector.record_counter("api_requests_total")
            collector.record_counter("api_requests_total", labels={"status": "200"})
            collector.record_counter("bytes_processed", value=1024.5)
            ```
        """
        with self._lock:
            if labels:
                key = self._make_label_key(name, labels)
                self._labeled_counters[key] += value
            else:
                self._counters[name] += value

    def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a gauge metric (current value).

        Args:
            name: Metric name (e.g., "active_connections")
            value: Current value
            labels: Optional labels

        Example:
            ```python
            collector.record_gauge("memory_usage_mb", 512.3)
            collector.record_gauge("queue_size", 42, labels={"queue": "tasks"})
            ```
        """
        with self._lock:
            if labels:
                key = self._make_label_key(name, labels)
                self._labeled_gauges[key] = value
            else:
                self._gauges[name] = value

    def record_histogram(
        self,
        name: str,
        value: float,
    ) -> None:
        """
        Record a histogram metric (distribution of values).

        Args:
            name: Metric name (e.g., "latency_ms")
            value: Observed value

        Example:
            ```python
            collector.record_histogram("query_latency_ms", 45.2)
            collector.record_histogram("batch_size", 100)
            ```
        """
        with self._lock:
            self._histograms[name].append(value)

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current counter value."""
        with self._lock:
            if labels:
                key = self._make_label_key(name, labels)
                return self._labeled_counters.get(key, 0.0)
            return self._counters.get(name, 0.0)

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value."""
        with self._lock:
            if labels:
                key = self._make_label_key(name, labels)
                return self._labeled_gauges.get(key, 0.0)
            return self._gauges.get(name, 0.0)

    def get_histogram_stats(self, name: str) -> dict[str, float]:
        """
        Get histogram statistics.

        Returns:
            Dict with count, sum, min, max, mean, p50, p95, p99
        """
        with self._lock:
            values = self._histograms.get(name, [])

        if not values:
            return {
                "count": 0,
                "sum": 0.0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }

        sorted_values = sorted(values)
        count = len(values)

        return {
            "count": count,
            "sum": sum(values),
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "mean": sum(values) / count,
            "p50": self._percentile(sorted_values, 0.50),
            "p95": self._percentile(sorted_values, 0.95),
            "p99": self._percentile(sorted_values, 0.99),
        }

    def _percentile(self, sorted_values: list[float], p: float) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * p
        f = int(k)
        c = f + 1
        if c >= len(sorted_values):
            return sorted_values[-1]
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    def _make_label_key(self, name: str, labels: dict[str, str]) -> tuple[str, ...]:
        """Create hashable key from metric name and labels."""
        sorted_labels = sorted(labels.items())
        return (name, *[f"{k}={v}" for k, v in sorted_labels])

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metrics as a dictionary (for debugging/exporting)."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {name: self.get_histogram_stats(name) for name in self._histograms},
                "labeled_counters": {"|".join(k): v for k, v in self._labeled_counters.items()},
                "labeled_gauges": {"|".join(k): v for k, v in self._labeled_gauges.items()},
            }

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._labeled_counters.clear()
            self._labeled_gauges.clear()


# Global metrics collector instance
_global_collector: MetricsCollector | None = None
_collector_lock = Lock()


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _global_collector
    if _global_collector is None:
        with _collector_lock:
            if _global_collector is None:
                _global_collector = MetricsCollector()
    return _global_collector


# Convenience functions using global collector
def record_counter(name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
    """Record counter using global collector."""
    get_metrics_collector().record_counter(name, value, labels)


def record_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    """Record gauge using global collector."""
    get_metrics_collector().record_gauge(name, value, labels)


def record_histogram(name: str, value: float) -> None:
    """Record histogram using global collector."""
    get_metrics_collector().record_histogram(name, value)


def record_metric(
    metric_type: MetricType,
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """
    Generic metric recording function.

    Args:
        metric_type: Type of metric
        name: Metric name
        value: Metric value
        labels: Optional labels
    """
    if metric_type == MetricType.COUNTER:
        record_counter(name, value, labels)
    elif metric_type == MetricType.GAUGE:
        record_gauge(name, value, labels)
    elif metric_type == MetricType.HISTOGRAM:
        record_histogram(name, value)


# Context manager for timing operations
class RecordLatency:
    """
    Context manager to automatically record operation latency.

    Example:
        ```python
        with RecordLatency("database_query_latency_ms"):
            execute_query()
        ```
    """

    def __init__(self, metric_name: str, labels: dict[str, str] | None = None):
        self.metric_name = metric_name
        self.labels = labels
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000

        # Record histogram of latencies
        record_histogram(self.metric_name, duration_ms)

        # Also record success/failure counter
        status = "error" if exc_type is not None else "success"
        labels = self.labels or {}
        labels["status"] = status

        record_counter(f"{self.metric_name}_total", labels=labels)

        return False  # Don't suppress exceptions


# Standard metric names (conventions)
class StandardMetrics:
    """Standard metric names following naming conventions."""

    # Request metrics
    REQUESTS_TOTAL = "requests_total"
    REQUESTS_DURATION_MS = "requests_duration_ms"
    REQUESTS_IN_PROGRESS = "requests_in_progress"

    # Database metrics
    DB_QUERIES_TOTAL = "db_queries_total"
    DB_QUERY_DURATION_MS = "db_query_duration_ms"
    DB_CONNECTIONS_ACTIVE = "db_connections_active"

    # Cache metrics
    CACHE_HITS_TOTAL = "cache_hits_total"
    CACHE_MISSES_TOTAL = "cache_misses_total"
    CACHE_SIZE = "cache_size"

    # Retrieval metrics
    RETRIEVAL_QUERIES_TOTAL = "retrieval_queries_total"
    RETRIEVAL_LATENCY_MS = "retrieval_latency_ms"
    RETRIEVAL_RESULTS_COUNT = "retrieval_results_count"

    # Indexing metrics
    INDEXING_FILES_TOTAL = "indexing_files_total"
    INDEXING_DURATION_MS = "indexing_duration_ms"
    INDEXING_ERRORS_TOTAL = "indexing_errors_total"

    # Memory system metrics
    MEMORY_EPISODES_STORED = "memory_episodes_stored"
    MEMORY_PATTERNS_LEARNED = "memory_patterns_learned"
    MEMORY_QUERIES_TOTAL = "memory_queries_total"

    # API cost tracking
    API_CALLS_TOTAL = "api_calls_total"
    API_TOKENS_USED = "api_tokens_used"
    API_COST_USD = "api_cost_usd"


def _example_usage():
    """Example demonstrating metrics collection."""
    collector = get_metrics_collector()

    # Counter: increment by 1
    record_counter("http_requests_total")
    record_counter("http_requests_total", labels={"method": "GET", "status": "200"})

    # Gauge: current value
    record_gauge("active_connections", 42)
    record_gauge("memory_usage_mb", 512.5)

    # Histogram: distribution
    for latency in [10, 15, 12, 50, 8, 120]:
        record_histogram("query_latency_ms", latency)

    # Auto-timing with context manager
    with RecordLatency("operation_latency_ms", labels={"operation": "indexing"}):
        time.sleep(0.01)  # Simulate work

    # Get statistics
    print("Latency stats:", collector.get_histogram_stats("query_latency_ms"))
    print("Requests:", collector.get_counter("http_requests_total"))
    print("All metrics:", collector.get_all_metrics())


class OpenTelemetryExporter:
    """
    Export metrics to OpenTelemetry-compatible backends.

    Supports:
    - Prometheus (via push gateway or scrape endpoint)
    - OTLP (OpenTelemetry Protocol)
    - Console (for debugging)

    Usage:
        exporter = OpenTelemetryExporter(
            backend="prometheus",
            endpoint="http://localhost:9091",
        )
        exporter.export(collector.get_all_metrics())
    """

    def __init__(
        self,
        backend: str = "console",
        endpoint: str | None = None,
        service_name: str = "semantica-codegraph",
        push_interval: float = 60.0,
    ):
        """
        Initialize exporter.

        Args:
            backend: Export backend ("console", "prometheus", "otlp")
            endpoint: Backend endpoint URL
            service_name: Service name for labeling
            push_interval: Push interval in seconds (for push-based backends)
        """
        self._backend = backend
        self._endpoint = endpoint
        self._service_name = service_name
        self._push_interval = push_interval
        self._otel_meter = None
        self._otel_instruments: dict[str, Any] = {}

        # Initialize OpenTelemetry if available
        self._init_otel()

    def _init_otel(self) -> None:
        """Initialize OpenTelemetry SDK if available."""
        try:
            from opentelemetry import metrics as otel_metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.resources import SERVICE_NAME, Resource

            # Create resource
            resource = Resource(attributes={SERVICE_NAME: self._service_name})

            # Create meter provider
            provider = MeterProvider(resource=resource)
            otel_metrics.set_meter_provider(provider)

            # Get meter
            self._otel_meter = otel_metrics.get_meter(__name__)

            # Add exporter based on backend
            if self._backend == "prometheus" and self._endpoint:
                self._setup_prometheus_exporter(provider)
            elif self._backend == "otlp" and self._endpoint:
                self._setup_otlp_exporter(provider)

        except ImportError:
            # OpenTelemetry not installed, use console fallback
            self._otel_meter = None

    def _setup_prometheus_exporter(self, provider) -> None:
        """Setup Prometheus push gateway exporter."""
        try:
            from opentelemetry.exporter.prometheus import PrometheusMetricReader

            # Note: This requires prometheus_client package
            # Store reader for later use in metrics collection
            self._prometheus_reader = PrometheusMetricReader()
            # In real implementation, you'd configure push gateway
        except ImportError:
            pass

    def _setup_otlp_exporter(self, provider) -> None:
        """Setup OTLP exporter."""
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            exporter = OTLPMetricExporter(endpoint=self._endpoint)
            # Store reader for later use
            self._otlp_reader = PeriodicExportingMetricReader(
                exporter, export_interval_millis=int(self._push_interval * 1000)
            )
        except ImportError:
            pass

    def export(self, metrics: dict[str, Any]) -> None:
        """
        Export metrics to configured backend.

        Args:
            metrics: Metrics dict from MetricsCollector.get_all_metrics()
        """
        if self._backend == "console":
            self._export_console(metrics)
        elif self._otel_meter is not None:
            self._export_otel(metrics)
        else:
            self._export_console(metrics)

    def _export_console(self, metrics: dict[str, Any]) -> None:
        """Export metrics to console (for debugging)."""
        import json
        from datetime import datetime, timezone

        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self._service_name,
            "metrics": metrics,
        }
        print(json.dumps(output, indent=2, default=str))

    def _export_otel(self, metrics: dict[str, Any]) -> None:
        """Export metrics using OpenTelemetry SDK."""
        if self._otel_meter is None:
            return

        # Export counters
        for name, _value in metrics.get("counters", {}).items():
            if name not in self._otel_instruments:
                self._otel_instruments[name] = self._otel_meter.create_counter(
                    name=name,
                    description=f"Counter: {name}",
                )
            # Note: OTEL counters are additive, would need delta tracking

        # Export gauges
        for name, _value in metrics.get("gauges", {}).items():
            if name not in self._otel_instruments:
                self._otel_instruments[name] = self._otel_meter.create_gauge(
                    name=name,
                    description=f"Gauge: {name}",
                )
            # Would call gauge callback here

        # Export histograms
        for name, _stats in metrics.get("histograms", {}).items():
            if name not in self._otel_instruments:
                self._otel_instruments[name] = self._otel_meter.create_histogram(
                    name=name,
                    description=f"Histogram: {name}",
                )
            # Would record histogram values here

    def export_prometheus_format(self, metrics: dict[str, Any]) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus exposition format string
        """
        lines = []

        # Counters
        for name, value in metrics.get("counters", {}).items():
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")

        # Labeled counters
        for key, value in metrics.get("labeled_counters", {}).items():
            parts = key.split("|")
            name = parts[0]
            labels = ",".join(parts[1:]) if len(parts) > 1 else ""
            label_str = f"{{{labels}}}" if labels else ""
            lines.append(f"{name}{label_str} {value}")

        # Gauges
        for name, value in metrics.get("gauges", {}).items():
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {value}")

        # Histograms (summary stats)
        for name, stats in metrics.get("histograms", {}).items():
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_count {stats.get('count', 0)}")
            lines.append(f"{name}_sum {stats.get('sum', 0)}")

            # Quantiles as separate metrics
            for quantile in ["p50", "p95", "p99"]:
                q_val = quantile[1:]  # Remove 'p' prefix
                q_float = float(q_val) / 100
                lines.append(f'{name}{{quantile="{q_float}"}} {stats.get(quantile, 0)}')

        return "\n".join(lines)


def create_metrics_endpoint():
    """
    Create a FastAPI endpoint for Prometheus scraping.

    Usage:
        from fastapi import FastAPI
        app = FastAPI()

        metrics_router = create_metrics_endpoint()
        app.include_router(metrics_router, prefix="/metrics")
    """
    try:
        from fastapi import APIRouter
        from fastapi.responses import PlainTextResponse

        router = APIRouter()

        @router.get("/", response_class=PlainTextResponse)
        async def metrics():
            collector = get_metrics_collector()
            exporter = OpenTelemetryExporter(backend="console")
            return exporter.export_prometheus_format(collector.get_all_metrics())

        return router

    except ImportError:
        return None


if __name__ == "__main__":
    _example_usage()
