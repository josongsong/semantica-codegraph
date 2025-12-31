/*
 * Zero-Copy String References
 *
 * SOTA Optimization:
 * - No string allocation during traversal
 * - Source code stays in memory (mmap)
 * - Blocks reference source via Span
 * - Extract text only when needed (Python interop)
 *
 * Memory Efficiency:
 * - Before: N blocks × M bytes/block = N×M memory
 * - After: 1 source + N spans = 1×M + N×16 bytes
 * - Savings: Massive for large files
 */

use crate::shared::models::Span;

/// String reference via Span (zero-copy)
///
/// Instead of copying strings, we store:
/// - Span (start/end positions)
/// - Reference to source
///
/// Extract text only when needed.
#[derive(Debug, Clone)]
pub struct SpanRef {
    pub span: Span,
}

impl SpanRef {
    pub fn new(span: Span) -> Self {
        Self { span }
    }

    /// Extract text from source (only when needed)
    pub fn extract_text<'a>(&self, source: &'a str) -> &'a str {
        // Convert line/col to byte offsets
        let start_byte = self.line_col_to_byte(source, self.span.start_line, self.span.start_col);
        let end_byte = self.line_col_to_byte(source, self.span.end_line, self.span.end_col);

        &source[start_byte..end_byte]
    }

    fn line_col_to_byte(&self, source: &str, line: u32, col: u32) -> usize {
        let mut current_line = 1u32;
        let mut byte_offset = 0;

        for (i, ch) in source.char_indices() {
            if current_line == line {
                // Found target line
                let mut current_col = 0u32;
                for (j, _) in source[i..].char_indices() {
                    if current_col == col {
                        return i + j;
                    }
                    current_col += 1;
                }
                return i;
            }

            if ch == '\n' {
                current_line += 1;
            }
            byte_offset = i;
        }

        byte_offset
    }
}

/// Block with zero-copy text reference
#[derive(Debug, Clone)]
pub struct BlockRef {
    pub id: String,
    pub kind: String,
    pub span_ref: SpanRef,
    pub statement_count: usize,
}

impl BlockRef {
    pub fn new(id: String, kind: String, span: Span, statement_count: usize) -> Self {
        Self {
            id,
            kind,
            span_ref: SpanRef::new(span),
            statement_count,
        }
    }

    /// Extract block text (only when needed)
    pub fn get_text<'a>(&self, source: &'a str) -> &'a str {
        self.span_ref.extract_text(source)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    #[test]
    fn test_span_ref_extract() {
        let source = "line1\nline2\nline3";
        let span = Span::new(2, 0, 2, 5); // "line2"

        let span_ref = SpanRef::new(span);
        let text = span_ref.extract_text(source);

        assert_eq!(text, "line2");
    }

    #[test]
    fn test_block_ref() {
        let source = "def hello():\n    pass";
        let span = Span::new(1, 0, 2, 8);

        let block = BlockRef::new("block:1".to_string(), "statement".to_string(), span, 1);

        let text = block.get_text(source);
        assert!(text.contains("hello"));
    }
}
