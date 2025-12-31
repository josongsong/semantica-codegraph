"""
RFC-039 P0.2: Cache Monitoring Metrics

Prometheus metrics for 3-Tier Cache observability.

Metrics:
- codegraph_cache_hits_total: Cache hits by tier
- codegraph_cache_misses_total: Cache misses
- codegraph_cache_size_bytes: Cache size by tier
- codegraph_cache_evictions_total: Evictions by tier
- codegraph_build_duration_seconds: Build duration by cache state

Usage:
    from monitoring.cache_metrics import record_cache_telemetry

    telemetry = await builder.get_l0_telemetry()
    record_cache_telemetry(telemetry, build_duration=5.2)
"""

from typing import Any

try:
    from prometheus_client import Counter, Histogram, Gauge

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


# Metrics (lazy init)
_cache_hits: Counter | None = None
_cache_misses: Counter | None = None
_cache_size: Gauge | None = None
_cache_evictions: Counter | None = None
_build_duration: Histogram | None = None


def _init_metrics():
    """Initialize Prometheus metrics (lazy)."""
    global _cache_hits, _cache_misses, _cache_size, _cache_evictions, _build_duration

    if not HAS_PROMETHEUS:
        return

    if _cache_hits is None:
        _cache_hits = Counter(
            "codegraph_cache_hits_total",
            "Total cache hits",
            ["tier"],  # l0, l1, l2
        )

    if _cache_misses is None:
        _cache_misses = Counter("codegraph_cache_misses_total", "Total cache misses")

    if _cache_size is None:
        _cache_size = Gauge(
            "codegraph_cache_size_bytes",
            "Cache size in bytes",
            ["tier"],  # l0, l1, l2
        )

    if _cache_evictions is None:
        _cache_evictions = Counter(
            "codegraph_cache_evictions_total",
            "Total cache evictions",
            ["tier"],  # l0, l1
        )

    if _build_duration is None:
        _build_duration = Histogram(
            "codegraph_build_duration_seconds",
            "Build duration in seconds",
            ["cache_state"],  # cold, warm_l2, watch_l0
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        )


def record_cache_telemetry(telemetry: dict[str, Any], build_duration: float | None = None):
    """
    Record cache telemetry to Prometheus.

    Args:
        telemetry: Telemetry dict from builder.get_l0_telemetry()
        build_duration: Build duration in seconds (optional)
    """
    if not HAS_PROMETHEUS:
        return

    _init_metrics()

    # Record hits by tier
    if _cache_hits:
        l0_hits = telemetry.get("l0_hits", 0)
        l1_hits = telemetry.get("l1_hits", 0)
        l2_hits = telemetry.get("l2_hits", 0)

        if l0_hits > 0:
            _cache_hits.labels(tier="l0").inc(l0_hits)
        if l1_hits > 0:
            _cache_hits.labels(tier="l1").inc(l1_hits)
        if l2_hits > 0:
            _cache_hits.labels(tier="l2").inc(l2_hits)

    # Record misses
    if _cache_misses:
        misses = telemetry.get("misses", 0)
        if misses > 0:
            _cache_misses.inc(misses)

    # Record cache sizes
    if _cache_size:
        l0_entries = telemetry.get("l0_entries", 0)
        l1_bytes = telemetry.get("l1_bytes", 0)
        l2_bytes = telemetry.get("l2_disk_bytes", 0)

        # Estimate L0 size (entries * avg 50KB)
        l0_bytes = l0_entries * 50 * 1024

        _cache_size.labels(tier="l0").set(l0_bytes)
        _cache_size.labels(tier="l1").set(l1_bytes)
        _cache_size.labels(tier="l2").set(l2_bytes)

    # Record evictions
    if _cache_evictions:
        l1_evictions = telemetry.get("l1_evictions", 0)
        if l1_evictions > 0:
            _cache_evictions.labels(tier="l1").inc(l1_evictions)

    # Record build duration
    if _build_duration and build_duration:
        # Determine cache state
        if l0_hits > 0:
            cache_state = "watch_l0"
        elif l2_hits > 0:
            cache_state = "warm_l2"
        else:
            cache_state = "cold"

        _build_duration.labels(cache_state=cache_state).observe(build_duration)


def get_cache_summary(telemetry: dict[str, Any]) -> str:
    """
    Generate human-readable cache summary.

    Args:
        telemetry: Telemetry dict

    Returns:
        Formatted summary string
    """
    total_requests = (
        telemetry.get("l0_hits", 0)
        + telemetry.get("l1_hits", 0)
        + telemetry.get("l2_hits", 0)
        + telemetry.get("misses", 0)
    )

    if total_requests == 0:
        return "No cache activity"

    l0_rate = telemetry.get("l0_hits", 0) / total_requests * 100
    l1_rate = telemetry.get("l1_hits", 0) / total_requests * 100
    l2_rate = telemetry.get("l2_hits", 0) / total_requests * 100
    miss_rate = telemetry.get("misses", 0) / total_requests * 100

    return f"""
Cache Summary:
  L0: {telemetry.get("l0_hits", 0):>6} hits ({l0_rate:>5.1f}%) - Fast: {telemetry.get("l0_fast_hits", 0)}, Hash: {telemetry.get("l0_hash_hits", 0)}
  L1: {telemetry.get("l1_hits", 0):>6} hits ({l1_rate:>5.1f}%)
  L2: {telemetry.get("l2_hits", 0):>6} hits ({l2_rate:>5.1f}%)
  Miss: {telemetry.get("misses", 0):>4} ({miss_rate:>5.1f}%)
  
  L0: {telemetry.get("l0_entries", 0)} entries
  L1: {telemetry.get("l1_entries", 0)} entries, {telemetry.get("l1_bytes", 0) / 1024 / 1024:.1f} MB
  L2: {telemetry.get("l2_entries", 0)} entries, {telemetry.get("l2_disk_bytes", 0) / 1024 / 1024:.1f} MB
  
  Evictions: L1={telemetry.get("l1_evictions", 0)}
  Failures: {telemetry.get("l0_failures", 0)} (negative cache)
    """.strip()
