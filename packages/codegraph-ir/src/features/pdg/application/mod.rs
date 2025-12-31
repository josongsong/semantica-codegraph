//! PDG Application Layer
//!
//! Use cases for Program Dependence Graph.
//! Implementation: see `infrastructure/pdg.rs` (1,207 LOC)
//!
//! Main entry point: `ProgramDependenceGraph::new()`

pub use crate::features::pdg::infrastructure::{
    DependencyType, PDGEdge, PDGNode, ProgramDependenceGraph,
};
