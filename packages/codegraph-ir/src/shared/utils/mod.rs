//! Utility modules shared across features
//!
//! Common utilities used by multiple features:
//! - `id_generator`: Unique ID generation
//! - `scope_stack`: Scope management for symbol resolution
//! - `tree_sitter`: Tree-sitter AST traversal and extraction (SOTA)
//! - `node_extractors`: DRY utilities for extracting info from IR nodes/edges

pub mod id_generator;
pub mod node_extractors;
pub mod scope_stack;
pub mod tree_sitter;

// Re-exports for convenience
pub use node_extractors::{
    extract_variable_uses, extract_variables_for_function, extract_variables_for_ssa,
    find_function_by_name,
};
