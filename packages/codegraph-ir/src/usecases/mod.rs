//! Usecase Layer - High-level operations for indexing triggers
//!
//! This module provides clean, idiomatic Rust APIs for triggering
//! full and incremental indexing operations. These are designed to
//! be called by:
//! - Git Hooks handlers
//! - Scheduler jobs
//! - Manual trigger APIs
//! - Cold Start initialization
//!
//! NOT for direct Python consumption - use PyO3 bindings in lib.rs instead.

pub mod indexing_service;

// Re-export main API
pub use indexing_service::{IndexingRequest, IndexingResult, IndexingService};
