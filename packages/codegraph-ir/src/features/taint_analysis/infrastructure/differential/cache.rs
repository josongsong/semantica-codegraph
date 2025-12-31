/*
 * Differential Analysis Cache
 *
 * Caches analysis results to avoid re-analyzing unchanged code.
 *
 * Cache strategy:
 * 1. Key: (commit SHA, file path) → Analysis result hash
 * 2. TTL: 15 minutes (self-cleaning)
 * 3. Invalidation: On file change or dependency change
 *
 * Performance target: 50-80% cache hit rate for typical PR workflow
 */

use super::error::{DifferentialError, DifferentialResult};
use super::result::DifferentialTaintResult;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};

/// Cache key for analysis results
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CacheKey {
    /// Commit SHA or version identifier
    pub version: String,
    /// File path
    pub file_path: String,
}

impl CacheKey {
    /// Create new cache key
    pub fn new(version: impl Into<String>, file_path: impl Into<String>) -> Self {
        Self {
            version: version.into(),
            file_path: file_path.into(),
        }
    }
}

/// Cached analysis result with metadata
#[derive(Debug, Clone)]
struct CachedEntry {
    /// The cached result
    result: DifferentialTaintResult,
    /// When this entry was created
    created_at: Instant,
    /// Hit count for statistics
    hit_count: usize,
}

impl CachedEntry {
    fn new(result: DifferentialTaintResult) -> Self {
        Self {
            result,
            created_at: Instant::now(),
            hit_count: 0,
        }
    }

    fn is_expired(&self, ttl: Duration) -> bool {
        self.created_at.elapsed() > ttl
    }
}

/// Cache for differential analysis results
pub struct AnalysisCache {
    /// Internal cache storage
    cache: Arc<RwLock<HashMap<CacheKey, CachedEntry>>>,
    /// Time-to-live for cache entries
    ttl: Duration,
    /// Cache statistics
    stats: Arc<RwLock<CacheStats>>,
}

/// Cache statistics
#[derive(Debug, Clone, Default)]
pub struct CacheStats {
    /// Total hits
    pub hits: usize,
    /// Total misses
    pub misses: usize,
    /// Total evictions (expired entries)
    pub evictions: usize,
}

impl CacheStats {
    /// Calculate hit rate (0.0-1.0)
    pub fn hit_rate(&self) -> f64 {
        let total = self.hits + self.misses;
        if total == 0 {
            0.0
        } else {
            self.hits as f64 / total as f64
        }
    }
}

impl AnalysisCache {
    /// Create new cache with default TTL (15 minutes)
    pub fn new() -> Self {
        Self::with_ttl(Duration::from_secs(15 * 60))
    }

    /// Create cache with custom TTL
    pub fn with_ttl(ttl: Duration) -> Self {
        Self {
            cache: Arc::new(RwLock::new(HashMap::new())),
            ttl,
            stats: Arc::new(RwLock::new(CacheStats::default())),
        }
    }

    /// Get cached result
    pub fn get(&self, key: &CacheKey) -> Option<DifferentialTaintResult> {
        // Clean expired entries first
        self.clean_expired();

        let mut cache = self.cache.write().ok()?;
        let mut stats = self.stats.write().ok()?;

        if let Some(entry) = cache.get_mut(key) {
            if !entry.is_expired(self.ttl) {
                // Cache hit
                entry.hit_count += 1;
                stats.hits += 1;
                return Some(entry.result.clone());
            } else {
                // Expired entry
                cache.remove(key);
                stats.evictions += 1;
            }
        }

        // Cache miss
        stats.misses += 1;
        None
    }

    /// Store result in cache
    pub fn put(&self, key: CacheKey, result: DifferentialTaintResult) -> DifferentialResult<()> {
        let mut cache = self
            .cache
            .write()
            .map_err(|e| DifferentialError::cache_error(format!("Cache lock error: {}", e)))?;

        cache.insert(key, CachedEntry::new(result));
        Ok(())
    }

    /// Invalidate specific entry
    pub fn invalidate(&self, key: &CacheKey) -> DifferentialResult<()> {
        let mut cache = self
            .cache
            .write()
            .map_err(|e| DifferentialError::cache_error(format!("Cache lock error: {}", e)))?;

        cache.remove(key);
        Ok(())
    }

    /// Invalidate all entries for a file path (across all versions)
    pub fn invalidate_file(&self, file_path: &str) -> DifferentialResult<()> {
        let mut cache = self
            .cache
            .write()
            .map_err(|e| DifferentialError::cache_error(format!("Cache lock error: {}", e)))?;

        cache.retain(|k, _| k.file_path != file_path);
        Ok(())
    }

    /// Clear entire cache
    pub fn clear(&self) -> DifferentialResult<()> {
        let mut cache = self
            .cache
            .write()
            .map_err(|e| DifferentialError::cache_error(format!("Cache lock error: {}", e)))?;

        cache.clear();
        Ok(())
    }

    /// Clean expired entries
    fn clean_expired(&self) {
        if let Ok(mut cache) = self.cache.write() {
            if let Ok(mut stats) = self.stats.write() {
                let before_count = cache.len();
                cache.retain(|_, entry| !entry.is_expired(self.ttl));
                let after_count = cache.len();
                stats.evictions += before_count - after_count;
            }
        }
    }

    /// Get cache statistics
    pub fn stats(&self) -> CacheStats {
        self.stats.read().map(|s| s.clone()).unwrap_or_default()
    }

    /// Get current cache size
    pub fn size(&self) -> usize {
        self.cache.read().map(|c| c.len()).unwrap_or(0)
    }
}

impl Default for AnalysisCache {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_basic_operations() {
        let cache = AnalysisCache::new();
        let key = CacheKey::new("abc123", "test.py");

        // Initially empty
        assert!(cache.get(&key).is_none());

        // Put and get
        let result = DifferentialTaintResult::new();
        cache.put(key.clone(), result.clone()).unwrap();
        assert!(cache.get(&key).is_some());
        assert_eq!(cache.size(), 1);

        // Invalidate
        cache.invalidate(&key).unwrap();
        assert!(cache.get(&key).is_none());
        assert_eq!(cache.size(), 0);
    }

    #[test]
    fn test_cache_expiration() {
        let cache = AnalysisCache::with_ttl(Duration::from_millis(50));
        let key = CacheKey::new("abc123", "test.py");

        // Put entry
        let result = DifferentialTaintResult::new();
        cache.put(key.clone(), result.clone()).unwrap();
        assert!(cache.get(&key).is_some());

        // Wait for expiration
        std::thread::sleep(Duration::from_millis(100));

        // Should be expired
        assert!(cache.get(&key).is_none());
    }

    #[test]
    fn test_cache_invalidate_file() {
        let cache = AnalysisCache::new();

        let key1 = CacheKey::new("abc123", "test.py");
        let key2 = CacheKey::new("def456", "test.py");
        let key3 = CacheKey::new("abc123", "other.py");

        let result = DifferentialTaintResult::new();
        cache.put(key1.clone(), result.clone()).unwrap();
        cache.put(key2.clone(), result.clone()).unwrap();
        cache.put(key3.clone(), result.clone()).unwrap();

        assert_eq!(cache.size(), 3);

        // Invalidate all entries for test.py
        cache.invalidate_file("test.py").unwrap();

        assert!(cache.get(&key1).is_none());
        assert!(cache.get(&key2).is_none());
        assert!(cache.get(&key3).is_some()); // other.py should remain
        assert_eq!(cache.size(), 1);
    }

    #[test]
    fn test_cache_stats() {
        let cache = AnalysisCache::new();
        let key = CacheKey::new("abc123", "test.py");

        let result = DifferentialTaintResult::new();
        cache.put(key.clone(), result.clone()).unwrap();

        // Miss (first get after put)
        let stats = cache.stats();
        assert_eq!(stats.misses, 0);

        // Hit
        assert!(cache.get(&key).is_some());
        let stats = cache.stats();
        assert_eq!(stats.hits, 1);
        assert_eq!(stats.hit_rate(), 1.0);

        // Another miss
        let key2 = CacheKey::new("def456", "other.py");
        assert!(cache.get(&key2).is_none());
        let stats = cache.stats();
        assert_eq!(stats.hits, 1);
        assert_eq!(stats.misses, 1);
        assert_eq!(stats.hit_rate(), 0.5);
    }

    #[test]
    fn test_cache_clear() {
        let cache = AnalysisCache::new();

        let key1 = CacheKey::new("abc123", "test.py");
        let key2 = CacheKey::new("def456", "other.py");

        let result = DifferentialTaintResult::new();
        cache.put(key1.clone(), result.clone()).unwrap();
        cache.put(key2.clone(), result.clone()).unwrap();

        assert_eq!(cache.size(), 2);

        cache.clear().unwrap();
        assert_eq!(cache.size(), 0);
        assert!(cache.get(&key1).is_none());
        assert!(cache.get(&key2).is_none());
    }
}
