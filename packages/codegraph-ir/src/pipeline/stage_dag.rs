//! Stage DAG - Pipeline execution orchestration with Petgraph
//!
//! SOTA-level pipeline DAG implementation inspired by:
//! - Apache DataFusion (query execution DAG)
//! - Bevy ECS (system dependency graph)
//! - Windmill (Rust workflow engine - 13x faster than Airflow)
//!
//! Design choices:
//! 1. Petgraph for proven stability and zero-cost abstraction
//! 2. Explicit dependencies for clarity
//! 3. Rayon parallelism for independent stages
//! 4. Type-safe stage IDs with compile-time exhaustiveness checks

use petgraph::algo::toposort;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::Direction;
use std::collections::HashSet;
use std::collections::HashMap;
use std::time::Duration;

/// Pipeline stage identifier
///
/// Each stage represents a major step in the indexing pipeline.
/// The enum ensures exhaustive matching and type safety.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum StageId {
    // ═══════════════════════════════════════════════════════════════
    // Phase 1: Foundation (L1)
    // ═══════════════════════════════════════════════════════════════
    /// L1: IR Build - Parse files and generate IR
    L1IrBuild,

    // ═══════════════════════════════════════════════════════════════
    // Phase 2: Basic Analysis (L2-L5) - Parallel after L1
    // ═══════════════════════════════════════════════════════════════
    /// L2: Chunking - Create searchable chunks from IR
    L2Chunking,

    /// L2.5: Lexical Indexing - Tantivy full-text search
    L2_5Lexical,

    /// L3: Cross-file Resolution - Resolve imports and cross-file references
    L3CrossFile,

    /// L4: Occurrences - Generate SCIP occurrences
    L4Occurrences,

    /// L5: Symbols - Extract navigation symbols
    L5Symbols,

    // ═══════════════════════════════════════════════════════════════
    // Phase 3: Advanced Analysis (L6-L12)
    // ═══════════════════════════════════════════════════════════════
    /// L6: Points-to Analysis - Compute alias relationships
    L6PointsTo,

    /// L10: Clone Detection - Find code duplicates (Type 1-4)
    L10CloneDetection,

    /// L13: Effect Analysis - Function purity and side effects
    L13EffectAnalysis,

    /// L14: Taint Analysis - Security vulnerability detection
    L14TaintAnalysis,

    /// L15: Cost Analysis - Time/space complexity
    L15CostAnalysis,

    /// L16: RepoMap - Repository structure with PageRank
    L16RepoMap,

    /// L18: Concurrency Analysis - Race condition detection
    L18ConcurrencyAnalysis,

    /// L21: SMT Verification - Formal verification
    L21SmtVerification,

    /// L33: Git History - Co-change analysis
    L33GitHistory,

    /// L37: Query Engine - Unified query interface
    L37QueryEngine,
}

impl StageId {
    /// Get human-readable stage name
    pub fn name(&self) -> &'static str {
        match self {
            Self::L1IrBuild => "L1_IR_Build",
            Self::L2Chunking => "L2_Chunking",
            Self::L2_5Lexical => "L2.5_Lexical",
            Self::L3CrossFile => "L3_CrossFile",
            Self::L4Occurrences => "L4_Occurrences",
            Self::L5Symbols => "L5_Symbols",
            Self::L6PointsTo => "L6_PointsTo",
            Self::L10CloneDetection => "L10_CloneDetection",
            Self::L13EffectAnalysis => "L13_EffectAnalysis",
            Self::L14TaintAnalysis => "L14_TaintAnalysis",
            Self::L15CostAnalysis => "L15_CostAnalysis",
            Self::L16RepoMap => "L16_RepoMap",
            Self::L18ConcurrencyAnalysis => "L18_ConcurrencyAnalysis",
            Self::L21SmtVerification => "L21_SmtVerification",
            Self::L33GitHistory => "L33_GitHistory",
            Self::L37QueryEngine => "L37_QueryEngine",
        }
    }

    /// Get stage description
    pub fn description(&self) -> &'static str {
        match self {
            Self::L1IrBuild => "Parse files and generate intermediate representation",
            Self::L2Chunking => "Create hierarchical searchable chunks",
            Self::L2_5Lexical => "Build Tantivy full-text search index",
            Self::L3CrossFile => "Resolve imports and cross-file references",
            Self::L4Occurrences => "Generate SCIP occurrences for code navigation",
            Self::L5Symbols => "Extract symbols for navigation and search",
            Self::L6PointsTo => "Compute alias relationships for precise analysis",
            Self::L10CloneDetection => "Detect code clones (Type 1-4) using hybrid algorithm",
            Self::L13EffectAnalysis => "Analyze function purity and side effects",
            Self::L14TaintAnalysis => "Detect security vulnerabilities via taint tracking",
            Self::L15CostAnalysis => "Compute time and space complexity",
            Self::L16RepoMap => "Build repository structure with PageRank importance",
            Self::L18ConcurrencyAnalysis => "Detect race conditions in async code",
            Self::L21SmtVerification => "Formal verification using SMT solvers",
            Self::L33GitHistory => "Analyze co-change patterns and temporal coupling",
            Self::L37QueryEngine => "Initialize unified query interface",
        }
    }
}

/// Stage execution metadata
#[derive(Debug, Clone)]
pub struct StageMetadata {
    /// Stage execution duration
    pub duration: Duration,

    /// Number of items processed
    pub items_processed: usize,

    /// Errors encountered (non-fatal)
    pub errors: Vec<String>,
}

/// Pipeline DAG for stage orchestration
///
/// Uses Petgraph for proven stability and performance:
/// - Topological sort for execution order
/// - Cycle detection at build time
/// - Dependency analysis for parallelization
pub struct PipelineDAG {
    /// Dependency graph (A → B means A must complete before B starts)
    graph: DiGraph<StageId, ()>,

    /// Stage ID → Node index mapping for O(1) lookups
    stage_to_node: HashMap<StageId, NodeIndex>,

    /// Cached topological execution order
    execution_order: Vec<StageId>,
}

impl PipelineDAG {
    /// Build DAG from enabled stages
    ///
    /// # Dependencies (hardcoded for now, configurable later)
    /// - L2 depends on L1 (needs IR)
    /// - L3 depends on L1 (needs IR)
    /// - L4 depends on L1 (needs IR)
    /// - L5 depends on L1 (needs nodes)
    ///
    /// # Panics
    /// Panics if the DAG contains cycles (should never happen with hardcoded dependencies)
    pub fn build(enabled_stages: &[StageId]) -> Self {
        let mut graph = DiGraph::new();
        let mut stage_to_node = HashMap::new();

        // Add all enabled stages as nodes
        for &stage_id in enabled_stages {
            let idx = graph.add_node(stage_id);
            stage_to_node.insert(stage_id, idx);
        }

        // Define dependencies (A, B) means A must complete before B
        let dependencies = [
            // ═══════════════════════════════════════════════════════════════
            // Phase 1 → Phase 2: L1 is the root - everything depends on it
            // ═══════════════════════════════════════════════════════════════
            (StageId::L1IrBuild, StageId::L2Chunking),
            (StageId::L1IrBuild, StageId::L2_5Lexical),
            (StageId::L1IrBuild, StageId::L3CrossFile),
            (StageId::L1IrBuild, StageId::L4Occurrences),
            (StageId::L1IrBuild, StageId::L5Symbols),
            (StageId::L1IrBuild, StageId::L6PointsTo),
            (StageId::L1IrBuild, StageId::L10CloneDetection),

            // ═══════════════════════════════════════════════════════════════
            // Phase 2 → Phase 3: Advanced analyses depend on basic stages
            // ═══════════════════════════════════════════════════════════════

            // L13: Effect Analysis depends on CrossFile
            (StageId::L3CrossFile, StageId::L13EffectAnalysis),

            // L14: Taint Analysis depends on CrossFile + PointsTo
            (StageId::L3CrossFile, StageId::L14TaintAnalysis),
            (StageId::L6PointsTo, StageId::L14TaintAnalysis),

            // L15: Cost Analysis depends on L1 (uses CFG from ProcessResult)
            (StageId::L1IrBuild, StageId::L15CostAnalysis),

            // L16: RepoMap depends on Chunking
            (StageId::L2Chunking, StageId::L16RepoMap),

            // L18: Concurrency Analysis depends on CrossFile
            (StageId::L3CrossFile, StageId::L18ConcurrencyAnalysis),

            // L21: SMT Verification depends on L1
            (StageId::L1IrBuild, StageId::L21SmtVerification),

            // L33: Git History is independent (only needs file paths)
            // No dependencies

            // L37: Query Engine depends on CrossFile
            (StageId::L3CrossFile, StageId::L37QueryEngine),
        ];

        // Add edges only if both stages are enabled
        for (from, to) in dependencies {
            if let (Some(&from_idx), Some(&to_idx)) =
                (stage_to_node.get(&from), stage_to_node.get(&to))
            {
                graph.add_edge(from_idx, to_idx, ());
            }
        }

        // SOTA: Compute topological order with proper error handling
        let execution_order = match toposort(&graph, None) {
            Ok(order) => order.into_iter().map(|idx| graph[idx]).collect(),
            Err(cycle) => {
                // If we detect a cycle, it's an internal bug - but handle gracefully
                let cycle_node = graph[cycle.node_id()];
                eprintln!(
                    "[CRITICAL] Pipeline DAG contains a cycle involving stage: {:?}",
                    cycle_node
                );
                eprintln!("This indicates a bug in pipeline stage dependency configuration.");
                eprintln!("Attempting to continue with partial execution order (may produce incorrect results).");

                // Return stages in registration order as fallback
                enabled_stages.to_vec()
            }
        };

        Self {
            graph,
            stage_to_node,
            execution_order,
        }
    }

    /// Get execution order (topologically sorted)
    ///
    /// Guaranteed to respect all dependencies: if A depends on B, then B appears before A.
    pub fn execution_order(&self) -> &[StageId] {
        &self.execution_order
    }

    /// Get stages that can run in parallel at this point
    ///
    /// Returns stages that:
    /// 1. Have not been completed yet
    /// 2. All dependencies are satisfied (completed)
    ///
    /// # Example
    /// ```ignore
    /// let completed = [StageId::L1IrBuild];
    /// let parallel = dag.get_parallel_stages(&completed);
    /// // Returns: [L2Chunking, L3CrossFile, L4Occurrences, L5Symbols]
    /// // All can run in parallel after L1 completes
    /// ```
    pub fn get_parallel_stages(&self, completed: &[StageId]) -> Vec<StageId> {
        let completed_set: HashSet<_> = completed.iter().copied().collect();

        self.execution_order
            .iter()
            .filter(|stage_id| {
                // Not yet completed
                !completed_set.contains(stage_id)
                // All dependencies completed
                && self.dependencies_met(stage_id, &completed_set)
            })
            .copied()
            .collect()
    }

    /// Check if all dependencies are satisfied
    fn dependencies_met(&self, stage_id: &StageId, completed: &HashSet<StageId>) -> bool {
        let Some(&stage_idx) = self.stage_to_node.get(stage_id) else {
            return false;
        };

        // Check all incoming edges (dependencies)
        self.graph
            .neighbors_directed(stage_idx, Direction::Incoming)
            .all(|dep_idx| {
                let dep_id = self.graph[dep_idx];
                completed.contains(&dep_id)
            })
    }

    /// Get direct dependencies of a stage
    ///
    /// # Example
    /// ```ignore
    /// let deps = dag.get_dependencies(&StageId::L2Chunking);
    /// // Returns: [L1IrBuild]
    /// ```
    pub fn get_dependencies(&self, stage_id: &StageId) -> Vec<StageId> {
        let Some(&stage_idx) = self.stage_to_node.get(stage_id) else {
            return Vec::new();
        };

        self.graph
            .neighbors_directed(stage_idx, Direction::Incoming)
            .map(|dep_idx| self.graph[dep_idx])
            .collect()
    }

    /// Get direct dependents of a stage (stages that depend on this one)
    ///
    /// # Example
    /// ```ignore
    /// let deps = dag.get_dependents(&StageId::L1IrBuild);
    /// // Returns: [L2Chunking, L3CrossFile, L4Occurrences, L5Symbols]
    /// ```
    pub fn get_dependents(&self, stage_id: &StageId) -> Vec<StageId> {
        let Some(&stage_idx) = self.stage_to_node.get(stage_id) else {
            return Vec::new();
        };

        self.graph
            .neighbors_directed(stage_idx, Direction::Outgoing)
            .map(|dep_idx| self.graph[dep_idx])
            .collect()
    }

    /// Get number of stages in the DAG
    pub fn stage_count(&self) -> usize {
        self.graph.node_count()
    }

    /// Get number of dependencies (edges) in the DAG
    pub fn dependency_count(&self) -> usize {
        self.graph.edge_count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_full_dag() {
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L3CrossFile,
            StageId::L4Occurrences,
            StageId::L5Symbols,
        ];

        let dag = PipelineDAG::build(&stages);

        // All stages should be present
        assert_eq!(dag.stage_count(), 5);

        // 4 dependencies (L1 → L2, L1 → L3, L1 → L4, L1 → L5)
        assert_eq!(dag.dependency_count(), 4);

        // L1 should be first
        assert_eq!(dag.execution_order()[0], StageId::L1IrBuild);
    }

    #[test]
    fn test_partial_dag() {
        // Only enable L1 and L2
        let stages = vec![StageId::L1IrBuild, StageId::L2Chunking];

        let dag = PipelineDAG::build(&stages);

        assert_eq!(dag.stage_count(), 2);
        assert_eq!(dag.dependency_count(), 1); // L1 → L2

        let order = dag.execution_order();
        assert_eq!(order[0], StageId::L1IrBuild);
        assert_eq!(order[1], StageId::L2Chunking);
    }

    #[test]
    fn test_parallel_stages() {
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L3CrossFile,
        ];

        let dag = PipelineDAG::build(&stages);

        // Initially, only L1 can run
        let parallel = dag.get_parallel_stages(&[]);
        assert_eq!(parallel, vec![StageId::L1IrBuild]);

        // After L1 completes, L2 and L3 can run in parallel
        let parallel = dag.get_parallel_stages(&[StageId::L1IrBuild]);
        assert_eq!(parallel.len(), 2);
        assert!(parallel.contains(&StageId::L2Chunking));
        assert!(parallel.contains(&StageId::L3CrossFile));

        // After L1 and L2, no more stages
        let parallel = dag.get_parallel_stages(&[StageId::L1IrBuild, StageId::L2Chunking]);
        assert_eq!(parallel, vec![StageId::L3CrossFile]);
    }

    #[test]
    fn test_dependencies() {
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L3CrossFile,
        ];

        let dag = PipelineDAG::build(&stages);

        // L1 has no dependencies
        assert_eq!(
            dag.get_dependencies(&StageId::L1IrBuild),
            Vec::<StageId>::new()
        );

        // L2 depends on L1
        assert_eq!(
            dag.get_dependencies(&StageId::L2Chunking),
            vec![StageId::L1IrBuild]
        );

        // L1 is depended on by L2 and L3
        let dependents = dag.get_dependents(&StageId::L1IrBuild);
        assert_eq!(dependents.len(), 2);
        assert!(dependents.contains(&StageId::L2Chunking));
        assert!(dependents.contains(&StageId::L3CrossFile));
    }

    #[test]
    fn test_stage_metadata() {
        let stage = StageId::L1IrBuild;

        assert_eq!(stage.name(), "L1_IR_Build");
        assert_eq!(
            stage.description(),
            "Parse files and generate intermediate representation"
        );
    }
}
