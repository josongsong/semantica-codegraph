// Function Summary for Interprocedural Taint Analysis
//
// Academic References:
// - Reps, T. et al. (1995). "Precise Interprocedural Dataflow Analysis via Graph Reachability"
// - Tripp, O. et al. (2009). "TAJ: Effective Taint Analysis of Web Applications"
//
// Ported from Python: packages/codegraph-engine/.../analyzers/function_summary.py

use lru::LruCache;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::num::NonZeroUsize;

/// Function taint summary: captures how taint propagates through a function
///
/// This allows analyzing functions in isolation and reusing results,
/// which is essential for scalable interprocedural analysis.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FunctionTaintSummary {
    /// Unique function ID: file:line:name:signature
    pub function_id: String,

    /// Parameter indices that propagate taint (0-based)
    /// If param N is in this set, taint flows from param N to return value
    pub tainted_params: HashSet<usize>,

    /// Whether return value can be tainted
    pub tainted_return: bool,

    /// Global variables that can be tainted by this function
    pub tainted_globals: HashSet<String>,

    /// Object attributes that can be tainted (e.g., "self.field")
    pub tainted_attributes: HashSet<String>,

    /// Whether this function sanitizes its inputs
    /// If true, calling this function removes taint
    pub sanitizes: bool,

    /// Confidence score (0.0-1.0)
    /// Lower values indicate uncertainty in the analysis
    pub confidence: f32,

    /// Analysis metadata (e.g., source file, line number)
    pub metadata: HashMap<String, String>,
}

impl FunctionTaintSummary {
    /// Create a new empty summary
    pub fn new(function_id: String) -> Self {
        Self {
            function_id,
            tainted_params: HashSet::new(),
            tainted_return: false,
            tainted_globals: HashSet::new(),
            tainted_attributes: HashSet::new(),
            sanitizes: false,
            confidence: 1.0,
            metadata: HashMap::new(),
        }
    }

    /// Check if a call with given tainted args produces tainted output
    ///
    /// Returns true if:
    /// 1. Function is not a sanitizer, AND
    /// 2. Return value is tainted, AND
    /// 3. At least one tainted arg flows to return
    pub fn is_tainted_call(&self, tainted_args: &HashSet<usize>) -> bool {
        // Sanitizers always return clean data
        if self.sanitizes {
            return false;
        }

        // If return is not tainted, output is clean
        if !self.tainted_return {
            return false;
        }

        // Check if any tainted arg flows to return
        !tainted_args.is_disjoint(&self.tainted_params)
    }

    /// Merge another summary into this one (for fixpoint iteration)
    ///
    /// Returns true if this summary changed
    ///
    /// This implements the lattice join operation:
    /// - Tainted params: union (more params = less precise but safe)
    /// - Tainted return: OR (if either says tainted, it's tainted)
    /// - Globals/attributes: union
    /// - Sanitizes: OR (conservative)
    pub fn merge(&mut self, other: &Self) -> bool {
        let mut changed = false;

        // Union of tainted params
        for &param in &other.tainted_params {
            if self.tainted_params.insert(param) {
                changed = true;
            }
        }

        // OR of tainted return
        if !self.tainted_return && other.tainted_return {
            self.tainted_return = true;
            changed = true;
        }

        // Union of tainted globals
        for global in &other.tainted_globals {
            if self.tainted_globals.insert(global.clone()) {
                changed = true;
            }
        }

        // Union of tainted attributes
        for attr in &other.tainted_attributes {
            if self.tainted_attributes.insert(attr.clone()) {
                changed = true;
            }
        }

        // OR of sanitizes (conservative: if either sanitizes, we assume it does)
        if !self.sanitizes && other.sanitizes {
            self.sanitizes = true;
            changed = true;
        }

        // Confidence: take minimum (conservative)
        if other.confidence < self.confidence {
            self.confidence = other.confidence;
            changed = true;
        }

        changed
    }

    /// Check if this summary represents a sanitizer function
    pub fn is_sanitizer(&self) -> bool {
        self.sanitizes
    }

    /// Get the set of parameters that propagate taint
    pub fn get_tainted_params(&self) -> &HashSet<usize> {
        &self.tainted_params
    }

    /// Mark a parameter as tainted
    pub fn add_tainted_param(&mut self, param_idx: usize) {
        self.tainted_params.insert(param_idx);
    }

    /// Mark return as tainted
    pub fn set_tainted_return(&mut self, tainted: bool) {
        self.tainted_return = tainted;
    }

    /// Add a tainted global variable
    pub fn add_tainted_global(&mut self, global: String) {
        self.tainted_globals.insert(global);
    }

    /// Add a tainted object attribute
    pub fn add_tainted_attribute(&mut self, attr: String) {
        self.tainted_attributes.insert(attr);
    }

    /// Mark as sanitizer
    pub fn set_sanitizer(&mut self, is_sanitizer: bool) {
        self.sanitizes = is_sanitizer;
    }
}

/// LRU cache for function summaries
///
/// Uses LRU eviction policy to limit memory usage while maintaining
/// good hit rates for frequently called functions
pub struct FunctionSummaryCache {
    /// LRU cache mapping function_id -> summary
    cache: LruCache<String, FunctionTaintSummary>,

    /// Cache hits counter
    hits: usize,

    /// Cache misses counter
    misses: usize,
}

impl FunctionSummaryCache {
    /// Create a new cache with the given maximum size
    pub fn new(max_size: usize) -> Self {
        let capacity = NonZeroUsize::new(max_size).expect("Cache size must be > 0");
        Self {
            cache: LruCache::new(capacity),
            hits: 0,
            misses: 0,
        }
    }

    /// Create a cache with default size (10,000 entries)
    pub fn with_default_size() -> Self {
        Self::new(10_000)
    }

    /// Get a summary from the cache
    ///
    /// Returns None if not found
    /// Updates hit/miss statistics
    pub fn get(&mut self, function_id: &str) -> Option<&FunctionTaintSummary> {
        match self.cache.get(function_id) {
            Some(summary) => {
                self.hits += 1;
                Some(summary)
            }
            None => {
                self.misses += 1;
                None
            }
        }
    }

    /// Get a mutable reference to a summary
    pub fn get_mut(&mut self, function_id: &str) -> Option<&mut FunctionTaintSummary> {
        self.cache.get_mut(function_id)
    }

    /// Insert or update a summary in the cache
    pub fn put(&mut self, summary: FunctionTaintSummary) {
        self.cache.put(summary.function_id.clone(), summary);
    }

    /// Check if a summary exists in the cache
    pub fn contains(&self, function_id: &str) -> bool {
        self.cache.contains(function_id)
    }

    /// Remove a summary from the cache
    pub fn remove(&mut self, function_id: &str) -> Option<FunctionTaintSummary> {
        self.cache.pop(function_id)
    }

    /// Clear the cache
    pub fn clear(&mut self) {
        self.cache.clear();
        self.hits = 0;
        self.misses = 0;
    }

    /// Get cache hit rate (0.0-1.0)
    pub fn hit_rate(&self) -> f32 {
        let total = self.hits + self.misses;
        if total == 0 {
            0.0
        } else {
            self.hits as f32 / total as f32
        }
    }

    /// Get total number of cache accesses
    pub fn total_accesses(&self) -> usize {
        self.hits + self.misses
    }

    /// Get number of cache hits
    pub fn hits(&self) -> usize {
        self.hits
    }

    /// Get number of cache misses
    pub fn misses(&self) -> usize {
        self.misses
    }

    /// Get current cache size
    pub fn len(&self) -> usize {
        self.cache.len()
    }

    /// Check if cache is empty
    pub fn is_empty(&self) -> bool {
        self.cache.is_empty()
    }

    /// Get cache statistics as a string
    pub fn stats(&self) -> String {
        format!(
            "Cache: {} entries, {} hits, {} misses, {:.2}% hit rate",
            self.len(),
            self.hits,
            self.misses,
            self.hit_rate() * 100.0
        )
    }
}

impl Default for FunctionSummaryCache {
    fn default() -> Self {
        Self::with_default_size()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_summary() {
        let summary = FunctionTaintSummary::new("test_func".to_string());
        assert!(!summary.is_tainted_call(&HashSet::from([0])));
        assert!(!summary.is_sanitizer());
        assert_eq!(summary.confidence, 1.0);
    }

    #[test]
    fn test_tainted_call_detection() {
        let mut summary = FunctionTaintSummary::new("test_func".to_string());
        summary.add_tainted_param(0);
        summary.set_tainted_return(true);

        // Param 0 is tainted and in args -> output is tainted
        assert!(summary.is_tainted_call(&HashSet::from([0])));

        // Param 1 is not a tainted param -> output is not tainted
        assert!(!summary.is_tainted_call(&HashSet::from([1])));

        // No tainted args -> output is not tainted
        assert!(!summary.is_tainted_call(&HashSet::new()));
    }

    #[test]
    fn test_sanitizer_always_clean() {
        let mut summary = FunctionTaintSummary::new("sanitize_func".to_string());
        summary.add_tainted_param(0);
        summary.set_tainted_return(true);
        summary.set_sanitizer(true);

        // Even with tainted params, sanitizer returns clean
        assert!(!summary.is_tainted_call(&HashSet::from([0])));
    }

    #[test]
    fn test_merge_summaries() {
        let mut s1 = FunctionTaintSummary::new("func".to_string());
        s1.add_tainted_param(0);
        s1.set_tainted_return(true);

        let mut s2 = FunctionTaintSummary::new("func".to_string());
        s2.add_tainted_param(1);
        s2.add_tainted_global("global_var".to_string());

        // Merge s2 into s1
        let changed = s1.merge(&s2);
        assert!(changed);

        // s1 should now have both param 0 and param 1
        assert!(s1.tainted_params.contains(&0));
        assert!(s1.tainted_params.contains(&1));
        assert!(s1.tainted_globals.contains("global_var"));
        assert!(s1.tainted_return);
    }

    #[test]
    fn test_merge_idempotent() {
        let mut s1 = FunctionTaintSummary::new("func".to_string());
        s1.add_tainted_param(0);

        let s2 = s1.clone();

        // Merging identical summaries should not change anything
        let changed = s1.merge(&s2);
        assert!(!changed);
    }

    #[test]
    fn test_cache_hit_miss() {
        let mut cache = FunctionSummaryCache::new(10);

        // Miss
        assert!(cache.get("func1").is_none());
        assert_eq!(cache.misses(), 1);
        assert_eq!(cache.hits(), 0);

        // Put and hit
        let summary = FunctionTaintSummary::new("func1".to_string());
        cache.put(summary);
        assert!(cache.get("func1").is_some());
        assert_eq!(cache.hits(), 1);
        assert_eq!(cache.hit_rate(), 0.5); // 1 hit / 2 total
    }

    #[test]
    fn test_cache_lru_eviction() {
        let mut cache = FunctionSummaryCache::new(2);

        // Fill cache
        cache.put(FunctionTaintSummary::new("func1".to_string()));
        cache.put(FunctionTaintSummary::new("func2".to_string()));

        // Access func1 (make it recently used)
        cache.get("func1");

        // Add func3 (should evict func2, not func1)
        cache.put(FunctionTaintSummary::new("func3".to_string()));

        assert!(cache.contains("func1"));
        assert!(!cache.contains("func2"));
        assert!(cache.contains("func3"));
    }

    #[test]
    fn test_cache_stats() {
        let mut cache = FunctionSummaryCache::new(10);
        cache.put(FunctionTaintSummary::new("func1".to_string()));

        cache.get("func1"); // hit
        cache.get("func2"); // miss

        let stats = cache.stats();
        assert!(stats.contains("1 hits"));
        assert!(stats.contains("1 misses"));
        assert!(stats.contains("50.00% hit rate"));
    }
}
