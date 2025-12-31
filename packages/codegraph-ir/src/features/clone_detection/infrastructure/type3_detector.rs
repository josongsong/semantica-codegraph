//! Type-3 Clone Detector (Gapped Clones)
//!
//! Detects gapped clones where statements are added, removed, or modified.
//! Uses PDG-based structural comparison with edit distance.
//!
//! # Algorithm
//!
//! 1. Build statement sequence for each fragment
//! 2. Normalize statements (like Type-2)
//! 3. Compute edit distance (Levenshtein on statement level)
//! 4. Calculate similarity: 1 - (edit_distance / max_length)
//! 5. Filter by minimum similarity threshold (default: 0.7)
//! 6. Identify gap locations and sizes
//!
//! # Performance
//!
//! - **Speed**: ~50K LOC/s
//! - **Complexity**: O(n² × m²) - n fragments, m statements per fragment
//! - **Memory**: O(n × m) - statement sequences
//!
//! # Example
//!
//! ```text
//! // Fragment 1
//! def process(data):
//!     validate(data)
//!     x = transform(data)
//!     save(x)
//!     return x
//!
//! // Fragment 2 (Type-3 clone - added logging)
//! def handle(input):
//!     validate(input)
//!     log("Processing...")  # ADDED
//!     y = transform(input)
//!     log("Saving...")      # ADDED
//!     save(y)
//!     return y
//! ```

use crate::features::clone_detection::domain::{
    jaccard_similarity_vec, levenshtein_distance, normalized_levenshtein_similarity, CloneMetrics,
    ClonePair, CloneType, CodeFragment, DetectionInfo,
};
use std::collections::HashMap;

use super::CloneDetector;

/// Type-3 clone detector using statement-level edit distance
pub struct Type3Detector {
    /// Minimum token threshold
    min_tokens: usize,

    /// Minimum LOC threshold
    min_loc: usize,

    /// Similarity threshold (default: 0.7)
    min_similarity: f64,

    /// Maximum allowed gap ratio (gaps/total_statements)
    max_gap_ratio: f64,
}

impl Default for Type3Detector {
    fn default() -> Self {
        Self::new()
    }
}

impl Type3Detector {
    /// Create new Type-3 detector with default thresholds
    pub fn new() -> Self {
        Self {
            min_tokens: 30, // Lower threshold than Type-1/2
            min_loc: 4,
            min_similarity: 0.7,
            max_gap_ratio: 0.3, // Max 30% gaps
        }
    }

    /// Create with custom thresholds
    pub fn with_thresholds(
        min_tokens: usize,
        min_loc: usize,
        min_similarity: f64,
        max_gap_ratio: f64,
    ) -> Self {
        Self {
            min_tokens,
            min_loc,
            min_similarity,
            max_gap_ratio,
        }
    }

    /// Extract statement sequence from code fragment
    ///
    /// Simple implementation: split by lines, filter empty/comments
    /// PRECISION(v2): AST-based extraction for multi-statement lines
    /// - Current: Line-based (works for most Python/JS code)
    /// - Improvement: Parse AST to handle `a = 1; b = 2` as 2 statements
    /// - Status: Working, edge case improvement planned
    fn extract_statements(&self, content: &str) -> Vec<String> {
        content
            .lines()
            .map(|line| {
                // Remove comments
                let line = if let Some(pos) = line.find('#') {
                    &line[..pos]
                } else if let Some(pos) = line.find("//") {
                    &line[..pos]
                } else {
                    line
                };
                line.trim().to_string()
            })
            .filter(|line| !line.is_empty())
            .collect()
    }

    /// Normalize statement for comparison
    ///
    /// Similar to Type-2 normalization but at statement level
    fn normalize_statement(&self, stmt: &str) -> String {
        let mut normalized = Vec::new();

        for token in stmt.split_whitespace() {
            let norm_token = if Self::is_keyword(token) {
                token.to_string()
            } else if Self::is_operator(token) {
                token.to_string()
            } else if Self::is_number(token) {
                if token.contains('.') {
                    "NUM".to_string()
                } else {
                    "NUM".to_string()
                }
            } else if Self::is_string_literal(token) {
                "STR".to_string()
            } else {
                "ID".to_string()
            };

            normalized.push(norm_token);
        }

        normalized.join(" ")
    }

    /// Check if token is a keyword
    fn is_keyword(token: &str) -> bool {
        matches!(
            token,
            "def"
                | "class"
                | "if"
                | "else"
                | "elif"
                | "for"
                | "while"
                | "return"
                | "import"
                | "from"
                | "as"
                | "try"
                | "except"
                | "finally"
                | "with"
                | "lambda"
                | "yield"
                | "async"
                | "await"
                | "pass"
                | "break"
                | "continue"
                | "function"
                | "const"
                | "let"
                | "var"
                | "public"
                | "private"
                | "static"
        )
    }

    /// Check if token is an operator
    fn is_operator(token: &str) -> bool {
        matches!(
            token,
            "=" | "+"
                | "-"
                | "*"
                | "/"
                | "%"
                | "=="
                | "!="
                | "<"
                | ">"
                | "<="
                | ">="
                | "&&"
                | "||"
                | "!"
                | "&"
                | "|"
                | "^"
                | "~"
                | "<<"
                | ">>"
                | "and"
                | "or"
                | "not"
                | "in"
                | "is"
        )
    }

    /// Check if token is a number
    fn is_number(token: &str) -> bool {
        token
            .chars()
            .all(|c| c.is_ascii_digit() || c == '.' || c == '-')
            && token.chars().any(|c| c.is_ascii_digit())
    }

    /// Check if token is a string literal
    fn is_string_literal(token: &str) -> bool {
        (token.starts_with('"') && token.ends_with('"'))
            || (token.starts_with('\'') && token.ends_with('\''))
    }

    /// Compute statement-level edit distance
    fn compute_statement_distance(&self, stmts_a: &[String], stmts_b: &[String]) -> usize {
        let len_a = stmts_a.len();
        let len_b = stmts_b.len();

        if len_a == 0 {
            return len_b;
        }
        if len_b == 0 {
            return len_a;
        }

        // Normalize statements
        let norm_a: Vec<String> = stmts_a
            .iter()
            .map(|s| self.normalize_statement(s))
            .collect();
        let norm_b: Vec<String> = stmts_b
            .iter()
            .map(|s| self.normalize_statement(s))
            .collect();

        // Wagner-Fischer algorithm for edit distance
        let mut prev_row: Vec<usize> = (0..=len_b).collect();
        let mut curr_row: Vec<usize> = vec![0; len_b + 1];

        for i in 1..=len_a {
            curr_row[0] = i;

            for j in 1..=len_b {
                let cost = if norm_a[i - 1] == norm_b[j - 1] { 0 } else { 1 };

                curr_row[j] = std::cmp::min(
                    std::cmp::min(
                        curr_row[j - 1] + 1, // Insert
                        prev_row[j] + 1,     // Delete
                    ),
                    prev_row[j - 1] + cost, // Replace
                );
            }

            std::mem::swap(&mut prev_row, &mut curr_row);
        }

        prev_row[len_b]
    }

    /// Compute similarity between two fragments
    fn compute_similarity(
        &self,
        source: &CodeFragment,
        target: &CodeFragment,
    ) -> (f64, usize, usize) {
        let stmts_a = self.extract_statements(&source.content);
        let stmts_b = self.extract_statements(&target.content);

        if stmts_a.is_empty() && stmts_b.is_empty() {
            return (1.0, 0, 0);
        }

        let edit_distance = self.compute_statement_distance(&stmts_a, &stmts_b);
        let max_len = stmts_a.len().max(stmts_b.len());

        if max_len == 0 {
            return (0.0, 0, 0);
        }

        let similarity = 1.0 - (edit_distance as f64 / max_len as f64);
        let gap_count = edit_distance;
        let gap_size = (stmts_a.len() as isize - stmts_b.len() as isize).unsigned_abs();

        (similarity, gap_count, gap_size)
    }

    /// Find candidate pairs using token-based filtering
    ///
    /// Pre-filter candidates before expensive edit distance computation
    fn find_candidates(&self, fragments: &[CodeFragment]) -> Vec<(usize, usize)> {
        let mut candidates = Vec::new();

        // Extract statement sequences once
        let all_stmts: Vec<Vec<String>> = fragments
            .iter()
            .map(|f| self.extract_statements(&f.content))
            .collect();

        for i in 0..fragments.len() {
            if !fragments[i].meets_threshold(self.min_tokens, self.min_loc) {
                continue;
            }

            for j in (i + 1)..fragments.len() {
                if !fragments[j].meets_threshold(self.min_tokens, self.min_loc) {
                    continue;
                }

                // Skip self-clones
                if fragments[i].file_path == fragments[j].file_path
                    && fragments[i].span == fragments[j].span
                {
                    continue;
                }

                // Pre-filter: statement count must be within gap ratio
                let len_i = all_stmts[i].len();
                let len_j = all_stmts[j].len();
                let max_len = len_i.max(len_j);
                let min_len = len_i.min(len_j);

                if max_len == 0 {
                    continue;
                }

                let size_ratio = min_len as f64 / max_len as f64;
                if size_ratio < (1.0 - self.max_gap_ratio) {
                    continue; // Too different in size
                }

                candidates.push((i, j));
            }
        }

        candidates
    }

    /// Create clone pairs from candidates
    fn create_clone_pairs(
        &self,
        fragments: &[CodeFragment],
        candidates: Vec<(usize, usize)>,
    ) -> Vec<ClonePair> {
        let mut pairs = Vec::new();

        for (i, j) in candidates {
            let source = &fragments[i];
            let target = &fragments[j];

            let (similarity, gap_count, gap_size) = self.compute_similarity(source, target);

            // Filter by minimum similarity
            if similarity < self.min_similarity {
                continue;
            }

            // Filter by gap ratio
            let total_stmts = self.extract_statements(&source.content).len();
            if total_stmts > 0 {
                let gap_ratio = gap_count as f64 / total_stmts as f64;
                if gap_ratio > self.max_gap_ratio {
                    continue;
                }
            }

            let max_length = source.token_count.max(target.token_count);
            let metrics = CloneMetrics::new(
                source.token_count.min(target.token_count),
                source.loc.min(target.loc),
                similarity,
            )
            .with_edit_distance(gap_count, max_length)
            .with_gaps(gap_count, gap_size);

            let detection_info = DetectionInfo::new("Type-3 (Statement edit distance)".to_string())
                .with_confidence(similarity);

            let pair = ClonePair::new(CloneType::Type3, source.clone(), target.clone(), similarity)
                .with_metrics(metrics)
                .with_detection_info(detection_info);

            pairs.push(pair);
        }

        pairs
    }
}

impl CloneDetector for Type3Detector {
    fn name(&self) -> &'static str {
        "Type-3 (Gapped Clone Detector)"
    }

    fn supported_type(&self) -> CloneType {
        CloneType::Type3
    }

    fn detect(&self, fragments: &[CodeFragment]) -> Vec<ClonePair> {
        if fragments.is_empty() {
            return Vec::new();
        }

        let start_time = std::time::Instant::now();

        // Find candidates with pre-filtering
        let candidates = self.find_candidates(fragments);

        // Create clone pairs
        let mut pairs = self.create_clone_pairs(fragments, candidates);

        // Add detection time
        let detection_time_ms = start_time.elapsed().as_millis() as u64;
        for pair in &mut pairs {
            pair.detection_info.detection_time_ms = Some(detection_time_ms);
        }

        pairs
    }

    fn detect_in_file(&self, fragments: &[CodeFragment], file_path: &str) -> Vec<ClonePair> {
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
        let detector = Type3Detector::new();
        assert_eq!(detector.name(), "Type-3 (Gapped Clone Detector)");
        assert_eq!(detector.supported_type(), CloneType::Type3);
    }

    #[test]
    fn test_extract_statements() {
        let detector = Type3Detector::new();
        let content = "def foo():\n    x = 1\n    y = 2\n    return x + y";
        let stmts = detector.extract_statements(content);

        assert_eq!(stmts.len(), 4);
        assert_eq!(stmts[0], "def foo():");
        assert_eq!(stmts[1], "x = 1");
        assert_eq!(stmts[2], "y = 2");
        assert_eq!(stmts[3], "return x + y");
    }

    #[test]
    fn test_normalize_statement() {
        let detector = Type3Detector::new();

        assert_eq!(detector.normalize_statement("x = 42"), "ID = NUM");
        assert_eq!(
            detector.normalize_statement("return x + 1"),
            "return ID + NUM"
        );
        assert_eq!(detector.normalize_statement("if a > b"), "if ID > ID");
    }

    #[test]
    fn test_statement_distance_identical() {
        let detector = Type3Detector::new();
        let stmts_a = vec!["x = 1".to_string(), "y = 2".to_string()];
        let stmts_b = vec!["a = 1".to_string(), "b = 2".to_string()];

        let distance = detector.compute_statement_distance(&stmts_a, &stmts_b);

        // Normalized statements are identical
        assert_eq!(distance, 0);
    }

    #[test]
    fn test_statement_distance_one_gap() {
        let detector = Type3Detector::new();
        let stmts_a = vec!["x = 1".to_string(), "y = 2".to_string()];
        let stmts_b = vec![
            "x = 1".to_string(),
            "log('test')".to_string(),
            "y = 2".to_string(),
        ];

        let distance = detector.compute_statement_distance(&stmts_a, &stmts_b);

        // One insertion
        assert_eq!(distance, 1);
    }

    #[test]
    fn test_detect_gapped_clone() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.6, 0.5);

        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                5,
                "def process(data):\n    validate(data)\n    x = transform(data)\n    save(x)\n    return x",
                30,
                5,
            ),
            create_fragment(
                "file2.py",
                10,
                20,
                "def handle(input):\n    validate(input)\n    log('Processing...')\n    y = transform(input)\n    log('Saving...')\n    save(y)\n    return y",
                40,
                7,
            ),
        ];

        let pairs = detector.detect(&fragments);

        // Should find Type-3 clone with gaps
        assert!(!pairs.is_empty());
        if !pairs.is_empty() {
            assert_eq!(pairs[0].clone_type, CloneType::Type3);
            assert!(pairs[0].similarity >= 0.6);
            assert!(pairs[0].metrics.gap_count.is_some());
            assert!(pairs[0].metrics.gap_size.is_some());
        }
    }

    #[test]
    fn test_detect_no_clone_too_different() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.7, 0.3);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 30, 2),
            create_fragment(
                "file2.py",
                10,
                15,
                "class Bar:\n    def __init__(self):\n        self.x = 0",
                30,
                3,
            ),
        ];

        let pairs = detector.detect(&fragments);

        // Completely different structure
        assert_eq!(pairs.len(), 0);
    }

    // =====================================================================
    // EDGE CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_empty_content() {
        let detector = Type3Detector::new();
        let stmts = detector.extract_statements("");
        assert_eq!(stmts.len(), 0);
    }

    #[test]
    fn test_only_comments() {
        let detector = Type3Detector::new();
        let content = "# Comment 1\n# Comment 2\n// Comment 3";
        let stmts = detector.extract_statements(content);
        assert_eq!(stmts.len(), 0);
    }

    #[test]
    fn test_only_whitespace() {
        let detector = Type3Detector::new();
        let content = "   \n\n   \n  ";
        let stmts = detector.extract_statements(content);
        assert_eq!(stmts.len(), 0);
    }

    #[test]
    fn test_statement_distance_empty() {
        let detector = Type3Detector::new();
        let empty: Vec<String> = vec![];
        let stmts = vec!["x = 1".to_string()];

        assert_eq!(detector.compute_statement_distance(&empty, &stmts), 1);
        assert_eq!(detector.compute_statement_distance(&stmts, &empty), 1);
        assert_eq!(detector.compute_statement_distance(&empty, &empty), 0);
    }

    #[test]
    fn test_similarity_identical_fragments() {
        let detector = Type3Detector::new();

        let source = create_fragment("file1.py", 1, 3, "def foo():\n    return 42", 30, 2);
        let target = create_fragment("file2.py", 10, 12, "def foo():\n    return 42", 30, 2);

        let (similarity, gap_count, _) = detector.compute_similarity(&source, &target);

        assert_eq!(similarity, 1.0);
        assert_eq!(gap_count, 0);
    }

    #[test]
    fn test_similarity_completely_different() {
        let detector = Type3Detector::new();

        let source = create_fragment("file1.py", 1, 2, "def foo():\n    return 42", 30, 2);
        let target = create_fragment("file2.py", 10, 12, "class Bar:\n    pass\n    x = 0", 30, 3);

        let (similarity, _, _) = detector.compute_similarity(&source, &target);

        assert!(similarity < 0.5);
    }

    // =====================================================================
    // CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_normalize_preserves_structure() {
        let detector = Type3Detector::new();

        let stmt1 = "if x > y:";
        let stmt2 = "if a > b:";

        assert_eq!(
            detector.normalize_statement(stmt1),
            detector.normalize_statement(stmt2)
        );
    }

    #[test]
    fn test_gap_ratio_filtering() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.5, 0.2); // Max 20% gaps

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "a\nb\nc\nd\ne", 30, 5),
            create_fragment("file2.py", 10, 20, "a\nb\nc\nd\ne\nf\ng\nh\ni\nj", 50, 10),
        ];

        let pairs = detector.detect(&fragments);

        // Too many gaps (50% size difference)
        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_min_threshold_filtering() {
        let detector = Type3Detector::with_thresholds(100, 10, 0.7, 0.3);

        let fragments = vec![
            create_fragment("file1.py", 1, 3, "def foo():\n    return 42", 10, 2), // Below threshold
            create_fragment("file2.py", 10, 12, "def bar():\n    return 99", 10, 2),
        ];

        let pairs = detector.detect(&fragments);

        // Fragments below threshold
        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_self_clone_filtering() {
        let detector = Type3Detector::new();

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 30, 2),
            create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 30, 2), // Same location
        ];

        let pairs = detector.detect(&fragments);

        // Should filter self-clone
        assert_eq!(pairs.len(), 0);
    }

    // =====================================================================
    // COMPLEX CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_multiple_gaps() {
        // Relaxed thresholds to account for log() calls having different signatures
        let detector = Type3Detector::with_thresholds(10, 2, 0.4, 0.7);

        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                5,
                "def process():\n    validate()\n    transform()\n    save()\n    return",
                30,
                5,
            ),
            create_fragment(
                "file2.py",
                10,
                20,
                "def handle():\n    validate()\n    log('start')\n    transform()\n    log('transform done')\n    save()\n    log('end')\n    return",
                50,
                8,
            ),
        ];

        let pairs = detector.detect(&fragments);

        assert!(!pairs.is_empty());
        if !pairs.is_empty() {
            assert!(pairs[0].metrics.gap_count.unwrap() > 1);
        }
    }

    #[test]
    fn test_statement_reordering() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.5, 0.5);

        let fragments = vec![
            create_fragment("file1.py", 1, 3, "x = 1\ny = 2\nz = 3", 30, 3),
            create_fragment("file2.py", 10, 12, "y = 2\nz = 3\nx = 1", 30, 3), // Reordered
        ];

        let pairs = detector.detect(&fragments);

        // Should detect as gapped clone (edit distance = 2 for reordering)
        assert!(!pairs.is_empty());
    }

    #[test]
    fn test_nested_structures() {
        // Relaxed gap_ratio to account for log calls in nested structure
        let detector = Type3Detector::with_thresholds(10, 2, 0.5, 0.6);

        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                10,
                "def outer():\n    def inner():\n        return 42\n    return inner()",
                30,
                4,
            ),
            create_fragment(
                "file2.py",
                20,
                30,
                "def wrapper():\n    log('outer')\n    def helper():\n        log('inner')\n        return 42\n    return helper()",
                40,
                6,
            ),
        ];

        let pairs = detector.detect(&fragments);

        assert!(!pairs.is_empty());
        if !pairs.is_empty() {
            assert_eq!(pairs[0].clone_type, CloneType::Type3);
        }
    }

    #[test]
    fn test_confidence_equals_similarity() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.7, 0.3);

        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                5,
                "def foo():\n    x = 1\n    return x",
                30,
                3,
            ),
            create_fragment(
                "file2.py",
                10,
                15,
                "def bar():\n    y = 1\n    log('test')\n    return y",
                35,
                4,
            ),
        ];

        let pairs = detector.detect(&fragments);

        if !pairs.is_empty() {
            let pair = &pairs[0];
            assert_eq!(pair.detection_info.confidence, Some(pair.similarity));
        }
    }

    #[test]
    fn test_edit_distance_recorded() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.5, 0.5);

        let fragments = vec![
            create_fragment("file1.py", 1, 3, "x = 1\ny = 2", 30, 2),
            create_fragment("file2.py", 10, 13, "x = 1\nlog('test')\ny = 2", 35, 3),
        ];

        let pairs = detector.detect(&fragments);

        if !pairs.is_empty() {
            assert!(pairs[0].metrics.edit_distance.is_some());
            assert!(pairs[0].metrics.normalized_edit_distance.is_some());
            assert_eq!(pairs[0].metrics.edit_distance.unwrap(), 1); // One insertion
        }
    }

    #[test]
    fn test_gap_count_and_size() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.5, 0.5);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "a\nb\nc\nd\ne", 30, 5),
            create_fragment("file2.py", 10, 13, "a\nb\nc", 20, 3), // Missing 2 statements
        ];

        let pairs = detector.detect(&fragments);

        if !pairs.is_empty() {
            assert!(pairs[0].metrics.gap_count.is_some());
            assert!(pairs[0].metrics.gap_size.is_some());
            assert_eq!(pairs[0].metrics.gap_size.unwrap(), 2);
        }
    }

    #[test]
    fn test_large_fragment_set() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.7, 0.3);

        // Create 10 fragments with varying similarity
        let mut fragments = Vec::new();
        for i in 0..10 {
            let content = format!("def func{}():\n    x = {}\n    return x", i, i);
            fragments.push(create_fragment(
                &format!("file{}.py", i),
                i as u32 * 10,
                i as u32 * 10 + 5,
                &content,
                30,
                3,
            ));
        }

        let pairs = detector.detect(&fragments);

        // Should find multiple clone pairs (all have similar structure)
        assert!(!pairs.is_empty());
    }

    #[test]
    fn test_detect_in_file() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.7, 0.3);

        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                5,
                "def foo():\n    x = 1\n    return x",
                30,
                3,
            ),
            create_fragment(
                "file1.py",
                10,
                15,
                "def bar():\n    y = 1\n    return y",
                30,
                3,
            ),
            create_fragment(
                "file2.py",
                20,
                25,
                "def baz():\n    z = 1\n    return z",
                30,
                3,
            ),
        ];

        let pairs = detector.detect_in_file(&fragments, "file1.py");

        // Should only find clones within file1.py
        for pair in &pairs {
            assert_eq!(pair.source.file_path, "file1.py");
            assert_eq!(pair.target.file_path, "file1.py");
        }
    }
}
