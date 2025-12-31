//! Common test utilities for codegraph-ir
//!
//! This module provides shared fixtures, assertions, and builders
//! for integration and end-to-end tests.

mod fixtures;
mod assertions;
mod builders;

// Re-export all utilities
pub use fixtures::*;
pub use assertions::*;
pub use builders::*;
