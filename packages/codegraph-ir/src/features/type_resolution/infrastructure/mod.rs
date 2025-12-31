//! Type Resolution infrastructure
//!
//! Contains both the simple type resolver (currently used in pipeline)
//! and SOTA Hindley-Milner constraint solver for future integration.

pub mod type_resolver;

// SOTA: Constraint-based type inference (Hindley-Milner)
pub mod constraint_solver;
pub mod inference_engine;
pub mod signature_cache;
pub mod type_narrowing;

pub use type_resolver::*;

// Re-export SOTA types for direct API access
pub use constraint_solver::{Constraint, ConstraintSolver, InferType, SolverError, Substitution};
