//! SOTA IR Indexing Pipeline Architecture
//!
//! RFC-SOTA-PIPELINE: High-performance parallel indexing pipeline
//!
//! # Design Philosophy
//!
//! This pipeline is designed for maximum throughput with proper dependency management.
//! Key principles:
//! - **Parallel by default**: Independent stages run concurrently
//! - **DAG-based orchestration**: Petgraph for proven dependency resolution
//! - **Zero-copy where possible**: References and arenas for memory efficiency
//! - **Incremental-ready**: Stage outputs can be cached and reused
//!
//! # Pipeline Stages (L1-L9)
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────────────────────┐
//! │                    SOTA IR Indexing Pipeline                                │
//! ├─────────────────────────────────────────────────────────────────────────────┤
//! │                                                                             │
//! │  ╔═══════════════════════════════════════════════════════════════════════╗ │
//! │  ║  PHASE 1: Foundation (Sequential - must complete first)               ║ │
//! │  ╠═══════════════════════════════════════════════════════════════════════╣ │
//! │  ║  L1: IR Build                                                         ║ │
//! │  ║      Parse → AST → Nodes + Edges + Occurrences                        ║ │
//! │  ║      (tree-sitter, multi-language, parallel per-file)                 ║ │
//! │  ╚═══════════════════════════════════════════════════════════════════════╝ │
//! │                              │                                              │
//! │                              ▼                                              │
//! │  ╔═══════════════════════════════════════════════════════════════════════╗ │
//! │  ║  PHASE 2: Analysis (Parallel - all can run concurrently)              ║ │
//! │  ╠═══════════════════════════════════════════════════════════════════════╣ │
//! │  ║  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  ║ │
//! │  ║  │ L2: Chunking │ │ L3: CrossFile│ │ L4: FlowGraph│ │ L5: Types    │  ║ │
//! │  ║  │ (semantic    │ │ (import      │ │ (CFG + BFG   │ │ (inference   │  ║ │
//! │  ║  │  search)     │ │  resolution) │ │  per-func)   │ │  per-file)   │  ║ │
//! │  ║  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  ║ │
//! │  ╚═══════════════════════════════════════════════════════════════════════╝ │
//! │                              │                                              │
//! │                              ▼                                              │
//! │  ╔═══════════════════════════════════════════════════════════════════════╗ │
//! │  ║  PHASE 3: Advanced Analysis (Parallel - depends on Phase 2)           ║ │
//! │  ╠═══════════════════════════════════════════════════════════════════════╣ │
//! │  ║  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                   ║ │
//! │  ║  │ L6: DataFlow │ │ L7: SSA      │ │ L8: Symbols  │                   ║ │
//! │  ║  │ (DFG, needs  │ │ (needs CFG   │ │ (navigation  │                   ║ │
//! │  ║  │  CFG)        │ │  + DFG)      │ │  extraction) │                   ║ │
//! │  ║  └──────────────┘ └──────────────┘ └──────────────┘                   ║ │
//! │  ╚═══════════════════════════════════════════════════════════════════════╝ │
//! │                              │                                              │
//! │                              ▼                                              │
//! │  ╔═══════════════════════════════════════════════════════════════════════╗ │
//! │  ║  PHASE 4: Repository-Wide Analysis (Sequential - needs all above)     ║ │
//! │  ╠═══════════════════════════════════════════════════════════════════════╣ │
//! │  ║  L9: Points-to Analysis                                               ║ │
//! │  ║      Andersen/Steensgaard whole-program alias analysis                ║ │
//! │  ╚═══════════════════════════════════════════════════════════════════════╝ │
//! │                                                                             │
//! └─────────────────────────────────────────────────────────────────────────────┘
//! ```
//!
//! # Stage Dependencies (DAG)
//!
//! ```text
//!                    L1 (IR Build)
//!                    /  |  |  \
//!                   /   |  |   \
//!                  ▼    ▼  ▼    ▼
//!          L2    L3    L4    L5
//!      (Chunk) (XFile) (Flow) (Types)
//!                       |  \    |
//!                       |   \   |
//!                       ▼    ▼  ▼
//!                      L6   L7  L8
//!                    (DFG) (SSA)(Sym)
//!                       \   |   /
//!                        \  |  /
//!                         ▼ ▼ ▼
//!                          L9
//!                      (PointsTo)
//! ```
//!
//! # Performance Targets
//!
//! | Stage | Target | Notes |
//! |-------|--------|-------|
//! | L1: IR Build | 500K+ LOC/s | tree-sitter + Rayon |
//! | L2: Chunking | 1M+ LOC/s | Hierarchical builder |
//! | L3: CrossFile | 100K+ files/s | DashMap parallel |
//! | L4: FlowGraph | 50K+ funcs/s | petgraph CFG/BFG |
//! | L5: Types | 100K+ nodes/s | Inference engine |
//! | L6: DataFlow | 50K+ funcs/s | DFG builder |
//! | L7: SSA | 50K+ funcs/s | Braun 2013 algorithm |
//! | L8: Symbols | 200K+ nodes/s | Simple extraction |
//! | L9: PointsTo | 10K+ constraints/s | Andersen/Steensgaard |

use std::collections::{HashMap, HashSet};
use std::time::{Duration, Instant};

use petgraph::algo::toposort;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::Direction;

/// Pipeline stage identifier (L1-L9)
///
/// Each stage represents a major step in the SOTA indexing pipeline.
/// Stages are grouped into phases for parallel execution.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SOTAStageId {
    // ═══════════════════════════════════════════════════════════════════
    // PHASE 1: Foundation (Sequential)
    // ═══════════════════════════════════════════════════════════════════
    /// L1: IR Build - Parse files and generate IR (nodes, edges, occurrences)
    ///
    /// Input: Source files
    /// Output: Vec<Node>, Vec<Edge>, Vec<Occurrence>
    /// Parallelism: Per-file (Rayon)
    L1IrBuild,

    // ═══════════════════════════════════════════════════════════════════
    // PHASE 2: Analysis (Parallel)
    // ═══════════════════════════════════════════════════════════════════
    /// L2: Chunking - Create hierarchical searchable chunks
    ///
    /// Input: Nodes from L1
    /// Output: Vec<Chunk>
    /// Dependencies: L1
    L2Chunking,

    /// L3: Cross-File Resolution - Resolve imports and references
    ///
    /// Input: Nodes, Edges from L1
    /// Output: GlobalContext (import resolution, file dependencies)
    /// Dependencies: L1
    L3CrossFile,

    /// L4: Flow Graph - Build CFG and BFG per function
    ///
    /// Input: Nodes, Edges from L1
    /// Output: Vec<CFGEdge>, Vec<BasicFlowGraph>
    /// Dependencies: L1
    L4FlowGraph,

    /// L5: Type Resolution - Infer types for nodes
    ///
    /// Input: Nodes, Edges from L1
    /// Output: Vec<TypeEntity>
    /// Dependencies: L1
    L5Types,

    // ═══════════════════════════════════════════════════════════════════
    // PHASE 3: Advanced Analysis (Parallel, depends on Phase 2)
    // ═══════════════════════════════════════════════════════════════════
    /// L6: Data Flow Graph - Build DFG per function
    ///
    /// Input: Nodes, Edges, CFG from L4
    /// Output: Vec<DataFlowGraph>
    /// Dependencies: L4 (FlowGraph)
    L6DataFlow,

    /// L7: SSA - Static Single Assignment form
    ///
    /// Input: CFG from L4, DFG from L6
    /// Output: Vec<SSAGraph>
    /// Dependencies: L4, L6
    L7SSA,

    /// L8: Symbols - Extract navigation symbols
    ///
    /// Input: Nodes from L1, Types from L5
    /// Output: Vec<Symbol>
    /// Dependencies: L1, L5 (optional)
    L8Symbols,

    // ═══════════════════════════════════════════════════════════════════
    // PHASE 4: Repository-Wide Analysis (Sequential)
    // ═══════════════════════════════════════════════════════════════════
    /// L9: Points-to Analysis - Whole-program alias analysis
    ///
    /// Input: All nodes and edges
    /// Output: PointsToSummary
    /// Dependencies: All previous stages
    L9PointsTo,
}

impl SOTAStageId {
    /// Get phase number (1-4)
    pub fn phase(&self) -> u8 {
        match self {
            Self::L1IrBuild => 1,
            Self::L2Chunking | Self::L3CrossFile | Self::L4FlowGraph | Self::L5Types => 2,
            Self::L6DataFlow | Self::L7SSA | Self::L8Symbols => 3,
            Self::L9PointsTo => 4,
        }
    }

    /// Get human-readable stage name
    pub fn name(&self) -> &'static str {
        match self {
            Self::L1IrBuild => "L1_IR_Build",
            Self::L2Chunking => "L2_Chunking",
            Self::L3CrossFile => "L3_CrossFile",
            Self::L4FlowGraph => "L4_FlowGraph",
            Self::L5Types => "L5_Types",
            Self::L6DataFlow => "L6_DataFlow",
            Self::L7SSA => "L7_SSA",
            Self::L8Symbols => "L8_Symbols",
            Self::L9PointsTo => "L9_PointsTo",
        }
    }

    /// Get stage description
    pub fn description(&self) -> &'static str {
        match self {
            Self::L1IrBuild => "Parse files and generate IR (nodes, edges, occurrences)",
            Self::L2Chunking => "Create hierarchical searchable chunks",
            Self::L3CrossFile => "Resolve imports and cross-file references",
            Self::L4FlowGraph => "Build CFG and BFG per function",
            Self::L5Types => "Infer types for nodes",
            Self::L6DataFlow => "Build data flow graph per function",
            Self::L7SSA => "Convert to Static Single Assignment form",
            Self::L8Symbols => "Extract navigation symbols",
            Self::L9PointsTo => "Compute alias analysis (Andersen/Steensgaard)",
        }
    }

    /// Get all stages in a phase
    pub fn stages_in_phase(phase: u8) -> Vec<Self> {
        match phase {
            1 => vec![Self::L1IrBuild],
            2 => vec![
                Self::L2Chunking,
                Self::L3CrossFile,
                Self::L4FlowGraph,
                Self::L5Types,
            ],
            3 => vec![Self::L6DataFlow, Self::L7SSA, Self::L8Symbols],
            4 => vec![Self::L9PointsTo],
            _ => vec![],
        }
    }

    /// Get all stages
    pub fn all() -> Vec<Self> {
        vec![
            Self::L1IrBuild,
            Self::L2Chunking,
            Self::L3CrossFile,
            Self::L4FlowGraph,
            Self::L5Types,
            Self::L6DataFlow,
            Self::L7SSA,
            Self::L8Symbols,
            Self::L9PointsTo,
        ]
    }
}

/// Stage control flags for enabling/disabling stages
#[derive(Debug, Clone)]
pub struct SOTAStageControl {
    /// Phase 1: Foundation
    pub enable_ir_build: bool, // L1 - always required

    /// Phase 2: Analysis
    pub enable_chunking: bool, // L2
    pub enable_cross_file: bool, // L3
    pub enable_flow_graph: bool, // L4
    pub enable_types: bool,      // L5

    /// Phase 3: Advanced Analysis
    pub enable_data_flow: bool, // L6
    pub enable_ssa: bool,     // L7
    pub enable_symbols: bool, // L8

    /// Phase 4: Repository-Wide
    pub enable_points_to: bool, // L9
}

impl Default for SOTAStageControl {
    fn default() -> Self {
        Self {
            // Phase 1: Always on
            enable_ir_build: true,

            // Phase 2: Default on for indexing
            enable_chunking: true,
            enable_cross_file: true,
            enable_flow_graph: true,
            enable_types: true,

            // Phase 3: Default on
            enable_data_flow: true,
            enable_ssa: true,
            enable_symbols: true,

            // Phase 4: Default on
            enable_points_to: true,
        }
    }
}

impl SOTAStageControl {
    /// Create minimal config (L1 only)
    pub fn minimal() -> Self {
        Self {
            enable_ir_build: true,
            enable_chunking: false,
            enable_cross_file: false,
            enable_flow_graph: false,
            enable_types: false,
            enable_data_flow: false,
            enable_ssa: false,
            enable_symbols: false,
            enable_points_to: false,
        }
    }

    /// Create search-optimized config (L1-L3, L8)
    pub fn search_optimized() -> Self {
        Self {
            enable_ir_build: true,
            enable_chunking: true,
            enable_cross_file: true,
            enable_flow_graph: false,
            enable_types: false,
            enable_data_flow: false,
            enable_ssa: false,
            enable_symbols: true,
            enable_points_to: false,
        }
    }

    /// Create analysis-optimized config (all stages)
    pub fn analysis_optimized() -> Self {
        Self::default()
    }

    /// Get enabled stages as list
    pub fn enabled_stages(&self) -> Vec<SOTAStageId> {
        let mut stages = Vec::new();

        if self.enable_ir_build {
            stages.push(SOTAStageId::L1IrBuild);
        }
        if self.enable_chunking {
            stages.push(SOTAStageId::L2Chunking);
        }
        if self.enable_cross_file {
            stages.push(SOTAStageId::L3CrossFile);
        }
        if self.enable_flow_graph {
            stages.push(SOTAStageId::L4FlowGraph);
        }
        if self.enable_types {
            stages.push(SOTAStageId::L5Types);
        }
        if self.enable_data_flow {
            stages.push(SOTAStageId::L6DataFlow);
        }
        if self.enable_ssa {
            stages.push(SOTAStageId::L7SSA);
        }
        if self.enable_symbols {
            stages.push(SOTAStageId::L8Symbols);
        }
        if self.enable_points_to {
            stages.push(SOTAStageId::L9PointsTo);
        }

        stages
    }
}

/// Stage execution metadata
#[derive(Debug, Clone, Default)]
pub struct SOTAStageMetadata {
    /// Stage execution duration
    pub duration: Duration,

    /// Number of items processed
    pub items_processed: usize,

    /// Number of items produced
    pub items_produced: usize,

    /// Processing rate (items/sec)
    pub rate: f64,

    /// Errors encountered (non-fatal)
    pub errors: Vec<String>,
}

impl SOTAStageMetadata {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_timing(items_processed: usize, items_produced: usize, duration: Duration) -> Self {
        let rate = if duration.as_secs_f64() > 0.0 {
            items_processed as f64 / duration.as_secs_f64()
        } else {
            0.0
        };

        Self {
            duration,
            items_processed,
            items_produced,
            rate,
            errors: Vec::new(),
        }
    }
}

/// IR Indexing Pipeline DAG for stage orchestration
///
/// Uses Petgraph for proven stability and performance:
/// - Topological sort for execution order
/// - Cycle detection at build time
/// - Phase-based parallel execution
pub struct IRPipelineDAG {
    /// Dependency graph (A → B means A must complete before B starts)
    graph: DiGraph<SOTAStageId, ()>,

    /// Stage ID → Node index mapping for O(1) lookups
    stage_to_node: HashMap<SOTAStageId, NodeIndex>,

    /// Cached topological execution order
    execution_order: Vec<SOTAStageId>,

    /// Stages grouped by phase for parallel execution
    phases: HashMap<u8, Vec<SOTAStageId>>,
}

impl IRPipelineDAG {
    /// Build DAG from enabled stages
    ///
    /// # Dependencies
    ///
    /// Phase 1 → Phase 2:
    /// - L1 → L2, L3, L4, L5 (all Phase 2 depends on L1)
    ///
    /// Phase 2 → Phase 3:
    /// - L4 → L6 (DataFlow needs FlowGraph)
    /// - L4, L6 → L7 (SSA needs CFG and DFG)
    /// - L1 → L8 (Symbols needs Nodes)
    /// - L5 → L8 (Symbols optionally uses Types)
    ///
    /// Phase 3 → Phase 4:
    /// - All → L9 (PointsTo needs everything)
    pub fn build(enabled_stages: &[SOTAStageId]) -> Self {
        let mut graph = DiGraph::new();
        let mut stage_to_node = HashMap::new();
        let mut phases: HashMap<u8, Vec<SOTAStageId>> = HashMap::new();

        // Add all enabled stages as nodes
        for &stage_id in enabled_stages {
            let idx = graph.add_node(stage_id);
            stage_to_node.insert(stage_id, idx);
            phases.entry(stage_id.phase()).or_default().push(stage_id);
        }

        // Define dependencies (from, to) - "from" must complete before "to"
        let dependencies = [
            // Phase 1 → Phase 2
            (SOTAStageId::L1IrBuild, SOTAStageId::L2Chunking),
            (SOTAStageId::L1IrBuild, SOTAStageId::L3CrossFile),
            (SOTAStageId::L1IrBuild, SOTAStageId::L4FlowGraph),
            (SOTAStageId::L1IrBuild, SOTAStageId::L5Types),
            // Phase 2 → Phase 3
            (SOTAStageId::L4FlowGraph, SOTAStageId::L6DataFlow),
            (SOTAStageId::L4FlowGraph, SOTAStageId::L7SSA),
            (SOTAStageId::L6DataFlow, SOTAStageId::L7SSA),
            (SOTAStageId::L1IrBuild, SOTAStageId::L8Symbols),
            // L5 → L8 is optional (symbols can work without types)

            // Phase 3 → Phase 4
            (SOTAStageId::L2Chunking, SOTAStageId::L9PointsTo),
            (SOTAStageId::L3CrossFile, SOTAStageId::L9PointsTo),
            (SOTAStageId::L6DataFlow, SOTAStageId::L9PointsTo),
            (SOTAStageId::L7SSA, SOTAStageId::L9PointsTo),
            (SOTAStageId::L8Symbols, SOTAStageId::L9PointsTo),
        ];

        // Add edges only if both stages are enabled
        for (from, to) in dependencies {
            if let (Some(&from_idx), Some(&to_idx)) =
                (stage_to_node.get(&from), stage_to_node.get(&to))
            {
                graph.add_edge(from_idx, to_idx, ());
            }
        }

        // Compute topological order
        let execution_order = match toposort(&graph, None) {
            Ok(order) => order.into_iter().map(|idx| graph[idx]).collect(),
            Err(cycle) => {
                let cycle_node = graph[cycle.node_id()];
                eprintln!(
                    "[CRITICAL] Pipeline DAG contains a cycle involving stage: {:?}",
                    cycle_node
                );
                enabled_stages.to_vec()
            }
        };

        Self {
            graph,
            stage_to_node,
            execution_order,
            phases,
        }
    }

    /// Get execution order (topologically sorted)
    pub fn execution_order(&self) -> &[SOTAStageId] {
        &self.execution_order
    }

    /// Get stages in a specific phase
    pub fn get_phase_stages(&self, phase: u8) -> Vec<SOTAStageId> {
        self.phases.get(&phase).cloned().unwrap_or_default()
    }

    /// Get stages that can run in parallel given completed stages
    pub fn get_parallel_stages(&self, completed: &[SOTAStageId]) -> Vec<SOTAStageId> {
        let completed_set: HashSet<_> = completed.iter().copied().collect();

        self.execution_order
            .iter()
            .filter(|stage_id| {
                !completed_set.contains(stage_id) && self.dependencies_met(stage_id, &completed_set)
            })
            .copied()
            .collect()
    }

    /// Check if all dependencies are satisfied
    fn dependencies_met(&self, stage_id: &SOTAStageId, completed: &HashSet<SOTAStageId>) -> bool {
        let Some(&stage_idx) = self.stage_to_node.get(stage_id) else {
            return false;
        };

        self.graph
            .neighbors_directed(stage_idx, Direction::Incoming)
            .all(|dep_idx| {
                let dep_id = self.graph[dep_idx];
                completed.contains(&dep_id)
            })
    }

    /// Get direct dependencies of a stage
    pub fn get_dependencies(&self, stage_id: &SOTAStageId) -> Vec<SOTAStageId> {
        let Some(&stage_idx) = self.stage_to_node.get(stage_id) else {
            return Vec::new();
        };

        self.graph
            .neighbors_directed(stage_idx, Direction::Incoming)
            .map(|dep_idx| self.graph[dep_idx])
            .collect()
    }

    /// Get number of phases
    pub fn phase_count(&self) -> usize {
        self.phases.len()
    }

    /// Get number of stages
    pub fn stage_count(&self) -> usize {
        self.graph.node_count()
    }

    /// Print pipeline visualization
    pub fn visualize(&self) -> String {
        let mut output = String::new();
        output.push_str("SOTA Pipeline DAG:\n");
        output.push_str("==================\n\n");

        for phase in 1..=4 {
            let stages = self.get_phase_stages(phase);
            if stages.is_empty() {
                continue;
            }

            output.push_str(&format!("Phase {}: ", phase));
            match phase {
                1 => output.push_str("Foundation (Sequential)\n"),
                2 => output.push_str("Analysis (Parallel)\n"),
                3 => output.push_str("Advanced Analysis (Parallel)\n"),
                4 => output.push_str("Repository-Wide (Sequential)\n"),
                _ => output.push_str("Unknown\n"),
            }

            for stage in &stages {
                let deps = self.get_dependencies(stage);
                let dep_str = if deps.is_empty() {
                    "none".to_string()
                } else {
                    deps.iter().map(|d| d.name()).collect::<Vec<_>>().join(", ")
                };
                output.push_str(&format!("  - {} (deps: {})\n", stage.name(), dep_str));
            }
            output.push('\n');
        }

        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sota_stage_phases() {
        assert_eq!(SOTAStageId::L1IrBuild.phase(), 1);
        assert_eq!(SOTAStageId::L2Chunking.phase(), 2);
        assert_eq!(SOTAStageId::L6DataFlow.phase(), 3);
        assert_eq!(SOTAStageId::L9PointsTo.phase(), 4);
    }

    #[test]
    fn test_sota_dag_full() {
        let stages = SOTAStageId::all();
        let dag = IRPipelineDAG::build(&stages);

        assert_eq!(dag.stage_count(), 9);
        assert_eq!(dag.phase_count(), 4);

        // L1 should be first
        assert_eq!(dag.execution_order()[0], SOTAStageId::L1IrBuild);

        // L9 should be last
        assert_eq!(
            dag.execution_order().last().unwrap(),
            &SOTAStageId::L9PointsTo
        );
    }

    #[test]
    fn test_sota_dag_parallel_stages() {
        let stages = SOTAStageId::all();
        let dag = IRPipelineDAG::build(&stages);

        // Initially only L1 can run
        let parallel = dag.get_parallel_stages(&[]);
        assert_eq!(parallel, vec![SOTAStageId::L1IrBuild]);

        // After L1, Phase 2 stages can run in parallel
        let parallel = dag.get_parallel_stages(&[SOTAStageId::L1IrBuild]);
        assert!(parallel.contains(&SOTAStageId::L2Chunking));
        assert!(parallel.contains(&SOTAStageId::L3CrossFile));
        assert!(parallel.contains(&SOTAStageId::L4FlowGraph));
        assert!(parallel.contains(&SOTAStageId::L5Types));
        assert!(parallel.contains(&SOTAStageId::L8Symbols)); // L8 only needs L1
    }

    #[test]
    fn test_sota_dag_dependencies() {
        let stages = SOTAStageId::all();
        let dag = IRPipelineDAG::build(&stages);

        // L1 has no dependencies
        assert!(dag.get_dependencies(&SOTAStageId::L1IrBuild).is_empty());

        // L7 (SSA) depends on L4 and L6
        let l7_deps = dag.get_dependencies(&SOTAStageId::L7SSA);
        assert!(l7_deps.contains(&SOTAStageId::L4FlowGraph));
        assert!(l7_deps.contains(&SOTAStageId::L6DataFlow));
    }

    #[test]
    fn test_sota_stage_control() {
        let minimal = SOTAStageControl::minimal();
        assert_eq!(minimal.enabled_stages().len(), 1);
        assert!(minimal.enabled_stages().contains(&SOTAStageId::L1IrBuild));

        let search = SOTAStageControl::search_optimized();
        assert!(search.enabled_stages().contains(&SOTAStageId::L2Chunking));
        assert!(!search.enabled_stages().contains(&SOTAStageId::L4FlowGraph));

        let full = SOTAStageControl::analysis_optimized();
        assert_eq!(full.enabled_stages().len(), 9);
    }

    #[test]
    fn test_sota_dag_visualization() {
        let stages = SOTAStageId::all();
        let dag = IRPipelineDAG::build(&stages);
        let viz = dag.visualize();

        assert!(viz.contains("Phase 1: Foundation"));
        assert!(viz.contains("Phase 2: Analysis"));
        assert!(viz.contains("L1_IR_Build"));
        assert!(viz.contains("L9_PointsTo"));
    }
}
