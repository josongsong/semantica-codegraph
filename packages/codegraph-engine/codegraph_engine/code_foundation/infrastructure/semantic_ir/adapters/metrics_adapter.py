"""
Body Hash Metrics Adapter (Hexagonal Architecture - Infrastructure)

Implements BodyHashMetricsPort using observability framework.
"""

from codegraph_shared.common.observability import record_counter, record_histogram
from codegraph_engine.code_foundation.domain.semantic_ir.ports import BodyHashMetricsPort


class ObservabilityMetricsAdapter:
    """
    Production-grade metrics adapter using observability framework.

    Implements BodyHashMetricsPort (domain interface) using
    structured metrics (infrastructure).

    SOTA Features:
    - Thread-safe (observability framework handles it)
    - Prometheus-compatible
    - High-cardinality labels (file_path hashed)
    """

    def record_computation(self, file_path: str, duration_ms: float, cache_hit: bool) -> None:
        """
        Record body hash computation event.

        Metrics:
        - Counter: body_hash_computations_total (labels: cache_hit)
        - Histogram: body_hash_duration_ms
        """
        record_counter(
            "semantic_ir_body_hash_computations_total",
            labels={"cache_hit": str(cache_hit).lower()},
        )

        record_histogram("semantic_ir_body_hash_duration_ms", duration_ms)

        # Cache hit rate tracking
        if cache_hit:
            record_counter("semantic_ir_body_hash_cache_hits_total")
        else:
            record_counter("semantic_ir_body_hash_cache_misses_total")

    def record_cache_size(self, size: int) -> None:
        """
        Record current cache size.

        Metrics:
        - Histogram: body_hash_cache_size
        """
        record_histogram("semantic_ir_body_hash_cache_size", size)

    def record_error(self, error_type: str, file_path: str) -> None:
        """
        Record error event.

        Metrics:
        - Counter: body_hash_errors_total (labels: error_type)
        """
        record_counter(
            "semantic_ir_body_hash_errors_total",
            labels={"error_type": error_type},
        )


class NoOpMetricsAdapter:
    """
    No-op adapter for testing/disabled metrics.

    Implements BodyHashMetricsPort with no side effects.
    """

    def record_computation(self, file_path: str, duration_ms: float, cache_hit: bool) -> None:
        pass

    def record_cache_size(self, size: int) -> None:
        pass

    def record_error(self, error_type: str, file_path: str) -> None:
        pass


def create_default_metrics_adapter(enable_metrics: bool = True) -> BodyHashMetricsPort:
    """
    Factory for creating default metrics adapter.

    Args:
        enable_metrics: Whether to enable actual metrics (default: True)

    Returns:
        ObservabilityMetricsAdapter if enabled, NoOpMetricsAdapter otherwise
    """
    if enable_metrics:
        return ObservabilityMetricsAdapter()
    return NoOpMetricsAdapter()


__all__ = [
    "ObservabilityMetricsAdapter",
    "NoOpMetricsAdapter",
    "create_default_metrics_adapter",
]
