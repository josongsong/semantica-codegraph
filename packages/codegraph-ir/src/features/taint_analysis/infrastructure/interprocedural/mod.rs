/*
 * Interprocedural Taint Analysis Module
 *
 * Tracks taint flow across function calls and file boundaries.
 *
 * SOTA Algorithm: Context-Sensitive Interprocedural Analysis
 * - Bottom-up summary computation (callees first)
 * - Top-down taint propagation with contexts
 * - Worklist-based fixpoint iteration
 * - Circular call detection with Tarjan's SCC algorithm
 *
 * Architecture:
 * - context.rs: Call contexts for context-sensitive analysis
 * - taint_path.rs: Taint propagation path tracking
 * - summary.rs: Function summaries (field-sensitive)
 * - call_graph.rs: Call graph protocol (trait + implementation)
 * - analyzer.rs: Main interprocedural analysis engine
 *
 * Reference:
 * - Python implementation: interprocedural_taint.py (2,110 lines)
 * - "Inter-procedural Data Flow Analysis" (Sharir & Pnueli, 1981)
 * - "Context-Sensitive Taint Analysis" (Tripp et al., 2009)
 */

mod analyzer;
mod call_graph;
mod context;
mod summary;
mod taint_path;

// Re-export public API
pub use analyzer::InterproceduralTaintAnalyzer;
pub use call_graph::{CallGraphProvider, SimpleCallGraph};
pub use context::CallContext;
pub use summary::FunctionSummary;
pub use taint_path::TaintPath;
