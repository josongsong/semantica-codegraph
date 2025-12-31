"""
Retrieval Metrics Collection

Retrieval 관련 메트릭을 수집합니다.
- 검색 latency
- Cache hit rate
- Result count
- mAP/Recall (evaluation)
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

# Counters
_retrieval_queries_total = None
_retrieval_cache_hits = None
_retrieval_cache_misses = None

# Histograms
_retrieval_latency_histogram = None
_retrieval_result_count_histogram = None

# Gauges (for evaluation metrics)
_retrieval_map_gauge = None
_retrieval_recall_gauge = None


def _init_instruments():
    """Initialize OTEL metric instruments."""
    global _retrieval_queries_total, _retrieval_cache_hits, _retrieval_cache_misses
    global _retrieval_latency_histogram, _retrieval_result_count_histogram
    global _retrieval_map_gauge, _retrieval_recall_gauge

    meter = _get_meter()
    if meter is None:
        return

    try:
        # Counters
        _retrieval_queries_total = meter.create_counter(
            name="retrieval.queries.total",
            description="Total number of retrieval queries",
            unit="1",
        )

        _retrieval_cache_hits = meter.create_counter(
            name="retrieval.cache.hits",
            description="Number of cache hits",
            unit="1",
        )

        _retrieval_cache_misses = meter.create_counter(
            name="retrieval.cache.misses",
            description="Number of cache misses",
            unit="1",
        )

        # Histograms
        _retrieval_latency_histogram = meter.create_histogram(
            name="retrieval.latency",
            description="Retrieval query latency",
            unit="ms",
        )

        _retrieval_result_count_histogram = meter.create_histogram(
            name="retrieval.result_count",
            description="Number of results returned",
            unit="1",
        )

        # Gauges (using UpDownCounter as approximation)
        _retrieval_map_gauge = meter.create_up_down_counter(
            name="retrieval.map",
            description="Mean Average Precision (evaluation)",
            unit="1",
        )

        _retrieval_recall_gauge = meter.create_up_down_counter(
            name="retrieval.recall",
            description="Recall@k (evaluation)",
            unit="1",
        )

        logger.info("retrieval_metrics_initialized")
    except Exception as e:
        logger.warning("retrieval_metrics_init_failed", error=str(e))


# Initialize on module import
_init_instruments()


# ============================================================================
# Metric Recording Functions
# ============================================================================


def record_retrieval_query(
    intent: str = "unknown",
    scope: str = "repository",
    status: str = "success",
    repo_id: str | None = None,
) -> None:
    """
    Record retrieval query count.

    Args:
        intent: Query intent (e.g., "definition", "usage", "implementation")
        scope: Search scope (e.g., "repository", "workspace", "file")
        status: Query status ("success", "error")
        repo_id: Optional repository ID
    """
    if _retrieval_queries_total is None:
        return

    try:
        attributes = {
            "intent": intent,
            "scope": scope,
            "status": status,
        }
        if repo_id:
            attributes["repo_id"] = repo_id

        _retrieval_queries_total.add(1, attributes)
    except Exception as e:
        logger.debug("record_retrieval_query_failed", error=str(e))


def record_cache_hit(
    cache_type: str = "embedding",
    repo_id: str | None = None,
) -> None:
    """
    Record cache hit.

    Args:
        cache_type: Type of cache (e.g., "embedding", "chunk", "result")
        repo_id: Optional repository ID
    """
    if _retrieval_cache_hits is None:
        return

    try:
        attributes = {"cache_type": cache_type}
        if repo_id:
            attributes["repo_id"] = repo_id

        _retrieval_cache_hits.add(1, attributes)
    except Exception as e:
        logger.debug("record_cache_hit_failed", error=str(e))


def record_cache_miss(
    cache_type: str = "embedding",
    repo_id: str | None = None,
) -> None:
    """
    Record cache miss.

    Args:
        cache_type: Type of cache
        repo_id: Optional repository ID
    """
    if _retrieval_cache_misses is None:
        return

    try:
        attributes = {"cache_type": cache_type}
        if repo_id:
            attributes["repo_id"] = repo_id

        _retrieval_cache_misses.add(1, attributes)
    except Exception as e:
        logger.debug("record_cache_miss_failed", error=str(e))


def record_retrieval_latency(
    latency_ms: float,
    intent: str = "unknown",
    scope: str = "repository",
    stage: str = "total",
) -> None:
    """
    Record retrieval latency.

    Args:
        latency_ms: Latency in milliseconds
        intent: Query intent
        scope: Search scope
        stage: Retrieval stage (e.g., "total", "search", "fusion", "rerank")
    """
    if _retrieval_latency_histogram is None:
        return

    try:
        attributes = {
            "intent": intent,
            "scope": scope,
            "stage": stage,
        }

        _retrieval_latency_histogram.record(latency_ms, attributes)
    except Exception as e:
        logger.debug("record_retrieval_latency_failed", error=str(e))


def record_result_count(
    count: int,
    intent: str = "unknown",
    scope: str = "repository",
) -> None:
    """
    Record number of results returned.

    Args:
        count: Number of results
        intent: Query intent
        scope: Search scope
    """
    if _retrieval_result_count_histogram is None:
        return

    try:
        attributes = {
            "intent": intent,
            "scope": scope,
        }

        _retrieval_result_count_histogram.record(count, attributes)
    except Exception as e:
        logger.debug("record_result_count_failed", error=str(e))


def record_evaluation_metrics(
    map_score: float,
    recall_at_10: float,
    dataset: str = "golden_set",
) -> None:
    """
    Record evaluation metrics (mAP, Recall@k).

    Args:
        map_score: Mean Average Precision
        recall_at_10: Recall at k=10
        dataset: Evaluation dataset name
    """
    if _retrieval_map_gauge is None or _retrieval_recall_gauge is None:
        return

    try:
        attributes = {"dataset": dataset}

        # Record as scaled integers (multiply by 1000 to preserve precision)
        _retrieval_map_gauge.add(int(map_score * 1000), attributes)
        _retrieval_recall_gauge.add(int(recall_at_10 * 1000), attributes)
    except Exception as e:
        logger.debug("record_evaluation_metrics_failed", error=str(e))


# ============================================================================
# Helper Functions
# ============================================================================


def calculate_cache_hit_rate(hits: int, total: int) -> float:
    """
    Calculate cache hit rate.

    Args:
        hits: Number of cache hits
        total: Total number of requests

    Returns:
        Cache hit rate (0.0 to 1.0)
    """
    if total == 0:
        return 0.0
    return hits / total
