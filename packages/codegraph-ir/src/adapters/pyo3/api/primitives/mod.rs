//! RFC-071: Analysis Primitives API
//!
//! SOTA 2025: Mathematically Complete Static Analysis Primitives
//!
//! This module implements the 5 fundamental analysis primitives:
//! - P1: REACH   - Graph Reachability (Euler 1736)
//! - P2: FIXPOINT - Fixed-Point Iteration (Tarski 1955)
//! - P3: PROPAGATE - Abstract Value Propagation (Cousot 1977)
//! - P4: CONTEXT - Context-Sensitive Analysis (Shivers 1991)
//! - P5: RESOLVE - Symbol Resolution (Church 1936)
//!
//! Architecture:
//! - AnalysisSession: Stateful handle keeping IR in Rust memory
//! - Recipe System: Batch primitive execution for FFI minimization
//! - Lazy Result Access: On-demand results for large datasets
//!
//! Performance Targets:
//! - Session creation: < 10ms (Python → Rust)
//! - REACH: 10-50x faster than Python
//! - FIXPOINT: 5-20x faster
//! - Recipe execution: Single FFI call for complex analyses

pub mod session;
pub mod reach;
pub mod resolve;
pub mod fixpoint;
pub mod propagate;
pub mod context;

// Re-exports
pub use session::{AnalysisSession, SessionConfig, SessionStats};
pub use reach::{ReachDirection, ReachResult, GraphType};
pub use resolve::{ResolveQuery, ResolveResult};
pub use fixpoint::{
    Lattice, PowerSetLattice, FlatLattice, IntervalLattice,
    FixpointConfig, FixpointResult, FixpointEngine,
    reaching_definitions, live_variables,
};
pub use propagate::{
    AbstractValue, TaintDomain, NullnessDomain, SignDomain,
    PropagationConfig, PropagationResult, PropagationEngine,
    Diagnostic, DiagnosticKind, PropagationStats,
    taint_analysis, null_analysis, sign_analysis,
};
pub use context::{
    ContextStrategy, CallContext, ContextValue, ContextConfig,
    ContextResult, ContextualizedNode, ContextualizedEdge, ContextStats,
    SelectiveHeuristics,
    with_context, zero_cfa, one_cfa, two_cfa, object_sensitive, type_sensitive,
};
