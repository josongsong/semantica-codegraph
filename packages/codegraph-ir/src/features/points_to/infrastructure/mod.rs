//! Infrastructure layer for Points-to Analysis
//!
//! SOTA algorithm implementations and optimizations:
//! - **UnionFind**: O(α(n)) disjoint set operations
//! - **SparseBitmap**: Deferred sorting + batch operations (SOTA)
//! - **AndersenSolver**: Field-sensitive inclusion-based solver
//! - **SteensgaardSolver**: Fast equality-based solver
//! - **FlowSensitivePTA**: LOAD/STORE with strong/weak updates
//! - **WavePropagation**: LCD + topological ordering (SOTA)
//! - **ContextSensitive**: Object sensitivity + heap cloning (SOTA)

pub mod union_find;
pub mod sparse_bitmap;
pub mod andersen_solver;
pub mod steensgaard_solver;
pub mod wave_propagation;
pub mod scc_detector;
pub mod flow_sensitive_solver;
pub mod context_sensitive;
pub mod demand_driven;
pub mod incremental_pta;
// pub mod parallel_andersen;  // Disabled: missing crossbeam dependency

pub use union_find::UnionFind;
pub use sparse_bitmap::SparseBitmap;
pub use andersen_solver::{AndersenSolver, AndersenConfig, AndersenResult, AndersenStats, ParallelAndersenSolver};
pub use steensgaard_solver::SteensgaardSolver;
pub use flow_sensitive_solver::{FlowSensitivePTA, FlowSensitiveResult, AnalysisStats};
pub use context_sensitive::{
    ContextSensitiveSolver, ContextSensitiveConfig, ContextSensitiveResult,
    ContextStrategy, Context, ContextVar, HeapObject,
};
pub use wave_propagation::{LazyCycleDetector, WaveWorklist, WaveOrder};
