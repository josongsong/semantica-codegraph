//! # SOTA Points-to Analysis Module
//!
//! High-performance pointer analysis implementation combining:
//! - **Steensgaard's Algorithm**: O(n·α(n)) fast approximation using Union-Find
//! - **Andersen's Algorithm**: O(n²) precise inclusion-based analysis with SCC optimization
//! - **Wave Propagation**: Topological ordering for efficient fixpoint computation
//! - **Sparse Bitmaps**: Memory-efficient points-to set representation
//!
//! ## Academic References
//! - Steensgaard, B. "Points-to Analysis in Almost Linear Time" (POPL 1996)
//! - Andersen, L. O. "Program Analysis and Specialization for C" (PhD 1994)
//! - Pearce et al. "Efficient Field-Sensitive Pointer Analysis" (CC 2004)
//! - Hardekopf & Lin "The Ant and the Grasshopper" (PLDI 2007)
//! - Yu et al. "SHARP: Fast Incremental Context-Sensitive Pointer Analysis" (OOPSLA 2022)
//!
//! ## Performance Targets
//! - 10-50x faster than Python implementation
//! - ~100K variables/second on single core
//! - ~500K variables/second with parallel processing
//!
//! ## Usage
//! ```text
//! use codegraph_ir::features::points_to::{PointsToAnalyzer, AnalysisConfig};
//!
//! let config = AnalysisConfig::default();
//! let mut analyzer = PointsToAnalyzer::new(config);
//!
//! // Add constraints
//! analyzer.add_alloc("x", "alloc:1:T");
//! analyzer.add_copy("y", "x");
//!
//! // Solve and get results
//! let graph = analyzer.solve();
//! assert!(graph.may_alias("x", "y"));
//! ```

pub mod application;
pub mod domain;
pub mod infrastructure;
pub mod ports;

// Re-exports for public API
pub use application::analyzer::{AnalysisConfig, AnalysisMode, PointsToAnalyzer};
pub use domain::abstract_location::AbstractLocation;
pub use domain::constraint::{Constraint, ConstraintKind};
pub use domain::points_to_graph::PointsToGraph;
// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::andersen_solver::AndersenSolver;
#[doc(hidden)]
pub use infrastructure::sparse_bitmap::SparseBitmap;
#[doc(hidden)]
pub use infrastructure::steensgaard_solver::SteensgaardSolver;
#[doc(hidden)]
pub use infrastructure::union_find::UnionFind;
