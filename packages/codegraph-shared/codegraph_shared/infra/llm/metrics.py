"""
LLM Metrics Collection

LLM 호출 관련 메트릭을 수집합니다.
- 토큰 사용량 (input/output)
- 비용 (USD)
- Latency (ms)
- 에러율
"""

from codegraph_shared.infra.observability import get_logger
from codegraph_shared.infra.observability.otel_setup import get_meter

logger = get_logger(__name__)

# Get OTEL meter
_meter = None


def _get_meter():
    """Get or create OTEL meter."""
    global _meter
    if _meter is None:
        _meter = get_meter(__name__)
    return _meter


# ============================================================================
# Metric Instruments
# ============================================================================

# Counters (monotonically increasing)
_llm_requests_total = None
_llm_tokens_total = None
_llm_cost_total = None
_llm_errors_total = None
_metrics_errors_total = None  # Track metric recording failures

# Histograms (distributions)
_llm_latency_histogram = None
_llm_tokens_per_request_histogram = None


def _init_instruments():
    """Initialize OTEL metric instruments."""
    global _llm_requests_total, _llm_tokens_total, _llm_cost_total, _llm_errors_total
    global _llm_latency_histogram, _llm_tokens_per_request_histogram, _metrics_errors_total

    meter = _get_meter()
    if meter is None:
        return

    try:
        # Counters
        _llm_requests_total = meter.create_counter(
            name="llm.requests.total",
            description="Total number of LLM API requests",
            unit="1",
        )

        _llm_tokens_total = meter.create_counter(
            name="llm.tokens.total",
            description="Total number of tokens used (input + output)",
            unit="tokens",
        )

        _llm_cost_total = meter.create_counter(
            name="llm.cost.total",
            description="Total cost in USD",
            unit="USD",
        )

        _llm_errors_total = meter.create_counter(
            name="llm.errors.total",
            description="Total number of LLM errors",
            unit="1",
        )

        # Histograms
        _llm_latency_histogram = meter.create_histogram(
            name="llm.latency",
            description="LLM request latency",
            unit="ms",
        )

        _llm_tokens_per_request_histogram = meter.create_histogram(
            name="llm.tokens.per_request",
            description="Tokens per request distribution",
            unit="tokens",
        )

        _metrics_errors_total = meter.create_counter(
            name="llm.metrics.errors.total",
            description="Total number of metric recording errors",
            unit="1",
        )

        logger.info("llm_metrics_initialized")
    except Exception as e:
        logger.warning("llm_metrics_init_failed", error=str(e))


def _ensure_instruments():
    """
    Ensure instruments are initialized (lazy initialization).

    This is called by each record_* function to handle the case where
    the module was imported before setup_otel() was called.
    """
    global _llm_requests_total

    # Check if already initialized
    if _llm_requests_total is not None:
        return

    # Try to initialize
    _init_instruments()


# ============================================================================
# Metric Recording Functions
# ============================================================================


def record_llm_request(
    model: str,
    provider: str = "unknown",
    operation: str = "completion",
    status: str = "success",
    tenant_id: str | None = None,
    repo_id: str | None = None,
) -> None:
    """
    Record LLM request count.

    Args:
        model: Model name (e.g., "gpt-4o-mini")
        provider: Provider name (e.g., "openai", "local")
        operation: Operation type (e.g., "completion", "embedding", "chat")
        status: Request status ("success", "error")
        tenant_id: Optional tenant ID
        repo_id: Optional repository ID
    """
    _ensure_instruments()
    if _llm_requests_total is None:
        return

    try:
        attributes = {
            "model": model,
            "provider": provider,
            "operation": operation,
            "status": status,
        }
        if tenant_id:
            attributes["tenant_id"] = tenant_id
        if repo_id:
            attributes["repo_id"] = repo_id

        _llm_requests_total.add(1, attributes)
    except Exception as e:
        logger.warning("record_llm_request_failed", error=str(e), attributes=attributes)
        if _metrics_errors_total:
            try:
                _metrics_errors_total.add(1, {"metric": "llm_requests_total"})
            except Exception:
                pass  # Don't cascade errors


def record_llm_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
    provider: str = "unknown",
    operation: str = "completion",
    tenant_id: str | None = None,
    repo_id: str | None = None,
) -> None:
    """
    Record LLM token usage.

    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        provider: Provider name
        operation: Operation type
        tenant_id: Optional tenant ID
        repo_id: Optional repository ID
    """
    _ensure_instruments()
    if _llm_tokens_total is None or _llm_tokens_per_request_histogram is None:
        return

    try:
        total_tokens = input_tokens + output_tokens

        attributes = {
            "model": model,
            "provider": provider,
            "operation": operation,
            "token_type": "total",
        }
        if tenant_id:
            attributes["tenant_id"] = tenant_id
        if repo_id:
            attributes["repo_id"] = repo_id

        # Counter: total tokens
        _llm_tokens_total.add(total_tokens, attributes)

        # Histogram: tokens per request
        _llm_tokens_per_request_histogram.record(total_tokens, attributes)

        # Separate counters for input/output
        input_attrs = {**attributes, "token_type": "input"}
        output_attrs = {**attributes, "token_type": "output"}

        _llm_tokens_total.add(input_tokens, input_attrs)
        _llm_tokens_total.add(output_tokens, output_attrs)
    except Exception as e:
        logger.warning("record_llm_tokens_failed", error=str(e))
        if _metrics_errors_total:
            try:
                _metrics_errors_total.add(1, {"metric": "llm_tokens_total"})
            except Exception:
                pass


def record_llm_cost(
    model: str,
    cost_usd: float,
    provider: str = "unknown",
    operation: str = "completion",
    tenant_id: str | None = None,
    repo_id: str | None = None,
) -> None:
    """
    Record LLM cost in USD.

    Args:
        model: Model name
        cost_usd: Cost in USD
        provider: Provider name
        operation: Operation type
        tenant_id: Optional tenant ID
        repo_id: Optional repository ID
    """
    _ensure_instruments()
    if _llm_cost_total is None:
        return

    try:
        attributes = {
            "model": model,
            "provider": provider,
            "operation": operation,
        }
        if tenant_id:
            attributes["tenant_id"] = tenant_id
        if repo_id:
            attributes["repo_id"] = repo_id

        _llm_cost_total.add(cost_usd, attributes)
    except Exception as e:
        logger.warning("record_llm_cost_failed", error=str(e))
        if _metrics_errors_total:
            try:
                _metrics_errors_total.add(1, {"metric": "llm_cost_total"})
            except Exception:
                pass


def record_llm_latency(
    model: str,
    latency_ms: float,
    provider: str = "unknown",
    operation: str = "completion",
    status: str = "success",
) -> None:
    """
    Record LLM request latency.

    Args:
        model: Model name
        latency_ms: Latency in milliseconds
        provider: Provider name
        operation: Operation type
        status: Request status
    """
    _ensure_instruments()
    if _llm_latency_histogram is None:
        return

    try:
        attributes = {
            "model": model,
            "provider": provider,
            "operation": operation,
            "status": status,
        }

        _llm_latency_histogram.record(latency_ms, attributes)
    except Exception as e:
        logger.warning("record_llm_latency_failed", error=str(e))
        if _metrics_errors_total:
            try:
                _metrics_errors_total.add(1, {"metric": "llm_latency"})
            except Exception:
                pass


def record_llm_error(
    model: str,
    error_type: str,
    provider: str = "unknown",
    operation: str = "completion",
) -> None:
    """
    Record LLM error.

    Args:
        model: Model name
        error_type: Error type (e.g., "rate_limit", "timeout", "api_error")
        provider: Provider name
        operation: Operation type
    """
    _ensure_instruments()
    if _llm_errors_total is None:
        return

    try:
        attributes = {
            "model": model,
            "provider": provider,
            "operation": operation,
            "error_type": error_type,
        }

        _llm_errors_total.add(1, attributes)
    except Exception as e:
        logger.warning("record_llm_error_failed", error=str(e))
        if _metrics_errors_total:
            try:
                _metrics_errors_total.add(1, {"metric": "llm_errors_total"})
            except Exception:
                pass


# ============================================================================
# Helper Functions
# ============================================================================


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    provider: str = "openai",
) -> float:
    """
    Calculate LLM cost based on token usage.

    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        provider: Provider name

    Returns:
        Cost in USD

    Pricing (as of 2024-11):
    - GPT-4o: $2.50/1M input, $10.00/1M output
    - GPT-4o-mini: $0.15/1M input, $0.60/1M output
    - text-embedding-3-small: $0.02/1M tokens
    """
    # Pricing table (per 1M tokens)
    pricing = {
        "openai": {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4": {"input": 30.00, "output": 60.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
            "text-embedding-3-small": {"input": 0.02, "output": 0.02},
            "text-embedding-3-large": {"input": 0.13, "output": 0.13},
        },
        "local": {
            # Local models have no cost
            "default": {"input": 0.0, "output": 0.0},
        },
    }

    # Get pricing for provider/model
    provider_pricing = pricing.get(provider, {})
    model_pricing = provider_pricing.get(model, provider_pricing.get("default", {"input": 0.0, "output": 0.0}))

    # Calculate cost
    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]

    return input_cost + output_cost
