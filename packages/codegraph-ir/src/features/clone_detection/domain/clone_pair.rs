//! Clone Pair Representation
//!
//! Represents a pair of code fragments that are clones of each other.
//! Includes similarity metrics and detection metadata.

use super::clone_type::CloneType;
use super::code_fragment::CodeFragment;
use serde::{Deserialize, Serialize};
use std::fmt;

/// A pair of code fragments that are clones
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ClonePair {
    /// Clone type classification
    pub clone_type: CloneType,

    /// Source code fragment
    pub source: CodeFragment,

    /// Target code fragment (clone of source)
    pub target: CodeFragment,

    /// Similarity score [0.0, 1.0]
    pub similarity: f64,

    /// Additional metrics
    pub metrics: CloneMetrics,

    /// Detection metadata
    pub detection_info: DetectionInfo,
}

/// Similarity and quality metrics for a clone pair
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CloneMetrics {
    /// Token-level similarity (Jaccard coefficient)
    pub token_similarity: f64,

    /// Line-level similarity
    pub line_similarity: f64,

    /// AST-level similarity (for Type-2+)
    pub ast_similarity: Option<f64>,

    /// Semantic similarity (for Type-4)
    pub semantic_similarity: Option<f64>,

    /// Edit distance (Levenshtein)
    pub edit_distance: Option<usize>,

    /// Normalized edit distance [0.0, 1.0]
    pub normalized_edit_distance: Option<f64>,

    /// Clone length (in tokens)
    pub clone_length_tokens: usize,

    /// Clone length (in LOC)
    pub clone_length_loc: usize,

    /// Gapped regions (for Type-3)
    pub gap_count: Option<usize>,

    /// Total gap size (lines)
    pub gap_size: Option<usize>,
}

/// Detection metadata
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DetectionInfo {
    /// Detection algorithm used
    pub algorithm: String,

    /// Detection time (milliseconds)
    pub detection_time_ms: Option<u64>,

    /// Detector version
    pub detector_version: String,

    /// Confidence score [0.0, 1.0]
    pub confidence: Option<f64>,

    /// Whether this is a true positive (for evaluation)
    pub is_true_positive: Option<bool>,

    /// Additional notes
    pub notes: Vec<String>,
}

impl ClonePair {
    /// Create a new clone pair
    pub fn new(
        clone_type: CloneType,
        source: CodeFragment,
        target: CodeFragment,
        similarity: f64,
    ) -> Self {
        let clone_length_tokens = source.token_count.min(target.token_count);
        let clone_length_loc = source.loc.min(target.loc);

        Self {
            clone_type,
            source,
            target,
            similarity,
            metrics: CloneMetrics {
                token_similarity: similarity,
                line_similarity: similarity,
                ast_similarity: None,
                semantic_similarity: None,
                edit_distance: None,
                normalized_edit_distance: None,
                clone_length_tokens,
                clone_length_loc,
                gap_count: None,
                gap_size: None,
            },
            detection_info: DetectionInfo {
                algorithm: clone_type.algorithm().to_string(),
                detection_time_ms: None,
                detector_version: "1.0.0".to_string(),
                confidence: None,
                is_true_positive: None,
                notes: Vec::new(),
            },
        }
    }

    /// Create with detailed metrics
    pub fn with_metrics(mut self, metrics: CloneMetrics) -> Self {
        self.metrics = metrics;
        self
    }

    /// Create with detection info
    pub fn with_detection_info(mut self, detection_info: DetectionInfo) -> Self {
        self.detection_info = detection_info;
        self
    }

    /// Add a note to detection info
    pub fn add_note(mut self, note: String) -> Self {
        self.detection_info.notes.push(note);
        self
    }

    /// Set confidence score
    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.detection_info.confidence = Some(confidence.clamp(0.0, 1.0));
        self
    }

    /// Check if clone pair is valid (meets thresholds)
    pub fn is_valid(&self) -> bool {
        let min_tokens = self.clone_type.min_token_threshold();
        let min_loc = self.clone_type.min_loc_threshold();
        let min_similarity = self.clone_type.similarity_threshold();

        self.source.meets_threshold(min_tokens, min_loc)
            && self.target.meets_threshold(min_tokens, min_loc)
            && self.similarity >= min_similarity
    }

    /// Check if source and target are in the same file
    pub fn is_same_file(&self) -> bool {
        self.source.file_path == self.target.file_path
    }

    /// Check if source and target overlap (for filtering)
    pub fn has_overlap(&self) -> bool {
        self.source.overlaps(&self.target)
    }

    /// Get overlap ratio (if any)
    pub fn overlap_ratio(&self) -> f64 {
        self.source.overlap_ratio(&self.target)
    }

    /// Get distance between fragments (in lines)
    pub fn distance_lines(&self) -> Option<usize> {
        if !self.is_same_file() {
            return None;
        }

        let (s1, e1) = self.source.line_range();
        let (s2, e2) = self.target.line_range();

        if e1 < s2 {
            Some(s2 - e1)
        } else if e2 < s1 {
            Some(s1 - e2)
        } else {
            Some(0) // Overlapping
        }
    }

    /// Check if this is a self-clone (same fragment)
    pub fn is_self_clone(&self) -> bool {
        self.is_same_file()
            && self.source.span == self.target.span
            && self.source.content == self.target.content
    }

    /// Get a unique identifier for this clone pair
    pub fn id(&self) -> String {
        format!(
            "{}:{}:{}-{}:{}:{}",
            self.source.file_path,
            self.source.span.start_line,
            self.source.span.end_line,
            self.target.file_path,
            self.target.span.start_line,
            self.target.span.end_line
        )
    }

    /// Get a normalized ID (smaller fragment first, for deduplication)
    pub fn normalized_id(&self) -> String {
        let source_key = (
            &self.source.file_path,
            self.source.span.start_line,
            self.source.span.end_line,
        );
        let target_key = (
            &self.target.file_path,
            self.target.span.start_line,
            self.target.span.end_line,
        );

        if source_key <= target_key {
            self.id()
        } else {
            format!(
                "{}:{}:{}-{}:{}:{}",
                self.target.file_path,
                self.target.span.start_line,
                self.target.span.end_line,
                self.source.file_path,
                self.source.span.start_line,
                self.source.span.end_line
            )
        }
    }

    /// Get quality score [0.0, 1.0]
    ///
    /// Quality = similarity * length_factor * confidence_factor
    pub fn quality_score(&self) -> f64 {
        let length_factor = self.length_factor();
        let confidence_factor = self.detection_info.confidence.unwrap_or(1.0);

        self.similarity * length_factor * confidence_factor
    }

    /// Calculate length factor [0.0, 1.0]
    ///
    /// Longer clones are generally more significant
    fn length_factor(&self) -> f64 {
        const MIN_TOKENS: f64 = 50.0;
        const MAX_TOKENS: f64 = 500.0;

        let tokens = self.metrics.clone_length_tokens as f64;
        ((tokens - MIN_TOKENS) / (MAX_TOKENS - MIN_TOKENS)).clamp(0.0, 1.0)
    }

    /// Check if this clone is a subset of another (contained within)
    pub fn is_subset_of(&self, other: &ClonePair) -> bool {
        (self.source.is_contained_in(&other.source) && self.target.is_contained_in(&other.target))
            || (self.source.is_contained_in(&other.target)
                && self.target.is_contained_in(&other.source))
    }

    /// Compute similarity with another clone pair (for clustering)
    pub fn similarity_with(&self, other: &ClonePair) -> f64 {
        // Jaccard similarity of fragments
        let source_overlap = self
            .source
            .overlap_ratio(&other.source)
            .max(self.source.overlap_ratio(&other.target));
        let target_overlap = self
            .target
            .overlap_ratio(&other.source)
            .max(self.target.overlap_ratio(&other.target));

        (source_overlap + target_overlap) / 2.0
    }
}

impl fmt::Display for ClonePair {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "ClonePair({}, {:.1}% similar, {} ↔ {})",
            self.clone_type,
            self.similarity * 100.0,
            self.source.location_string(),
            self.target.location_string()
        )
    }
}

impl CloneMetrics {
    /// Create default metrics
    pub fn new(tokens: usize, loc: usize, similarity: f64) -> Self {
        Self {
            token_similarity: similarity,
            line_similarity: similarity,
            ast_similarity: None,
            semantic_similarity: None,
            edit_distance: None,
            normalized_edit_distance: None,
            clone_length_tokens: tokens,
            clone_length_loc: loc,
            gap_count: None,
            gap_size: None,
        }
    }

    /// Add AST similarity (for Type-2+)
    pub fn with_ast_similarity(mut self, similarity: f64) -> Self {
        self.ast_similarity = Some(similarity);
        self
    }

    /// Add semantic similarity (for Type-4)
    pub fn with_semantic_similarity(mut self, similarity: f64) -> Self {
        self.semantic_similarity = Some(similarity);
        self
    }

    /// Add edit distance
    pub fn with_edit_distance(mut self, distance: usize, max_length: usize) -> Self {
        self.edit_distance = Some(distance);
        if max_length > 0 {
            self.normalized_edit_distance = Some(1.0 - (distance as f64 / max_length as f64));
        }
        self
    }

    /// Add gap information (for Type-3)
    pub fn with_gaps(mut self, gap_count: usize, gap_size: usize) -> Self {
        self.gap_count = Some(gap_count);
        self.gap_size = Some(gap_size);
        self
    }
}

impl DetectionInfo {
    /// Create new detection info
    pub fn new(algorithm: String) -> Self {
        Self {
            algorithm,
            detection_time_ms: None,
            detector_version: "1.0.0".to_string(),
            confidence: None,
            is_true_positive: None,
            notes: Vec::new(),
        }
    }

    /// Add detection time
    pub fn with_time(mut self, time_ms: u64) -> Self {
        self.detection_time_ms = Some(time_ms);
        self
    }

    /// Add confidence score
    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.confidence = Some(confidence.clamp(0.0, 1.0));
        self
    }

    /// Mark as true/false positive
    pub fn with_ground_truth(mut self, is_true_positive: bool) -> Self {
        self.is_true_positive = Some(is_true_positive);
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    fn create_test_fragment(
        file: &str,
        start_line: usize,
        end_line: usize,
        tokens: usize,
        loc: usize,
        content: &str,
    ) -> CodeFragment {
        CodeFragment::new(
            file.to_string(),
            Span::new(start_line as u32, 0, end_line as u32, 0),
            content.to_string(),
            tokens,
            loc,
        )
    }

    // =====================================================================
    // BASIC FUNCTIONALITY
    // =====================================================================

    #[test]
    fn test_clone_pair_new() {
        let source = create_test_fragment("test1.py", 1, 10, 50, 8, "def foo(): pass");
        let target = create_test_fragment("test2.py", 20, 30, 50, 8, "def bar(): pass");

        let pair = ClonePair::new(CloneType::Type2, source.clone(), target.clone(), 0.95);

        assert_eq!(pair.clone_type, CloneType::Type2);
        assert_eq!(pair.source, source);
        assert_eq!(pair.target, target);
        assert_eq!(pair.similarity, 0.95);
        assert_eq!(pair.metrics.clone_length_tokens, 50);
        assert_eq!(pair.metrics.clone_length_loc, 8);
    }

    #[test]
    fn test_with_metrics() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let metrics = CloneMetrics::new(50, 8, 0.9)
            .with_ast_similarity(0.85)
            .with_edit_distance(5, 100);

        let pair =
            ClonePair::new(CloneType::Type2, source, target, 0.9).with_metrics(metrics.clone());

        assert_eq!(pair.metrics.ast_similarity, Some(0.85));
        assert_eq!(pair.metrics.edit_distance, Some(5));
    }

    #[test]
    fn test_with_detection_info() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let detection = DetectionInfo::new("AST-based".to_string())
            .with_time(150)
            .with_confidence(0.9);

        let pair =
            ClonePair::new(CloneType::Type2, source, target, 0.9).with_detection_info(detection);

        assert_eq!(pair.detection_info.detection_time_ms, Some(150));
        assert_eq!(pair.detection_info.confidence, Some(0.9));
    }

    #[test]
    fn test_add_note() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let pair = ClonePair::new(CloneType::Type1, source, target, 1.0)
            .add_note("High confidence".to_string())
            .add_note("Manually verified".to_string());

        assert_eq!(pair.detection_info.notes.len(), 2);
        assert_eq!(pair.detection_info.notes[0], "High confidence");
    }

    #[test]
    fn test_with_confidence() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let pair = ClonePair::new(CloneType::Type1, source, target, 1.0).with_confidence(0.95);

        assert_eq!(pair.detection_info.confidence, Some(0.95));
    }

    #[test]
    fn test_is_valid() {
        let source = create_test_fragment("test.py", 1, 10, 50, 6, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 6, "code");

        // Type-1: requires similarity = 1.0, tokens >= 50, loc >= 6
        let pair1 = ClonePair::new(CloneType::Type1, source.clone(), target.clone(), 1.0);
        assert!(pair1.is_valid());

        // Type-1 with low similarity (invalid)
        let pair2 = ClonePair::new(CloneType::Type1, source.clone(), target.clone(), 0.9);
        assert!(!pair2.is_valid());

        // Type-3: requires similarity >= 0.7, tokens >= 30, loc >= 4
        let source_small = create_test_fragment("test.py", 1, 5, 30, 4, "code");
        let target_small = create_test_fragment("test.py", 10, 15, 30, 4, "code");
        let pair3 = ClonePair::new(CloneType::Type3, source_small, target_small, 0.75);
        assert!(pair3.is_valid());
    }

    #[test]
    fn test_is_same_file() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target1 = create_test_fragment("test.py", 20, 30, 50, 8, "code");
        let target2 = create_test_fragment("other.py", 20, 30, 50, 8, "code");

        let pair1 = ClonePair::new(CloneType::Type1, source.clone(), target1, 1.0);
        let pair2 = ClonePair::new(CloneType::Type1, source, target2, 1.0);

        assert!(pair1.is_same_file());
        assert!(!pair2.is_same_file());
    }

    #[test]
    fn test_has_overlap() {
        let source = create_test_fragment("test.py", 1, 15, 50, 10, "code");
        let target_overlap = create_test_fragment("test.py", 10, 20, 50, 10, "code");
        let target_no_overlap = create_test_fragment("test.py", 20, 30, 50, 10, "code");

        let pair1 = ClonePair::new(CloneType::Type2, source.clone(), target_overlap, 0.95);
        let pair2 = ClonePair::new(CloneType::Type2, source, target_no_overlap, 0.95);

        assert!(pair1.has_overlap());
        assert!(!pair2.has_overlap());
    }

    #[test]
    fn test_distance_lines() {
        let source = create_test_fragment("test.py", 1, 10, 50, 10, "code");
        let target1 = create_test_fragment("test.py", 20, 30, 50, 10, "code");
        let target2 = create_test_fragment("other.py", 1, 10, 50, 10, "code");

        let pair1 = ClonePair::new(CloneType::Type1, source.clone(), target1, 1.0);
        let pair2 = ClonePair::new(CloneType::Type1, source, target2, 1.0);

        assert_eq!(pair1.distance_lines(), Some(10)); // Lines 20 - 10 = 10
        assert_eq!(pair2.distance_lines(), None); // Different files
    }

    #[test]
    fn test_is_self_clone() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target_same = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target_different = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let pair1 = ClonePair::new(CloneType::Type1, source.clone(), target_same, 1.0);
        let pair2 = ClonePair::new(CloneType::Type1, source, target_different, 1.0);

        assert!(pair1.is_self_clone());
        assert!(!pair2.is_self_clone());
    }

    #[test]
    fn test_id() {
        let source = create_test_fragment("test1.py", 10, 20, 50, 8, "code");
        let target = create_test_fragment("test2.py", 30, 40, 50, 8, "code");

        let pair = ClonePair::new(CloneType::Type1, source, target, 1.0);
        let id = pair.id();

        assert!(id.contains("test1.py:10:20"));
        assert!(id.contains("test2.py:30:40"));
    }

    #[test]
    fn test_normalized_id() {
        let source = create_test_fragment("a.py", 10, 20, 50, 8, "code");
        let target = create_test_fragment("b.py", 30, 40, 50, 8, "code");

        let pair1 = ClonePair::new(CloneType::Type1, source.clone(), target.clone(), 1.0);
        let pair2 = ClonePair::new(CloneType::Type1, target, source, 1.0);

        // Normalized IDs should be identical regardless of order
        assert_eq!(pair1.normalized_id(), pair2.normalized_id());
    }

    #[test]
    fn test_quality_score() {
        let source = create_test_fragment("test.py", 1, 10, 100, 10, "code");
        let target = create_test_fragment("test.py", 20, 30, 100, 10, "code");

        let pair = ClonePair::new(CloneType::Type1, source, target, 0.95).with_confidence(0.9);

        let quality = pair.quality_score();
        assert!(quality > 0.0 && quality <= 1.0);
    }

    #[test]
    fn test_display() {
        let source = create_test_fragment("test1.py", 10, 20, 50, 8, "code");
        let target = create_test_fragment("test2.py", 30, 40, 50, 8, "code");

        let pair = ClonePair::new(CloneType::Type2, source, target, 0.95);
        let display = format!("{}", pair);

        assert!(display.contains("Type-2"));
        assert!(display.contains("95.0%"));
        assert!(display.contains("test1.py:10"));
        assert!(display.contains("test2.py:30"));
    }

    // =====================================================================
    // EDGE CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_confidence_clamping() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        // Over 1.0 should clamp to 1.0
        let pair1 = ClonePair::new(CloneType::Type1, source.clone(), target.clone(), 1.0)
            .with_confidence(1.5);
        assert_eq!(pair1.detection_info.confidence, Some(1.0));

        // Negative should clamp to 0.0
        let pair2 = ClonePair::new(CloneType::Type1, source.clone(), target.clone(), 1.0)
            .with_confidence(-0.5);
        assert_eq!(pair2.detection_info.confidence, Some(0.0));
    }

    #[test]
    fn test_quality_score_edge_cases() {
        let small_source = create_test_fragment("test.py", 1, 2, 10, 2, "x = 1");
        let small_target = create_test_fragment("test.py", 5, 6, 10, 2, "y = 1");

        let pair = ClonePair::new(CloneType::Type1, small_source, small_target, 1.0);
        let quality = pair.quality_score();

        // Small clone should have low quality score
        assert!(quality < 0.5);
    }

    #[test]
    fn test_distance_lines_overlap() {
        let source = create_test_fragment("test.py", 1, 15, 50, 10, "code");
        let target = create_test_fragment("test.py", 10, 25, 50, 10, "code");

        let pair = ClonePair::new(CloneType::Type2, source, target, 0.9);

        // Overlapping should return 0
        assert_eq!(pair.distance_lines(), Some(0));
    }

    #[test]
    fn test_distance_lines_reverse_order() {
        let source = create_test_fragment("test.py", 20, 30, 50, 10, "code");
        let target = create_test_fragment("test.py", 1, 10, 50, 10, "code");

        let pair = ClonePair::new(CloneType::Type2, source, target, 0.9);

        // Distance should be 10 regardless of order
        assert_eq!(pair.distance_lines(), Some(10));
    }

    #[test]
    fn test_is_subset_of() {
        let outer_source = create_test_fragment("test.py", 1, 100, 500, 50, "outer");
        let outer_target = create_test_fragment("test2.py", 1, 100, 500, 50, "outer");
        let inner_source = create_test_fragment("test.py", 20, 40, 100, 10, "inner");
        let inner_target = create_test_fragment("test2.py", 20, 40, 100, 10, "inner");

        let outer_pair = ClonePair::new(CloneType::Type1, outer_source, outer_target, 1.0);
        let inner_pair = ClonePair::new(CloneType::Type1, inner_source, inner_target, 1.0);

        assert!(inner_pair.is_subset_of(&outer_pair));
        assert!(!outer_pair.is_subset_of(&inner_pair));
    }

    #[test]
    fn test_similarity_with() {
        let source1 = create_test_fragment("test.py", 1, 20, 100, 15, "code");
        let target1 = create_test_fragment("test.py", 30, 50, 100, 15, "code");
        let source2 = create_test_fragment("test.py", 10, 25, 100, 12, "code");
        let target2 = create_test_fragment("test.py", 35, 55, 100, 15, "code");

        let pair1 = ClonePair::new(CloneType::Type2, source1, target1, 0.9);
        let pair2 = ClonePair::new(CloneType::Type2, source2, target2, 0.9);

        let similarity = pair1.similarity_with(&pair2);
        assert!(similarity >= 0.0 && similarity <= 1.0);
    }

    // =====================================================================
    // CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_zero_length_clone() {
        let source = create_test_fragment("test.py", 1, 1, 0, 0, "");
        let target = create_test_fragment("test.py", 2, 2, 0, 0, "");

        let pair = ClonePair::new(CloneType::Type1, source, target, 1.0);

        assert!(!pair.is_valid()); // Should not meet thresholds
        assert_eq!(pair.metrics.clone_length_tokens, 0);
    }

    #[test]
    fn test_asymmetric_lengths() {
        let source = create_test_fragment("test.py", 1, 10, 100, 10, "large");
        let target = create_test_fragment("test.py", 20, 25, 50, 5, "small");

        let pair = ClonePair::new(CloneType::Type3, source, target, 0.7);

        // Should use minimum
        assert_eq!(pair.metrics.clone_length_tokens, 50);
        assert_eq!(pair.metrics.clone_length_loc, 5);
    }

    #[test]
    fn test_normalized_id_reflexivity() {
        let source = create_test_fragment("test.py", 10, 20, 50, 8, "code");
        let target = create_test_fragment("test.py", 10, 20, 50, 8, "code"); // Same

        let pair = ClonePair::new(CloneType::Type1, source, target, 1.0);

        // Normalized ID should be consistent with regular ID for reflexive pairs
        assert_eq!(pair.id(), pair.normalized_id());
    }

    #[test]
    fn test_quality_score_no_confidence() {
        let source = create_test_fragment("test.py", 1, 10, 100, 10, "code");
        let target = create_test_fragment("test.py", 20, 30, 100, 10, "code");

        let pair = ClonePair::new(CloneType::Type1, source, target, 1.0);
        // No confidence set - should default to 1.0

        let quality = pair.quality_score();
        assert!(quality > 0.0);
    }

    #[test]
    fn test_serde_json_roundtrip() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let pair = ClonePair::new(CloneType::Type2, source, target, 0.95).with_confidence(0.9);

        let json = serde_json::to_string(&pair).unwrap();
        let deserialized: ClonePair = serde_json::from_str(&json).unwrap();

        assert_eq!(pair.clone_type, deserialized.clone_type);
        assert_eq!(pair.similarity, deserialized.similarity);
    }

    #[test]
    fn test_serde_msgpack_roundtrip() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let pair = ClonePair::new(CloneType::Type1, source, target, 1.0);

        let msgpack = rmp_serde::to_vec(&pair).unwrap();
        let deserialized: ClonePair = rmp_serde::from_slice(&msgpack).unwrap();

        assert_eq!(pair.clone_type, deserialized.clone_type);
    }

    // =====================================================================
    // COMPLEX CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_chain_builders() {
        let source = create_test_fragment("test.py", 1, 10, 50, 8, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 8, "code");

        let pair = ClonePair::new(CloneType::Type2, source, target, 0.95)
            .with_confidence(0.9)
            .add_note("Note 1".to_string())
            .add_note("Note 2".to_string())
            .with_detection_info(DetectionInfo::new("custom".to_string()));

        // Detection info should be overwritten by last call
        assert_eq!(pair.detection_info.algorithm, "custom");
        // But notes from add_note should persist? NO - with_detection_info replaces entire struct
        assert_eq!(pair.detection_info.notes.len(), 0);
    }

    #[test]
    fn test_metrics_builder_chain() {
        let metrics = CloneMetrics::new(100, 10, 0.9)
            .with_ast_similarity(0.85)
            .with_semantic_similarity(0.8)
            .with_edit_distance(10, 100)
            .with_gaps(2, 5);

        assert_eq!(metrics.ast_similarity, Some(0.85));
        assert_eq!(metrics.semantic_similarity, Some(0.8));
        assert_eq!(metrics.edit_distance, Some(10));
        assert_eq!(metrics.gap_count, Some(2));
        assert_eq!(metrics.gap_size, Some(5));
    }

    #[test]
    fn test_detection_info_builder_chain() {
        let info = DetectionInfo::new("algo".to_string())
            .with_time(100)
            .with_confidence(0.95)
            .with_ground_truth(true);

        assert_eq!(info.detection_time_ms, Some(100));
        assert_eq!(info.confidence, Some(0.95));
        assert_eq!(info.is_true_positive, Some(true));
    }

    #[test]
    fn test_edit_distance_normalized() {
        let metrics = CloneMetrics::new(100, 10, 0.9).with_edit_distance(20, 100);

        // Normalized = 1.0 - (20/100) = 0.8
        assert_eq!(metrics.normalized_edit_distance, Some(0.8));
    }

    #[test]
    fn test_edit_distance_normalized_zero_length() {
        let metrics = CloneMetrics::new(0, 0, 0.0).with_edit_distance(5, 0);

        // Division by zero - should not set normalized
        assert_eq!(metrics.normalized_edit_distance, None);
    }

    #[test]
    fn test_is_valid_all_clone_types() {
        let source = create_test_fragment("test.py", 1, 10, 50, 6, "code");
        let target = create_test_fragment("test.py", 20, 30, 50, 6, "code");

        // Type-1: requires 1.0 similarity
        let pair1 = ClonePair::new(CloneType::Type1, source.clone(), target.clone(), 1.0);
        assert!(pair1.is_valid());

        // Type-2: requires 0.95 similarity
        let pair2 = ClonePair::new(CloneType::Type2, source.clone(), target.clone(), 0.95);
        assert!(pair2.is_valid());

        // Type-3: requires 0.7 similarity, lower thresholds
        let small_source = create_test_fragment("test.py", 1, 5, 30, 4, "code");
        let small_target = create_test_fragment("test.py", 10, 15, 30, 4, "code");
        let pair3 = ClonePair::new(CloneType::Type3, small_source, small_target, 0.75);
        assert!(pair3.is_valid());

        // Type-4: requires 0.6 similarity, lowest thresholds
        let tiny_source = create_test_fragment("test.py", 1, 3, 20, 3, "code");
        let tiny_target = create_test_fragment("test.py", 5, 8, 20, 3, "code");
        let pair4 = ClonePair::new(CloneType::Type4, tiny_source, tiny_target, 0.65);
        assert!(pair4.is_valid());
    }

    #[test]
    fn test_quality_score_length_scaling() {
        let tiny_source = create_test_fragment("test.py", 1, 2, 10, 2, "x");
        let tiny_target = create_test_fragment("test.py", 5, 6, 10, 2, "x");

        let large_source = create_test_fragment("test.py", 1, 50, 500, 40, "large");
        let large_target = create_test_fragment("test.py", 60, 110, 500, 40, "large");

        let tiny_pair = ClonePair::new(CloneType::Type1, tiny_source, tiny_target, 1.0);
        let large_pair = ClonePair::new(CloneType::Type1, large_source, large_target, 1.0);

        // Larger clone should have higher quality score
        assert!(large_pair.quality_score() > tiny_pair.quality_score());
    }
}
