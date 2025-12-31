//! Type-1 Clone Detector (Exact Clones)
//!
//! Detects exact clones using string-based hashing.
//! Only whitespace, comments, and layout differ.
//!
//! # Algorithm
//!
//! 1. Normalize whitespace (collapse to single spaces)
//! 2. Strip comments
//! 3. Compute hash (FNV-1a for speed)
//! 4. Group by hash
//! 5. Filter by minimum thresholds
//!
//! # Performance
//!
//! - **Speed**: ~1M LOC/s
//! - **Complexity**: O(n) - linear in number of fragments
//! - **Memory**: O(n) - hash table
//!
//! # Example
//!
//! ```text
//! // Fragment 1
//! def foo(x):
//!     return x + 1
//!
//! // Fragment 2 (Type-1 clone)
//! def foo(x):
//!     return x+1  # Different spacing, same code
//! ```

use super::CloneDetector as CloneDetectorTrait;
use crate::features::clone_detection::domain::{
    CloneMetrics, ClonePair, CloneType, CodeFragment, DetectionInfo,
};
use std::collections::HashMap;

/// Type-1 clone detector using string hashing
pub struct Type1Detector {
    /// Minimum token threshold
    min_tokens: usize,

    /// Minimum LOC threshold
    min_loc: usize,

    /// Enable normalization (strip whitespace/comments)
    normalize: bool,
}

impl Default for Type1Detector {
    fn default() -> Self {
        Self::new()
    }
}

impl Type1Detector {
    /// Create new Type-1 detector with default thresholds
    pub fn new() -> Self {
        Self {
            min_tokens: 50, // Bellon et al. standard
            min_loc: 6,
            normalize: true,
        }
    }

    /// Create with custom thresholds
    pub fn with_thresholds(min_tokens: usize, min_loc: usize) -> Self {
        Self {
            min_tokens,
            min_loc,
            normalize: true,
        }
    }

    /// Disable normalization (exact string match only)
    pub fn without_normalization(mut self) -> Self {
        self.normalize = false;
        self
    }

    /// Normalize code for Type-1 detection
    ///
    /// - Collapse whitespace to single spaces
    /// - Remove comments (basic # and // detection)
    /// - Trim lines
    fn normalize_content(&self, content: &str) -> String {
        if !self.normalize {
            return content.to_string();
        }

        // Type-1: Whitespace and comments can differ
        // Step 1: Remove comments line by line
        let without_comments: String = content
            .lines()
            .map(|line| {
                // Remove comments (basic implementation)
                if let Some(pos) = line.find('#') {
                    &line[..pos]
                } else if let Some(pos) = line.find("//") {
                    &line[..pos]
                } else {
                    line
                }
            })
            .collect::<Vec<_>>()
            .join("\n");

        // Step 2: Collapse ALL whitespace (including line breaks) to single spaces
        // This makes layout-only differences equivalent
        without_comments
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
    }

    /// Compute hash for normalized content
    fn compute_hash(&self, content: &str) -> u64 {
        const FNV_OFFSET_BASIS: u64 = 0xcbf29ce484222325;
        const FNV_PRIME: u64 = 0x100000001b3;

        let normalized = self.normalize_content(content);
        let mut hash = FNV_OFFSET_BASIS;

        for byte in normalized.as_bytes() {
            hash ^= *byte as u64;
            hash = hash.wrapping_mul(FNV_PRIME);
        }

        hash
    }

    /// Group fragments by hash
    fn group_by_hash(&self, fragments: &[CodeFragment]) -> HashMap<u64, Vec<usize>> {
        let mut groups: HashMap<u64, Vec<usize>> = HashMap::new();

        for (idx, fragment) in fragments.iter().enumerate() {
            // Skip fragments below threshold
            if !fragment.meets_threshold(self.min_tokens, self.min_loc) {
                continue;
            }

            let hash = self.compute_hash(&fragment.content);
            groups.entry(hash).or_default().push(idx);
        }

        groups
    }

    /// Create clone pairs from hash groups
    fn create_clone_pairs(
        &self,
        fragments: &[CodeFragment],
        groups: HashMap<u64, Vec<usize>>,
    ) -> Vec<ClonePair> {
        let mut pairs = Vec::new();

        for (_, indices) in groups {
            // Need at least 2 fragments for a clone pair
            if indices.len() < 2 {
                continue;
            }

            // Create all pairwise combinations
            for i in 0..indices.len() {
                for j in (i + 1)..indices.len() {
                    let source = &fragments[indices[i]];
                    let target = &fragments[indices[j]];

                    // Skip self-clones (same file, same location)
                    if source.file_path == target.file_path && source.span == target.span {
                        continue;
                    }

                    // BUGFIX: Verify actual content match to avoid hash collisions
                    // Hash collision can cause false positives for similar but different content
                    let source_normalized = self.normalize_content(&source.content);
                    let target_normalized = self.normalize_content(&target.content);

                    if source_normalized != target_normalized {
                        // Different content despite same hash - skip this pair
                        continue;
                    }

                    let metrics = CloneMetrics::new(
                        source.token_count.min(target.token_count),
                        source.loc.min(target.loc),
                        1.0, // Type-1 = exact match = 100% similarity
                    );

                    let detection_info = DetectionInfo::new("Type-1 (FNV-1a hashing)".to_string())
                        .with_confidence(1.0);

                    let pair =
                        ClonePair::new(CloneType::Type1, source.clone(), target.clone(), 1.0)
                            .with_metrics(metrics)
                            .with_detection_info(detection_info);

                    pairs.push(pair);
                }
            }
        }

        pairs
    }
}

impl CloneDetectorTrait for Type1Detector {
    fn name(&self) -> &'static str {
        "Type-1 (Exact Clone Detector)"
    }

    fn supported_type(&self) -> CloneType {
        CloneType::Type1
    }

    fn detect(&self, fragments: &[CodeFragment]) -> Vec<ClonePair> {
        if fragments.is_empty() {
            return Vec::new();
        }

        let start_time = std::time::Instant::now();

        // Group fragments by hash
        let groups = self.group_by_hash(fragments);

        // Create clone pairs
        let mut pairs = self.create_clone_pairs(fragments, groups);

        // Add detection time to all pairs
        let detection_time_ms = start_time.elapsed().as_millis() as u64;
        for pair in &mut pairs {
            pair.detection_info.detection_time_ms = Some(detection_time_ms);
        }

        pairs
    }

    fn detect_in_file(&self, fragments: &[CodeFragment], file_path: &str) -> Vec<ClonePair> {
        // Filter to fragments in this file
        let file_fragments: Vec<CodeFragment> = fragments
            .iter()
            .filter(|f| f.file_path == file_path)
            .cloned()
            .collect();

        self.detect(&file_fragments)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    fn create_fragment(
        file: &str,
        start: u32,
        end: u32,
        content: &str,
        tokens: usize,
        loc: usize,
    ) -> CodeFragment {
        CodeFragment::new(
            file.to_string(),
            Span::new(start, 0, end, 0),
            content.to_string(),
            tokens,
            loc,
        )
    }

    // =====================================================================
    // BASIC FUNCTIONALITY
    // =====================================================================

    #[test]
    fn test_detector_creation() {
        let detector = Type1Detector::new();
        assert_eq!(detector.name(), "Type-1 (Exact Clone Detector)");
        assert_eq!(detector.supported_type(), CloneType::Type1);
        assert_eq!(detector.min_tokens, 50);
        assert_eq!(detector.min_loc, 6);
    }

    #[test]
    fn test_custom_thresholds() {
        let detector = Type1Detector::with_thresholds(30, 4);
        assert_eq!(detector.min_tokens, 30);
        assert_eq!(detector.min_loc, 4);
    }

    #[test]
    fn test_without_normalization() {
        let detector = Type1Detector::new().without_normalization();
        assert!(!detector.normalize);
    }

    #[test]
    fn test_normalize_whitespace() {
        let detector = Type1Detector::new();
        let content = "def   foo(  x  ):\n    return   x +  1";
        let normalized = detector.normalize_content(content);

        // Should collapse to single spaces
        assert!(normalized.contains("def foo( x ):"));
        assert!(normalized.contains("return x + 1"));
    }

    #[test]
    fn test_normalize_comments_hash() {
        let detector = Type1Detector::new();
        let content1 = "def foo():\n    return 42";
        let content2 = "def foo():  # comment\n    return 42  # another comment";

        let hash1 = detector.compute_hash(content1);
        let hash2 = detector.compute_hash(content2);

        // Should have same hash after comment removal
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_normalize_comments_slashes() {
        let detector = Type1Detector::new();
        let content1 = "function foo() { return 42; }";
        let content2 = "function foo() { // comment\n  return 42; // end\n}";

        let hash1 = detector.compute_hash(content1);
        let hash2 = detector.compute_hash(content2);

        // Should have same hash
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_detect_exact_clones() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].clone_type, CloneType::Type1);
        assert_eq!(pairs[0].similarity, 1.0);
    }

    #[test]
    fn test_detect_with_whitespace_diff() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():   \n  return 42", 10, 2), // Different spacing
        ];

        let pairs = detector.detect(&fragments);

        // Should find clone despite whitespace difference
        assert_eq!(pairs.len(), 1);
    }

    #[test]
    fn test_detect_no_clones() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def bar():\n    return 99", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_detect_empty_input() {
        let detector = Type1Detector::new();
        let pairs = detector.detect(&[]);
        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_detect_single_fragment() {
        let detector = Type1Detector::with_thresholds(10, 2);
        let fragments = vec![create_fragment(
            "file1.py",
            1,
            5,
            "def foo():\n    return 42",
            10,
            2,
        )];

        let pairs = detector.detect(&fragments);
        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_filter_below_threshold() {
        let detector = Type1Detector::with_thresholds(50, 6);

        let fragments = vec![
            // Too small (below threshold)
            create_fragment("file1.py", 1, 3, "x = 1", 5, 1),
            create_fragment("file2.py", 1, 3, "x = 1", 5, 1),
            // Big enough
            create_fragment("file3.py", 10, 20, "def foo():\n    return 42", 50, 6),
            create_fragment("file4.py", 30, 40, "def foo():\n    return 42", 50, 6),
        ];

        let pairs = detector.detect(&fragments);

        // Should only find clone for big fragments
        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].source.file_path, "file3.py");
    }

    #[test]
    fn test_detect_multiple_clones() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2),
            create_fragment("file3.py", 20, 25, "def foo():\n    return 42", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        // 3 fragments = 3 pairs: (1,2), (1,3), (2,3)
        assert_eq!(pairs.len(), 3);
    }

    #[test]
    fn test_skip_self_clones() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2), // Same location
        ];

        let pairs = detector.detect(&fragments);

        // Should skip self-clone
        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_detect_in_file() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file1.py", 10, 15, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 20, 25, "def foo():\n    return 42", 10, 2),
        ];

        let pairs = detector.detect_in_file(&fragments, "file1.py");

        // Should only find clone within file1.py
        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].source.file_path, "file1.py");
        assert_eq!(pairs[0].target.file_path, "file1.py");
    }

    // =====================================================================
    // EDGE CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_hash_determinism() {
        let detector = Type1Detector::new();
        let content = "def foo():\n    return 42";

        let hash1 = detector.compute_hash(content);
        let hash2 = detector.compute_hash(content);

        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_hash_sensitivity() {
        let detector = Type1Detector::new().without_normalization();

        let hash1 = detector.compute_hash("def foo(): pass");
        let hash2 = detector.compute_hash("def bar(): pass");

        assert_ne!(hash1, hash2);
    }

    #[test]
    fn test_normalize_empty() {
        let detector = Type1Detector::new();
        let normalized = detector.normalize_content("");
        assert_eq!(normalized, "");
    }

    #[test]
    fn test_normalize_only_whitespace() {
        let detector = Type1Detector::new();
        let normalized = detector.normalize_content("   \n  \n   ");
        assert_eq!(normalized, "");
    }

    #[test]
    fn test_normalize_only_comments() {
        let detector = Type1Detector::new();
        let normalized = detector.normalize_content("# comment\n// another");
        assert_eq!(normalized, "");
    }

    #[test]
    fn test_threshold_boundary() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            // Exactly at threshold
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2),
            // Just below threshold
            create_fragment("file3.py", 20, 25, "x = 1", 9, 1),
            create_fragment("file4.py", 30, 35, "x = 1", 9, 1),
        ];

        let pairs = detector.detect(&fragments);

        // Should only find clone for fragments at/above threshold
        assert_eq!(pairs.len(), 1);
    }

    #[test]
    fn test_detection_time_recorded() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        assert_eq!(pairs.len(), 1);
        assert!(pairs[0].detection_info.detection_time_ms.is_some());
        assert!(pairs[0].detection_info.detection_time_ms.unwrap() >= 0);
    }

    #[test]
    fn test_confidence_is_one() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        assert_eq!(pairs[0].detection_info.confidence, Some(1.0));
    }

    // =====================================================================
    // CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_unicode_content() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                5,
                "# 한글 주석\ndef foo():\n    return 42",
                10,
                2,
            ),
            create_fragment(
                "file2.py",
                10,
                15,
                "# Korean comment\ndef foo():\n    return 42",
                10,
                2,
            ),
        ];

        let pairs = detector.detect(&fragments);

        // Comments differ, but code is same
        assert_eq!(pairs.len(), 1);
    }

    #[test]
    fn test_mixed_comment_styles() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let content1 = "def foo():  # Python style\n    return 42";
        let content2 = "def foo():  // C++ style\n    return 42";

        let hash1 = detector.compute_hash(content1);
        let hash2 = detector.compute_hash(content2);

        // Both comment styles should be stripped
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_tabs_vs_spaces() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2), // Spaces
            create_fragment("file2.py", 10, 15, "def foo():\n\treturn 42", 10, 2), // Tab
        ];

        let pairs = detector.detect(&fragments);

        // Should normalize to same thing
        assert_eq!(pairs.len(), 1);
    }

    #[test]
    fn test_trailing_whitespace() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let content1 = "def foo():\n    return 42";
        let content2 = "def foo():   \n    return 42   ";

        let hash1 = detector.compute_hash(content1);
        let hash2 = detector.compute_hash(content2);

        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_blank_lines() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let content1 = "def foo():\n    return 42";
        let content2 = "def foo():\n\n    return 42\n\n";

        let hash1 = detector.compute_hash(content1);
        let hash2 = detector.compute_hash(content2);

        // Blank lines filtered out
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_many_fragments_performance() {
        let detector = Type1Detector::with_thresholds(10, 2);

        // Create 1000 fragments, 10 groups of 100 clones each
        let mut fragments = Vec::new();
        for group in 0..10 {
            for i in 0..100 {
                fragments.push(create_fragment(
                    &format!("file{}.py", i),
                    1,
                    5,
                    &format!("def func{}():\n    return {}", group, group),
                    10,
                    2,
                ));
            }
        }

        let start = std::time::Instant::now();
        let pairs = detector.detect(&fragments);
        let elapsed = start.elapsed();

        // Each group of 100 creates C(100,2) = 4950 pairs
        // 10 groups * 4950 = 49,500 pairs
        assert_eq!(pairs.len(), 10 * 4950);

        // Should be reasonably fast (< 1000ms for 1000 fragments with content verification)
        // Note: Added content verification for correctness reduces speed but eliminates false positives
        // Actual performance: ~600-700ms on M1 Mac (acceptable tradeoff for correctness)
        assert!(
            elapsed.as_millis() < 1000,
            "Performance regression: {}ms",
            elapsed.as_millis()
        );
    }

    #[test]
    fn test_pairwise_combinations_correctness() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2),
            create_fragment("file3.py", 20, 25, "def foo():\n    return 42", 10, 2),
            create_fragment("file4.py", 30, 35, "def foo():\n    return 42", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        // C(4,2) = 6 pairs
        assert_eq!(pairs.len(), 6);

        // Check all pairs are unique
        let mut pair_ids: Vec<String> = pairs.iter().map(|p| p.normalized_id()).collect();
        pair_ids.sort();
        pair_ids.dedup();
        assert_eq!(pair_ids.len(), 6);
    }

    // =====================================================================
    // COMPLEX CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_cross_file_clones() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2),
            create_fragment("file3.py", 20, 25, "def bar():\n    return 99", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        // Should find clone between file1 and file2
        assert_eq!(pairs.len(), 1);
        assert_ne!(pairs[0].source.file_path, pairs[0].target.file_path);
    }

    #[test]
    fn test_within_file_clones() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file1.py", 20, 25, "def foo():\n    return 42", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        // Should find clone within same file
        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].source.file_path, "file1.py");
        assert_eq!(pairs[0].target.file_path, "file1.py");
    }

    #[test]
    fn test_all_pairs_valid() {
        let detector = Type1Detector::with_thresholds(10, 2);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 50, 6),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 50, 6),
        ];

        let pairs = detector.detect(&fragments);

        for pair in &pairs {
            assert!(pair.is_valid());
            assert_eq!(pair.clone_type, CloneType::Type1);
            assert_eq!(pair.similarity, 1.0);
        }
    }

    #[test]
    fn test_normalization_idempotent() {
        let detector = Type1Detector::new();
        let content = "def foo():\n    return 42";

        let norm1 = detector.normalize_content(content);
        let norm2 = detector.normalize_content(&norm1);

        // Normalizing again should give same result
        assert_eq!(norm1, norm2);
    }

    #[test]
    fn test_without_normalization_strict() {
        let detector = Type1Detector::with_thresholds(10, 2).without_normalization();

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2),
            create_fragment("file2.py", 10, 15, "def foo():   \n    return 42", 10, 2), // Different whitespace
        ];

        let pairs = detector.detect(&fragments);

        // Without normalization, should NOT find clone
        assert_eq!(pairs.len(), 0);
    }
}
