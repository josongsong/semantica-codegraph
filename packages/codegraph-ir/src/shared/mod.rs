//! Shared module - Common types and utilities
//!
//! This module contains types that are shared across all features.
//! It has ZERO external dependencies (no tree-sitter, PyO3, etc.)

#[macro_use]
pub mod macros;
pub mod constants;
pub mod models;
pub mod parallel_optimizer;
pub mod ports;
pub mod utils;

// Re-exports for convenience
pub use models::*;
pub use parallel_optimizer::{
    global_optimizer, init_global_optimizer, AdaptiveThreadPoolOptimizer, WorkloadConfig,
    WorkloadProfiler,
};
pub use utils::id_generator::IdGenerator;
pub use utils::scope_stack::ScopeStack;
