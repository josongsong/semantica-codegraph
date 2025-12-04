# Observability Infrastructure

Production-ready observability stack with structured logging, metrics, and distributed tracing.

## Components

### 1. Structured Logging (structlog)

**File**: [logging.py](logging.py:1-360)

Provides JSON-structured logs with contextual information.

**Features**:
- JSON output for production (machine-readable)
- Console output for development (human-readable with colors)
- Thread-safe context propagation (`contextvars`)
- ISO timestamps
- Caller information (file, line, function)
- Exception formatting with stack traces

**Usage**:
```python
from src.infra.observability import get_logger, setup_logging, add_context

# Setup once at app startup
setup_logging(level="INFO", format="json")

# Get logger
logger = get_logger(__name__)

# Simple log
logger.info("user_logged_in", user_id=123, ip="192.168.1.1")

# Add context for all subsequent logs
add_context(request_id="req-abc-123", session_id="session-456")

# All logs now include request_id and session_id
logger.info("processing_payment", amount=99.99, currency="USD")
logger.warning("payment_delayed", reason="external_api_slow")

# Error logging
try:
    risky_operation()
except Exception as e:
    log_error(logger, "operation_failed", error=e, user_id=123)

# Performance logging
from src.infra.observability.logging import LogPerformance

with LogPerformance(logger, "database_query", query_type="SELECT"):
    results = execute_query()
# Logs: operation_complete, duration_ms=15.3, query_type=SELECT
```

**Output Example** (JSON format):
```json
{
  "event": "user_logged_in",
  "user_id": 123,
  "ip": "192.168.1.1",
  "timestamp": "2025-11-25T12:34:56.789Z",
  "level": "info",
  "logger": "src.api.auth",
  "request_id": "req-abc-123",
  "caller": "auth.py:42:login"
}
```

### 2. Metrics Collection (OpenTelemetry-compatible)

**File**: [metrics.py](metrics.py:1-380)

Collect and export metrics for monitoring and alerting.

**Metric Types**:
- **Counter**: Monotonically increasing (e.g., `requests_total`)
- **Gauge**: Current value (e.g., `active_connections`)
- **Histogram**: Distribution of values (e.g., `latency_ms`)

**Usage**:
```python
from src.infra.observability import (
    record_counter,
    record_gauge,
    record_histogram,
    StandardMetrics,
)
from src.infra.observability.metrics import RecordLatency

# Counter: increment requests
record_counter(StandardMetrics.REQUESTS_TOTAL)
record_counter(
    StandardMetrics.REQUESTS_TOTAL,
    labels={"method": "GET", "status": "200"}
)

# Gauge: current memory usage
record_gauge(StandardMetrics.MEMORY_USAGE_MB, 512.5)

# Histogram: query latency distribution
record_histogram(StandardMetrics.DB_QUERY_DURATION_MS, 45.2)

# Auto-timing with context manager
with RecordLatency("indexing_latency_ms", labels={"type": "incremental"}):
    index_files()
```

**Standard Metrics** ([StandardMetrics](metrics.py:320-355)):
- `requests_total` - Total HTTP requests
- `requests_duration_ms` - Request latency distribution
- `db_queries_total` - Database queries count
- `cache_hits_total` / `cache_misses_total` - Cache performance
- `retrieval_queries_total` - Retrieval system usage
- `api_tokens_used` - LLM API token consumption
- `api_cost_usd` - LLM API cost tracking

**Getting Metrics**:
```python
from src.infra.observability import get_metrics_collector

collector = get_metrics_collector()

# Get counter value
total = collector.get_counter("requests_total")

# Get histogram statistics
stats = collector.get_histogram_stats("query_latency_ms")
print(f"P95 latency: {stats['p95']:.2f}ms")

# Export all metrics (for Prometheus, DataDog, etc.)
all_metrics = collector.get_all_metrics()
```

### 3. Distributed Tracing (OpenTelemetry-compatible)

**File**: [tracing.py](tracing.py:1-420)

Track requests across system boundaries with distributed tracing.

**Features**:
- Automatic span creation and timing
- Parent-child span relationships (trace tree)
- Span attributes and events
- Error tracking
- Context propagation (thread-safe with `contextvars`)

**Usage**:
```python
from src.infra.observability import (
    start_span,
    add_span_attribute,
    add_span_event,
)
from src.infra.observability.tracing import SpanKind, TraceAttributes

# Server-side request handling
with start_span("process_request", kind=SpanKind.SERVER) as span:
    span.set_attribute(TraceAttributes.HTTP_METHOD, "POST")
    span.set_attribute(TraceAttributes.HTTP_URL, "/api/search")

    # Nested span for database
    with start_span("database_query", kind=SpanKind.CLIENT) as db_span:
        db_span.set_attribute(TraceAttributes.DB_OPERATION, "SELECT")
        db_span.add_event("query_start")
        results = db.query("SELECT * FROM users")
        db_span.add_event("query_complete", {"rows": len(results)})

    # Nested span for external API
    with start_span("llm_api_call", kind=SpanKind.CLIENT) as api_span:
        api_span.set_attribute("api.provider", "openai")
        api_span.set_attribute("api.model", "gpt-4")
        response = openai.complete(prompt)
```

**Decorator Usage**:
```python
from src.infra.observability.tracing import trace_function, SpanKind

@trace_function("calculate_embeddings", kind=SpanKind.INTERNAL)
def calculate_embeddings(texts: list[str]):
    # Function is automatically traced
    embeddings = model.encode(texts)
    return embeddings

# Async version
@trace_async_function("fetch_documents")
async def fetch_documents(query: str):
    docs = await search_index.query(query)
    return docs
```

**Trace Output**:
```python
{
  "span_id": "abc-123",
  "trace_id": "trace-xyz",
  "parent_span_id": null,
  "name": "process_request",
  "kind": "server",
  "start_time": "2025-11-25T12:00:00.000Z",
  "end_time": "2025-11-25T12:00:00.150Z",
  "duration_ms": 150.5,
  "status": "ok",
  "attributes": {
    "http.method": "POST",
    "http.url": "/api/search"
  },
  "events": [
    {
      "name": "database_query_start",
      "timestamp": "2025-11-25T12:00:00.010Z"
    }
  ]
}
```

## Integration Example

### Complete Observability Setup

```python
from src.infra.observability import (
    setup_logging,
    get_logger,
    add_context,
    record_counter,
    record_histogram,
    start_span,
    StandardMetrics,
)
from src.infra.observability.logging import LogPerformance
from src.infra.observability.metrics import RecordLatency
from src.infra.observability.tracing import SpanKind

# 1. Setup at application startup
def setup_observability():
    setup_logging(
        level="INFO",
        format="json",  # Use "console" for development
        include_timestamp=True,
        include_caller=True,
    )

# 2. Use in application code
async def search_api_endpoint(query: str, user_id: int):
    logger = get_logger(__name__)

    # Add request context
    add_context(
        request_id=generate_request_id(),
        user_id=user_id,
        endpoint="/api/search",
    )

    # Start distributed trace
    with start_span("search_request", kind=SpanKind.SERVER) as span:
        span.set_attribute("query.text", query)
        span.set_attribute("user.id", user_id)

        # Log request
        logger.info("search_request_received", query_length=len(query))

        # Metrics: increment request counter
        record_counter(
            StandardMetrics.REQUESTS_TOTAL,
            labels={"endpoint": "/api/search", "method": "POST"},
        )

        try:
            # Perform search with automatic timing
            with RecordLatency("search_latency_ms"):
                with LogPerformance(logger, "search_execution"):
                    results = await retrieval_service.search(query)

            # Record metrics
            record_histogram(
                StandardMetrics.RETRIEVAL_RESULTS_COUNT,
                len(results),
            )

            # Log success
            logger.info(
                "search_completed",
                results_count=len(results),
                has_results=len(results) > 0,
            )

            return results

        except Exception as e:
            # Log error
            logger.error(
                "search_failed",
                error_type=type(e).__name__,
                error_message=str(e),
                exception=e,
            )

            # Record error metric
            record_counter(
                StandardMetrics.REQUESTS_TOTAL,
                labels={"endpoint": "/api/search", "status": "error"},
            )

            # Span will automatically record error
            raise
```

## Deployment

### Production Configuration

**Environment Variables**:
```bash
# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Metrics export (OpenTelemetry)
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=semantica
OTEL_SERVICE_VERSION=1.0.0

# Tracing
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1  # Sample 10% of traces
```

### Exporting to Monitoring Systems

**Prometheus** (metrics):
```python
# Export metrics in Prometheus format
from prometheus_client import CollectorRegistry, Gauge, Counter, Histogram

def export_to_prometheus():
    collector = get_metrics_collector()
    metrics = collector.get_all_metrics()

    # Create Prometheus metrics
    for name, value in metrics["counters"].items():
        counter = Counter(name, f"Counter: {name}")
        counter.inc(value)

    for name, value in metrics["gauges"].items():
        gauge = Gauge(name, f"Gauge: {name}")
        gauge.set(value)
```

**OpenTelemetry Collector** (logs, metrics, traces):
```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  prometheus:
    endpoint: "0.0.0.0:9090"

  jaeger:
    endpoint: "jaeger:14250"

  logging:
    loglevel: info

service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [prometheus]

    traces:
      receivers: [otlp]
      exporters: [jaeger]
```

## Best Practices

### 1. Structured Logging
- ✅ Use key-value pairs, not string interpolation
- ✅ Add context early (request_id, user_id, etc.)
- ✅ Use consistent field names across services
- ❌ Don't log sensitive data (passwords, tokens, PII)

**Good**:
```python
logger.info("user_login", user_id=123, ip="192.168.1.1", success=True)
```

**Bad**:
```python
logger.info(f"User {user_id} logged in from {ip}")  # Not structured
```

### 2. Metrics Naming
- Use snake_case: `requests_total`, not `RequestsTotal`
- Include unit in name: `latency_ms`, `size_bytes`
- Use labels for dimensions: `{method="GET", status="200"}`
- Follow [Prometheus naming conventions](https://prometheus.io/docs/practices/naming/)

### 3. Tracing
- Create spans for all I/O operations (DB, API, cache)
- Keep span names concise and actionable
- Use semantic attributes from [OpenTelemetry spec](https://opentelemetry.io/docs/specs/semconv/)
- Sample traces in production (e.g., 10%) to reduce overhead

### 4. Performance
- Log at appropriate levels (DEBUG for verbose, INFO for key events)
- Use sampling for high-volume traces
- Batch metric exports
- Avoid logging in tight loops

## Testing

Run observability tests:
```bash
python -m pytest tests/infra/test_observability.py -v
```

## Dependencies

```toml
[project.dependencies]
structlog = ">=24.1.0"  # Structured logging
```

Optional (for OpenTelemetry integration):
```toml
opentelemetry-api = ">=1.20.0"
opentelemetry-sdk = ">=1.20.0"
opentelemetry-exporter-otlp = ">=1.20.0"
opentelemetry-instrumentation = ">=0.41b0"
```

## Next Steps

- [ ] Integrate with OpenTelemetry SDK for production export
- [ ] Setup Prometheus scraping endpoint
- [ ] Configure Jaeger/Zipkin for trace visualization
- [ ] Add alerting rules (e.g., error rate > 5%)
- [ ] Setup log aggregation (ELK, Loki, CloudWatch)
