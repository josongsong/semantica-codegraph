"""
Query Metrics - L11급 SOTA

Performance monitoring for query execution.

Metrics:
- Execution time
- Cache hit rate
- Nodes/edges visited
- Result size

SOLID:
- S: Metrics collection only
- O: Extensible metrics
- L: Consistent interface
- I: Focused metrics API
- D: No external dependencies

Thread Safety:
    All counters use atomic operations.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryMetrics:
    """
    Metrics for a single query execution

    Attributes:
        query_id: Unique query ID
        start_time: Query start (seconds since epoch)
        end_time: Query end (seconds since epoch)
        duration_ms: Execution duration (milliseconds)
        nodes_visited: Number of nodes visited
        edges_traversed: Number of edges traversed
        cache_hits: Cache hits
        cache_misses: Cache misses
        result_size: Result size (number of paths/nodes)
        strategy: Execution strategy used
        error: Error message (if failed)
    """

    query_id: str
    start_time: float
    end_time: float | None = None
    duration_ms: float = 0.0
    nodes_visited: int = 0
    edges_traversed: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    result_size: int = 0
    strategy: str = "default"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MetricsCollector:
    """
    Collects and aggregates query metrics

    Thread-safe metrics collection.

    Features:
    - Per-query metrics
    - Aggregated statistics
    - Cache hit rate
    - Performance histograms

    Example:
        collector = MetricsCollector()

        with collector.track_query("q1") as metrics:
            # Execute query
            metrics.nodes_visited = 100
            metrics.result_size = 5

        stats = collector.get_stats()
        print(f"Avg duration: {stats['avg_duration_ms']:.2f}ms")
    """

    def __init__(self):
        """Initialize metrics collector"""
        self._lock = threading.RLock()
        self._metrics: list[QueryMetrics] = []
        self._total_queries = 0
        self._failed_queries = 0

    def track_query(self, query_id: str) -> "QueryTracker":
        """
        Track a query execution

        Args:
            query_id: Unique query ID

        Returns:
            QueryTracker context manager

        Example:
            with collector.track_query("q1") as metrics:
                # Execute query
                metrics.nodes_visited = 100
        """
        return QueryTracker(self, query_id)

    def record_metrics(self, metrics: QueryMetrics) -> None:
        """
        Record metrics for a completed query

        Args:
            metrics: Query metrics
        """
        with self._lock:
            self._metrics.append(metrics)
            self._total_queries += 1
            if metrics.error:
                self._failed_queries += 1

    def get_stats(self) -> dict[str, Any]:
        """
        Get aggregated statistics

        Returns:
            Statistics dictionary

        Stats:
            - total_queries: Total queries executed
            - failed_queries: Failed queries
            - avg_duration_ms: Average execution time
            - p50_duration_ms: Median duration
            - p95_duration_ms: 95th percentile
            - p99_duration_ms: 99th percentile
            - total_cache_hits: Total cache hits
            - total_cache_misses: Total cache misses
            - cache_hit_rate: Cache hit rate (0-1)
        """
        with self._lock:
            if not self._metrics:
                return {
                    "total_queries": 0,
                    "failed_queries": 0,
                    "avg_duration_ms": 0.0,
                    "cache_hit_rate": 0.0,
                }

            durations = [m.duration_ms for m in self._metrics if m.duration_ms > 0]
            cache_hits = sum(m.cache_hits for m in self._metrics)
            cache_misses = sum(m.cache_misses for m in self._metrics)
            total_cache_ops = cache_hits + cache_misses

            durations_sorted = sorted(durations)
            n = len(durations_sorted)

            return {
                "total_queries": self._total_queries,
                "failed_queries": self._failed_queries,
                "success_rate": (self._total_queries - self._failed_queries) / self._total_queries
                if self._total_queries > 0
                else 0.0,
                "avg_duration_ms": sum(durations) / len(durations) if durations else 0.0,
                "p50_duration_ms": durations_sorted[n // 2] if n > 0 else 0.0,
                "p95_duration_ms": durations_sorted[int(n * 0.95)] if n > 0 else 0.0,
                "p99_duration_ms": durations_sorted[int(n * 0.99)] if n > 0 else 0.0,
                "min_duration_ms": min(durations) if durations else 0.0,
                "max_duration_ms": max(durations) if durations else 0.0,
                "total_cache_hits": cache_hits,
                "total_cache_misses": cache_misses,
                "cache_hit_rate": cache_hits / total_cache_ops if total_cache_ops > 0 else 0.0,
            }

    def get_recent_metrics(self, n: int = 10) -> list[QueryMetrics]:
        """
        Get recent query metrics

        Args:
            n: Number of recent metrics

        Returns:
            List of recent QueryMetrics
        """
        with self._lock:
            return self._metrics[-n:]

    def clear(self) -> None:
        """Clear all metrics (for testing)"""
        with self._lock:
            self._metrics.clear()
            self._total_queries = 0
            self._failed_queries = 0


class QueryTracker:
    """
    Context manager for tracking query execution

    Example:
        with collector.track_query("q1") as metrics:
            # Execute query
            metrics.nodes_visited = 100
            metrics.result_size = 5
    """

    def __init__(self, collector: MetricsCollector, query_id: str):
        """
        Initialize tracker

        Args:
            collector: Metrics collector
            query_id: Query ID
        """
        self._collector = collector
        self._metrics = QueryMetrics(
            query_id=query_id,
            start_time=time.time(),
        )

    def __enter__(self) -> QueryMetrics:
        """Enter context - start tracking"""
        return self._metrics

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - record metrics"""
        self._metrics.end_time = time.time()
        self._metrics.duration_ms = (self._metrics.end_time - self._metrics.start_time) * 1000

        if exc_val:
            self._metrics.error = str(exc_val)

        self._collector.record_metrics(self._metrics)
        return False  # Don't suppress exceptions


__all__ = ["QueryMetrics", "MetricsCollector", "QueryTracker"]
