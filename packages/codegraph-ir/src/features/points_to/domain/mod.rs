//! Domain models for Points-to Analysis
//!
//! Core abstractions independent of analysis algorithm:
//! - AbstractLocation: Heap allocation site abstraction
//! - PointsToGraph: Points-to relation representation
//! - Constraint: Analysis constraints (ALLOC, COPY, LOAD, STORE)
//! - FlowState: Flow-sensitive analysis state (RFC-002)

pub mod abstract_location;
pub mod constraint;
pub mod flow_state;
pub mod points_to_graph;

pub use abstract_location::AbstractLocation;
pub use constraint::{Constraint, ConstraintKind};
pub use flow_state::{FlowState, LocationSet, ProgramPoint, UpdateKind};
pub use points_to_graph::PointsToGraph;
