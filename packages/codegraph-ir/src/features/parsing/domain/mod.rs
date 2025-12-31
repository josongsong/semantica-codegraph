//! Parsing domain models

mod parsed_tree;
mod syntax_node;

pub use parsed_tree::{ParseError, ParsedTree};
pub use syntax_node::{SyntaxKind, SyntaxNode};
