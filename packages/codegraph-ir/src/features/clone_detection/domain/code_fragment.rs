//! Code Fragment Representation
//!
//! Represents a fragment of code that can be part of a clone pair.
//! Contains source location, content, and metadata for clone detection.

use crate::shared::models::Span;
use serde::{Deserialize, Serialize};
use std::fmt;

/// A fragment of code that can be analyzed for clones
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CodeFragment {
    /// File path
    pub file_path: String,

    /// Start and end positions in source
    pub span: Span,

    /// Original source code
    pub content: String,

    /// Normalized content (for Type-2 detection)
    ///
    /// Identifiers replaced with placeholders, whitespace normalized
    pub normalized_content: Option<String>,

    /// Hash of original content (for Type-1 detection)
    pub content_hash: Option<String>,

    /// Hash of normalized content (for Type-2 detection)
    pub normalized_hash: Option<String>,

    /// Number of tokens
    pub token_count: usize,

    /// Lines of code (excluding whitespace/comments)
    pub loc: usize,

    /// Node IDs in the IR (for linking to AST/PDG)
    pub node_ids: Vec<String>,

    /// Function/class/method name (if fragment is a function)
    pub enclosing_function: Option<String>,

    /// Additional metadata
    pub metadata: FragmentMetadata,
}

/// Additional metadata for code fragments
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FragmentMetadata {
    /// Language (python, typescript, java, etc.)
    pub language: String,

    /// Complexity metrics
    pub cyclomatic_complexity: Option<usize>,

    /// Number of unique identifiers
    pub unique_identifiers: Option<usize>,

    /// Number of function calls
    pub function_calls: Option<usize>,

    /// Is this fragment a complete function?
    pub is_complete_function: bool,

    /// Is this fragment a class method?
    pub is_method: bool,
}

impl CodeFragment {
    /// Create a new code fragment
    pub fn new(
        file_path: String,
        span: Span,
        content: String,
        token_count: usize,
        loc: usize,
    ) -> Self {
        Self {
            file_path,
            span,
            content,
            normalized_content: None,
            content_hash: None,
            normalized_hash: None,
            token_count,
            loc,
            node_ids: Vec::new(),
            enclosing_function: None,
            metadata: FragmentMetadata {
                language: "unknown".to_string(),
                cyclomatic_complexity: None,
                unique_identifiers: None,
                function_calls: None,
                is_complete_function: false,
                is_method: false,
            },
        }
    }

    /// Create a new fragment with metadata
    pub fn with_metadata(mut self, metadata: FragmentMetadata) -> Self {
        self.metadata = metadata;
        self
    }

    /// Add normalized content and hash
    pub fn with_normalized(mut self, normalized_content: String, normalized_hash: String) -> Self {
        self.normalized_content = Some(normalized_content);
        self.normalized_hash = Some(normalized_hash);
        self
    }

    /// Add content hash (MD5, SHA256, etc.)
    pub fn with_content_hash(mut self, hash: String) -> Self {
        self.content_hash = Some(hash);
        self
    }

    /// Add node IDs for linking to IR
    pub fn with_node_ids(mut self, node_ids: Vec<String>) -> Self {
        self.node_ids = node_ids;
        self
    }

    /// Add enclosing function name
    pub fn with_enclosing_function(mut self, function_name: String) -> Self {
        self.enclosing_function = Some(function_name);
        self
    }

    /// Get file name (without path)
    pub fn file_name(&self) -> &str {
        self.file_path.rsplit('/').next().unwrap_or(&self.file_path)
    }

    /// Get line range (start_line, end_line)
    pub fn line_range(&self) -> (usize, usize) {
        (self.span.start_line as usize, self.span.end_line as usize)
    }

    /// Get number of lines (end - start + 1)
    pub fn num_lines(&self) -> usize {
        (self.span.end_line.saturating_sub(self.span.start_line) + 1) as usize
    }

    /// Check if fragment meets minimum size threshold
    pub fn meets_threshold(&self, min_tokens: usize, min_loc: usize) -> bool {
        self.token_count >= min_tokens && self.loc >= min_loc
    }

    /// Check if fragment overlaps with another fragment
    pub fn overlaps(&self, other: &CodeFragment) -> bool {
        if self.file_path != other.file_path {
            return false;
        }

        // Check line overlap
        let (s1, e1) = self.line_range();
        let (s2, e2) = other.line_range();

        !(e1 < s2 || e2 < s1)
    }

    /// Calculate overlap ratio with another fragment
    ///
    /// Returns: overlap_lines / min(self.lines, other.lines)
    pub fn overlap_ratio(&self, other: &CodeFragment) -> f64 {
        if !self.overlaps(other) {
            return 0.0;
        }

        let (s1, e1) = self.line_range();
        let (s2, e2) = other.line_range();

        let overlap_start = s1.max(s2);
        let overlap_end = e1.min(e2);
        let overlap_lines = (overlap_end - overlap_start + 1) as f64;

        let min_lines = self.num_lines().min(other.num_lines()) as f64;

        overlap_lines / min_lines
    }

    /// Check if fragment is contained within another fragment
    pub fn is_contained_in(&self, other: &CodeFragment) -> bool {
        if self.file_path != other.file_path {
            return false;
        }

        let (s1, e1) = self.line_range();
        let (s2, e2) = other.line_range();

        s1 >= s2 && e1 <= e2
    }

    /// Get a human-readable location string
    pub fn location_string(&self) -> String {
        format!(
            "{}:{}:{}",
            self.file_name(),
            self.span.start_line,
            self.span.start_col
        )
    }

    /// Compute MD5 hash of content
    #[cfg(feature = "md5")]
    pub fn compute_md5_hash(&self) -> String {
        use md5::{Digest, Md5};
        let mut hasher = Md5::new();
        hasher.update(self.content.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    /// Compute SHA256 hash of content
    #[cfg(feature = "sha256")]
    pub fn compute_sha256_hash(&self) -> String {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(self.content.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    /// Compute simple FNV-1a hash (fast, no external deps)
    pub fn compute_fnv1a_hash(&self) -> u64 {
        const FNV_OFFSET_BASIS: u64 = 0xcbf29ce484222325;
        const FNV_PRIME: u64 = 0x100000001b3;

        let mut hash = FNV_OFFSET_BASIS;
        for byte in self.content.as_bytes() {
            hash ^= *byte as u64;
            hash = hash.wrapping_mul(FNV_PRIME);
        }
        hash
    }
}

impl fmt::Display for CodeFragment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "CodeFragment({}, lines {}-{}, {} tokens, {} LOC)",
            self.file_name(),
            self.span.start_line,
            self.span.end_line,
            self.token_count,
            self.loc
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_fragment(
        file: &str,
        start_line: usize,
        end_line: usize,
        tokens: usize,
        loc: usize,
    ) -> CodeFragment {
        CodeFragment::new(
            file.to_string(),
            Span::new(start_line as u32, 0, end_line as u32, 0),
            format!("test content lines {}-{}", start_line, end_line),
            tokens,
            loc,
        )
    }

    // =====================================================================
    // BASIC FUNCTIONALITY
    // =====================================================================

    #[test]
    fn test_code_fragment_new() {
        let fragment = create_test_fragment("test.py", 10, 20, 50, 10);

        assert_eq!(fragment.file_path, "test.py");
        assert_eq!(fragment.span.start_line, 10);
        assert_eq!(fragment.span.end_line, 20);
        assert_eq!(fragment.token_count, 50);
        assert_eq!(fragment.loc, 10);
        assert!(fragment.normalized_content.is_none());
        assert!(fragment.content_hash.is_none());
    }

    #[test]
    fn test_with_metadata() {
        let metadata = FragmentMetadata {
            language: "python".to_string(),
            cyclomatic_complexity: Some(5),
            unique_identifiers: Some(10),
            function_calls: Some(3),
            is_complete_function: true,
            is_method: false,
        };

        let fragment =
            create_test_fragment("test.py", 1, 10, 50, 8).with_metadata(metadata.clone());

        assert_eq!(fragment.metadata.language, "python");
        assert_eq!(fragment.metadata.cyclomatic_complexity, Some(5));
        assert!(fragment.metadata.is_complete_function);
    }

    #[test]
    fn test_with_normalized() {
        let fragment = create_test_fragment("test.py", 1, 5, 20, 4)
            .with_normalized("normalized".to_string(), "hash123".to_string());

        assert_eq!(fragment.normalized_content, Some("normalized".to_string()));
        assert_eq!(fragment.normalized_hash, Some("hash123".to_string()));
    }

    #[test]
    fn test_with_content_hash() {
        let fragment =
            create_test_fragment("test.py", 1, 5, 20, 4).with_content_hash("abc123".to_string());

        assert_eq!(fragment.content_hash, Some("abc123".to_string()));
    }

    #[test]
    fn test_with_node_ids() {
        let node_ids = vec!["node1".to_string(), "node2".to_string()];
        let fragment = create_test_fragment("test.py", 1, 5, 20, 4).with_node_ids(node_ids.clone());

        assert_eq!(fragment.node_ids, node_ids);
    }

    #[test]
    fn test_with_enclosing_function() {
        let fragment = create_test_fragment("test.py", 1, 5, 20, 4)
            .with_enclosing_function("my_function".to_string());

        assert_eq!(fragment.enclosing_function, Some("my_function".to_string()));
    }

    #[test]
    fn test_file_name() {
        let fragment = create_test_fragment("/path/to/test.py", 1, 5, 20, 4);
        assert_eq!(fragment.file_name(), "test.py");

        let fragment2 = create_test_fragment("test.py", 1, 5, 20, 4);
        assert_eq!(fragment2.file_name(), "test.py");
    }

    #[test]
    fn test_line_range() {
        let fragment = create_test_fragment("test.py", 10, 25, 50, 15);
        assert_eq!(fragment.line_range(), (10, 25));
    }

    #[test]
    fn test_num_lines() {
        let fragment = create_test_fragment("test.py", 10, 20, 50, 10);
        assert_eq!(fragment.num_lines(), 11); // 20 - 10 + 1

        let fragment2 = create_test_fragment("test.py", 5, 5, 10, 1);
        assert_eq!(fragment2.num_lines(), 1); // Single line
    }

    #[test]
    fn test_meets_threshold() {
        let fragment = create_test_fragment("test.py", 1, 10, 50, 8);

        assert!(fragment.meets_threshold(40, 5));
        assert!(fragment.meets_threshold(50, 8));
        assert!(!fragment.meets_threshold(60, 8)); // Token threshold not met
        assert!(!fragment.meets_threshold(50, 10)); // LOC threshold not met
    }

    #[test]
    fn test_location_string() {
        let fragment = create_test_fragment("/path/to/test.py", 42, 50, 100, 8);
        assert_eq!(fragment.location_string(), "test.py:42:0");
    }

    #[test]
    fn test_display() {
        let fragment = create_test_fragment("test.py", 10, 20, 50, 8);
        let display = format!("{}", fragment);

        assert!(display.contains("test.py"));
        assert!(display.contains("10-20"));
        assert!(display.contains("50 tokens"));
        assert!(display.contains("8 LOC"));
    }

    // =====================================================================
    // OVERLAP DETECTION
    // =====================================================================

    #[test]
    fn test_overlaps_no_overlap() {
        let frag1 = create_test_fragment("test.py", 1, 10, 50, 10);
        let frag2 = create_test_fragment("test.py", 15, 25, 50, 10);

        assert!(!frag1.overlaps(&frag2));
        assert!(!frag2.overlaps(&frag1));
    }

    #[test]
    fn test_overlaps_partial() {
        let frag1 = create_test_fragment("test.py", 1, 15, 50, 10);
        let frag2 = create_test_fragment("test.py", 10, 20, 50, 10);

        assert!(frag1.overlaps(&frag2));
        assert!(frag2.overlaps(&frag1));
    }

    #[test]
    fn test_overlaps_complete_overlap() {
        let frag1 = create_test_fragment("test.py", 5, 20, 50, 10);
        let frag2 = create_test_fragment("test.py", 10, 15, 30, 5);

        assert!(frag1.overlaps(&frag2));
        assert!(frag2.overlaps(&frag1));
    }

    #[test]
    fn test_overlaps_different_files() {
        let frag1 = create_test_fragment("test1.py", 1, 10, 50, 10);
        let frag2 = create_test_fragment("test2.py", 5, 15, 50, 10);

        assert!(!frag1.overlaps(&frag2));
    }

    #[test]
    fn test_overlaps_exact_same() {
        let frag1 = create_test_fragment("test.py", 10, 20, 50, 10);
        let frag2 = create_test_fragment("test.py", 10, 20, 50, 10);

        assert!(frag1.overlaps(&frag2));
    }

    #[test]
    fn test_overlap_ratio_no_overlap() {
        let frag1 = create_test_fragment("test.py", 1, 10, 50, 10);
        let frag2 = create_test_fragment("test.py", 20, 30, 50, 10);

        assert_eq!(frag1.overlap_ratio(&frag2), 0.0);
    }

    #[test]
    fn test_overlap_ratio_partial() {
        let frag1 = create_test_fragment("test.py", 1, 10, 50, 10);
        let frag2 = create_test_fragment("test.py", 5, 15, 50, 10);

        // Overlap: lines 5-10 (6 lines)
        // Min lines: 10
        // Ratio: 6/10 = 0.6
        assert_eq!(frag1.overlap_ratio(&frag2), 0.6);
    }

    #[test]
    fn test_overlap_ratio_complete() {
        let frag1 = create_test_fragment("test.py", 1, 20, 100, 20);
        let frag2 = create_test_fragment("test.py", 5, 10, 30, 5);

        // Overlap: lines 5-10 (6 lines)
        // Min lines: 6 (frag2)
        // Ratio: 6/6 = 1.0
        assert_eq!(frag2.overlap_ratio(&frag1), 1.0);
    }

    #[test]
    fn test_is_contained_in() {
        let outer = create_test_fragment("test.py", 1, 100, 500, 50);
        let inner = create_test_fragment("test.py", 20, 40, 100, 10);

        assert!(inner.is_contained_in(&outer));
        assert!(!outer.is_contained_in(&inner));
    }

    #[test]
    fn test_is_contained_in_exact() {
        let frag1 = create_test_fragment("test.py", 10, 20, 50, 10);
        let frag2 = create_test_fragment("test.py", 10, 20, 50, 10);

        assert!(frag1.is_contained_in(&frag2));
    }

    #[test]
    fn test_is_contained_in_different_files() {
        let frag1 = create_test_fragment("test1.py", 10, 20, 50, 10);
        let frag2 = create_test_fragment("test2.py", 5, 30, 100, 20);

        assert!(!frag1.is_contained_in(&frag2));
    }

    // =====================================================================
    // HASHING
    // =====================================================================

    #[test]
    fn test_fnv1a_hash() {
        let frag1 = CodeFragment::new(
            "test.py".to_string(),
            Span::new(1, 0, 5, 0),
            "hello world".to_string(),
            5,
            1,
        );

        let frag2 = CodeFragment::new(
            "test.py".to_string(),
            Span::new(1, 0, 5, 0),
            "hello world".to_string(),
            5,
            1,
        );

        let frag3 = CodeFragment::new(
            "test.py".to_string(),
            Span::new(1, 0, 5, 0),
            "different content".to_string(),
            5,
            1,
        );

        assert_eq!(frag1.compute_fnv1a_hash(), frag2.compute_fnv1a_hash());
        assert_ne!(frag1.compute_fnv1a_hash(), frag3.compute_fnv1a_hash());
    }

    #[test]
    fn test_fnv1a_hash_empty() {
        let frag = CodeFragment::new(
            "test.py".to_string(),
            Span::new(1, 0, 1, 0),
            "".to_string(),
            0,
            0,
        );

        // Empty string should give FNV offset basis
        assert_eq!(frag.compute_fnv1a_hash(), 0xcbf29ce484222325);
    }

    // =====================================================================
    // SERIALIZATION
    // =====================================================================

    #[test]
    fn test_serde_json_roundtrip() {
        let fragment = create_test_fragment("test.py", 1, 10, 50, 8)
            .with_content_hash("abc123".to_string())
            .with_enclosing_function("foo".to_string());

        let json = serde_json::to_string(&fragment).unwrap();
        let deserialized: CodeFragment = serde_json::from_str(&json).unwrap();

        assert_eq!(fragment.file_path, deserialized.file_path);
        assert_eq!(fragment.span, deserialized.span);
        assert_eq!(fragment.token_count, deserialized.token_count);
        assert_eq!(fragment.content_hash, deserialized.content_hash);
    }

    #[test]
    fn test_serde_msgpack_roundtrip() {
        let fragment = create_test_fragment("test.py", 1, 10, 50, 8);

        let msgpack = rmp_serde::to_vec(&fragment).unwrap();
        let deserialized: CodeFragment = rmp_serde::from_slice(&msgpack).unwrap();

        assert_eq!(fragment, deserialized);
    }

    // =====================================================================
    // EDGE CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_zero_length_fragment() {
        let fragment = create_test_fragment("test.py", 5, 5, 0, 0);
        assert_eq!(fragment.num_lines(), 1);
        assert!(!fragment.meets_threshold(1, 1));
    }

    #[test]
    fn test_negative_line_range_saturating() {
        // If end_line < start_line (invalid), saturating_sub should give 0
        let fragment = CodeFragment::new(
            "test.py".to_string(),
            Span::new(10, 0, 5, 0), // Invalid: end < start
            "invalid".to_string(),
            0,
            0,
        );

        // saturating_sub(10, 5) = 0, then + 1 = 1
        assert_eq!(fragment.num_lines(), 1);
    }

    #[test]
    fn test_overlap_boundary_adjacent() {
        let frag1 = create_test_fragment("test.py", 1, 10, 50, 10);
        let frag2 = create_test_fragment("test.py", 11, 20, 50, 10);

        // Adjacent, not overlapping
        assert!(!frag1.overlaps(&frag2));
    }

    #[test]
    fn test_overlap_boundary_touching() {
        let frag1 = create_test_fragment("test.py", 1, 10, 50, 10);
        let frag2 = create_test_fragment("test.py", 10, 20, 50, 10);

        // Line 10 is shared
        assert!(frag1.overlaps(&frag2));
    }

    #[test]
    fn test_fnv1a_hash_collision_resistance() {
        // Different strings should give different hashes (very unlikely collision)
        let frag1 = CodeFragment::new(
            "test.py".to_string(),
            Span::new(1, 0, 1, 0),
            "a".to_string(),
            1,
            1,
        );
        let frag2 = CodeFragment::new(
            "test.py".to_string(),
            Span::new(1, 0, 1, 0),
            "b".to_string(),
            1,
            1,
        );

        assert_ne!(frag1.compute_fnv1a_hash(), frag2.compute_fnv1a_hash());
    }

    #[test]
    fn test_file_name_edge_cases() {
        // No path separator
        let frag1 = create_test_fragment("test.py", 1, 5, 10, 2);
        assert_eq!(frag1.file_name(), "test.py");

        // Multiple separators
        let frag2 = create_test_fragment("/a/b/c/test.py", 1, 5, 10, 2);
        assert_eq!(frag2.file_name(), "test.py");

        // Trailing separator
        let frag3 = create_test_fragment("/path/to/", 1, 5, 10, 2);
        assert_eq!(frag3.file_name(), "");
    }

    // =====================================================================
    // CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_large_line_numbers() {
        let fragment = create_test_fragment("test.py", 1_000_000, 2_000_000, 50_000, 100_000);

        assert_eq!(fragment.num_lines(), 1_000_001);
        assert_eq!(fragment.line_range(), (1_000_000, 2_000_000));
    }

    #[test]
    fn test_meets_threshold_boundary() {
        let fragment = create_test_fragment("test.py", 1, 10, 50, 6);

        // Exact threshold
        assert!(fragment.meets_threshold(50, 6));

        // Just below threshold
        assert!(!fragment.meets_threshold(51, 6));
        assert!(!fragment.meets_threshold(50, 7));
    }

    #[test]
    fn test_overlap_ratio_symmetry() {
        let frag1 = create_test_fragment("test.py", 1, 20, 100, 20);
        let frag2 = create_test_fragment("test.py", 10, 15, 50, 5);

        // Overlap ratio may not be symmetric (uses min of both sizes)
        let ratio1 = frag1.overlap_ratio(&frag2);
        let ratio2 = frag2.overlap_ratio(&frag1);

        // Both should be >= 0 and <= 1
        assert!(ratio1 >= 0.0 && ratio1 <= 1.0);
        assert!(ratio2 >= 0.0 && ratio2 <= 1.0);
    }

    #[test]
    fn test_chained_builders() {
        let fragment = create_test_fragment("test.py", 1, 10, 50, 8)
            .with_content_hash("hash1".to_string())
            .with_normalized("norm".to_string(), "hash2".to_string())
            .with_node_ids(vec!["n1".to_string()])
            .with_enclosing_function("func".to_string());

        assert_eq!(fragment.content_hash, Some("hash1".to_string()));
        assert_eq!(fragment.normalized_hash, Some("hash2".to_string()));
        assert_eq!(fragment.node_ids.len(), 1);
        assert_eq!(fragment.enclosing_function, Some("func".to_string()));
    }

    #[test]
    fn test_metadata_defaults() {
        let fragment = create_test_fragment("test.py", 1, 5, 20, 4);

        assert_eq!(fragment.metadata.language, "unknown");
        assert_eq!(fragment.metadata.cyclomatic_complexity, None);
        assert!(!fragment.metadata.is_complete_function);
        assert!(!fragment.metadata.is_method);
    }

    // =====================================================================
    // COMPLEX CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_multiple_overlaps() {
        let base = create_test_fragment("test.py", 1, 100, 500, 50);
        let frags = vec![
            create_test_fragment("test.py", 10, 30, 100, 10),
            create_test_fragment("test.py", 25, 50, 150, 15),
            create_test_fragment("test.py", 45, 70, 200, 20),
        ];

        // All should overlap with base
        for frag in &frags {
            assert!(frag.overlaps(&base));
            assert!(base.overlaps(frag));
        }

        // Some should overlap with each other
        assert!(frags[0].overlaps(&frags[1])); // 10-30 overlaps 25-50
        assert!(frags[1].overlaps(&frags[2])); // 25-50 overlaps 45-70
        assert!(!frags[0].overlaps(&frags[2])); // 10-30 doesn't overlap 45-70
    }

    #[test]
    fn test_containment_transitivity() {
        let outer = create_test_fragment("test.py", 1, 100, 500, 50);
        let middle = create_test_fragment("test.py", 20, 80, 300, 30);
        let inner = create_test_fragment("test.py", 40, 60, 100, 10);

        assert!(inner.is_contained_in(&middle));
        assert!(middle.is_contained_in(&outer));
        assert!(inner.is_contained_in(&outer)); // Transitivity
    }

    #[test]
    fn test_fnv1a_hash_consistency() {
        let content = "def foo():\n    return 42\n";
        let frag = CodeFragment::new(
            "test.py".to_string(),
            Span::new(1, 0, 2, 0),
            content.to_string(),
            5,
            2,
        );

        let hash1 = frag.compute_fnv1a_hash();
        let hash2 = frag.compute_fnv1a_hash();

        assert_eq!(hash1, hash2); // Deterministic
    }

    #[test]
    fn test_location_string_consistency() {
        let fragment = create_test_fragment("/very/long/path/to/file.py", 123, 456, 100, 50);
        let loc_str = fragment.location_string();

        assert!(loc_str.contains("file.py"));
        assert!(loc_str.contains("123"));
        assert!(!loc_str.contains("/very/long/path"));
    }
}
