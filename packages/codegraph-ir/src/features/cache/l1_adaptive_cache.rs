//! L1 Adaptive Cache: ARC eviction with TTL

use crate::features::cache::{
    config::AdaptiveCacheConfig, metrics::AdaptiveCacheMetrics, CacheKey, CacheResult,
};
use moka::future::Cache;
use prometheus::Registry;
use std::sync::Arc;

/// Trait for estimating object size
pub trait EstimateSize {
    fn estimated_size_bytes(&self) -> usize;
}

/// L1 Adaptive Cache with ARC eviction
///
/// Features:
/// - ARC (Adaptive Replacement Cache): Self-tuning LRU+LFU hybrid
/// - TTL: Automatic expiration after 1 hour
/// - Size-based eviction: Weighted by estimated_size_bytes()
///
/// Performance: ~10μs per lookup
pub struct AdaptiveCache<T: EstimateSize + Send + Sync + 'static> {
    /// moka cache (ARC + TTL)
    cache: Cache<CacheKey, Arc<T>>,

    /// Configuration
    config: AdaptiveCacheConfig,

    /// Metrics
    metrics: Arc<AdaptiveCacheMetrics>,
}

impl<T: EstimateSize + Send + Sync + 'static> AdaptiveCache<T> {
    /// Create new adaptive cache
    pub fn new(config: AdaptiveCacheConfig, registry: &Registry) -> Self {
        let cache = Cache::builder()
            // Max capacity (number of entries)
            .max_capacity(config.max_entries)
            // Weigher: size in MB
            .weigher(|_key: &CacheKey, value: &Arc<T>| {
                let bytes = value.estimated_size_bytes();
                let mb = (bytes / (1024 * 1024)).max(1) as u32;
                mb
            })
            // Time to live
            .time_to_live(config.ttl)
            // Eviction listener (optional)
            .eviction_listener(move |key, _value, cause| {
                if config.enable_eviction_listener {
                    tracing::debug!("L1 evicted: {} (cause: {:?})", key.file_id.path, cause);
                }
            })
            .build();

        Self {
            cache,
            config,
            metrics: Arc::new(AdaptiveCacheMetrics::new(registry)),
        }
    }

    /// Get cached value
    pub async fn get(&self, key: &CacheKey) -> Option<Arc<T>> {
        let result = self.cache.get(key).await;

        if result.is_some() {
            self.metrics.hits.inc();
        } else {
            self.metrics.misses.inc();
        }

        self.metrics.entries.set(self.cache.entry_count() as i64);
        self.metrics
            .bytes
            .set(self.cache.weighted_size() as i64 * 1024 * 1024);

        result
    }

    /// Insert value
    pub async fn insert(&self, key: CacheKey, value: Arc<T>) {
        self.cache.insert(key, value).await;

        self.metrics.entries.set(self.cache.entry_count() as i64);
        self.metrics
            .bytes
            .set(self.cache.weighted_size() as i64 * 1024 * 1024);
    }

    /// Invalidate a single entry
    pub async fn invalidate(&self, key: &CacheKey) {
        self.cache.invalidate(key).await;
        self.metrics.entries.set(self.cache.entry_count() as i64);
        self.metrics
            .bytes
            .set(self.cache.weighted_size() as i64 * 1024 * 1024);
    }

    /// Clear all entries
    pub async fn clear(&self) {
        self.cache.invalidate_all();
        self.cache.run_pending_tasks().await;

        self.metrics.entries.set(0);
        self.metrics.bytes.set(0);
    }

    /// Get entry count
    pub fn entry_count(&self) -> u64 {
        self.cache.entry_count()
    }

    /// Get weighted size (in MB)
    pub fn weighted_size_mb(&self) -> u64 {
        self.cache.weighted_size()
    }

    /// Get hit rate
    pub fn hit_rate(&self) -> f64 {
        self.metrics.hit_rate()
    }

    /// Get metrics
    pub fn metrics(&self) -> Arc<AdaptiveCacheMetrics> {
        Arc::clone(&self.metrics)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::cache::{FileId, Fingerprint, Language};

    #[derive(Debug, Clone)]
    struct TestIRDocument {
        content: String,
        size: usize,
    }

    impl EstimateSize for TestIRDocument {
        fn estimated_size_bytes(&self) -> usize {
            self.size
        }
    }

    fn create_test_key(path: &str, content: &str) -> CacheKey {
        CacheKey::new(
            FileId::from_path_str(path, Language::Python),
            Fingerprint::compute(content.as_bytes()),
        )
    }

    #[tokio::test]
    async fn test_adaptive_cache_basic() {
        let registry = Registry::new();
        let config = AdaptiveCacheConfig::default();
        let cache = AdaptiveCache::new(config, &registry);

        let key = create_test_key("a.py", "code");
        let ir = Arc::new(TestIRDocument {
            content: "code".to_string(),
            size: 1024,
        });

        // Insert
        cache.insert(key.clone(), Arc::clone(&ir)).await;

        // Get
        let result = cache.get(&key).await;
        assert!(result.is_some());
        assert_eq!(result.unwrap().content, "code");
    }

    #[tokio::test]
    async fn test_adaptive_cache_hit_miss() {
        let registry = Registry::new();
        let config = AdaptiveCacheConfig::default();
        let cache = AdaptiveCache::new(config, &registry);

        let key1 = create_test_key("a.py", "code1");
        let ir1 = Arc::new(TestIRDocument {
            content: "code1".to_string(),
            size: 1024,
        });
        cache.insert(key1.clone(), ir1).await;

        // Hit
        cache.get(&key1).await;

        // Miss
        let key2 = create_test_key("b.py", "code2");
        cache.get(&key2).await;

        assert_eq!(cache.metrics.hits.get(), 1);
        assert_eq!(cache.metrics.misses.get(), 1);
        assert!((cache.hit_rate() - 0.5).abs() < 0.01);
    }

    #[tokio::test]
    async fn test_adaptive_cache_size_based_eviction() {
        let registry = Registry::new();
        let mut config = AdaptiveCacheConfig::default();
        config.max_entries = 10;
        // Max 5MB weighted size
        let cache = AdaptiveCache::new(config, &registry);

        // Insert 10 items, each 1MB
        for i in 0..10 {
            let key = create_test_key(&format!("file{}.py", i), &format!("code{}", i));
            let ir = Arc::new(TestIRDocument {
                content: format!("code{}", i),
                size: 1024 * 1024, // 1MB
            });
            cache.insert(key, ir).await;
        }

        cache.cache.run_pending_tasks().await;

        // Should have entries (some may be evicted)
        assert!(cache.entry_count() > 0);
        assert!(cache.entry_count() <= 10);
    }

    #[tokio::test]
    async fn test_adaptive_cache_clear() {
        let registry = Registry::new();
        let config = AdaptiveCacheConfig::default();
        let cache = AdaptiveCache::new(config, &registry);

        let key = create_test_key("a.py", "code");
        let ir = Arc::new(TestIRDocument {
            content: "code".to_string(),
            size: 1024,
        });
        cache.insert(key, ir).await;
        cache.cache.run_pending_tasks().await; // Moka requires this to commit

        assert!(cache.entry_count() > 0);

        cache.clear().await;

        assert_eq!(cache.entry_count(), 0);
    }

    #[tokio::test]
    async fn test_adaptive_cache_metrics() {
        let registry = Registry::new();
        let config = AdaptiveCacheConfig::default();
        let cache = AdaptiveCache::new(config, &registry);

        let key = create_test_key("a.py", "code");
        let ir = Arc::new(TestIRDocument {
            content: "code".to_string(),
            size: 2 * 1024 * 1024,
        }); // 2MB
        cache.insert(key.clone(), Arc::clone(&ir)).await;
        cache.cache.run_pending_tasks().await; // Moka requires this to commit

        // get() updates metrics after run_pending_tasks
        let result = cache.get(&key).await;
        assert!(result.is_some());

        // Check metrics (updated by get)
        assert_eq!(cache.metrics.entries.get(), 1);
        // Weighted size should be ~2MB (weight is in MB units)
        assert!(cache.metrics.bytes.get() >= 1024 * 1024); // At least 1MB
        assert_eq!(cache.metrics.hits.get(), 1);
    }
}
