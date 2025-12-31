//! Parsed tree representation
//!
//! Abstracts the parsed AST for downstream processing.

use super::syntax_node::SyntaxNode;
use crate::shared::models::Span;

/// Parsed syntax tree
#[derive(Debug, Clone)]
pub struct ParsedTree {
    /// Root node of the tree
    pub root: SyntaxNode,

    /// Source code
    pub source: String,

    /// File path (for error messages)
    pub file_path: String,

    /// Language
    pub language: String,

    /// Whether parsing had errors
    pub has_errors: bool,

    /// Parse errors (if any)
    pub errors: Vec<ParseError>,
}

/// Parse error
#[derive(Debug, Clone)]
pub struct ParseError {
    pub message: String,
    pub span: Span,
}

impl ParsedTree {
    pub fn new(root: SyntaxNode, source: String, file_path: String, language: String) -> Self {
        Self {
            root,
            source,
            file_path,
            language,
            has_errors: false,
            errors: Vec::new(),
        }
    }

    pub fn with_errors(mut self, errors: Vec<ParseError>) -> Self {
        self.has_errors = !errors.is_empty();
        self.errors = errors;
        self
    }

    /// Get source text for a span
    pub fn text_for_span(&self, span: &Span) -> &str {
        // Simple line-based extraction
        let lines: Vec<&str> = self.source.lines().collect();

        if span.start_line == span.end_line {
            let line_idx = (span.start_line as usize).saturating_sub(1);
            if let Some(line) = lines.get(line_idx) {
                let start = span.start_col as usize;
                let end = span.end_col as usize;
                if start <= line.len() && end <= line.len() {
                    return &line[start..end];
                }
            }
        }

        // Multi-line or fallback
        ""
    }

    /// Get line count
    pub fn line_count(&self) -> usize {
        self.source.lines().count()
    }

    /// Check if file is empty
    pub fn is_empty(&self) -> bool {
        self.source.trim().is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::parsing::domain::SyntaxKind;

    #[test]
    fn test_parsed_tree_line_count() {
        let root = SyntaxNode::new(SyntaxKind::Block, Span::zero());
        let tree = ParsedTree::new(
            root,
            "line1\nline2\nline3".to_string(),
            "test.py".to_string(),
            "python".to_string(),
        );
        assert_eq!(tree.line_count(), 3);
    }
}
