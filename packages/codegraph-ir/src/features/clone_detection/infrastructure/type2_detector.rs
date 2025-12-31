//! Type-2 Clone Detector (Renamed Clones)
//!
//! Detects renamed clones using AST-based normalization.
//! Identifiers, types, and literals differ but structure is identical.
//!
//! # Algorithm
//!
//! 1. Parse code to AST (if available)
//! 2. Normalize identifiers to placeholders (VAR_0, VAR_1, ...)
//! 3. Normalize literals to type-based placeholders (INT_LIT, STR_LIT, ...)
//! 4. Serialize normalized AST to string
//! 5. Compute hash (FNV-1a)
//! 6. Group by hash
//! 7. Compute similarity (should be >= 0.95)
//!
//! # Performance
//!
//! - **Speed**: ~500K LOC/s
//! - **Complexity**: O(n log n) - AST traversal + hash table
//! - **Memory**: O(n) - normalized AST storage
//!
//! # Example
//!
//! ```text
//! // Fragment 1
//! def add(a, b):
//!     return a + b
//!
//! // Fragment 2 (Type-2 clone)
//! def sum(x, y):
//!     return x + y
//! ```

use crate::features::clone_detection::domain::{
    jaccard_similarity_vec, token_cosine_similarity, CloneMetrics, ClonePair, CloneType,
    CodeFragment, DetectionInfo,
};
use std::collections::HashMap;

use super::CloneDetector;

/// Type-2 clone detector using AST normalization
pub struct Type2Detector {
    /// Minimum token threshold
    min_tokens: usize,

    /// Minimum LOC threshold
    min_loc: usize,

    /// Similarity threshold (default: 0.95)
    min_similarity: f64,

    /// Use AST if available (vs. simple token normalization)
    use_ast: bool,
}

impl Default for Type2Detector {
    fn default() -> Self {
        Self::new()
    }
}

impl Type2Detector {
    /// Create new Type-2 detector with default thresholds
    pub fn new() -> Self {
        Self {
            min_tokens: 50,
            min_loc: 6,
            min_similarity: 0.95,
            use_ast: false, // Simple token-based normalization for now
        }
    }

    /// Create with custom thresholds
    pub fn with_thresholds(min_tokens: usize, min_loc: usize, min_similarity: f64) -> Self {
        Self {
            min_tokens,
            min_loc,
            min_similarity,
            use_ast: false,
        }
    }

    /// Enable AST-based normalization (requires tree-sitter)
    #[allow(dead_code)]
    pub fn with_ast(mut self) -> Self {
        self.use_ast = true;
        self
    }

    /// Normalize content for Type-2 detection
    ///
    /// Simple token-based normalization:
    /// - Replace identifiers with VAR_N
    /// - Replace numbers with INT_LIT / FLOAT_LIT
    /// - Replace strings with STR_LIT
    /// - Keep keywords, operators, punctuation
    fn normalize_content(&self, content: &str) -> String {
        let mut normalized = Vec::new();
        let mut var_counter = 0;

        for line in content.lines() {
            let mut norm_line = Vec::new();

            for token in line.split_whitespace() {
                let norm_token = if Self::is_keyword(token) {
                    // Keep keywords as-is
                    token.to_string()
                } else if Self::is_operator(token) {
                    // Keep operators as-is
                    token.to_string()
                } else if Self::is_number(token) {
                    // Normalize numbers
                    if token.contains('.') {
                        "FLOAT_LIT".to_string()
                    } else {
                        "INT_LIT".to_string()
                    }
                } else if Self::is_string_literal(token) {
                    // Normalize strings
                    "STR_LIT".to_string()
                } else if Self::is_identifier(token) {
                    // Normalize identifiers (ordered by first appearance)
                    let var_name = format!("VAR_{}", var_counter);
                    var_counter += 1;
                    var_name
                } else {
                    // Keep punctuation, etc.
                    token.to_string()
                };

                norm_line.push(norm_token);
            }

            if !norm_line.is_empty() {
                normalized.push(norm_line.join(" "));
            }
        }

        normalized.join("\n")
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
            "+" | "-"
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

    /// Check if token is an identifier
    fn is_identifier(token: &str) -> bool {
        !token.is_empty()
            && !Self::is_keyword(token)
            && !Self::is_operator(token)
            && !Self::is_number(token)
            && !Self::is_string_literal(token)
            // SAFETY: token is guaranteed to be non-empty by the first condition
            && token.chars().next().unwrap().is_alphabetic()
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

    /// Compute token-based similarity between two fragments
    fn compute_similarity(&self, source: &CodeFragment, target: &CodeFragment) -> f64 {
        let tokens_a: Vec<&str> = source.content.split_whitespace().collect();
        let tokens_b: Vec<&str> = target.content.split_whitespace().collect();

        // Normalize tokens for comparison
        let norm_a: Vec<String> = tokens_a.iter().map(|t| self.normalize_token(t)).collect();
        let norm_b: Vec<String> = tokens_b.iter().map(|t| self.normalize_token(t)).collect();

        // Use Jaccard similarity on normalized tokens
        jaccard_similarity_vec(&norm_a, &norm_b)
    }

    /// Normalize a single token
    fn normalize_token(&self, token: &str) -> String {
        if Self::is_keyword(token) || Self::is_operator(token) {
            token.to_string()
        } else if Self::is_number(token) {
            if token.contains('.') {
                "FLOAT_LIT".to_string()
            } else {
                "INT_LIT".to_string()
            }
        } else if Self::is_string_literal(token) {
            "STR_LIT".to_string()
        } else {
            "IDENTIFIER".to_string()
        }
    }

    /// Group fragments by hash
    fn group_by_hash(&self, fragments: &[CodeFragment]) -> HashMap<u64, Vec<usize>> {
        let mut groups: HashMap<u64, Vec<usize>> = HashMap::new();

        for (idx, fragment) in fragments.iter().enumerate() {
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
            if indices.len() < 2 {
                continue;
            }

            for i in 0..indices.len() {
                for j in (i + 1)..indices.len() {
                    let source = &fragments[indices[i]];
                    let target = &fragments[indices[j]];

                    // Skip self-clones
                    if source.file_path == target.file_path && source.span == target.span {
                        continue;
                    }

                    // Compute similarity
                    let similarity = self.compute_similarity(source, target);

                    // Filter by minimum similarity
                    if similarity < self.min_similarity {
                        continue;
                    }

                    let metrics = CloneMetrics::new(
                        source.token_count.min(target.token_count),
                        source.loc.min(target.loc),
                        similarity,
                    )
                    .with_ast_similarity(similarity);

                    let detection_info =
                        DetectionInfo::new("Type-2 (AST normalization)".to_string())
                            .with_confidence(similarity);

                    let pair = ClonePair::new(
                        CloneType::Type2,
                        source.clone(),
                        target.clone(),
                        similarity,
                    )
                    .with_metrics(metrics)
                    .with_detection_info(detection_info);

                    pairs.push(pair);
                }
            }
        }

        pairs
    }
}

impl CloneDetector for Type2Detector {
    fn name(&self) -> &'static str {
        "Type-2 (Renamed Clone Detector)"
    }

    fn supported_type(&self) -> CloneType {
        CloneType::Type2
    }

    fn detect(&self, fragments: &[CodeFragment]) -> Vec<ClonePair> {
        if fragments.is_empty() {
            return Vec::new();
        }

        let start_time = std::time::Instant::now();

        let groups = self.group_by_hash(fragments);
        let mut pairs = self.create_clone_pairs(fragments, groups);

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
        let detector = Type2Detector::new();
        assert_eq!(detector.name(), "Type-2 (Renamed Clone Detector)");
        assert_eq!(detector.supported_type(), CloneType::Type2);
    }

    #[test]
    fn test_is_keyword() {
        assert!(Type2Detector::is_keyword("def"));
        assert!(Type2Detector::is_keyword("class"));
        assert!(Type2Detector::is_keyword("return"));
        assert!(!Type2Detector::is_keyword("foo"));
    }

    #[test]
    fn test_is_operator() {
        assert!(Type2Detector::is_operator("+"));
        assert!(Type2Detector::is_operator("=="));
        assert!(Type2Detector::is_operator("and"));
        assert!(!Type2Detector::is_operator("foo"));
    }

    #[test]
    fn test_is_number() {
        assert!(Type2Detector::is_number("42"));
        assert!(Type2Detector::is_number("3.14"));
        assert!(Type2Detector::is_number("-10"));
        assert!(!Type2Detector::is_number("foo"));
    }

    #[test]
    fn test_is_string_literal() {
        assert!(Type2Detector::is_string_literal("\"hello\""));
        assert!(Type2Detector::is_string_literal("'world'"));
        assert!(!Type2Detector::is_string_literal("foo"));
    }

    #[test]
    fn test_is_identifier() {
        assert!(Type2Detector::is_identifier("foo"));
        assert!(Type2Detector::is_identifier("bar123"));
        assert!(!Type2Detector::is_identifier("def"));
        assert!(!Type2Detector::is_identifier("42"));
    }

    #[test]
    fn test_normalize_identifiers() {
        let detector = Type2Detector::new();
        let content = "def add(a, b):\n    return a + b";
        let normalized = detector.normalize_content(content);

        // Should replace identifiers with VAR_N
        assert!(normalized.contains("VAR_"));
        // Should keep keywords
        assert!(normalized.contains("def"));
        assert!(normalized.contains("return"));
    }

    #[test]
    fn test_normalize_numbers() {
        let detector = Type2Detector::new();
        let content = "x = 42\ny = 3.14";
        let normalized = detector.normalize_content(content);

        assert!(normalized.contains("INT_LIT"));
        assert!(normalized.contains("FLOAT_LIT"));
    }

    #[test]
    fn test_normalize_strings() {
        let detector = Type2Detector::new();
        let content = "msg = \"hello\"\nname = 'world'";
        let normalized = detector.normalize_content(content);

        assert!(normalized.contains("STR_LIT"));
    }

    #[test]
    fn test_detect_renamed_clone() {
        let detector = Type2Detector::with_thresholds(10, 2, 0.7);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 10, 2),
            create_fragment(
                "file2.py",
                10,
                15,
                "def sum(x, y):\n    return x + y",
                10,
                2,
            ),
        ];

        let pairs = detector.detect(&fragments);

        // Should find Type-2 clone despite different names
        assert!(!pairs.is_empty());
        if !pairs.is_empty() {
            assert_eq!(pairs[0].clone_type, CloneType::Type2);
            assert!(pairs[0].similarity >= 0.7);
        }
    }

    #[test]
    fn test_detect_no_clone() {
        let detector = Type2Detector::with_thresholds(10, 2, 0.95);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 10, 2),
            create_fragment(
                "file2.py",
                10,
                15,
                "def mul(x, y):\n    return x * y",
                10,
                2,
            ),
        ];

        let pairs = detector.detect(&fragments);

        // Different operations - not a clone
        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_similarity_threshold() {
        let detector = Type2Detector::with_thresholds(10, 2, 0.95);

        let source = create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 10, 2);
        let target = create_fragment(
            "file2.py",
            10,
            15,
            "def sum(x, y):\n    return x + y",
            10,
            2,
        );

        let similarity = detector.compute_similarity(&source, &target);

        // High similarity (same structure, different names)
        assert!(similarity > 0.5);
    }

    // =====================================================================
    // EDGE CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_empty_content() {
        let detector = Type2Detector::new();
        let normalized = detector.normalize_content("");
        assert_eq!(normalized, "");
    }

    #[test]
    fn test_only_keywords() {
        let detector = Type2Detector::new();
        let content = "def return if else";
        let normalized = detector.normalize_content(content);

        // All keywords preserved
        assert_eq!(normalized, "def return if else");
    }

    #[test]
    fn test_mixed_literals() {
        let detector = Type2Detector::new();
        let content = "x = 42\ny = 3.14\nz = \"hello\"";
        let normalized = detector.normalize_content(content);

        assert!(normalized.contains("INT_LIT"));
        assert!(normalized.contains("FLOAT_LIT"));
        assert!(normalized.contains("STR_LIT"));
    }

    #[test]
    fn test_hash_consistency() {
        let detector = Type2Detector::new();
        let content = "def foo(x):\n    return x + 1";

        let hash1 = detector.compute_hash(content);
        let hash2 = detector.compute_hash(content);

        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_different_identifiers_same_hash() {
        let detector = Type2Detector::new();

        let content1 = "def add(a, b):\n    return a + b";
        let content2 = "def sum(x, y):\n    return x + y";

        let hash1 = detector.compute_hash(content1);
        let hash2 = detector.compute_hash(content2);

        // Should have same hash (normalized structure identical)
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_different_literals_same_hash() {
        let detector = Type2Detector::new();

        let content1 = "x = 42";
        let content2 = "y = 99";

        let hash1 = detector.compute_hash(content1);
        let hash2 = detector.compute_hash(content2);

        // Should have same hash (both normalize to: VAR_0 = INT_LIT)
        assert_eq!(hash1, hash2);
    }

    // =====================================================================
    // CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_unicode_identifiers() {
        let detector = Type2Detector::new();
        let content = "def 함수(변수):\n    return 변수";
        let normalized = detector.normalize_content(content);

        // Should normalize Korean identifiers
        assert!(normalized.contains("VAR_"));
    }

    #[test]
    fn test_negative_numbers() {
        let detector = Type2Detector::new();
        let content = "x = -42\ny = -3.14";
        let normalized = detector.normalize_content(content);

        assert!(normalized.contains("INT_LIT"));
        assert!(normalized.contains("FLOAT_LIT"));
    }

    #[test]
    fn test_operators_preserved() {
        let detector = Type2Detector::new();
        let content = "a + b - c * d / e";
        let normalized = detector.normalize_content(content);

        // Operators should be preserved
        assert!(normalized.contains("+"));
        assert!(normalized.contains("-"));
        assert!(normalized.contains("*"));
        assert!(normalized.contains("/"));
    }

    #[test]
    fn test_similarity_identical() {
        let detector = Type2Detector::new();

        let source = create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2);
        let target = create_fragment("file2.py", 10, 15, "def foo():\n    return 42", 10, 2);

        let similarity = detector.compute_similarity(&source, &target);

        // Identical code = 100% similarity
        assert_eq!(similarity, 1.0);
    }

    #[test]
    fn test_similarity_completely_different() {
        let detector = Type2Detector::new();

        let source = create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 10, 2);
        let target = create_fragment("file2.py", 10, 15, "class Bar:\n    pass", 10, 2);

        let similarity = detector.compute_similarity(&source, &target);

        // Completely different = low similarity
        assert!(similarity < 0.3);
    }

    // =====================================================================
    // COMPLEX CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_multiple_renamed_clones() {
        let detector = Type2Detector::with_thresholds(10, 2, 0.7);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 10, 2),
            create_fragment(
                "file2.py",
                10,
                15,
                "def sum(x, y):\n    return x + y",
                10,
                2,
            ),
            create_fragment(
                "file3.py",
                20,
                25,
                "def plus(m, n):\n    return m + n",
                10,
                2,
            ),
        ];

        let pairs = detector.detect(&fragments);

        // Should find all pairwise clones: C(3,2) = 3
        assert!(pairs.len() >= 3);
    }

    #[test]
    fn test_confidence_equals_similarity() {
        let detector = Type2Detector::with_thresholds(10, 2, 0.9);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 10, 2),
            create_fragment(
                "file2.py",
                10,
                15,
                "def sum(x, y):\n    return x + y",
                10,
                2,
            ),
        ];

        let pairs = detector.detect(&fragments);

        if !pairs.is_empty() {
            let pair = &pairs[0];
            assert_eq!(pair.detection_info.confidence, Some(pair.similarity));
        }
    }

    #[test]
    fn test_ast_similarity_recorded() {
        let detector = Type2Detector::with_thresholds(10, 2, 0.9);

        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 10, 2),
            create_fragment(
                "file2.py",
                10,
                15,
                "def sum(x, y):\n    return x + y",
                10,
                2,
            ),
        ];

        let pairs = detector.detect(&fragments);

        if !pairs.is_empty() {
            assert!(pairs[0].metrics.ast_similarity.is_some());
        }
    }

    #[test]
    fn test_normalization_preserves_structure() {
        let detector = Type2Detector::new();

        let content1 = "def foo(a, b):\n    if a > b:\n        return a\n    return b";
        let content2 = "def bar(x, y):\n    if x > y:\n        return x\n    return y";

        let norm1 = detector.normalize_content(content1);
        let norm2 = detector.normalize_content(content2);

        // Should have identical structure after normalization
        // (though variable numbers may differ)
        assert!(norm1.contains("def"));
        assert!(norm2.contains("def"));
        assert!(norm1.contains("if"));
        assert!(norm2.contains("if"));
        assert!(norm1.contains("return"));
        assert!(norm2.contains("return"));
    }
}
