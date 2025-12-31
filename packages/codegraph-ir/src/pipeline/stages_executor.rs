//! Pipeline Stages Executor
//!
//! SOTA Design: Each stage is a separate, testable module.
//! This eliminates the "God Object" anti-pattern from processor.rs.
//!
//! Benefits:
//! - Single Responsibility: Each executor does one thing
//! - Open/Closed: Easy to add new stages
//! - Testable: Mock dependencies for each stage
//! - Composable: Orchestrator combines stages

use crate::features::data_flow::domain::DataFlowGraph;
use crate::features::flow_graph::domain::{BasicFlowGraph, CFGEdge};
use crate::features::ssa::domain::SSAGraph;
use crate::shared::models::Occurrence;
use crate::shared::utils::{
    extract_variable_uses, extract_variables_for_function, extract_variables_for_ssa,
    find_function_by_name,
};
use crate::shared::models::{Edge, Node};
use std::time::{Duration, Instant};

/// Result from a stage execution
pub struct StageResult<T> {
    pub output: T,
    pub duration: Duration,
    pub errors: Vec<String>,
}

impl<T> StageResult<T> {
    pub fn new(output: T, duration: Duration) -> Self {
        Self {
            output,
            duration,
            errors: Vec::new(),
        }
    }

    pub fn with_errors(mut self, errors: Vec<String>) -> Self {
        self.errors = errors;
        self
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// L4: Data Flow Stage
// ═══════════════════════════════════════════════════════════════════════════
//
// NOTE: L3 Flow Graph extraction is implemented in processor.rs via extract_bfg_graphs()
// This stage executor architecture is for future modularization when we separate
// BFG extraction from the main processor into its own stage executor.

/// L4 Data Flow Executor
///
/// Builds def-use chains and data flow graph.
pub struct DataFlowExecutor;

impl DataFlowExecutor {
    pub fn execute(
        &self,
        nodes: &[Node],
        edges: &[Edge],
        bfg_graphs: &[BasicFlowGraph],
        _cfg_edges: &[CFGEdge],
    ) -> StageResult<Vec<DataFlowGraph>> {
        let start = Instant::now();

        let mut dfg_graphs = Vec::new();

        // For each function, extract variables and build DFG using shared utilities
        for bfg in bfg_graphs {
            // Find function node by name using shared utility
            let Some(func) = find_function_by_name(nodes, &bfg.function_id) else {
                // Function not found - create empty DFG
                let empty_dfg = crate::features::data_flow::infrastructure::dfg::build_dfg(
                    bfg.function_id.clone(),
                    &[],
                    &[],
                );
                dfg_graphs.push(empty_dfg.into());
                continue;
            };

            let func_id = &func.id;

            // Extract definitions using shared utility
            let definitions = extract_variables_for_function(nodes, func_id);

            // Extract uses using shared utility
            let uses = extract_variable_uses(edges, func_id);

            // Build DFG
            let dfg = crate::features::data_flow::infrastructure::dfg::build_dfg(
                bfg.function_id.clone(),
                &definitions,
                &uses,
            );

            // Convert infrastructure to domain type
            dfg_graphs.push(dfg.into());
        }

        StageResult::new(dfg_graphs, start.elapsed())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// L5: SSA Stage (SOTA: Braun-inspired CFG-based Phi Insertion)
// ═══════════════════════════════════════════════════════════════════════════

use crate::features::ssa::infrastructure::cfg_adapter::BFGCFGAdapter;
use crate::features::ssa::infrastructure::braun_ssa_builder::CFGProvider;
use crate::features::ssa::domain::{SSAVariable, PhiNode};
use std::collections::HashSet;

/// L5 SSA Executor (SOTA: Braun 2013-inspired)
///
/// Uses CFG structure for accurate Phi node placement.
/// Key insight from Braun: Phi nodes at merge points (blocks with multiple predecessors).
pub struct SSAExecutor;

impl SSAExecutor {
    pub fn execute(
        &self,
        nodes: &[Node],
        _edges: &[Edge],
        _dfg_graphs: &[DataFlowGraph],
        bfg_graphs: &[BasicFlowGraph],
        cfg_edges: &[CFGEdge],
    ) -> StageResult<Vec<SSAGraph>> {
        let start = Instant::now();

        let mut ssa_graphs = Vec::new();

        for bfg in bfg_graphs {
            // Find function node by name using shared utility
            let Some(func) = find_function_by_name(nodes, &bfg.function_id) else {
                ssa_graphs.push(SSAGraph {
                    function_id: bfg.function_id.clone(),
                    variables: Vec::new(),
                    phi_nodes: Vec::new(),
                });
                continue;
            };

            let func_id = &func.id;

            // Extract variable definitions with block mapping
            let definitions = extract_variables_for_ssa(nodes, func_id, &bfg.entry_block_id);

            // SOTA: Use BFGCFGAdapter to get CFG structure for Braun-style Phi placement
            let cfg_adapter = BFGCFGAdapter::new(bfg, cfg_edges);

            // Build SSA with SOTA Phi placement
            let ssa = self.build_ssa_with_braun_phi(
                bfg.function_id.clone(),
                &definitions,
                &cfg_adapter,
            );

            ssa_graphs.push(ssa);
        }

        StageResult::new(ssa_graphs, start.elapsed())
    }

    /// Build SSA with Braun-inspired Phi node placement
    ///
    /// Key SOTA insight: Phi nodes are placed at merge points (blocks with >1 predecessor).
    /// This is more accurate than simple block-based versioning.
    fn build_ssa_with_braun_phi<C: CFGProvider>(
        &self,
        function_id: String,
        definitions: &[(String, String)], // (var_name, block_id)
        cfg: &C,
    ) -> SSAGraph {
        use std::collections::HashMap;

        let mut variables = Vec::new();
        let mut phi_nodes = Vec::new();
        let mut version_map: HashMap<String, usize> = HashMap::new();
        let mut block_versions: HashMap<String, HashMap<String, usize>> = HashMap::new();

        // Phase 1: Assign versions to each definition
        for (var_name, block_id) in definitions {
            let version = version_map.entry(var_name.clone()).or_insert(0);
            let ssa_name = format!("{}_{}", var_name, version);

            variables.push(SSAVariable {
                name: ssa_name,
                version: *version,
                def_block_id: block_id.clone(),
            });

            block_versions
                .entry(block_id.clone())
                .or_default()
                .insert(var_name.clone(), *version);

            *version += 1;
        }

        // Phase 2: SOTA Phi placement - use CFG structure
        // Braun's key insight: Phi nodes needed at blocks with multiple predecessors
        // where different versions of the same variable merge
        let mut var_blocks: HashMap<String, Vec<(String, usize)>> = HashMap::new();

        for (block_id, versions) in &block_versions {
            for (var_name, &version) in versions {
                var_blocks
                    .entry(var_name.clone())
                    .or_default()
                    .push((block_id.clone(), version));
            }
        }

        // For each variable defined in multiple blocks, check if Phi is needed
        for (var_name, blocks) in var_blocks {
            if blocks.len() <= 1 {
                continue;
            }

            // Find merge points using CFG predecessor info
            let block_ids: HashSet<_> = blocks.iter().map(|(b, _)| b.clone()).collect();

            // Check each block - if it has predecessors from different def blocks, needs Phi
            for (block_id, _) in &blocks {
                let preds = cfg.predecessors(block_id);

                // SOTA: If this block has multiple predecessors with different versions
                // of the same variable, we need a Phi node
                if preds.len() > 1 {
                    let pred_versions: Vec<_> = preds
                        .iter()
                        .filter_map(|pred| {
                            block_versions
                                .get(pred)
                                .and_then(|v| v.get(&var_name))
                                .map(|&ver| (pred.clone(), ver))
                        })
                        .collect();

                    if pred_versions.len() > 1 {
                        // Different versions merging - need Phi
                        let max_version = blocks.iter().map(|(_, v)| v).max().unwrap_or(&0);

                        phi_nodes.push(PhiNode {
                            variable: var_name.clone(),
                            version: *max_version + 1,
                            predecessors: pred_versions,
                        });
                    }
                }
            }
        }

        // Fallback: If no CFG-based Phis found, use simple multi-block detection
        if phi_nodes.is_empty() {
            let mut var_blocks_simple: HashMap<String, Vec<(String, usize)>> = HashMap::new();

            for (block_id, versions) in &block_versions {
                for (var_name, &version) in versions {
                    var_blocks_simple
                        .entry(var_name.clone())
                        .or_default()
                        .push((block_id.clone(), version));
                }
            }

            for (var_name, blocks) in var_blocks_simple {
                if blocks.len() > 1 {
                    let max_version = blocks.iter().map(|(_, v)| v).max().unwrap_or(&0);
                    phi_nodes.push(PhiNode {
                        variable: var_name,
                        version: *max_version + 1,
                        predecessors: blocks,
                    });
                }
            }
        }

        SSAGraph {
            function_id,
            variables,
            phi_nodes,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// L6: Advanced Analysis Stage (SOTA Implementations)
// ═══════════════════════════════════════════════════════════════════════════

use super::stages::{PDGSummary, SliceSummary, TaintSummary};
use crate::features::pdg::infrastructure::pdg::{PDGBuilder, PDGNode, ProgramDependenceGraph};
use crate::features::slicing::infrastructure::slicer::{ProgramSlicer, SliceType};
use crate::features::taint_analysis::infrastructure::taint::{CallGraphNode, TaintAnalyzer, TaintPath, TaintSeverity};
use crate::shared::models::{EdgeKind, NodeKind, Span};
use std::collections::HashMap;

/// L6 PDG Executor (SOTA: Ferrante/Weiser PDG with petgraph)
///
/// Combines CFG (control) and DFG (data) into Program Dependence Graph.
/// Enables efficient forward/backward slicing for bug analysis.
pub struct PDGExecutor {
    /// Built PDGs (stored for slicing)
    pdgs: HashMap<String, ProgramDependenceGraph>,
}

impl PDGExecutor {
    pub fn new() -> Self {
        Self {
            pdgs: HashMap::new(),
        }
    }

    /// Execute full PDG construction (SOTA: builds actual PDGs)
    ///
    /// This method builds real PDGs using the Ferrante/Weiser algorithm,
    /// not just summaries. PDGs are stored for later slicing operations.
    pub fn execute(
        &mut self,
        dfg_graphs: &[DataFlowGraph],
        cfg_edges: &[CFGEdge],
        bfg_graphs: &[BasicFlowGraph],
    ) -> StageResult<Vec<PDGSummary>> {
        let start = Instant::now();
        let mut summaries = Vec::new();

        for bfg in bfg_graphs {
            // Find corresponding DFG
            let dfg = dfg_graphs
                .iter()
                .find(|d| d.function_id == bfg.function_id);

            let Some(dfg) = dfg else {
                // No DFG - create summary with counts only
                let control_edges = cfg_edges
                    .iter()
                    .filter(|e| e.source_block_id.contains(&bfg.function_id))
                    .count();

                summaries.push(PDGSummary {
                    function_id: bfg.function_id.clone(),
                    node_count: bfg.blocks.len(),
                    control_edges,
                    data_edges: 0,
                });
                continue;
            };

            // SOTA: Build actual PDG using Ferrante/Weiser algorithm
            let pdg = self.build_pdg_internal(&bfg.function_id, dfg, cfg_edges, bfg);

            // Extract summary from built PDG
            let summary = PDGSummary {
                function_id: bfg.function_id.clone(),
                node_count: pdg.node_count(),
                control_edges: pdg.control_edge_count(),
                data_edges: pdg.data_edge_count(),
            };

            // Store PDG for later slicing
            self.pdgs.insert(bfg.function_id.clone(), pdg);

            summaries.push(summary);
        }

        StageResult::new(summaries, start.elapsed())
    }

    /// Build PDG using SOTA Ferrante/Weiser algorithm
    fn build_pdg_internal(
        &self,
        function_id: &str,
        dfg: &DataFlowGraph,
        cfg_edges: &[CFGEdge],
        bfg: &BasicFlowGraph,
    ) -> ProgramDependenceGraph {
        let mut builder = PDGBuilder::new();

        // Add nodes from BFG blocks
        for block in &bfg.blocks {
            let node = PDGNode::new(
                block.id.clone(),
                block.label.clone(),
                block.span.start_line,
                Span::new(
                    block.span.start_line,
                    block.span.start_col,
                    block.span.end_line,
                    block.span.end_col,
                ),
            );
            builder.add_node(node);
        }

        // Add CFG edges (control dependencies)
        let func_cfg_edges: Vec<_> = cfg_edges
            .iter()
            .filter(|e| e.source_block_id.contains(function_id))
            .cloned()
            .map(|e| crate::features::flow_graph::infrastructure::cfg::CFGEdge {
                source_block_id: e.source_block_id,
                target_block_id: e.target_block_id,
                edge_type: e.edge_type.into(),
            })
            .collect();
        builder.add_cfg_edges(func_cfg_edges);

        // Add DFG edges (data dependencies)
        let infra_dfg = crate::features::data_flow::infrastructure::dfg::DataFlowGraph {
            function_id: dfg.function_id.clone(),
            nodes: dfg.nodes.iter().map(|n| n.clone().into()).collect(),
            def_use_edges: dfg.def_use_edges.clone(),
        };
        builder.add_dfg(&infra_dfg);

        builder.build(function_id.to_string())
    }

    /// Get built PDG for a function (for slicing)
    pub fn get_pdg(&self, function_id: &str) -> Option<&ProgramDependenceGraph> {
        self.pdgs.get(function_id)
    }

    /// Get all built PDGs
    pub fn get_all_pdgs(&self) -> &HashMap<String, ProgramDependenceGraph> {
        &self.pdgs
    }
}

impl Default for PDGExecutor {
    fn default() -> Self {
        Self::new()
    }
}

/// L6 Taint Executor (SOTA: Full Parallel BFS with Rayon)
///
/// Tracks data flow from sources (user input) to sinks (dangerous operations).
/// Uses parallel search across source nodes for performance.
///
/// SOTA Integration:
/// - Uses `analyze()` instead of `quick_check()` for complete taint path discovery
/// - Stores actual TaintPaths for vulnerability reporting
/// - Provides per-path severity levels
pub struct TaintExecutor {
    /// Discovered taint paths (stored for vulnerability reporting)
    taint_paths: Vec<TaintPath>,
    /// Analyzer instance (for custom rules)
    analyzer: TaintAnalyzer,
}

impl TaintExecutor {
    pub fn new() -> Self {
        Self {
            taint_paths: Vec::new(),
            analyzer: TaintAnalyzer::new(),
        }
    }

    /// Add custom source pattern
    pub fn add_source(&mut self, pattern: &str, description: &str) {
        self.analyzer.add_source(pattern, description);
    }

    /// Add custom sink pattern
    pub fn add_sink(&mut self, pattern: &str, description: &str, severity: TaintSeverity) {
        self.analyzer.add_sink(pattern, description, severity);
    }

    /// Add custom sanitizer
    pub fn add_sanitizer(&mut self, pattern: &str) {
        self.analyzer.add_sanitizer(pattern);
    }

    /// Execute SOTA taint analysis (full parallel path discovery)
    pub fn execute(&mut self, nodes: &[Node], edges: &[Edge]) -> StageResult<Vec<TaintSummary>> {
        let start = Instant::now();

        // Build call graph from CALLS edges
        let mut call_graph: HashMap<String, CallGraphNode> = HashMap::new();

        // Add all function nodes
        for node in nodes {
            if matches!(node.kind, NodeKind::Function | NodeKind::Method) {
                let name = node.name.clone().unwrap_or_default();
                call_graph.insert(
                    node.id.clone(),
                    CallGraphNode {
                        id: node.id.clone(),
                        name: name.clone(),
                        callees: Vec::new(),
                    },
                );
            }
        }

        // Add call relationships
        for edge in edges {
            if matches!(edge.kind, EdgeKind::Calls) {
                if let Some(caller) = call_graph.get_mut(&edge.source_id) {
                    caller.callees.push(edge.target_id.clone());
                }
            }
        }

        if call_graph.is_empty() {
            return StageResult::new(Vec::new(), start.elapsed());
        }

        // SOTA: Run full taint analysis with parallel BFS
        // This discovers ALL taint paths, not just quick checks
        let taint_paths = self.analyzer.analyze(&call_graph);

        // Store taint paths for later retrieval
        self.taint_paths = taint_paths;

        // Build detailed summaries from discovered paths
        let mut summaries = Vec::new();

        if !self.taint_paths.is_empty() {
            // Group paths by source
            let mut by_source: HashMap<String, Vec<&TaintPath>> = HashMap::new();
            for path in &self.taint_paths {
                by_source.entry(path.source.clone()).or_default().push(path);
            }

            // Create summary for each source
            for (source, paths) in by_source {
                let unique_sinks: HashSet<_> = paths.iter().map(|p| &p.sink).collect();
                let unsanitized = paths.iter().filter(|p| !p.is_sanitized).count();

                summaries.push(TaintSummary {
                    function_id: source,
                    sources_found: 1,
                    sinks_found: unique_sinks.len(),
                    taint_flows: unsanitized, // Only count unsanitized as actual vulnerabilities
                });
            }
        }

        StageResult::new(summaries, start.elapsed())
    }

    /// Get all discovered taint paths
    pub fn get_taint_paths(&self) -> &[TaintPath] {
        &self.taint_paths
    }

    /// Get unsanitized (vulnerable) paths only
    pub fn get_vulnerable_paths(&self) -> Vec<&TaintPath> {
        self.taint_paths.iter().filter(|p| !p.is_sanitized).collect()
    }

    /// Get high severity paths only
    pub fn get_high_severity_paths(&self) -> Vec<&TaintPath> {
        self.taint_paths
            .iter()
            .filter(|p| matches!(p.severity, TaintSeverity::High) && !p.is_sanitized)
            .collect()
    }

    /// Get taint analyzer statistics
    pub fn get_stats(&self) -> crate::features::taint_analysis::infrastructure::taint::TaintStats {
        self.analyzer.get_stats()
    }
}

impl Default for TaintExecutor {
    fn default() -> Self {
        Self::new()
    }
}

/// L6 Slice Executor (SOTA: Weiser's Algorithm with LRU Memoization)
///
/// PDG-based code slicing for LLM context optimization.
/// Memoized for 5-20x speedup on repeated queries.
///
/// # SOTA Features
/// - Backward/Forward/Hybrid slicing (Weiser, 1984)
/// - Thin Slicing (Sridharan et al., PLDI 2007) - data dependencies only
/// - Chopping (Jackson & Rollins, FSE 1994) - source→target paths
pub struct SliceExecutor {
    slicer: ProgramSlicer,
}

impl SliceExecutor {
    pub fn new() -> Self {
        Self {
            slicer: ProgramSlicer::new(),
        }
    }

    /// Execute slicing on-demand for specific criterion
    pub fn execute_slice(
        &mut self,
        pdg: &ProgramDependenceGraph,
        criterion: &str,
        slice_type: SliceType,
        max_depth: Option<usize>,
    ) -> StageResult<SliceSummary> {
        let start = Instant::now();

        let result = match slice_type {
            SliceType::Backward => self.slicer.backward_slice(pdg, criterion, max_depth),
            SliceType::Forward => self.slicer.forward_slice(pdg, criterion, max_depth),
            SliceType::Hybrid => self.slicer.hybrid_slice(pdg, criterion, max_depth),
        };

        let summary = SliceSummary {
            function_id: pdg.function_id.clone(),
            criterion: criterion.to_string(),
            slice_size: result.slice_nodes.len(),
        };

        StageResult::new(summary, start.elapsed())
    }

    /// Execute thin slicing (SOTA: Sridharan et al., PLDI 2007)
    ///
    /// "Why does this variable have this value?" - ignoring control flow
    /// Thin slices are typically 30-50% smaller than full slices.
    pub fn execute_thin_slice(
        &mut self,
        pdg: &ProgramDependenceGraph,
        target: &str,
        max_depth: Option<usize>,
    ) -> StageResult<SliceSummary> {
        let start = Instant::now();

        let result = self.slicer.thin_slice(pdg, target, max_depth);

        let summary = SliceSummary {
            function_id: pdg.function_id.clone(),
            criterion: target.to_string(),
            slice_size: result.slice_nodes.len(),
        };

        StageResult::new(summary, start.elapsed())
    }

    /// Execute chopping (SOTA: Jackson & Rollins, FSE 1994)
    ///
    /// `Chop(source, target) = backward_slice(target) ∩ forward_slice(source)`
    /// "What code connects source to target?"
    pub fn execute_chop(
        &mut self,
        pdg: &ProgramDependenceGraph,
        source: &str,
        target: &str,
        max_depth: Option<usize>,
    ) -> StageResult<SliceSummary> {
        let start = Instant::now();

        let result = self.slicer.chop(pdg, source, target, max_depth);

        let summary = SliceSummary {
            function_id: pdg.function_id.clone(),
            criterion: format!("{}→{}", source, target),
            slice_size: result.slice_nodes.len(),
        };

        StageResult::new(summary, start.elapsed())
    }

    /// Get cache statistics
    pub fn cache_stats(
        &self,
    ) -> crate::features::slicing::infrastructure::slicer::SlicerCacheStats {
        self.slicer.get_cache_stats()
    }
}

impl Default for SliceExecutor {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Type Extraction Stage
// ═══════════════════════════════════════════════════════════════════════════
//
// NOTE: Type extraction is implemented in processor.rs via extract_type_entities()
// This stage executor architecture is for future modularization.

// ═══════════════════════════════════════════════════════════════════════════
// Occurrence Generation Stage
// ═══════════════════════════════════════════════════════════════════════════

/// Occurrence Generation Executor
///
/// Generates SCIP occurrences for code navigation.
pub struct OccurrenceExecutor;

impl OccurrenceExecutor {
    pub fn execute(&self, nodes: &[Node], _edges: &[Edge]) -> StageResult<Vec<Occurrence>> {
        let start = Instant::now();

        // Generate occurrences using centralized function from pipeline processor
        let occurrences = crate::pipeline::processor::generate_occurrences_pub(nodes, _edges);

        StageResult::new(occurrences, start.elapsed())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_data_flow_executor() {
        let executor = DataFlowExecutor;
        let result = executor.execute(&[], &[], &[], &[]);

        assert_eq!(result.output.len(), 0);
        assert_eq!(result.errors.len(), 0);
    }

    #[test]
    fn test_ssa_executor() {
        let executor = SSAExecutor;
        let result = executor.execute(&[], &[], &[], &[], &[]);

        assert_eq!(result.output.len(), 0);
        assert_eq!(result.errors.len(), 0);
    }
}
