//! Bloom filter wrapper for cache existence checks

use probabilistic_collections::bloom::BloomFilter as ProbBloomFilter;
use std::hash::Hash;

/// Bloom filter for O(1) existence checks
///
/// False positive rate: ~0.01 (1%)
/// False negative rate: 0 (impossible)
pub struct BloomFilter<T> {
    filter: ProbBloomFilter<T>,
    capacity: usize,
    false_positive_rate: f64,
}

impl<T: Hash> BloomFilter<T> {
    /// Create new bloom filter
    ///
    /// # Arguments
    /// * `capacity` - Expected number of elements
    /// * `false_positive_rate` - Target FP rate (default: 0.01)
    pub fn new(capacity: usize, false_positive_rate: f64) -> Self {
        let filter = ProbBloomFilter::new(capacity, false_positive_rate);

        Self {
            filter,
            capacity,
            false_positive_rate,
        }
    }

    /// Insert element
    pub fn insert(&mut self, item: &T) {
        self.filter.insert(item);
    }

    /// Check if element might exist (false positives possible)
    pub fn contains(&self, item: &T) -> bool {
        self.filter.contains(item)
    }

    /// Clear all entries
    pub fn clear(&mut self) {
        self.filter = ProbBloomFilter::new(self.capacity, self.false_positive_rate);
    }

    /// Get capacity
    pub fn capacity(&self) -> usize {
        self.capacity
    }
}

impl<T: Hash> Default for BloomFilter<T> {
    fn default() -> Self {
        Self::new(10_000, 0.01)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bloom_filter_basic() {
        let mut filter = BloomFilter::new(100, 0.01);

        filter.insert(&"key1");
        filter.insert(&"key2");

        assert!(filter.contains(&"key1"));
        assert!(filter.contains(&"key2"));
        assert!(!filter.contains(&"key3")); // Should be false (no false negatives)
    }

    #[test]
    fn test_bloom_filter_false_positive_rate() {
        let capacity = 1000;
        let mut filter = BloomFilter::new(capacity, 0.01);

        // Insert capacity elements
        for i in 0..capacity {
            filter.insert(&i);
        }

        // Test false positive rate on non-existent elements
        let test_count = 10000;
        let mut false_positives = 0;

        for i in capacity..(capacity + test_count) {
            if filter.contains(&i) {
                false_positives += 1;
            }
        }

        let fp_rate = false_positives as f64 / test_count as f64;

        // Should be close to 1% (with some tolerance)
        assert!(fp_rate < 0.05, "FP rate too high: {}", fp_rate);
    }

    #[test]
    fn test_bloom_filter_clear() {
        let mut filter = BloomFilter::new(100, 0.01);

        filter.insert(&"key1");
        assert!(filter.contains(&"key1"));

        filter.clear();
        assert!(!filter.contains(&"key1"));
    }

    #[test]
    fn test_bloom_filter_default() {
        let filter: BloomFilter<String> = BloomFilter::default();
        assert_eq!(filter.capacity(), 10_000);
    }
}
