//! Clone Detection Infrastructure
//!
//! Implements the 4-tier clone detection system:
//! - Type-1: Exact clones (string hashing)
//! - Type-2: Renamed clones (AST normalization)
//! - Type-3: Gapped clones (PDG + edit distance)
//! - Type-4: Semantic clones (graph isomorphism)

use crate::features::clone_detection::domain::{
    CloneDeduplicator, ClonePair, CloneType, CodeFragment,
};

mod edge_case_tests;
pub mod hybrid_detector; // SOTA: Industry-grade hybrid approach
pub mod lsh; // LSH infrastructure for optimization
pub mod optimized_detector; // Phase 4: Optimized detector with LSH + caching
pub mod token_hash_index; // Fast Type-1 detection via token hashing
pub mod type1_detector;
pub mod type2_detector;
pub mod type3_detector;
pub mod type4_detector; // Edge case and stress tests

pub use hybrid_detector::{HybridCloneDetector, HybridDetectorStats};
pub use optimized_detector::{OptimizedCloneDetector, OptimizedDetectorStats};
pub use token_hash_index::{TokenHashIndex, TokenHashStats};
pub use type1_detector::Type1Detector;
pub use type2_detector::Type2Detector;
pub use type3_detector::Type3Detector;
pub use type4_detector::{PDGEdge, PDGNode, SimplePDG, Type4Detector};

// Import trait to use its methods
use self::CloneDetector as _;

/// Clone detector trait
///
/// All clone detectors implement this interface for uniform API
pub trait CloneDetector {
    /// Get detector name
    fn name(&self) -> &'static str;

    /// Get supported clone type
    fn supported_type(&self) -> CloneType;

    /// Detect clones across all fragments
    fn detect(&self, fragments: &[CodeFragment]) -> Vec<ClonePair>;

    /// Detect clones within a specific file
    fn detect_in_file(&self, fragments: &[CodeFragment], file_path: &str) -> Vec<ClonePair>;
}

/// Multi-level clone detector that runs all 4 types
pub struct MultiLevelDetector {
    type1: Type1Detector,
    type2: Type2Detector,
    type3: Type3Detector,
    type4: Type4Detector,
}

impl MultiLevelDetector {
    /// Create new multi-level detector with default thresholds
    pub fn new() -> Self {
        Self {
            type1: Type1Detector::new(),
            type2: Type2Detector::new(),
            type3: Type3Detector::new(),
            type4: Type4Detector::new(),
        }
    }

    /// Detect all clone types
    ///
    /// Runs all 4 detectors and merges results with efficient deduplication.
    ///
    /// # Performance Improvement
    /// - Old: O(n²) with 3x `clone()` calls
    /// - New: O(n) with single HashSet deduplication
    /// - Memory: 3x reduction (no intermediate clones)
    pub fn detect_all(&self, fragments: &[CodeFragment]) -> Vec<ClonePair> {
        // Collect results from all detectors
        let pair_sets = vec![
            self.type1.detect(fragments),
            self.type2.detect(fragments),
            self.type3.detect(fragments),
            self.type4.detect(fragments),
        ];

        // Merge and deduplicate efficiently (O(n) instead of O(n²))
        CloneDeduplicator::merge_sets(pair_sets)
    }

    /// Detect specific clone type
    pub fn detect_type(&self, fragments: &[CodeFragment], clone_type: CloneType) -> Vec<ClonePair> {
        match clone_type {
            CloneType::Type1 => self.type1.detect(fragments),
            CloneType::Type2 => self.type2.detect(fragments),
            CloneType::Type3 => self.type3.detect(fragments),
            CloneType::Type4 => self.type4.detect(fragments),
        }
    }
}

impl Default for MultiLevelDetector {
    fn default() -> Self {
        Self::new()
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

    #[test]
    fn test_multi_level_detector_creation() {
        let detector = MultiLevelDetector::new();
        assert_eq!(detector.type1.name(), "Type-1 (Exact Clone Detector)");
        assert_eq!(detector.type2.name(), "Type-2 (Renamed Clone Detector)");
    }

    #[test]
    fn test_detect_type1_specific() {
        let detector = MultiLevelDetector::new();

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 50, 6),
            create_fragment(
                "file2.py",
                10,
                15,
                "def add(a, b):\n    return a + b",
                50,
                6,
            ),
        ];

        let pairs = detector.detect_type(&fragments, CloneType::Type1);
        assert!(!pairs.is_empty());
        assert_eq!(pairs[0].clone_type, CloneType::Type1);
    }

    #[test]
    fn test_detect_type2_specific() {
        let detector = MultiLevelDetector::new();

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 50, 6),
            create_fragment(
                "file2.py",
                10,
                15,
                "def sum(x, y):\n    return x + y",
                50,
                6,
            ),
        ];

        let pairs = detector.detect_type(&fragments, CloneType::Type2);
        assert!(!pairs.is_empty());
        assert_eq!(pairs[0].clone_type, CloneType::Type2);
    }

    #[test]
    fn test_detect_all_excludes_duplicates() {
        let detector = MultiLevelDetector::new();

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 50, 6),
            create_fragment(
                "file2.py",
                10,
                15,
                "def add(a, b):\n    return a + b",
                50,
                6,
            ),
        ];

        let pairs = detector.detect_all(&fragments);

        // Should only have Type-1 clone, not duplicate Type-2
        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].clone_type, CloneType::Type1);
    }

    #[test]
    fn test_detect_all_includes_both_types() {
        let detector = MultiLevelDetector::new();

        let fragments = vec![
            // Type-1 clone pair
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 50, 6),
            create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 50, 6),
            // Type-2 clone pair (different identifiers)
            create_fragment(
                "file3.py",
                20,
                25,
                "def add(a, b):\n    return a + b",
                50,
                6,
            ),
            create_fragment(
                "file4.py",
                30,
                35,
                "def sum(x, y):\n    return x + y",
                50,
                6,
            ),
        ];

        let pairs = detector.detect_all(&fragments);

        // Should have both Type-1 and Type-2 pairs
        assert!(pairs.len() >= 2);
        assert!(pairs.iter().any(|p| p.clone_type == CloneType::Type1));
        assert!(pairs.iter().any(|p| p.clone_type == CloneType::Type2));
    }
}
