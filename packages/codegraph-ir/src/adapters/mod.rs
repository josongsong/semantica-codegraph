//! Inbound adapters - external systems connecting to our application
//!
//! Currently: PyO3 (Python bindings)
//! Future: CLI, gRPC, HTTP, etc.

#[cfg(feature = "python")]
pub mod pyo3;
