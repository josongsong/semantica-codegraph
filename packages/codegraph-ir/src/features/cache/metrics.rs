//! Prometheus metrics for cache system

use prometheus::{
    register_histogram_with_registry, register_int_counter_with_registry,
    register_int_gauge_with_registry, Histogram, HistogramOpts, IntCounter, IntGauge, Opts,
    Registry,
};
use std::sync::Arc;

/// L0 Session Cache Metrics
#[derive(Clone)]
pub struct SessionCacheMetrics {
    pub hits: IntCounter,
    pub misses: IntCounter,
    pub fast_path_hits: IntCounter,
    pub entries: IntGauge,
    pub purged: IntCounter,
}

impl SessionCacheMetrics {
    pub fn new(registry: &Registry) -> Self {
        Self {
            hits: register_int_counter_with_registry!(
                Opts::new("cache_l0_hits_total", "L0 cache hits"),
                registry
            )
            .unwrap(),
            misses: register_int_counter_with_registry!(
                Opts::new("cache_l0_misses_total", "L0 cache misses"),
                registry
            )
            .unwrap(),
            fast_path_hits: register_int_counter_with_registry!(
                Opts::new(
                    "cache_l0_fast_path_hits_total",
                    "L0 fast path hits (mtime+size)"
                ),
                registry
            )
            .unwrap(),
            entries: register_int_gauge_with_registry!(
                Opts::new("cache_l0_entries", "L0 cache entry count"),
                registry
            )
            .unwrap(),
            purged: register_int_counter_with_registry!(
                Opts::new("cache_l0_purged_total", "L0 purged orphan entries"),
                registry
            )
            .unwrap(),
        }
    }

    pub fn hit_rate(&self) -> f64 {
        let hits = self.hits.get() as f64;
        let total = hits + self.misses.get() as f64;
        if total > 0.0 {
            hits / total
        } else {
            0.0
        }
    }
}

/// L1 Adaptive Cache Metrics
#[derive(Clone)]
pub struct AdaptiveCacheMetrics {
    pub hits: IntCounter,
    pub misses: IntCounter,
    pub entries: IntGauge,
    pub evictions: IntCounter,
    pub bytes: IntGauge,
}

impl AdaptiveCacheMetrics {
    pub fn new(registry: &Registry) -> Self {
        Self {
            hits: register_int_counter_with_registry!(
                Opts::new("cache_l1_hits_total", "L1 cache hits"),
                registry
            )
            .unwrap(),
            misses: register_int_counter_with_registry!(
                Opts::new("cache_l1_misses_total", "L1 cache misses"),
                registry
            )
            .unwrap(),
            entries: register_int_gauge_with_registry!(
                Opts::new("cache_l1_entries", "L1 cache entry count"),
                registry
            )
            .unwrap(),
            evictions: register_int_counter_with_registry!(
                Opts::new("cache_l1_evictions_total", "L1 cache evictions"),
                registry
            )
            .unwrap(),
            bytes: register_int_gauge_with_registry!(
                Opts::new("cache_l1_bytes", "L1 cache memory usage"),
                registry
            )
            .unwrap(),
        }
    }

    pub fn hit_rate(&self) -> f64 {
        let hits = self.hits.get() as f64;
        let total = hits + self.misses.get() as f64;
        if total > 0.0 {
            hits / total
        } else {
            0.0
        }
    }
}

/// L2 Disk Cache Metrics
#[derive(Clone)]
pub struct DiskCacheMetrics {
    pub hits: IntCounter,
    pub misses: IntCounter,
    pub writes: IntCounter,
    pub corrupted: IntCounter,
    pub read_latency: Histogram,
    pub write_latency: Histogram,
}

impl DiskCacheMetrics {
    pub fn new(registry: &Registry) -> Self {
        Self {
            hits: register_int_counter_with_registry!(
                Opts::new("cache_l2_hits_total", "L2 cache hits"),
                registry
            )
            .unwrap(),
            misses: register_int_counter_with_registry!(
                Opts::new("cache_l2_misses_total", "L2 cache misses"),
                registry
            )
            .unwrap(),
            writes: register_int_counter_with_registry!(
                Opts::new("cache_l2_writes_total", "L2 cache writes"),
                registry
            )
            .unwrap(),
            corrupted: register_int_counter_with_registry!(
                Opts::new("cache_l2_corrupted_total", "L2 corrupted entries"),
                registry
            )
            .unwrap(),
            read_latency: register_histogram_with_registry!(
                HistogramOpts::new("cache_l2_read_latency_seconds", "L2 read latency")
                    .buckets(vec![0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1]),
                registry
            )
            .unwrap(),
            write_latency: register_histogram_with_registry!(
                HistogramOpts::new("cache_l2_write_latency_seconds", "L2 write latency")
                    .buckets(vec![0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]),
                registry
            )
            .unwrap(),
        }
    }
}

/// Tiered Cache Metrics (unified)
#[derive(Clone)]
pub struct TieredCacheMetrics {
    pub l0_hits: IntCounter,
    pub l1_hits: IntCounter,
    pub l2_hits: IntCounter,
    pub misses: IntCounter,
    pub total_latency: Histogram,
}

impl TieredCacheMetrics {
    pub fn new(registry: &Registry) -> Self {
        Self {
            l0_hits: register_int_counter_with_registry!(
                Opts::new("cache_tiered_l0_hits_total", "Tiered cache L0 hits"),
                registry
            )
            .unwrap(),
            l1_hits: register_int_counter_with_registry!(
                Opts::new("cache_tiered_l1_hits_total", "Tiered cache L1 hits"),
                registry
            )
            .unwrap(),
            l2_hits: register_int_counter_with_registry!(
                Opts::new("cache_tiered_l2_hits_total", "Tiered cache L2 hits"),
                registry
            )
            .unwrap(),
            misses: register_int_counter_with_registry!(
                Opts::new("cache_tiered_misses_total", "Tiered cache total misses"),
                registry
            )
            .unwrap(),
            total_latency: register_histogram_with_registry!(
                HistogramOpts::new(
                    "cache_tiered_total_latency_seconds",
                    "Total cache lookup latency"
                )
                .buckets(vec![0.000001, 0.00001, 0.0001, 0.001, 0.01, 0.1, 1.0]),
                registry
            )
            .unwrap(),
        }
    }

    pub fn overall_hit_rate(&self) -> f64 {
        let hits = (self.l0_hits.get() + self.l1_hits.get() + self.l2_hits.get()) as f64;
        let total = hits + self.misses.get() as f64;
        if total > 0.0 {
            hits / total
        } else {
            0.0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_cache_metrics() {
        let registry = Registry::new();
        let metrics = SessionCacheMetrics::new(&registry);

        metrics.hits.inc();
        metrics.hits.inc();
        metrics.misses.inc();

        assert_eq!(metrics.hits.get(), 2);
        assert_eq!(metrics.misses.get(), 1);
        assert!((metrics.hit_rate() - 0.666).abs() < 0.01);
    }

    #[test]
    fn test_tiered_cache_metrics() {
        let registry = Registry::new();
        let metrics = TieredCacheMetrics::new(&registry);

        metrics.l0_hits.inc_by(5);
        metrics.l1_hits.inc_by(3);
        metrics.l2_hits.inc_by(2);
        metrics.misses.inc_by(10);

        // Total hits = 10, total = 20
        assert!((metrics.overall_hit_rate() - 0.5).abs() < 0.01);
    }
}
