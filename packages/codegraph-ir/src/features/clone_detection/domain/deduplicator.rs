//! Clone Pair Deduplicator
//!
//! Pure business logic for removing duplicate clone pairs.
//! No external dependencies - belongs in domain layer.

use super::{ClonePair, CodeFragment};
use std::collections::HashSet;

/// Clone pair deduplicator
///
/// Removes duplicate clone pairs based on source/target identity.
/// Uses efficient HashSet for O(n) deduplication instead of O(n²) nested loops.
pub struct CloneDeduplicator;

impl CloneDeduplicator {
    /// Deduplicate clone pairs
    ///
    /// Two pairs are considered duplicates if they have:
    /// - Same source file_path and span
    /// - Same target file_path and span
    ///
    /// # Performance
    /// - Old approach: O(n²) with 3x `clone()` calls
    /// - New approach: O(n) with single HashSet
    ///
    /// # Example
    /// ```
    /// use codegraph_ir::features::clone_detection::domain::{ClonePair, CloneDeduplicator};
    ///
    /// let pairs = vec![/* ... */];
    /// let unique_pairs = CloneDeduplicator::deduplicate(pairs);
    /// ```
    pub fn deduplicate(pairs: Vec<ClonePair>) -> Vec<ClonePair> {
        let mut seen = HashSet::new();
        pairs
            .into_iter()
            .filter(|pair| {
                let key = Self::pair_key(pair);
                seen.insert(key)
            })
            .collect()
    }

    /// Deduplicate from iterator (zero-copy when possible)
    pub fn deduplicate_iter<I>(pairs: I) -> Vec<ClonePair>
    where
        I: IntoIterator<Item = ClonePair>,
    {
        let mut seen = HashSet::new();
        pairs
            .into_iter()
            .filter(|pair| {
                let key = Self::pair_key(pair);
                seen.insert(key)
            })
            .collect()
    }

    /// Generate unique key for a clone pair
    ///
    /// Key format: (source_file, source_span, target_file, target_span)
    fn pair_key(pair: &ClonePair) -> (String, (u32, u32, u32, u32), String, (u32, u32, u32, u32)) {
        (
            pair.source.file_path.clone(),
            (
                pair.source.span.start_line,
                pair.source.span.start_col,
                pair.source.span.end_line,
                pair.source.span.end_col,
            ),
            pair.target.file_path.clone(),
            (
                pair.target.span.start_line,
                pair.target.span.start_col,
                pair.target.span.end_line,
                pair.target.span.end_col,
            ),
        )
    }

    /// Merge multiple clone pair sets with deduplication
    ///
    /// Efficiently merges results from Type-1, Type-2, Type-3, Type-4 detectors
    /// without intermediate clones.
    ///
    /// # Example
    /// ```
    /// use codegraph_ir::features::clone_detection::domain::CloneDeduplicator;
    ///
    /// // Each detector produces its own set of clone pairs
    /// let type1_pairs = vec![];  // Exact clones
    /// let type2_pairs = vec![];  // Renamed clones
    /// let type3_pairs = vec![];  // Near-miss clones
    /// let type4_pairs = vec![];  // Semantic clones
    ///
    /// let sets = vec![type1_pairs, type2_pairs, type3_pairs, type4_pairs];
    /// let merged = CloneDeduplicator::merge_sets(sets);
    /// assert!(merged.is_empty());  // All empty inputs
    /// ```
    pub fn merge_sets(pair_sets: Vec<Vec<ClonePair>>) -> Vec<ClonePair> {
        let total_size: usize = pair_sets.iter().map(|s| s.len()).sum();
        let mut all_pairs = Vec::with_capacity(total_size);

        for pairs in pair_sets {
            all_pairs.extend(pairs);
        }

        Self::deduplicate(all_pairs)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::clone_detection::domain::{CloneType, CodeFragment};
    use crate::shared::models::Span;

    fn create_pair(
        source_file: &str,
        source_line: u32,
        target_file: &str,
        target_line: u32,
    ) -> ClonePair {
        let source = CodeFragment::new(
            source_file.to_string(),
            Span::new(source_line, 0, source_line + 5, 0),
            "test code".to_string(),
            10,
            5,
        );

        let target = CodeFragment::new(
            target_file.to_string(),
            Span::new(target_line, 0, target_line + 5, 0),
            "test code".to_string(),
            10,
            5,
        );

        ClonePair::new(CloneType::Type1, source, target, 1.0)
    }

    #[test]
    fn test_deduplicate_removes_duplicates() {
        let pairs = vec![
            create_pair("file1.py", 1, "file2.py", 10),
            create_pair("file1.py", 1, "file2.py", 10), // duplicate
            create_pair("file3.py", 20, "file4.py", 30),
        ];

        let unique = CloneDeduplicator::deduplicate(pairs);
        assert_eq!(unique.len(), 2);
    }

    #[test]
    fn test_deduplicate_keeps_different_pairs() {
        let pairs = vec![
            create_pair("file1.py", 1, "file2.py", 10),
            create_pair("file1.py", 2, "file2.py", 10), // different source line
            create_pair("file1.py", 1, "file2.py", 20), // different target line
        ];

        let unique = CloneDeduplicator::deduplicate(pairs);
        assert_eq!(unique.len(), 3);
    }

    #[test]
    fn test_merge_sets() {
        let set1 = vec![create_pair("file1.py", 1, "file2.py", 10)];
        let set2 = vec![
            create_pair("file1.py", 1, "file2.py", 10), // duplicate with set1
            create_pair("file3.py", 20, "file4.py", 30),
        ];
        let set3 = vec![create_pair("file5.py", 40, "file6.py", 50)];

        let merged = CloneDeduplicator::merge_sets(vec![set1, set2, set3]);
        assert_eq!(merged.len(), 3); // 4 total - 1 duplicate = 3
    }

    #[test]
    fn test_deduplicate_empty() {
        let pairs: Vec<ClonePair> = vec![];
        let unique = CloneDeduplicator::deduplicate(pairs);
        assert_eq!(unique.len(), 0);
    }
}
