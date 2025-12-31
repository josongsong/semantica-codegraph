//! Tiered Cache: L0 → L1 → L2 facade with promotion and background sync
//!
//! Implements a multi-tier caching strategy:
//! - **L0 (Session Cache)**: Lock-free, fast-path mtime+size check
//! - **L1 (Adaptive Cache)**: ARC eviction with TTL
//! - **L2 (Disk Cache)**: Persistent rkyv+mmap storage
//!
//! Data flow:
//! - **Read**: L0 → L1 → L2 → compute + backfill
//! - **Write**: Synchronous to L0/L1, background to L2
//! - **Promotion**: L2 hit → backfill L1, L1 hit → backfill L0

use crate::features::cache::{
    config::TieredCacheConfig, l1_adaptive_cache::EstimateSize, metrics::TieredCacheMetrics,
    AdaptiveCache, CacheError, CacheKey, CacheResult, DiskCache, FileMetadata, SessionCache,
};
use dashmap::DashMap;
use prometheus::Registry;
use rkyv::bytecheck::CheckBytes;
use rkyv::ser::serializers::AllocSerializer;
use rkyv::validation::validators::DefaultValidator;
use rkyv::{Archive, Deserialize as RkyvDeserialize, Serialize as RkyvSerialize};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::mpsc;

/// Background write operation
enum WriteOp<T> {
    Set(CacheKey, Arc<T>),
    Invalidate(CacheKey),
}

/// Tiered Cache (L0 + L1 + L2)
pub struct TieredCache<T: EstimateSize + Send + Sync + 'static> {
    pub l0: SessionCache<T>,
    pub l1: AdaptiveCache<T>,
    pub l2: DiskCache,
    config: TieredCacheConfig,
    metrics: Arc<TieredCacheMetrics>,

    /// Background L2 write channel
    l2_writer: Option<mpsc::UnboundedSender<WriteOp<T>>>,
}

impl<T> TieredCache<T>
where
    T: EstimateSize + Send + Sync + Clone + 'static,
    T: Archive,
    T::Archived: CheckBytes<DefaultValidator<'static>> + RkyvDeserialize<T, rkyv::Infallible>,
    T: RkyvSerialize<AllocSerializer<1024>>,
{
    pub fn new(config: TieredCacheConfig, registry: &Registry) -> CacheResult<Self> {
        let l0 = SessionCache::new(config.l0.clone(), registry);
        let l1 = AdaptiveCache::new(config.l1.clone(), registry);
        let l2 = DiskCache::new_with_registry(config.l2.clone(), registry)?;

        let metrics = Arc::new(TieredCacheMetrics::new(registry));

        // Spawn background L2 writer task
        let l2_writer = if config.enable_background_l2_writes {
            let (tx, mut rx) = mpsc::unbounded_channel::<WriteOp<T>>();
            let l2_clone = Arc::new(l2.clone());

            tokio::spawn(async move {
                while let Some(op) = rx.recv().await {
                    match op {
                        WriteOp::Set(key, value) => {
                            // Background write to L2 (best-effort)
                            let _ = l2_clone.set(&key, &*value);
                        }
                        WriteOp::Invalidate(key) => {
                            let _ = l2_clone.invalidate(&key);
                        }
                    }
                }
            });

            Some(tx)
        } else {
            None
        };

        Ok(Self {
            l0,
            l1,
            l2,
            config,
            metrics,
            l2_writer,
        })
    }

    /// Get with tiered lookup and promotion
    pub async fn get(
        &self,
        key: &CacheKey,
        metadata: &FileMetadata,
    ) -> CacheResult<Option<Arc<T>>> {
        let start = Instant::now();

        // L0 check (fast path)
        if let Some(value) =
            self.l0
                .check_fast_path(&key.file_id, metadata.mtime_ns, metadata.size_bytes)
        {
            self.metrics.l0_hits.inc();
            self.metrics
                .total_latency
                .observe(start.elapsed().as_secs_f64());
            return Ok(Some(value));
        }

        // L0 check (full)
        if let Some(value) = self.l0.get(key) {
            self.metrics.l0_hits.inc();
            self.metrics
                .total_latency
                .observe(start.elapsed().as_secs_f64());
            return Ok(Some(value));
        }

        // L1 check
        if let Some(value) = self.l1.get(key).await {
            // Promote to L0
            let size_bytes = value.estimated_size_bytes();
            self.l0
                .insert(key.clone(), value.clone(), metadata.clone(), size_bytes);
            self.metrics.l1_hits.inc();
            self.metrics
                .total_latency
                .observe(start.elapsed().as_secs_f64());
            return Ok(Some(value));
        }

        // L2 check
        if let Some(value) = self.l2.get::<T>(key)? {
            // Promote to L1 and L0
            let size_bytes = value.estimated_size_bytes();
            self.l1.insert(key.clone(), value.clone()).await;
            self.l0
                .insert(key.clone(), value.clone(), metadata.clone(), size_bytes);
            self.metrics.l2_hits.inc();
            self.metrics
                .total_latency
                .observe(start.elapsed().as_secs_f64());
            return Ok(Some(value));
        }

        // All levels missed
        self.metrics.misses.inc();
        self.metrics
            .total_latency
            .observe(start.elapsed().as_secs_f64());
        Ok(None)
    }

    /// Set across all tiers
    pub async fn set(
        &self,
        key: &CacheKey,
        value: Arc<T>,
        metadata: &FileMetadata,
    ) -> CacheResult<()> {
        let size_bytes = value.estimated_size_bytes();

        // L0 (synchronous)
        self.l0
            .insert(key.clone(), value.clone(), metadata.clone(), size_bytes);

        // L1 (synchronous)
        self.l1.insert(key.clone(), value.clone()).await;

        // L2 (background or synchronous)
        if let Some(writer) = &self.l2_writer {
            // Background write
            writer
                .send(WriteOp::Set(key.clone(), value))
                .map_err(|_| CacheError::Internal("L2 writer channel closed".into()))?;
        } else {
            // Synchronous write
            self.l2.set(key, &*value)?;
        }

        Ok(())
    }

    /// Invalidate across all tiers
    pub async fn invalidate(&self, key: &CacheKey) -> CacheResult<()> {
        // L0
        self.l0.invalidate(&key.file_id);

        // L1
        self.l1.invalidate(key).await;

        // L2 (background or synchronous)
        if let Some(writer) = &self.l2_writer {
            writer
                .send(WriteOp::Invalidate(key.clone()))
                .map_err(|_| CacheError::Internal("L2 writer channel closed".into()))?;
        } else {
            self.l2.invalidate(key)?;
        }

        Ok(())
    }

    /// Clear all tiers
    pub async fn clear(&self) -> CacheResult<()> {
        self.l0.clear();
        self.l1.clear().await;
        self.l2.clear()?;
        Ok(())
    }

    /// Get overall hit rate
    pub fn hit_rate(&self) -> f64 {
        self.metrics.overall_hit_rate()
    }

    /// Purge orphaned L0 entries
    pub fn purge_orphans(
        &self,
        current_files: &std::collections::HashSet<crate::features::cache::FileId>,
    ) {
        self.l0.purge_orphans(current_files);
    }
}

impl Clone for DiskCache {
    fn clone(&self) -> Self {
        // For background writer - create a new instance sharing the same config
        // This is safe because DiskCache uses interior mutability (DashMap)
        Self {
            config: self.config.clone(),
            metrics: self.metrics.clone(),
            mmap_cache: DashMap::new(), // New cache for isolation
            index: self.index.clone(),  // Shared index
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::cache::config::{
        AdaptiveCacheConfig, DiskCacheConfig, SessionCacheConfig,
    };
    use crate::features::cache::{FileId, Fingerprint, Language};
    use std::time::Duration;
    use tempfile::TempDir;

    #[derive(Debug, Clone, PartialEq, Archive, RkyvSerialize, RkyvDeserialize)]
    #[archive(check_bytes)]
    struct TestData {
        id: u64,
        value: String,
    }

    impl EstimateSize for TestData {
        fn estimated_size_bytes(&self) -> usize {
            std::mem::size_of::<Self>() + self.value.len()
        }
    }

    fn temp_config() -> (TieredCacheConfig, TempDir) {
        let temp_dir = TempDir::new().unwrap();
        let config = TieredCacheConfig {
            l0: SessionCacheConfig {
                max_entries: 100,
                enable_bloom_filter: true,
                bloom_capacity: 1000,
                bloom_fp_rate: 0.01,
            },
            l1: AdaptiveCacheConfig {
                max_entries: 50,
                max_bytes: 10 * 1024 * 1024, // 10MB
                ttl: Duration::from_secs(3600),
                enable_eviction_listener: false,
            },
            l2: DiskCacheConfig {
                cache_dir: temp_dir.path().to_path_buf(),
                enable_compression: false,
                enable_rocksdb: false,
            },
            enable_background_l2_writes: false, // Synchronous for tests
        };
        (config, temp_dir)
    }

    #[tokio::test]
    async fn test_tiered_cache_basic() {
        let (config, _temp) = temp_config();
        let registry = Registry::new();
        let cache = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 123456789,
            size_bytes: 1024,
            fingerprint: Fingerprint::compute(b"test"),
        };
        let data = Arc::new(TestData {
            id: 42,
            value: "hello".into(),
        });

        // Set
        cache.set(&key, data.clone(), &metadata).await.unwrap();

        // Get (should hit L0)
        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(*retrieved, *data);
        assert_eq!(cache.metrics.l0_hits.get(), 1);
    }

    #[tokio::test]
    async fn test_tiered_cache_promotion_l2_to_l1() {
        let (config, _temp) = temp_config();
        let registry = Registry::new();
        let cache: TieredCache<TestData> = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 123456789,
            size_bytes: 1024,
            fingerprint: Fingerprint::compute(b"test"),
        };
        let data = Arc::new(TestData {
            id: 1,
            value: "data".into(),
        });

        // Write directly to L2 (bypass L0/L1)
        cache.l2.set(&key, &*data).unwrap();

        // Get (should hit L2 and promote to L0 + L1)
        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(*retrieved, *data);
        assert_eq!(cache.metrics.l2_hits.get(), 1);

        // Second get should hit L0 (promoted before L1 in lookup order)
        let retrieved2 = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(*retrieved2, *data);
        // L0 is checked before L1, so L0 hit is expected
        assert_eq!(cache.metrics.l0_hits.get(), 1);
    }

    #[tokio::test]
    async fn test_tiered_cache_invalidate() {
        let (config, _temp) = temp_config();
        let registry = Registry::new();
        let cache = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 123456789,
            size_bytes: 1024,
            fingerprint: Fingerprint::compute(b"test"),
        };
        let data = Arc::new(TestData {
            id: 1,
            value: "data".into(),
        });

        cache.set(&key, data.clone(), &metadata).await.unwrap();

        // Invalidate
        cache.invalidate(&key).await.unwrap();

        // Should miss all tiers
        let result = cache.get(&key, &metadata).await.unwrap();
        assert!(result.is_none());
        assert_eq!(cache.metrics.misses.get(), 1);
    }

    #[tokio::test]
    async fn test_tiered_cache_clear() {
        let (config, _temp) = temp_config();
        let registry = Registry::new();
        let cache = TieredCache::new(config, &registry).unwrap();

        for i in 0..10 {
            let key = CacheKey::from_file_id(FileId::from_path_str(
                &format!("test{}.py", i),
                Language::Python,
            ));
            let metadata = FileMetadata {
                mtime_ns: i,
                size_bytes: 100,
                fingerprint: Fingerprint::compute(format!("test{}", i).as_bytes()),
            };
            let data = Arc::new(TestData {
                id: i,
                value: format!("value{}", i),
            });
            cache.set(&key, data, &metadata).await.unwrap();
        }

        cache.clear().await.unwrap();

        // All should miss
        let key = CacheKey::from_file_id(FileId::from_path_str("test0.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 0,
            size_bytes: 100,
            fingerprint: Fingerprint::compute(b"test0"),
        };
        let result = cache.get(&key, &metadata).await.unwrap();
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_tiered_cache_fast_path() {
        let (config, _temp) = temp_config();
        let registry = Registry::new();
        let cache = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 999999999,
            size_bytes: 2048,
            fingerprint: Fingerprint::compute(b"fast_path_test"),
        };
        let data = Arc::new(TestData {
            id: 123,
            value: "fast".into(),
        });

        cache.set(&key, data.clone(), &metadata).await.unwrap();

        // Get with exact metadata (should use fast path)
        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(*retrieved, *data);

        // Should have hit L0 (fast path)
        assert!(cache.metrics.l0_hits.get() >= 1);
    }

    #[tokio::test]
    async fn test_tiered_cache_hit_rate() {
        let (config, _temp) = temp_config();
        let registry = Registry::new();
        let cache = TieredCache::new(config, &registry).unwrap();

        let key1 = CacheKey::from_file_id(FileId::from_path_str("test1.py", Language::Python));
        let key2 = CacheKey::from_file_id(FileId::from_path_str("test2.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 111111,
            size_bytes: 512,
            fingerprint: Fingerprint::compute(b"test"),
        };

        let data = Arc::new(TestData {
            id: 1,
            value: "data".into(),
        });

        // Set key1
        cache.set(&key1, data.clone(), &metadata).await.unwrap();

        // 2 hits on key1
        cache.get(&key1, &metadata).await.unwrap();
        cache.get(&key1, &metadata).await.unwrap();

        // 1 miss on key2
        cache.get(&key2, &metadata).await.unwrap();

        // Hit rate: 2/3 = 0.666...
        let hit_rate = cache.hit_rate();
        assert!((hit_rate - 0.666).abs() < 0.01);
    }
}
