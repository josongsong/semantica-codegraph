//! IR Generation Feature (L2)
pub mod application;
pub mod domain;
pub mod infrastructure;
pub mod ports;

// Re-export for query_engine
pub use domain::ir_document;
