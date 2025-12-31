//! Parsing infrastructure - external dependencies

pub mod base_extractor;
pub mod extractors;
pub mod tree_sitter; // Common extraction logic

pub use base_extractor::BaseExtractor;
pub use tree_sitter::TreeSitterParser;
