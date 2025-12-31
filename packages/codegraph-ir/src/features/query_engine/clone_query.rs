// CloneQueryBuilder - Specialized queries for clone detection
//
// Provides fluent API for code clone queries:
// - Filter by similarity threshold
// - Filter by clone type (Type-1, Type-2, Type-3, Type-4)
// - Filter by size (LOC, tokens)
// - Get clone groups/pairs

use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::features::query_engine::infrastructure::GraphIndex;

/// Clone type classification
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloneType {
    /// Type-1: Exact clones (only whitespace/comments differ)
    Type1,
    /// Type-2: Renamed clones (identifiers differ)
    Type2,
    /// Type-3: Near-miss clones (some statements added/removed)
    Type3,
    /// Type-4: Semantic clones (different syntax, same behavior)
    Type4,
}

impl CloneType {
    pub fn as_str(&self) -> &'static str {
        match self {
            CloneType::Type1 => "type1",
            CloneType::Type2 => "type2",
            CloneType::Type3 => "type3",
            CloneType::Type4 => "type4",
        }
    }

    /// Get minimum similarity threshold for this clone type
    pub fn min_similarity(&self) -> f64 {
        match self {
            CloneType::Type1 => 1.0,   // Exact match
            CloneType::Type2 => 0.95,  // Very high similarity
            CloneType::Type3 => 0.70,  // Moderate similarity
            CloneType::Type4 => 0.50,  // Semantic similarity
        }
    }
}

/// Clone pair result
#[derive(Debug, Clone)]
pub struct ClonePair {
    pub clone1_id: String,
    pub clone2_id: String,
    pub clone1_file: String,
    pub clone2_file: String,
    pub clone1_start_line: usize,
    pub clone1_end_line: usize,
    pub clone2_start_line: usize,
    pub clone2_end_line: usize,
    pub similarity: f64,
    pub clone_type: CloneType,
    pub size_loc: usize,  // Lines of code
    pub size_tokens: usize,
}

/// Clone group (multiple clones of same code)
#[derive(Debug, Clone)]
pub struct CloneGroup {
    pub group_id: String,
    pub clone_ids: Vec<String>,
    pub similarity: f64,
    pub clone_type: CloneType,
    pub size_loc: usize,
}

/// CloneQueryBuilder - Fluent API for clone detection queries
///
/// Example:
/// ```no_run
/// let clones = engine.query()
///     .clone_pairs()
///     .min_similarity(0.85)
///     .clone_type(CloneType::Type3)
///     .min_size(20)  // At least 20 LOC
///     .execute()?;
///
/// for pair in clones {
///     println!("Clone: {} <-> {} (similarity: {:.2})",
///         pair.clone1_file,
///         pair.clone2_file,
///         pair.similarity
///     );
/// }
/// ```
pub struct CloneQueryBuilder<'a> {
    index: &'a GraphIndex,
    ir_doc: &'a IRDocument,

    // Filters
    min_similarity_threshold: Option<f64>,
    clone_type_filter: Option<CloneType>,
    min_size_loc: Option<usize>,
    min_size_tokens: Option<usize>,
    file_filter: Option<String>,
    exclude_test_files: bool,

    // Pagination
    limit: Option<usize>,
}

impl<'a> CloneQueryBuilder<'a> {
    /// Create new CloneQueryBuilder
    pub fn new(index: &'a GraphIndex, ir_doc: &'a IRDocument) -> Self {
        Self {
            index,
            ir_doc,
            min_similarity_threshold: None,
            clone_type_filter: None,
            min_size_loc: None,
            min_size_tokens: None,
            file_filter: None,
            exclude_test_files: false,
            limit: None,
        }
    }

    /// Filter by minimum similarity threshold (0.0 to 1.0)
    ///
    /// Example:
    /// ```no_run
    /// .min_similarity(0.85)  // At least 85% similar
    /// .min_similarity(0.95)  // Very high similarity
    /// ```
    pub fn min_similarity(mut self, threshold: f64) -> Self {
        self.min_similarity_threshold = Some(threshold);
        self
    }

    /// Filter by clone type
    ///
    /// Example:
    /// ```no_run
    /// .clone_type(CloneType::Type3)  // Near-miss clones
    /// ```
    pub fn clone_type(mut self, clone_type: CloneType) -> Self {
        self.clone_type_filter = Some(clone_type);
        self
    }

    /// Filter by minimum size (lines of code)
    ///
    /// Example:
    /// ```no_run
    /// .min_size(20)  // At least 20 LOC
    /// ```
    pub fn min_size(mut self, loc: usize) -> Self {
        self.min_size_loc = Some(loc);
        self
    }

    /// Filter by minimum token count
    ///
    /// Example:
    /// ```no_run
    /// .min_tokens(50)  // At least 50 tokens
    /// ```
    pub fn min_tokens(mut self, tokens: usize) -> Self {
        self.min_size_tokens = Some(tokens);
        self
    }

    /// Filter by file path pattern
    ///
    /// Example:
    /// ```no_run
    /// .in_file("src/")  // Only clones in src/ directory
    /// ```
    pub fn in_file(mut self, pattern: &str) -> Self {
        self.file_filter = Some(pattern.to_string());
        self
    }

    /// Exclude test files from results
    ///
    /// Example:
    /// ```no_run
    /// .exclude_tests()  // Ignore test_*.py, *_test.py
    /// ```
    pub fn exclude_tests(mut self) -> Self {
        self.exclude_test_files = true;
        self
    }

    /// Limit number of results
    pub fn limit(mut self, limit: usize) -> Self {
        self.limit = Some(limit);
        self
    }

    /// Execute query and return clone pairs
    ///
    /// ## Integration Guide
    /// Use `CloneDetector` from `clone_detection::infrastructure`:
    /// ```ignore
    /// use crate::features::clone_detection::infrastructure::CloneDetector;
    /// let detector = CloneDetector::new(config);
    /// let pairs = detector.detect_all(&fragments);
    /// ```
    ///
    /// See: `clone_detection/infrastructure/mod.rs` (9,518 LOC)
    pub fn execute(self) -> Result<Vec<ClonePair>, String> {
        // INTEGRATION PENDING: Connect to CloneDetector
        // Impl exists at: clone_detection::infrastructure::CloneDetector
        Ok(Vec::new())
    }

    /// Get clone groups instead of pairs
    ///
    /// Example:
    /// ```no_run
    /// let groups = engine.query()
    ///     .clone_pairs()
    ///     .min_similarity(0.90)
    ///     .get_groups()?;
    /// ```
    pub fn get_groups(self) -> Result<Vec<CloneGroup>, String> {
        // INTEGRATION PENDING: Group clone pairs by similarity
        // Use clone_detection::domain::Deduplicator for grouping
        Ok(Vec::new())
    }
}

/// Helper methods for common clone queries
impl<'a> CloneQueryBuilder<'a> {
    /// Get exact clones (Type-1)
    ///
    /// Example:
    /// ```no_run
    /// let exact = engine.query()
    ///     .clone_pairs()
    ///     .exact_clones()
    ///     .execute()?;
    /// ```
    pub fn exact_clones(self) -> Self {
        self.clone_type(CloneType::Type1)
            .min_similarity(1.0)
    }

    /// Get renamed clones (Type-2)
    ///
    /// Example:
    /// ```no_run
    /// let renamed = engine.query()
    ///     .clone_pairs()
    ///     .renamed_clones()
    ///     .execute()?;
    /// ```
    pub fn renamed_clones(self) -> Self {
        self.clone_type(CloneType::Type2)
            .min_similarity(0.95)
    }

    /// Get near-miss clones (Type-3)
    ///
    /// Example:
    /// ```no_run
    /// let near_miss = engine.query()
    ///     .clone_pairs()
    ///     .near_miss_clones()
    ///     .execute()?;
    /// ```
    pub fn near_miss_clones(self) -> Self {
        self.clone_type(CloneType::Type3)
            .min_similarity(0.70)
    }

    /// Get semantic clones (Type-4)
    ///
    /// Example:
    /// ```no_run
    /// let semantic = engine.query()
    ///     .clone_pairs()
    ///     .semantic_clones()
    ///     .execute()?;
    /// ```
    pub fn semantic_clones(self) -> Self {
        self.clone_type(CloneType::Type4)
            .min_similarity(0.50)
    }

    /// Get only large clones (>50 LOC)
    ///
    /// Example:
    /// ```no_run
    /// let large = engine.query()
    ///     .clone_pairs()
    ///     .large_clones()
    ///     .execute()?;
    /// ```
    pub fn large_clones(self) -> Self {
        self.min_size(50)
    }

    /// Get production code clones only (exclude tests)
    ///
    /// Example:
    /// ```no_run
    /// let production = engine.query()
    ///     .clone_pairs()
    ///     .production_only()
    ///     .execute()?;
    /// ```
    pub fn production_only(self) -> Self {
        self.exclude_tests()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::features::query_engine::infrastructure::GraphIndex;

    #[test]
    fn test_clone_query_builder_creation() {
        let doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&doc);
        let _builder = CloneQueryBuilder::new(&index, &doc);
    }

    #[test]
    fn test_clone_query_filters() {
        let doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&doc);
        let builder = CloneQueryBuilder::new(&index, &doc);

        let _query = builder
            .min_similarity(0.85)
            .clone_type(CloneType::Type3)
            .min_size(20)
            .min_tokens(50)
            .in_file("src/")
            .exclude_tests();

        // Should compile and chain correctly
    }

    #[test]
    fn test_exact_clones_helper() {
        let doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&doc);
        let builder = CloneQueryBuilder::new(&index, &doc);

        let _query = builder
            .exact_clones()
            .min_size(10);

        // Should compile
    }

    #[test]
    fn test_clone_type_as_str() {
        assert_eq!(CloneType::Type1.as_str(), "type1");
        assert_eq!(CloneType::Type2.as_str(), "type2");
        assert_eq!(CloneType::Type3.as_str(), "type3");
        assert_eq!(CloneType::Type4.as_str(), "type4");
    }

    #[test]
    fn test_clone_type_min_similarity() {
        assert_eq!(CloneType::Type1.min_similarity(), 1.0);
        assert_eq!(CloneType::Type2.min_similarity(), 0.95);
        assert_eq!(CloneType::Type3.min_similarity(), 0.70);
        assert_eq!(CloneType::Type4.min_similarity(), 0.50);
    }

    #[test]
    fn test_near_miss_clones() {
        let doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&doc);
        let builder = CloneQueryBuilder::new(&index, &doc);

        let _query = builder
            .near_miss_clones()
            .large_clones()
            .production_only();

        // Should compile
    }
}
