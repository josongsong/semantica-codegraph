//! PyO3 adapter - Python bindings
//!
//! SOTA: Unified type conversion between Rust and Python.
//!
//! Modules:
//! - `convertible`: ToPyDict/FromPyDict traits for all IR types
//! - `converters`: Legacy converters (TODO: migrate to convertible)
//! - `bindings`: PyO3 function bindings (TODO: populate)

pub mod api;
mod bindings;
pub mod concurrency_bindings; // Concurrency Analysis bindings (Race/Deadlock detection)
mod converters;
pub mod convertible;
pub mod effect_bindings; // Effect Analysis bindings (Purity tracking)
#[cfg(feature = "sqlite")]
pub mod taint_advanced; // Advanced Taint Analysis bindings (RFC-ADVANCED-TAINT) - requires SQLite
pub mod trcr_bindings; // TRCR (Taint Rule Compiler & Runtime) bindings - 488 atoms + CWE rules

// Re-exports for convenience
pub use convertible::{
    extract_span_from_dict, results_to_py_list, span_to_py_dict, strings_to_py_list,
    vec_to_py_list, FromPyDict, ToPyDict, ToPyList,
};
