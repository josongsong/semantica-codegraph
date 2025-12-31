//! PyO3 API Bindings
//!
//! SOTA 2025: TypeSpec-driven API implementation
//!
//! This module implements the Codegraph Analysis API as defined in:
//! `typespec/operations/*.tsp`
//!
//! All functions follow the msgpack-first principle:
//! - Input: msgpack bytes (zero-copy from Python)
//! - Output: msgpack bytes (zero-copy to Python)
//! - GIL released during computation (true parallelism)

pub mod config;
pub mod graph_builder;
pub mod ir_processor;
pub mod query;
pub mod slice;
pub mod streaming;
pub mod taint;
// TEMPORARILY DISABLED: compilation errors preventing testing
// pub mod clone_detection;
pub mod rust_query_engine;
// pub mod lexical;  // TEMPORARILY DISABLED: SqliteChunkStore compilation error

// Re-export all pyfunction for lib.rs registration
pub use config::*;
pub use graph_builder::*;
pub use ir_processor::*;
pub use query::*;
pub use slice::*;
pub use streaming::*;
pub use taint::*;
// pub use clone_detection::*;
pub use rust_query_engine::*;
// pub use lexical::*;  // TEMPORARILY DISABLED
