/*
 * Infrastructure Layer - External dependencies
 *
 * HEXAGONAL ARCHITECTURE:
 * - Implements domain ports
 * - tree-sitter, PyO3, Rayon
 * - Adapters for external systems
 */

pub mod tree_sitter_adapter;
pub mod python_adapter;

pub use tree_sitter_adapter::TreeSitterParser;
pub use python_adapter::init_rayon;

