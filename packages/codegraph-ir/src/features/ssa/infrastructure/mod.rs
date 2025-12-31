//! SSA infrastructure
//!
//! Contains both the simple SSA implementation (currently used in pipeline)
//! and SOTA algorithms (Braun 2013, Sparse SSA) for future integration.

pub mod ssa;

// SOTA algorithms - available for direct use via API
pub mod braun_ssa_builder;
pub mod cfg_adapter;
pub mod errors;
pub mod phi_optimizer;
pub mod sparse_ssa_builder;

pub use ssa::*;

// Re-export SOTA types for direct API access
pub use braun_ssa_builder::{BraunSSABuilder, CFGProvider};
pub use cfg_adapter::BFGCFGAdapter;
pub use errors::*;
pub use phi_optimizer::*;
pub use sparse_ssa_builder::SparseSSABuilder;
