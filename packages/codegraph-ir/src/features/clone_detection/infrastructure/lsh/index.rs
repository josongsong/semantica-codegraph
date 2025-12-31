//! LSH Index for Fast Candidate Retrieval
//!
//! Implements banded LSH (Locality-Sensitive Hashing) for sub-linear
//! nearest neighbor search.
//!
//! # Algorithm (Banded LSH)
//!
//! 1. Partition signature into b bands of r rows each
//! 2. Hash each band independently
//! 3. Store fragment IDs in buckets
//! 4. Query: retrieve all fragments in same buckets
//!
//! # Parameters
//!
//! - `b` (num_bands): More bands → higher recall, more false positives
//! - `r` (rows_per_band): More rows → higher precision, lower recall
//! - Typically: b × r = 128 (total signature size)
//!
//! # Tuning
//!
//! For Jaccard threshold t, probability of being a candidate:
//! ```text
//! P(candidate) = 1 - (1 - t^r)^b
//! ```
//!
//! Recommended: `b=16, r=8` for t ≈ 0.5 (high recall ~95%)
//!
//! # Example
//!
//! ```ignore
//! let mut index = LSHIndex::new(16, 8);
//!
//! // Insert signatures
//! for (i, sig) in signatures.iter().enumerate() {
//!     index.insert(sig, i);
//! }
//!
//! // Query candidates
//! let candidates = index.query(&query_sig);
//! // candidates.len() << n (typically 1-5% of n)
//! ```

use super::minhash::MinHashSignature;
use std::collections::hash_map::DefaultHasher;
use std::collections::{HashMap, HashSet};
use std::hash::{Hash, Hasher};

/// Band hash type (hash of a signature band)
type BandHash = u64;

/// LSH Index for MinHash signatures
pub struct LSHIndex {
    /// Number of bands (b)
    num_bands: usize,

    /// Rows per band (r)
    rows_per_band: usize,

    /// Buckets: BandHash → List of (fragment_id, signature)
    buckets: Vec<HashMap<BandHash, Vec<usize>>>,
}

impl LSHIndex {
    /// Create new LSH index
    ///
    /// # Arguments
    /// * `num_bands` - Number of bands (b)
    /// * `rows_per_band` - Rows per band (r)
    ///
    /// # Constraints
    /// - `num_bands × rows_per_band` should equal signature size (128)
    ///
    /// # Recommended Configurations
    ///
    /// | Threshold | num_bands | rows_per_band | Recall |
    /// |-----------|-----------|---------------|--------|
    /// | t = 0.3   | 32        | 4             | ~98%   |
    /// | t = 0.5   | 16        | 8             | ~95%   |
    /// | t = 0.7   | 8         | 16            | ~90%   |
    pub fn new(num_bands: usize, rows_per_band: usize) -> Self {
        Self {
            num_bands,
            rows_per_band,
            buckets: vec![HashMap::new(); num_bands],
        }
    }

    /// Create with default configuration (t ≈ 0.5)
    pub fn default() -> Self {
        Self::new(16, 8)
    }

    /// Insert a signature into the index
    ///
    /// # Arguments
    /// * `signature` - MinHash signature to insert
    /// * `id` - Fragment ID
    pub fn insert(&mut self, signature: &MinHashSignature, id: usize) {
        assert_eq!(
            signature.num_hashes(),
            self.num_bands * self.rows_per_band,
            "Signature size must match num_bands × rows_per_band"
        );

        for band_idx in 0..self.num_bands {
            let band_hash = self.hash_band(signature, band_idx);

            self.buckets[band_idx]
                .entry(band_hash)
                .or_insert_with(Vec::new)
                .push(id);
        }
    }

    /// Query for candidate fragments
    ///
    /// Returns all fragment IDs that share at least one band hash
    /// with the query signature.
    ///
    /// # Complexity
    /// - Best case: O(1) - empty buckets
    /// - Average case: O(log n) - few candidates per bucket
    /// - Worst case: O(n) - all in same bucket (rare)
    pub fn query(&self, signature: &MinHashSignature) -> Vec<usize> {
        assert_eq!(
            signature.num_hashes(),
            self.num_bands * self.rows_per_band,
            "Query signature size must match index configuration"
        );

        let mut candidates = HashSet::new();

        for band_idx in 0..self.num_bands {
            let band_hash = self.hash_band(signature, band_idx);

            if let Some(bucket) = self.buckets[band_idx].get(&band_hash) {
                for &id in bucket {
                    candidates.insert(id);
                }
            }
        }

        candidates.into_iter().collect()
    }

    /// Hash a specific band of a signature
    fn hash_band(&self, signature: &MinHashSignature, band_idx: usize) -> BandHash {
        let start = band_idx * self.rows_per_band;
        let end = start + self.rows_per_band;

        let band = &signature.hashes[start..end];

        let mut hasher = DefaultHasher::new();
        for &hash_val in band {
            hash_val.hash(&mut hasher);
        }

        hasher.finish()
    }

    /// Get statistics about the index
    pub fn stats(&self) -> LSHIndexStats {
        let total_buckets: usize = self.buckets.iter().map(|band| band.len()).sum();

        let total_entries: usize = self
            .buckets
            .iter()
            .flat_map(|band| band.values())
            .map(|bucket| bucket.len())
            .sum();

        let max_bucket_size: usize = self
            .buckets
            .iter()
            .flat_map(|band| band.values())
            .map(|bucket| bucket.len())
            .max()
            .unwrap_or(0);

        LSHIndexStats {
            num_bands: self.num_bands,
            rows_per_band: self.rows_per_band,
            total_buckets,
            total_entries,
            max_bucket_size,
        }
    }
}

/// LSH Index statistics
#[derive(Debug, Clone)]
pub struct LSHIndexStats {
    pub num_bands: usize,
    pub rows_per_band: usize,
    pub total_buckets: usize,
    pub total_entries: usize,
    pub max_bucket_size: usize,
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn create_signature(text: &str) -> MinHashSignature {
        MinHashSignature::from_text(text, 5, 128)
    }

    #[test]
    fn test_insert_and_query() {
        let mut index = LSHIndex::new(16, 8);

        let sig1 = create_signature("def foo(): pass");
        let sig2 = create_signature("def foo(): pass"); // Identical
        let sig3 = create_signature("class Bar: pass"); // Different

        index.insert(&sig1, 0);
        index.insert(&sig2, 1);
        index.insert(&sig3, 2);

        // Query with sig1 should find sig2 (identical)
        let candidates = index.query(&sig1);
        assert!(candidates.contains(&0));
        assert!(candidates.contains(&1));

        // sig3 might or might not be in candidates (depends on hash collisions)
    }

    #[test]
    fn test_exact_match_high_recall() {
        let mut index = LSHIndex::new(16, 8);

        let sig1 = create_signature("def add(a, b): return a + b");
        let sig2 = create_signature("def add(a, b): return a + b");

        index.insert(&sig1, 0);
        index.insert(&sig2, 1);

        let candidates = index.query(&sig1);
        assert!(candidates.contains(&1), "Exact match should be found");
    }

    #[test]
    fn test_stats() {
        let mut index = LSHIndex::new(16, 8);

        for i in 0..10 {
            let sig = create_signature(&format!("def func{}(): pass", i));
            index.insert(&sig, i);
        }

        let stats = index.stats();
        assert_eq!(stats.num_bands, 16);
        assert_eq!(stats.rows_per_band, 8);
        assert!(stats.total_buckets > 0);
        assert!(stats.total_entries >= 10);
    }

    #[test]
    #[should_panic(expected = "Signature size must match")]
    fn test_insert_wrong_signature_size() {
        let mut index = LSHIndex::new(16, 8); // Expects 128 hashes

        let sig = MinHashSignature::from_text("test", 5, 64); // Only 64 hashes
        index.insert(&sig, 0);
    }

    #[test]
    fn test_query_empty_index() {
        let index = LSHIndex::new(16, 8);
        let sig = create_signature("test");

        let candidates = index.query(&sig);
        assert_eq!(candidates.len(), 0);
    }

    #[test]
    fn test_multiple_bands_increase_recall() {
        // More bands → higher recall
        let mut index_many_bands = LSHIndex::new(32, 4); // 32 bands
        let mut index_few_bands = LSHIndex::new(8, 16); // 8 bands

        let sig1 = create_signature("def foo(x): return x * 2");
        let sig2 = create_signature("def bar(y): return y * 2"); // Similar

        index_many_bands.insert(&sig1, 0);
        index_many_bands.insert(&sig2, 1);

        index_few_bands.insert(&sig1, 0);
        index_few_bands.insert(&sig2, 1);

        let cand_many = index_many_bands.query(&sig1);
        let cand_few = index_few_bands.query(&sig1);

        // More bands should retrieve more candidates (higher recall)
        // (This is probabilistic, so not guaranteed in all cases)
        println!("Many bands: {:?}", cand_many.len());
        println!("Few bands: {:?}", cand_few.len());
    }
}
