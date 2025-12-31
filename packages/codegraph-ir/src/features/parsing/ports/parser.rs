//! Parser port (interface)
//!
//! Defines the contract for parsing source code.

use crate::features::parsing::domain::ParsedTree;
use crate::shared::models::Result;

/// Parser trait - abstraction over parsing implementation
pub trait Parser: Send + Sync {
    /// Parse source code into a ParsedTree
    fn parse(&self, source: &str, file_path: &str) -> Result<ParsedTree>;

    /// Check if this parser supports the given file extension
    fn supports_extension(&self, ext: &str) -> bool;

    /// Get supported language name
    fn language_name(&self) -> &'static str;
}

/// Batch parsing support (optional trait)
pub trait BatchParser: Parser {
    /// Parse multiple files in parallel
    fn parse_batch(&self, files: &[(String, String)]) -> Vec<Result<ParsedTree>>;
}
