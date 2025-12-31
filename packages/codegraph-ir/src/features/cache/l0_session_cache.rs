//! L0 Session Cache: Lock-free in-memory cache with fast path

use crate::features::cache::{
    bloom::BloomFilter, config::SessionCacheConfig, metrics::SessionCacheMetrics, CacheKey,
    CacheResult, FileId, FileMetadata, Fingerprint,
};
use dashmap::DashMap;
use parking_lot::RwLock;
use prometheus::Registry;
use std::collections::HashSet;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

/// Cache entry with access tracking
#[derive(Clone)]
struct CacheEntry<T> {
    /// Cached value (shared ownership)
    value: Arc<T>,

    /// Access count (for priority)
    access_count: Arc<AtomicU64>,

    /// Last access time (Unix timestamp in nanoseconds)
    last_access_ns: Arc<AtomicU64>,

    /// Estimated size in bytes
    size_bytes: usize,
}

impl<T> CacheEntry<T> {
    fn new(value: Arc<T>, size_bytes: usize) -> Self {
        let now = unix_now_ns();
        Self {
            value,
            access_count: Arc::new(AtomicU64::new(1)),
            last_access_ns: Arc::new(AtomicU64::new(now)),
            size_bytes,
        }
    }

    fn touch(&self) {
        self.access_count.fetch_add(1, Ordering::Relaxed);
        self.last_access_ns.store(unix_now_ns(), Ordering::Relaxed);
    }
}

/// L0 Session Cache
///
/// Lock-free concurrent HashMap with:
/// - Fast path check (mtime + size, no content hash)
/// - Bloom filter for O(1) existence check
/// - Automatic orphan purging
///
/// Performance: <1μs per lookup
pub struct SessionCache<T> {
    /// Main storage (lock-free)
    store: DashMap<FileId, CacheEntry<T>>,

    /// Metadata for fast path
    metadata: DashMap<FileId, FileMetadata>,

    /// Bloom filter (optional, for false positive prevention)
    bloom: Option<Arc<RwLock<BloomFilter<FileId>>>>,

    /// Configuration
    config: SessionCacheConfig,

    /// Metrics
    metrics: Arc<SessionCacheMetrics>,
}

impl<T> SessionCache<T> {
    /// Create new session cache
    pub fn new(config: SessionCacheConfig, registry: &Registry) -> Self {
        let bloom = if config.enable_bloom_filter {
            Some(Arc::new(RwLock::new(BloomFilter::new(
                config.bloom_capacity,
                config.bloom_fp_rate,
            ))))
        } else {
            None
        };

        Self {
            store: DashMap::new(),
            metadata: DashMap::new(),
            bloom,
            config,
            metrics: Arc::new(SessionCacheMetrics::new(registry)),
        }
    }

    /// Fast path check (mtime + size only, no content hash)
    ///
    /// Returns cached value if mtime and size match, without verifying content hash.
    /// This is a probabilistic check - use with caution!
    ///
    /// Performance: ~1μs
    pub fn check_fast_path(
        &self,
        file_id: &FileId,
        mtime_ns: u64,
        size_bytes: u64,
    ) -> Option<Arc<T>> {
        // 1. Bloom filter check (O(1))
        if let Some(bloom) = &self.bloom {
            if !bloom.read().contains(file_id) {
                return None;
            }
        }

        // 2. Metadata check
        if let Some(meta) = self.metadata.get(file_id) {
            if meta.matches_fast(mtime_ns, size_bytes) {
                // Fast hit! Return cached value
                if let Some(entry) = self.store.get(file_id) {
                    entry.touch();
                    self.metrics.fast_path_hits.inc();
                    self.metrics.hits.inc();
                    return Some(Arc::clone(&entry.value));
                }
            }
        }

        None
    }

    /// Get cached value with full fingerprint verification
    ///
    /// Performance: ~10μs (includes fingerprint comparison)
    pub fn get(&self, key: &CacheKey) -> Option<Arc<T>> {
        // Check metadata first
        if let Some(meta) = self.metadata.get(&key.file_id) {
            if meta.fingerprint.matches(&key.fingerprint) {
                // Fingerprint matches, return cached value
                if let Some(entry) = self.store.get(&key.file_id) {
                    entry.touch();
                    self.metrics.hits.inc();
                    return Some(Arc::clone(&entry.value));
                }
            }
        }

        self.metrics.misses.inc();
        None
    }

    /// Insert value with metadata
    pub fn insert(&self, key: CacheKey, value: Arc<T>, metadata: FileMetadata, size_bytes: usize) {
        let entry = CacheEntry::new(value, size_bytes);

        self.store.insert(key.file_id.clone(), entry);
        self.metadata.insert(key.file_id.clone(), metadata);

        // Update bloom filter
        if let Some(bloom) = &self.bloom {
            bloom.write().insert(&key.file_id);
        }

        self.metrics.entries.set(self.store.len() as i64);
    }

    /// Invalidate a single entry
    pub fn invalidate(&self, file_id: &FileId) {
        self.store.remove(file_id);
        self.metadata.remove(file_id);
        self.metrics.entries.set(self.store.len() as i64);
    }

    /// Purge orphaned entries (files no longer in current set)
    ///
    /// Call this after each build to clean up deleted files.
    pub fn purge_orphans(&self, current_files: &HashSet<FileId>) {
        let mut purged = 0;

        self.store.retain(|file_id, _| {
            if current_files.contains(file_id) {
                true
            } else {
                purged += 1;
                self.metadata.remove(file_id);
                false
            }
        });

        if purged > 0 {
            tracing::debug!("L0 purged {} orphan entries", purged);
            self.metrics.purged.inc_by(purged);
            self.metrics.entries.set(self.store.len() as i64);
        }
    }

    /// Clear all entries
    pub fn clear(&self) {
        self.store.clear();
        self.metadata.clear();

        if let Some(bloom) = &self.bloom {
            bloom.write().clear();
        }

        self.metrics.entries.set(0);
    }

    /// Get entry count
    pub fn len(&self) -> usize {
        self.store.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.store.is_empty()
    }

    /// Get hit rate
    pub fn hit_rate(&self) -> f64 {
        self.metrics.hit_rate()
    }

    /// Get metrics
    pub fn metrics(&self) -> Arc<SessionCacheMetrics> {
        Arc::clone(&self.metrics)
    }
}

/// Get current Unix timestamp in nanoseconds
fn unix_now_ns() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};

    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::cache::{FileId, Language};

    #[derive(Debug, Clone, PartialEq)]
    struct TestIRDocument {
        content: String,
    }

    fn create_test_key(path: &str, content: &str) -> (CacheKey, FileMetadata) {
        let file_id = FileId::from_path_str(path, Language::Python);
        let fingerprint = Fingerprint::compute(content.as_bytes());
        let metadata = FileMetadata::new(unix_now_ns(), content.len() as u64, fingerprint);

        (CacheKey::new(file_id, fingerprint), metadata)
    }

    #[test]
    fn test_session_cache_basic() {
        let registry = Registry::new();
        let config = SessionCacheConfig::default();
        let cache = SessionCache::new(config, &registry);

        let (key, metadata) = create_test_key("a.py", "print('hello')");
        let ir = Arc::new(TestIRDocument {
            content: "print('hello')".to_string(),
        });

        // Insert
        cache.insert(key.clone(), Arc::clone(&ir), metadata, 100);

        // Get
        let result = cache.get(&key);
        assert!(result.is_some());
        assert_eq!(result.unwrap().content, "print('hello')");

        // Hit rate
        assert!(cache.hit_rate() > 0.0);
    }

    #[test]
    fn test_session_cache_fast_path() {
        let registry = Registry::new();
        let config = SessionCacheConfig::default();
        let cache = SessionCache::new(config, &registry);

        let (key, metadata) = create_test_key("a.py", "code");
        let ir = Arc::new(TestIRDocument {
            content: "code".to_string(),
        });

        cache.insert(key.clone(), Arc::clone(&ir), metadata.clone(), 100);

        // Fast path hit (mtime + size match)
        let result = cache.check_fast_path(&key.file_id, metadata.mtime_ns, metadata.size_bytes);
        assert!(result.is_some());

        // Fast path miss (different mtime)
        let result =
            cache.check_fast_path(&key.file_id, metadata.mtime_ns + 1, metadata.size_bytes);
        assert!(result.is_none());

        // Fast path miss (different size)
        let result =
            cache.check_fast_path(&key.file_id, metadata.mtime_ns, metadata.size_bytes + 1);
        assert!(result.is_none());
    }

    #[test]
    fn test_session_cache_purge_orphans() {
        let registry = Registry::new();
        let config = SessionCacheConfig::default();
        let cache = SessionCache::new(config, &registry);

        // Insert 3 files
        for (i, path) in ["a.py", "b.py", "c.py"].iter().enumerate() {
            let (key, metadata) = create_test_key(path, &format!("code{}", i));
            let ir = Arc::new(TestIRDocument {
                content: format!("code{}", i),
            });
            cache.insert(key, ir, metadata, 100);
        }

        assert_eq!(cache.len(), 3);

        // Current files: only a.py and b.py (c.py deleted)
        let current_files: HashSet<FileId> = vec![
            FileId::from_path_str("a.py", Language::Python),
            FileId::from_path_str("b.py", Language::Python),
        ]
        .into_iter()
        .collect();

        cache.purge_orphans(&current_files);

        assert_eq!(cache.len(), 2);
    }

    #[test]
    fn test_session_cache_clear() {
        let registry = Registry::new();
        let config = SessionCacheConfig::default();
        let cache = SessionCache::new(config, &registry);

        let (key, metadata) = create_test_key("a.py", "code");
        let ir = Arc::new(TestIRDocument {
            content: "code".to_string(),
        });
        cache.insert(key, ir, metadata, 100);

        assert!(!cache.is_empty());

        cache.clear();

        assert!(cache.is_empty());
    }

    #[test]
    fn test_session_cache_access_tracking() {
        let registry = Registry::new();
        let config = SessionCacheConfig::default();
        let cache = SessionCache::new(config, &registry);

        let (key, metadata) = create_test_key("a.py", "code");
        let ir = Arc::new(TestIRDocument {
            content: "code".to_string(),
        });
        cache.insert(key.clone(), ir, metadata, 100);

        // Access multiple times
        for _ in 0..5 {
            cache.get(&key);
        }

        // Verify access count via entry
        {
            let entry = cache.store.get(&key.file_id).unwrap();
            assert_eq!(entry.access_count.load(Ordering::Relaxed), 6); // 1 insert + 5 gets
        };
    }

    #[test]
    fn test_session_cache_metrics() {
        let registry = Registry::new();
        let config = SessionCacheConfig::default();
        let cache = SessionCache::new(config, &registry);

        let (key1, metadata1) = create_test_key("a.py", "code1");
        let ir1 = Arc::new(TestIRDocument {
            content: "code1".to_string(),
        });
        cache.insert(key1.clone(), ir1, metadata1, 100);

        // Hit
        cache.get(&key1);

        // Miss
        let (key2, _) = create_test_key("b.py", "code2");
        cache.get(&key2);

        assert_eq!(cache.metrics.hits.get(), 1);
        assert_eq!(cache.metrics.misses.get(), 1);
        assert!((cache.hit_rate() - 0.5).abs() < 0.01);
    }

    #[test]
    fn test_session_cache_bloom_filter() {
        let registry = Registry::new();
        let mut config = SessionCacheConfig::default();
        config.enable_bloom_filter = true;
        let cache = SessionCache::new(config, &registry);

        let (key, metadata) = create_test_key("a.py", "code");
        let ir = Arc::new(TestIRDocument {
            content: "code".to_string(),
        });
        cache.insert(key.clone(), ir, metadata.clone(), 100);

        // Fast path should use bloom filter
        let result = cache.check_fast_path(&key.file_id, metadata.mtime_ns, metadata.size_bytes);
        assert!(result.is_some());

        // Non-existent file should fail bloom filter check
        let other_id = FileId::from_path_str("other.py", Language::Python);
        let result = cache.check_fast_path(&other_id, 0, 0);
        assert!(result.is_none());
    }
}
