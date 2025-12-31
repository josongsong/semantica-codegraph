//! Process result and summary types
//!
//! All type definitions for the processor pipeline (L1-L7).
//! Moved from processor_legacy.rs during Phase 4 cleanup.

use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;
use crate::features::flow_graph::infrastructure::{bfg::BasicFlowGraph, cfg::CFGEdge};
use crate::features::heap_analysis::{
    FunctionEscapeInfo, MemorySafetyIssue, SecurityVulnerability,
};
use crate::features::ssa::infrastructure::ssa::SSAGraph;
use crate::features::type_resolution::domain::TypeEntity;
use crate::shared::models::{Edge, Node, Occurrence};

/// Process result (L1-L7 complete pipeline)
///
/// Contains all analysis results from the complete code analysis pipeline.
///
/// # Pipeline Stages
/// - **L1-L2**: IR generation (nodes, edges, occurrences)
/// - **L3**: Flow graphs + type resolution (BFG, CFG, types)
/// - **L4-L5**: Data flow + SSA (DFG, SSA graphs)
/// - **L6**: Advanced analyses (PDG, taint, points-to, slicing)
/// - **L7**: Heap analysis (memory safety, security)
#[derive(Debug, Clone, Default)]
pub struct ProcessResult {
    // L1-L2: IR
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,

    // 🚀 SOTA: Occurrences generated in L1 (instead of Python L2)
    pub occurrences: Vec<Occurrence>,

    // L3: Flow + Types
    pub bfg_graphs: Vec<BasicFlowGraph>,
    pub cfg_edges: Vec<CFGEdge>,
    pub type_entities: Vec<TypeEntity>,

    // L4-L5: Data Flow + SSA
    pub dfg_graphs: Vec<DataFlowGraph>,
    pub ssa_graphs: Vec<SSAGraph>,

    // L6: Advanced Analysis
    pub pdg_graphs: Vec<PDGSummary>,
    pub taint_results: Vec<TaintSummary>,
    pub slice_results: Vec<SliceSummary>,
    pub points_to_result: Option<PointsToSummary>,

    // L7: Heap Analysis (SOTA Memory Safety & Security & Escape)
    pub memory_safety_issues: Vec<MemorySafetyIssue>,
    pub security_vulnerabilities: Vec<SecurityVulnerability>,

    /// RFC-074: Escape Analysis results (per-function)
    /// Used by concurrency analyzer to reduce FP by 40-60%
    pub escape_info: Vec<FunctionEscapeInfo>,

    pub errors: Vec<String>,
}

impl ProcessResult {
    /// Create empty result with errors (for early failure cases)
    ///
    /// Used when parsing or language detection fails before any analysis can run.
    ///
    /// # Arguments
    /// * `errors` - Error messages to include in result
    ///
    /// # Returns
    /// ProcessResult with all fields empty except errors
    pub fn empty_with_errors(errors: Vec<String>) -> Self {
        Self {
            nodes: Vec::new(),
            edges: Vec::new(),
            occurrences: Vec::new(),
            bfg_graphs: Vec::new(),
            cfg_edges: Vec::new(),
            type_entities: Vec::new(),
            dfg_graphs: Vec::new(),
            ssa_graphs: Vec::new(),
            pdg_graphs: Vec::new(),
            taint_results: Vec::new(),
            slice_results: Vec::new(),
            points_to_result: None,
            memory_safety_issues: Vec::new(),
            security_vulnerabilities: Vec::new(),
            escape_info: Vec::new(),
            errors,
        }
    }
}

/// PDG summary for Python serialization (SOTA petgraph-based)
///
/// Statistics about Program Dependence Graph construction for a function.
///
/// # SOTA Features
/// - Petgraph-based construction (O(V+E) slicing)
/// - Combined control + data dependencies
/// - Entry/exit node tracking
#[derive(Debug, Clone)]
pub struct PDGSummary {
    pub function_id: String,
    pub node_count: usize,
    pub control_edges: usize,
    pub data_edges: usize,
    /// Whether petgraph-based PDG was constructed
    pub petgraph_enabled: bool,
    /// Total edge count (control + data)
    pub total_edges: usize,
}

/// Taint analysis summary (SOTA-enhanced)
///
/// Results from interprocedural taint analysis.
///
/// # SOTA Features
/// - Field-sensitive tracking
/// - Sanitizer detection (reduces false positives)
/// - Quick check optimization (2-phase analysis)
/// - Context-sensitive interprocedural analysis
#[derive(Debug, Clone)]
pub struct TaintSummary {
    pub function_id: String,
    pub sources_found: usize,
    pub sinks_found: usize,
    pub taint_flows: usize,
    /// Whether SOTA analyzer was used (field-sensitive, sanitizer detection)
    pub sota_enabled: bool,
    /// Number of paths filtered by sanitizer detection
    pub sanitized_paths: usize,
}

/// Slice summary
///
/// Results from program slicing (computed on-demand via API).
///
/// # Usage
/// Slicing is not computed during pipeline - use PDG API for on-demand slicing.
#[derive(Debug, Clone)]
pub struct SliceSummary {
    pub function_id: String,
    pub criterion: String,
    pub slice_size: usize,
}

/// Points-to analysis summary
///
/// Statistics from points-to analysis (Andersen/Steensgaard).
///
/// # Analysis Modes
/// - **Fast**: Steensgaard (O(N log N), less precise)
/// - **Precise**: Andersen (O(N³), highly precise)
/// - **Hybrid**: Auto-switch based on size
/// - **Auto**: Selects best mode based on input size
#[derive(Debug, Clone, PartialEq)]
pub struct PointsToSummary {
    /// Number of variables analyzed
    pub variables_count: usize,
    /// Number of allocation sites
    pub allocations_count: usize,
    /// Number of constraints processed
    pub constraints_count: usize,
    /// Number of may-alias pairs
    pub alias_pairs: usize,
    /// Analysis mode used (Fast, Precise, Hybrid, Auto)
    pub mode_used: String,
    /// Analysis duration in milliseconds
    pub duration_ms: f64,
}
