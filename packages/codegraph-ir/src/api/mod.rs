//! Language-Agnostic Core API
//!
//! This module provides pure Rust APIs that can be wrapped by any language binding.
//! All APIs are designed to be FFI-friendly and avoid language-specific types.

pub mod graph_query;

pub use graph_query::{GraphQuery, GraphStats, QueryFilter};
