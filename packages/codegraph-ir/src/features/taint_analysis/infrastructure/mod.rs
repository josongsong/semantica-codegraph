//! Taint Analysis infrastructure
//!
//! SOTA-grade taint analysis combining multiple academic techniques:
//! - Interprocedural analysis (context-sensitive)
//! - Points-to analysis (Andersen + Steensgaard) - 4,113 LOC
//! - Field-sensitive tracking
//! - SSA-based precision
//! - Sanitizer detection
//! - CFG/DFG integration

pub mod alias_analyzer; // Alias analysis engine
pub mod call_graph_builder; // IR integration
pub mod ide_framework; // IDE value propagation framework (SOTA)
pub mod ide_solver; // IDE tabulation solver (SOTA)
pub mod ifds_framework; // IFDS/IDE dataflow framework (SOTA)
pub mod ifds_ide_integration; // Integration examples and production patterns
pub mod ifds_solver; // IFDS tabulation algorithm (SOTA)
pub mod interprocedural; // SOTA: Refactored interprocedural taint (5 modules)
pub mod interprocedural_errors; // Error types
pub mod interprocedural_taint; // Legacy: kept for backward compatibility (test migration pending)
pub mod pta_ir_extractor; // Points-to constraint extraction from IR
pub mod sota_taint_analyzer; // COMPLETE SOTA integration
pub mod sparse_ifds;
pub mod taint;
pub mod type_narrowing; // Type narrowing engine
pub mod worklist_solver; // Fixpoint iteration engine // Sparse IFDS optimization (SOTA: 2-10x speedup)

// ✨ Advanced Taint Analysis (RFC-ADVANCED-TAINT)
pub mod backward_taint; // 🆕 Backward taint propagation (sink → source)
pub mod field_sensitive; // Field-level taint tracking
pub mod implicit_flow; // 🆕 Implicit flow analysis (control dependency taint)
pub mod path_condition_converter; // Bridge between Taint and SMT path conditions
pub mod path_sensitive; // Path-aware taint tracking
pub mod security_lattice; // Security Lattice + Non-interference (SOTA)

// 🆕 Differential Taint Analysis (RFC-001-IN-DEVELOPMENT)
pub mod differential; // Security regression detection

pub use taint::*;

// SOTA: Use refactored interprocedural module (primary)
pub use interprocedural::{
    CallContext, CallGraphProvider, FunctionSummary, InterproceduralTaintAnalyzer, SimpleCallGraph,
    TaintPath as InterproceduralTaintPath,
};

// Legacy re-exports (backward compatibility - will be removed in v3.0)
// Migration: Use `interprocedural` module instead
pub use call_graph_builder::*;
pub use interprocedural_errors::*;
pub use interprocedural_taint::{
    CallContext as LegacyCallContext, CallGraphProvider as LegacyCallGraphProvider,
    FunctionSummary as LegacyFunctionSummary,
    InterproceduralTaintAnalyzer as LegacyInterproceduralTaintAnalyzer,
};
pub use pta_ir_extractor::*;
pub use sota_taint_analyzer::*;

// Advanced taint exports
pub use alias_analyzer::{Alias, AliasAnalyzer, AliasSet, AliasStatistics, AliasType};
pub use backward_taint::{
    BackwardAssignFlow, BackwardIdentityFlow, BackwardTaintAnalyzer, BackwardTaintConfig,
    BackwardTaintFact, BackwardTaintPath, BackwardTaintStats,
};
pub use field_sensitive::{
    FieldIdentifier, FieldSensitiveTaintAnalyzer, FieldSensitiveVulnerability, FieldTaintState,
};
pub use ide_framework::{
    AllTopEdgeFunction, ConstantEdgeFunction, EdgeFunction, IDEProblem, IDEStatistics, IDEValue,
    IdentityEdgeFunction, JumpFunction, MicroFunction,
};
pub use ide_solver::{IDESolver, IDESolverResult};
pub use ifds_framework::{
    DataflowFact, ExplodedEdge, ExplodedEdgeKind, ExplodedNode, ExplodedSupergraph, FlowFunction,
    IFDSProblem, IFDSStatistics, IdentityFlowFunction, PathEdge, SummaryEdge,
};
pub use ifds_solver::{
    CFGEdge,
    CFGEdgeKind,
    IFDSSolver,
    IFDSSolverResult,
    CFG as IFDSCFG, // Renamed to avoid conflict with worklist_solver::CFG
};
pub use implicit_flow::{
    ControlDependency, ControlDependencyGraph, ImplicitFlowAnalyzer, ImplicitFlowConfig,
    ImplicitFlowSeverity, ImplicitFlowStats, ImplicitFlowVulnerability, ImplicitTaintSource,
    ImplicitTaintState,
};
pub use path_condition_converter::{convert_batch, convert_to_smt, ConversionResult};
pub use path_sensitive::{
    PathCondition, PathSensitiveTaintAnalyzer, PathSensitiveTaintState, PathSensitiveVulnerability,
};
pub use sparse_ifds::{
    taint_relevance_function, NodeRelevance, SparseCFG, SparseCFGStats, SparseEdge,
    SparseIFDSSolver, SparseIFDSStats, SparseNode,
};
pub use type_narrowing::{
    TypeConstraint, TypeNarrowingAnalyzer, TypeNarrowingInfo, TypeNarrowingKind, TypeState,
};
pub use worklist_solver::{CFGNode, TaintFact, WorklistTaintSolver, CFG};

// Security Lattice exports (SOTA: Non-interference)
pub use security_lattice::{
    ConfidentialityLevel, FlowViolation, IntegrityLevel, NonInterferenceChecker,
    SecurityAnnotation, SecurityContext, SecurityLabel, SecurityTypeInference,
};

// Differential taint exports
pub use differential::{
    CIExitCode,
    ChangeType,
    ChangedFile,
    DiffStats,
    DifferentialTaintAnalyzer,
    DifferentialTaintResult,
    GitDiffConfig,
    // Git Integration
    GitDifferentialAnalyzer,
    GitHubActionsReporter,
    GitLabCIReporter,
    // CI/CD Integration
    PRCommentFormatter,
    PartialFix,
    SanitizerInfo,
    SarifReport,
    Severity,
    TaintSink,
    TaintSource,
    Vulnerability,
    VulnerabilityCategory,
};
