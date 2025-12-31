//! Field Extraction from Source Code
//!
//! Extracts searchable fields from code:
//! 1. **String literals**: All quoted strings
//! 2. **Comments**: Line and block comments
//! 3. **Docstrings**: Documentation strings (language-specific)
//!
//! Uses Tree-sitter for accurate parsing.

use tree_sitter::{Node, Parser, Query, QueryCursor, Tree};

/// Extracted searchable fields from code.
#[derive(Debug, Clone, Default)]
pub struct ExtractedFields {
    /// All string literals (e.g., "hello", 'world')
    pub string_literals: String,

    /// All comments (line and block)
    pub comments: String,

    /// Docstrings (language-specific)
    pub docstrings: String,
}

/// Field extractor using Tree-sitter queries.
pub struct FieldExtractor {
    parser: Parser,
    language: tree_sitter::Language,
    queries: LanguageQueries,
}

/// Language-specific Tree-sitter queries.
struct LanguageQueries {
    string_query: Query,
    comment_query: Query,
    docstring_query: Option<Query>,
}

impl FieldExtractor {
    /// Create a new extractor for a specific language.
    pub fn new(language: tree_sitter::Language) -> Result<Self, tree_sitter::QueryError> {
        let mut parser = Parser::new();
        parser
            .set_language(&language)
            .map_err(|e| tree_sitter::QueryError {
                row: 0,
                column: 0,
                offset: 0,
                message: format!("Failed to set parser language: {:?}", e),
                kind: tree_sitter::QueryErrorKind::Language,
            })?;

        let queries = Self::build_queries(&language)?;

        Ok(Self {
            parser,
            language,
            queries,
        })
    }

    /// Build language-specific queries.
    fn build_queries(
        language: &tree_sitter::Language,
    ) -> Result<LanguageQueries, tree_sitter::QueryError> {
        // Try multiple string node types, use whichever works for this language
        let string_patterns = vec![
            "(string) @string",
            "(string_literal) @string",
            "(template_string) @string",
            "(raw_string_literal) @string",
        ];

        let mut string_query_src = String::new();
        for pattern in &string_patterns {
            if let Ok(_) = Query::new(language, pattern) {
                if !string_query_src.is_empty() {
                    string_query_src.push('\n');
                }
                string_query_src.push_str(pattern);
            }
        }

        // Fallback if no patterns work
        if string_query_src.is_empty() {
            string_query_src = "(string) @string".to_string();
        }

        let string_query = Query::new(language, &string_query_src)?;

        // Try multiple comment node types
        let comment_patterns = vec![
            "(comment) @comment",
            "(line_comment) @comment",
            "(block_comment) @comment",
        ];

        let mut comment_query_src = String::new();
        for pattern in &comment_patterns {
            if let Ok(_) = Query::new(language, pattern) {
                if !comment_query_src.is_empty() {
                    comment_query_src.push('\n');
                }
                comment_query_src.push_str(pattern);
            }
        }

        // Fallback if no patterns work
        if comment_query_src.is_empty() {
            comment_query_src = "(comment) @comment".to_string();
        }

        let comment_query = Query::new(language, &comment_query_src)?;

        // Python docstring query (optional, fails gracefully for non-Python)
        let docstring_query = Query::new(
            language,
            r#"
            (expression_statement
              (string) @docstring)
            "#,
        )
        .ok();

        Ok(LanguageQueries {
            string_query,
            comment_query,
            docstring_query,
        })
    }

    /// Extract all fields from source code.
    pub fn extract(&mut self, source: &str) -> ExtractedFields {
        let tree = match self.parser.parse(source, None) {
            Some(tree) => tree,
            None => return ExtractedFields::default(),
        };

        let mut fields = ExtractedFields::default();

        // Extract strings
        fields.string_literals = self.extract_strings(&tree, source);

        // Extract comments
        fields.comments = self.extract_comments(&tree, source);

        // Extract docstrings (if language supports)
        if self.queries.docstring_query.is_some() {
            fields.docstrings = self.extract_docstrings(&tree, source);
        }

        fields
    }

    fn extract_strings(&self, tree: &Tree, source: &str) -> String {
        let mut cursor = QueryCursor::new();
        let matches = cursor.matches(
            &self.queries.string_query,
            tree.root_node(),
            source.as_bytes(),
        );

        let mut strings = Vec::new();
        for m in matches {
            for capture in m.captures {
                if let Ok(text) = capture.node.utf8_text(source.as_bytes()) {
                    // Remove quotes
                    let trimmed = text.trim_matches(|c| c == '"' || c == '\'' || c == '`');
                    if !trimmed.is_empty() {
                        strings.push(trimmed.to_string());
                    }
                }
            }
        }

        strings.join(" ")
    }

    fn extract_comments(&self, tree: &Tree, source: &str) -> String {
        let mut cursor = QueryCursor::new();
        let matches = cursor.matches(
            &self.queries.comment_query,
            tree.root_node(),
            source.as_bytes(),
        );

        let mut comments = Vec::new();
        for m in matches {
            for capture in m.captures {
                if let Ok(text) = capture.node.utf8_text(source.as_bytes()) {
                    // Remove comment markers
                    let cleaned = text
                        .trim_start_matches("//")
                        .trim_start_matches("/*")
                        .trim_end_matches("*/")
                        .trim_start_matches("#")
                        .trim();
                    if !cleaned.is_empty() {
                        comments.push(cleaned.to_string());
                    }
                }
            }
        }

        comments.join(" ")
    }

    fn extract_docstrings(&self, tree: &Tree, source: &str) -> String {
        let query = match &self.queries.docstring_query {
            Some(q) => q,
            None => return String::new(),
        };

        let mut cursor = QueryCursor::new();
        let matches = cursor.matches(query, tree.root_node(), source.as_bytes());

        let mut docstrings = Vec::new();
        for m in matches {
            for capture in m.captures {
                if let Ok(text) = capture.node.utf8_text(source.as_bytes()) {
                    let trimmed = text.trim_matches(|c| c == '"' || c == '\'').trim();
                    if !trimmed.is_empty() {
                        docstrings.push(trimmed.to_string());
                    }
                }
            }
        }

        docstrings.join(" ")
    }
}

/// Language-agnostic fallback extractor (regex-based).
///
/// Used when Tree-sitter parsing fails or for unsupported languages.
pub struct RegexExtractor;

impl RegexExtractor {
    /// Extract fields using regex patterns.
    pub fn extract(source: &str) -> ExtractedFields {
        use regex::Regex;

        let mut fields = ExtractedFields::default();

        // Extract strings (simple regex)
        // SAFETY: This regex pattern is compile-time constant and known to be valid
        let string_re = Regex::new(r#"["']([^"'\\]|\\.)*["']"#).unwrap();
        fields.string_literals = string_re
            .find_iter(source)
            .map(|m| m.as_str().trim_matches(|c| c == '"' || c == '\''))
            .collect::<Vec<_>>()
            .join(" ");

        // Extract line comments (// and #)
        // SAFETY: This regex pattern is compile-time constant and known to be valid
        let line_comment_re = Regex::new(r"(?m)(//|#)(.*)$").unwrap();
        let mut comments = Vec::new();
        for cap in line_comment_re.captures_iter(source) {
            if let Some(text) = cap.get(2) {
                let trimmed = text.as_str().trim();
                if !trimmed.is_empty() {
                    comments.push(trimmed.to_string());
                }
            }
        }

        // Extract block comments (/* ... */)
        // SAFETY: This regex pattern is compile-time constant and known to be valid
        let block_comment_re = Regex::new(r"/\*(.|\n)*?\*/").unwrap();
        for m in block_comment_re.find_iter(source) {
            let text = m
                .as_str()
                .trim_start_matches("/*")
                .trim_end_matches("*/")
                .trim();
            if !text.is_empty() {
                comments.push(text.to_string());
            }
        }

        fields.comments = comments.join(" ");

        fields
    }
}

// SAFETY: All regex patterns below are compile-time constants and known to be valid.
// They are tested in the test suite and follow standard regex syntax.

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_regex_extractor_strings() {
        let source = r#"
        const greeting = "Hello, World!";
        const name = 'Alice';
        "#;

        let fields = RegexExtractor::extract(source);
        assert!(fields.string_literals.contains("Hello, World!"));
        assert!(fields.string_literals.contains("Alice"));
    }

    #[test]
    fn test_regex_extractor_comments() {
        let source = r#"
        // This is a line comment
        /* This is a block comment */
        # Python-style comment
        "#;

        let fields = RegexExtractor::extract(source);
        assert!(fields.comments.contains("This is a line comment"));
        assert!(fields.comments.contains("This is a block comment"));
        assert!(fields.comments.contains("Python-style comment"));
    }

    #[test]
    fn test_tree_sitter_python() {
        let source = r#"
def hello():
    """This is a docstring"""
    name = "Alice"
    # This is a comment
    return name
        "#;

        let mut extractor = FieldExtractor::new(tree_sitter_python::language()).unwrap();
        let fields = extractor.extract(source);

        assert!(fields.string_literals.contains("Alice"));
        assert!(fields.comments.contains("This is a comment"));
        assert!(fields.docstrings.contains("This is a docstring"));
    }

    #[test]
    fn test_tree_sitter_rust() {
        let source = r#"
        /// This is a doc comment
        fn hello() -> &'static str {
            let name = "Alice";
            // This is a line comment
            name
        }
        "#;

        let mut extractor = FieldExtractor::new(tree_sitter_rust::language()).unwrap();
        let fields = extractor.extract(source);

        assert!(fields.string_literals.contains("Alice"));
        assert!(fields.comments.contains("This is a line comment"));
    }
}
