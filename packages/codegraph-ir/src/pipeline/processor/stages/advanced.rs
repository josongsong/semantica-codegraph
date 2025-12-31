//! L6: Advanced Analyses - PDG, Taint, Points-to
//!
//! Extracted from processor_legacy.rs (lines 401-707)
//!
//! This stage handles:
//! - PDG (Program Dependence Graph) construction with petgraph
//! - SOTA taint analysis with field-sensitivity and sanitizer detection
//! - Points-to analysis (Andersen/Steensgaard)
//!
//! # Functions
//! - `run_taint_analysis()` - SOTA taint with quick check optimization (115 LOC)
//! - `run_points_to_analysis()` - Andersen/Steensgaard PTA (46 LOC)
//! - `build_pdg_summaries()` - PDG construction (58 LOC)
//!
//! # Helper Types
//! - `IRCallGraph` - Call graph adapter for taint analysis

use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;
use crate::features::flow_graph::infrastructure::{bfg::BasicFlowGraph, cfg::CFGEdge};
use crate::features::points_to::{
    AnalysisConfig as PTAConfig, AnalysisMode as PTAMode, PointsToAnalyzer,
};
use crate::features::taint_analysis::infrastructure::{
    interprocedural_taint::CallGraphProvider, // Use legacy trait that SOTATaintAnalyzer expects
    pta_ir_extractor::PTAIRExtractor,
    taint::{CallGraphNode, TaintAnalyzer},
    SOTAConfig,
    SOTATaintAnalyzer,
};
use crate::pipeline::processor::types::{PDGSummary, PointsToSummary, TaintSummary};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind};
use std::collections::{HashMap, HashSet};

/// Simple call graph wrapper implementing CallGraphProvider for SOTA analyzer
///
/// Extracts call relationships from IR nodes/edges for interprocedural taint analysis.
struct IRCallGraph {
    /// Function name -> list of callee names
    calls: HashMap<String, Vec<String>>,
    /// All function names
    functions: Vec<String>,
}

impl IRCallGraph {
    fn from_ir(nodes: &[Node], edges: &[Edge]) -> Self {
        let mut calls: HashMap<String, Vec<String>> = HashMap::new();
        let mut functions = Vec::new();

        // Collect all functions by name
        for node in nodes {
            if matches!(node.kind, NodeKind::Function | NodeKind::Method) {
                let name = node.name.clone().unwrap_or_default();
                if !name.is_empty() {
                    functions.push(name.clone());
                    calls.entry(name).or_insert_with(Vec::new);
                }
            }
        }

        // Build id -> name mapping for edge resolution
        let name_by_id: HashMap<&str, String> = nodes
            .iter()
            .filter(|n| matches!(n.kind, NodeKind::Function | NodeKind::Method))
            .filter_map(|n| n.name.as_ref().map(|name| (n.id.as_str(), name.clone())))
            .collect();

        // Add call relationships
        for edge in edges {
            if matches!(edge.kind, EdgeKind::Calls) {
                if let Some(caller_name) = name_by_id.get(edge.source_id.as_str()) {
                    // target_id might be a function name directly or an ID
                    let callee_name = name_by_id
                        .get(edge.target_id.as_str())
                        .cloned()
                        .unwrap_or_else(|| edge.target_id.clone());

                    if let Some(callees) = calls.get_mut(caller_name) {
                        if !callees.contains(&callee_name) {
                            callees.push(callee_name);
                        }
                    }
                }
            }
        }

        Self { calls, functions }
    }
}

impl CallGraphProvider for IRCallGraph {
    fn get_callees(&self, func_name: &str) -> Vec<String> {
        self.calls.get(func_name).cloned().unwrap_or_default()
    }

    fn get_functions(&self) -> Vec<String> {
        self.functions.clone()
    }
}

/// Run SOTA taint analysis on the codebase (L6)
///
/// Two-phase approach for performance:
/// 1. Quick check with basic analyzer (fast heuristic)
/// 2. If potential issues found, run SOTA analyzer (field-sensitive, sanitizer detection)
///
/// # SOTA Features
/// - Points-to analysis integration
/// - Field-sensitive tracking
/// - SSA-based precision
/// - Sanitizer detection
/// - Interprocedural analysis
///
/// # Arguments
/// * `nodes` - IR nodes
/// * `edges` - IR edges
///
/// # Returns
/// Vector of TaintSummary (typically 1 global summary)
pub fn run_taint_analysis(nodes: &[Node], edges: &[Edge]) -> Vec<TaintSummary> {
    // Quick check first using basic analyzer
    let mut legacy_call_graph: HashMap<String, CallGraphNode> = HashMap::new();
    for node in nodes {
        if matches!(node.kind, NodeKind::Function | NodeKind::Method) {
            let name = node.name.clone().unwrap_or_default();
            legacy_call_graph.insert(
                node.id.clone(),
                CallGraphNode {
                    id: node.id.clone(),
                    name: name.clone(),
                    callees: Vec::new(),
                },
            );
        }
    }
    for edge in edges {
        if matches!(edge.kind, EdgeKind::Calls) {
            if let Some(caller) = legacy_call_graph.get_mut(&edge.source_id) {
                caller.callees.push(edge.target_id.clone());
            }
        }
    }

    if legacy_call_graph.is_empty() {
        return Vec::new();
    }

    let basic_analyzer = TaintAnalyzer::new();
    let quick_result = basic_analyzer.quick_check(&legacy_call_graph);

    // If no potential issues found, return early
    if !quick_result.has_sources && !quick_result.has_sinks {
        return Vec::new();
    }

    // Build SOTA call graph and run full analysis
    let ir_call_graph = IRCallGraph::from_ir(nodes, edges);

    // Configure SOTA analyzer with production settings
    let sota_config = SOTAConfig {
        use_points_to: true,
        pta_mode: PTAMode::Auto,
        field_sensitive: true,
        use_ssa: true,
        detect_sanitizers: true,
        max_depth: 30,
        max_paths: 500,
    };

    let mut sota_analyzer = SOTATaintAnalyzer::new(ir_call_graph, sota_config);

    // Build source/sink maps from function names
    let mut sources: HashMap<String, HashSet<String>> = HashMap::new();
    let mut sinks: HashMap<String, HashSet<String>> = HashMap::new();

    for node in nodes {
        if !matches!(node.kind, NodeKind::Function | NodeKind::Method) {
            continue;
        }
        let Some(ref name) = node.name else { continue };
        let lower_name = name.to_lowercase();

        // Common source patterns (user input, external data)
        if lower_name.contains("input")
            || lower_name.contains("request")
            || lower_name.contains("read")
            || lower_name.contains("param")
            || lower_name.contains("user")
            || lower_name.contains("get_")
            || lower_name.contains("fetch")
            || lower_name.contains("recv")
        {
            sources.insert(name.clone(), HashSet::from(["0".to_string()]));
        }

        // Common sink patterns (dangerous operations)
        if lower_name.contains("exec")
            || lower_name.contains("query")
            || lower_name.contains("eval")
            || lower_name.contains("system")
            || lower_name.contains("write")
            || lower_name.contains("render")
            || lower_name.contains("html")
            || lower_name.contains("shell")
            || lower_name.contains("sql")
            || lower_name.contains("command")
        {
            sinks.insert(name.clone(), HashSet::from(["0".to_string()]));
        }
    }

    // Run SOTA analysis if we have sources and sinks
    let (taint_flows, sanitized_paths, sota_enabled) = if !sources.is_empty() && !sinks.is_empty() {
        let paths_before = quick_result.potential_vulnerabilities;
        let paths = sota_analyzer.analyze(&sources, &sinks);
        let stats = sota_analyzer.stats();

        let sanitized = if paths_before > paths.len() {
            paths_before - paths.len()
        } else {
            0
        };

        (
            paths.len(),
            sanitized,
            stats.points_to_enabled && stats.field_sensitive_enabled,
        )
    } else {
        (quick_result.potential_vulnerabilities, 0, false)
    };

    vec![TaintSummary {
        function_id: "global".to_string(),
        sources_found: sources
            .len()
            .max(if quick_result.has_sources { 1 } else { 0 }),
        sinks_found: sinks.len().max(if quick_result.has_sinks { 1 } else { 0 }),
        taint_flows,
        sota_enabled,
        sanitized_paths,
    }]
}

/// Run points-to analysis on the codebase (L6)
///
/// Integrates SOTA points-to analysis (Andersen/Steensgaard).
/// Auto mode selects best algorithm based on input size.
///
/// # Early Exit
/// - Skips if <5 nodes (not worth overhead)
/// - Skips if <2 constraints extracted
///
/// # Arguments
/// * `nodes` - IR nodes
/// * `edges` - IR edges
///
/// # Returns
/// Optional PointsToSummary with statistics
pub fn run_points_to_analysis(nodes: &[Node], edges: &[Edge]) -> Option<PointsToSummary> {
    // Skip if too few nodes (not worth the overhead)
    if nodes.len() < 5 {
        return None;
    }

    // Create PTA config - Fast mode (Steensgaard) after 13,771x optimization
    // After fixing critical bugs in Steensgaard (VarId iteration + UnionFind explosion),
    // Fast mode is now production-ready with excellent performance
    let config = PTAConfig {
        mode: PTAMode::Fast,    // ✅ Steensgaard: O(n·α(n)), 13,771x faster!
        field_sensitive: false, // ✅ Faster, acceptable precision loss
        max_iterations: 10,     // For Andersen fallback (shouldn't be used)
        auto_threshold: 10000,
        enable_scc: true,
        enable_wave: false,     // Not applicable for Steensgaard
        enable_parallel: false, // Disable parallel for per-file analysis
    };

    let mut analyzer = PointsToAnalyzer::new(config);
    let mut extractor = PTAIRExtractor::new();

    // Extract constraints from IR
    let constraint_count = extractor.extract_constraints(nodes, edges, &mut analyzer);

    // Skip if no meaningful constraints
    if constraint_count < 2 {
        return None;
    }

    // Solve points-to graph
    let result = analyzer.solve();

    // Calculate alias pairs (simplified - count non-trivial alias relationships)
    let alias_pairs = result.graph.stats.total_edges;

    Some(PointsToSummary {
        variables_count: result.stats.variables,
        allocations_count: result.stats.locations,
        constraints_count: result.stats.constraints_total,
        alias_pairs,
        mode_used: format!("{:?}", result.mode_used),
        duration_ms: result.stats.duration_ms,
    })
}

/// Build PDG summaries using SOTA petgraph-based PDGBuilder (L6)
///
/// Constructs actual ProgramDependenceGraph for each function.
/// Combines control dependencies (from CFG) and data dependencies (from DFG).
///
/// # Arguments
/// * `dfg_graphs` - Data flow graphs
/// * `cfg_edges` - Control flow edges
/// * `bfg_graphs` - Basic flow graphs (for node structure)
///
/// # Returns
/// Vector of PDGSummary with statistics
pub fn build_pdg_summaries(
    dfg_graphs: &[DataFlowGraph],
    cfg_edges: &[CFGEdge],
    bfg_graphs: &[BasicFlowGraph],
) -> Vec<PDGSummary> {
    use crate::features::pdg::infrastructure::pdg::{PDGBuilder, PDGNode};

    let mut summaries = Vec::new();

    for bfg in bfg_graphs {
        // Create PDGBuilder for this function
        let mut builder = PDGBuilder::new();

        // Add nodes from BFG blocks
        for block in &bfg.blocks {
            let span = block.span_ref.span;
            let pdg_node =
                PDGNode::new(block.id.clone(), block.kind.clone(), span.start_line, span)
                    .with_entry_exit(block.id.contains("entry"), block.id.contains("exit"));
            builder.add_node(pdg_node);
        }

        // Filter CFG edges for this function and add control dependencies
        let func_cfg_edges: Vec<_> = cfg_edges
            .iter()
            .filter(|e| e.source_block_id.contains(&bfg.function_id))
            .cloned()
            .collect();
        builder.add_cfg_edges(func_cfg_edges);

        // Find corresponding DFG and add data dependencies
        if let Some(dfg) = dfg_graphs.iter().find(|d| d.function_id == bfg.function_id) {
            builder.add_dfg(dfg);
        }

        // Build the actual PDG using petgraph
        let pdg = builder.build(bfg.function_id.clone());
        let stats = pdg.get_stats();

        summaries.push(PDGSummary {
            function_id: bfg.function_id.clone(),
            node_count: stats.node_count,
            control_edges: stats.control_edges,
            data_edges: stats.data_edges,
            petgraph_enabled: true,
            total_edges: stats.edge_count,
        });
    }

    summaries
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    #[test]
    fn test_taint_analysis_empty() {
        let nodes = vec![];
        let edges = vec![];

        let summaries = run_taint_analysis(&nodes, &edges);

        // No functions → empty
        assert_eq!(summaries.len(), 0);
    }

    #[test]
    fn test_points_to_analysis_too_few_nodes() {
        let nodes = vec![Node::new(
            "func:test".to_string(),
            NodeKind::Function,
            "test".to_string(),    // fqn
            "test.py".to_string(), // file_path
            Span::new(1, 0, 1, 10),
        )];
        let edges = vec![];

        let result = run_points_to_analysis(&nodes, &edges);

        // <5 nodes → None
        assert_eq!(result, None);
    }

    #[test]
    fn test_build_pdg_summaries_empty() {
        let dfgs = vec![];
        let cfg_edges = vec![];
        let bfgs = vec![];

        let summaries = build_pdg_summaries(&dfgs, &cfg_edges, &bfgs);

        assert_eq!(summaries.len(), 0);
    }

    #[test]
    fn test_ir_call_graph_from_ir() {
        let mut func1 = Node::new(
            "func:caller".to_string(),
            NodeKind::Function,
            "caller".to_string(),  // fqn
            "test.py".to_string(), // file_path
            Span::new(1, 0, 1, 10),
        );
        func1.name = Some("caller".to_string()); // Set name for IRCallGraph

        let mut func2 = Node::new(
            "func:callee".to_string(),
            NodeKind::Function,
            "callee".to_string(),  // fqn
            "test.py".to_string(), // file_path
            Span::new(2, 0, 2, 10),
        );
        func2.name = Some("callee".to_string()); // Set name for IRCallGraph

        let nodes = vec![func1, func2];

        let call_edge = Edge::new(
            "func:caller".to_string(),
            "func:callee".to_string(),
            EdgeKind::Calls,
        );

        let edges = vec![call_edge];

        let graph = IRCallGraph::from_ir(&nodes, &edges);

        assert_eq!(graph.functions.len(), 2);
        assert!(graph.functions.contains(&"caller".to_string()));
        assert!(graph.functions.contains(&"callee".to_string()));

        let callees = graph.get_callees("caller");
        assert_eq!(callees.len(), 1);
        assert_eq!(callees[0], "callee");
    }
}
