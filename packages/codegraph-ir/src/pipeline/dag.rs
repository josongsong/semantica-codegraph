//! Pipeline DAG - Workflow orchestration for analysis stages
//!
//! Adapted from semantica-task-engine for zero-dependency stage orchestration.
//!
//! # Design
//! - Stages can declare dependencies on other stages (depends_on)
//! - Cycle detection to prevent infinite loops
//! - Topological ordering for execution
//! - State management (Pending → Ready → Running → Succeeded/Failed)
//!
//! # Features
//! - Automatic ready_nodes() calculation after stage completion
//! - Parallel execution of independent stages
//! - Dependency-based scheduling

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::time::Duration;

/// Pipeline stage identifier
///
/// Each stage represents a major step in the indexing pipeline.
/// The enum ensures exhaustive matching and type safety.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StageId {
    // Phase 1: Foundation
    L1IrBuild,

    // Phase 2: Basic Analysis
    L2Chunking,
    L2_5Lexical,
    L3CrossFile,
    L4Occurrences,
    L5Symbols,

    // Phase 3: Advanced Analysis
    L6PointsTo,
    L10CloneDetection,
    L13EffectAnalysis,
    L14TaintAnalysis,
    L15CostAnalysis,
    L16RepoMap,
    L18ConcurrencyAnalysis,
    L21SmtVerification,
    L33GitHistory,
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

/// Stage node state in the DAG
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StageState {
    /// Waiting for dependencies
    Pending,
    /// All dependencies satisfied, ready to run
    Ready,
    /// Currently executing
    Running,
    /// Completed successfully
    Succeeded,
    /// Failed with error
    Failed,
    /// Skipped (dependency failed)
    Skipped,
}

/// A node in the DAG representing a stage
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageNode {
    /// Stage ID
    pub id: StageId,
    /// Current state
    pub state: StageState,
    /// Execution duration
    pub duration: Option<Duration>,
    /// Error message if failed
    pub error: Option<String>,
}

impl StageNode {
    /// Create a new stage node
    pub fn new(id: StageId) -> Self {
        Self {
            id,
            state: StageState::Pending,
            duration: None,
            error: None,
        }
    }

    /// Check if node is in terminal state
    pub fn is_terminal(&self) -> bool {
        matches!(
            self.state,
            StageState::Succeeded | StageState::Failed | StageState::Skipped
        )
    }

    /// Check if node can be executed
    pub fn is_ready(&self) -> bool {
        self.state == StageState::Ready
    }

    /// Mark as ready
    pub fn mark_ready(&mut self) {
        if self.state == StageState::Pending {
            self.state = StageState::Ready;
        }
    }

    /// Mark as running
    pub fn mark_running(&mut self) {
        self.state = StageState::Running;
    }

    /// Mark as succeeded
    pub fn mark_succeeded(&mut self, duration: Duration) {
        self.state = StageState::Succeeded;
        self.duration = Some(duration);
    }

    /// Mark as failed
    pub fn mark_failed(&mut self, error: String) {
        self.state = StageState::Failed;
        self.error = Some(error);
    }

    /// Mark as skipped
    pub fn mark_skipped(&mut self) {
        self.state = StageState::Skipped;
    }
}

/// A dependency edge in the DAG
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyEdge {
    /// Source stage (parent)
    pub from: StageId,
    /// Target stage (child)
    pub to: StageId,
}

impl DependencyEdge {
    /// Create a new dependency edge
    pub fn new(from: StageId, to: StageId) -> Self {
        Self { from, to }
    }
}

/// Pipeline DAG for stage orchestration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineDAG {
    /// Stages by ID
    pub stages: HashMap<StageId, StageNode>,
    /// Dependency edges (A → B means A must complete before B starts)
    pub edges: Vec<DependencyEdge>,
}

impl PipelineDAG {
    /// Build DAG from enabled stages
    ///
    /// # Dependencies (hardcoded based on analysis requirements)
    ///
    /// # Panics
    /// Panics if the DAG contains cycles (should never happen with hardcoded dependencies)
    pub fn build(enabled_stages: &[StageId]) -> Self {
        let mut stages = HashMap::new();

        // Add all enabled stages as nodes
        for &stage_id in enabled_stages {
            stages.insert(stage_id, StageNode::new(stage_id));
        }

        // Define dependencies (A, B) means A must complete before B
        let dependencies = [
            // Phase 1 → Phase 2: L1 is the root
            (StageId::L1IrBuild, StageId::L2Chunking),
            (StageId::L1IrBuild, StageId::L2_5Lexical),
            (StageId::L1IrBuild, StageId::L3CrossFile),
            (StageId::L1IrBuild, StageId::L4Occurrences),
            (StageId::L1IrBuild, StageId::L5Symbols),
            (StageId::L1IrBuild, StageId::L6PointsTo),
            (StageId::L1IrBuild, StageId::L10CloneDetection),
            // Phase 2 → Phase 3: Advanced analyses
            (StageId::L3CrossFile, StageId::L13EffectAnalysis),
            (StageId::L3CrossFile, StageId::L14TaintAnalysis),
            (StageId::L6PointsTo, StageId::L14TaintAnalysis),
            (StageId::L1IrBuild, StageId::L15CostAnalysis),
            (StageId::L2Chunking, StageId::L16RepoMap),
            (StageId::L3CrossFile, StageId::L18ConcurrencyAnalysis),
            (StageId::L1IrBuild, StageId::L21SmtVerification),
            (StageId::L3CrossFile, StageId::L37QueryEngine),
            // L33 Git History is independent (no dependencies)
        ];

        // Add edges only if both stages are enabled
        let edges: Vec<_> = dependencies
            .iter()
            .filter(|(from, to)| stages.contains_key(from) && stages.contains_key(to))
            .map(|&(from, to)| DependencyEdge::new(from, to))
            .collect();

        let mut dag = Self { stages, edges };

        // Validate no cycles
        if dag.has_cycle() {
            panic!("Pipeline DAG contains a cycle! This is a configuration bug.");
        }

        // Initialize root nodes as ready
        dag.initialize();

        dag
    }

    /// Get all dependencies for a stage
    pub fn dependencies(&self, stage_id: StageId) -> Vec<StageId> {
        self.edges
            .iter()
            .filter(|e| e.to == stage_id)
            .map(|e| e.from)
            .collect()
    }

    /// Get all children of a stage
    pub fn children(&self, stage_id: StageId) -> Vec<StageId> {
        self.edges
            .iter()
            .filter(|e| e.from == stage_id)
            .map(|e| e.to)
            .collect()
    }

    /// Check for cycles in the DAG
    pub fn has_cycle(&self) -> bool {
        let mut in_degree: HashMap<StageId, usize> = HashMap::new();

        // Initialize in-degrees
        for stage_id in self.stages.keys() {
            in_degree.insert(*stage_id, 0);
        }

        // Count incoming edges
        for edge in &self.edges {
            *in_degree.get_mut(&edge.to).unwrap() += 1;
        }

        // Start with stages that have no incoming edges
        let mut queue: VecDeque<StageId> = in_degree
            .iter()
            .filter(|(_, &count)| count == 0)
            .map(|(&stage, _)| stage)
            .collect();

        let mut visited = 0;

        while let Some(stage) = queue.pop_front() {
            visited += 1;

            // Reduce in-degree of children
            for edge in &self.edges {
                if edge.from == stage {
                    let count = in_degree.get_mut(&edge.to).unwrap();
                    *count -= 1;
                    if *count == 0 {
                        queue.push_back(edge.to);
                    }
                }
            }
        }

        // If we couldn't visit all stages, there's a cycle
        visited != self.stages.len()
    }

    /// Get topological execution order
    pub fn execution_order(&self) -> Vec<StageId> {
        let mut in_degree: HashMap<StageId, usize> = HashMap::new();
        let mut result = Vec::new();

        // Initialize
        for stage_id in self.stages.keys() {
            in_degree.insert(*stage_id, 0);
        }

        for edge in &self.edges {
            *in_degree.get_mut(&edge.to).unwrap() += 1;
        }

        let mut queue: VecDeque<StageId> = in_degree
            .iter()
            .filter(|(_, &count)| count == 0)
            .map(|(&stage, _)| stage)
            .collect();

        while let Some(stage) = queue.pop_front() {
            result.push(stage);

            for edge in &self.edges {
                if edge.from == stage {
                    let count = in_degree.get_mut(&edge.to).unwrap();
                    *count -= 1;
                    if *count == 0 {
                        queue.push_back(edge.to);
                    }
                }
            }
        }

        result
    }

    /// Get stages that are ready to execute (all dependencies satisfied)
    pub fn get_parallel_stages(&self, completed: &[StageId]) -> Vec<StageId> {
        let completed_set: HashSet<StageId> = completed.iter().copied().collect();

        self.stages
            .keys()
            .filter(|stage_id| {
                // Not yet completed
                !completed_set.contains(stage_id)
                    // All dependencies completed
                    && self.dependencies_met(stage_id, &completed_set)
                    // Stage is ready
                    && self.stages.get(stage_id).map(|s| s.is_ready()).unwrap_or(false)
            })
            .copied()
            .collect()
    }

    /// Check if all dependencies are satisfied
    fn dependencies_met(&self, stage_id: &StageId, completed: &HashSet<StageId>) -> bool {
        self.dependencies(*stage_id)
            .iter()
            .all(|dep_id| completed.contains(dep_id))
    }

    /// Get root stages (no dependencies)
    pub fn root_stages(&self) -> Vec<StageId> {
        let has_dependency: HashSet<StageId> = self.edges.iter().map(|e| e.to).collect();

        self.stages
            .keys()
            .filter(|id| !has_dependency.contains(id))
            .copied()
            .collect()
    }

    /// Initialize ready states for root stages
    pub fn initialize(&mut self) {
        let roots = self.root_stages();
        for root in roots {
            if let Some(stage) = self.stages.get_mut(&root) {
                stage.mark_ready();
            }
        }
    }

    /// Check if all dependencies for a stage are satisfied
    pub fn dependencies_satisfied(&self, stage_id: StageId) -> bool {
        self.dependencies(stage_id).iter().all(|dep_id| {
            self.stages
                .get(dep_id)
                .map(|s| s.state == StageState::Succeeded)
                .unwrap_or(false)
        })
    }

    /// Process stage completion and update ready states
    pub fn process_completion(&mut self, stage_id: StageId, succeeded: bool, duration: Duration) {
        // Update stage state
        if let Some(stage) = self.stages.get_mut(&stage_id) {
            if succeeded {
                stage.mark_succeeded(duration);
            } else {
                stage.mark_failed("Execution failed".to_string());
            }
        }

        // Check all pending stages if their dependencies are now satisfied
        let pending_stages: Vec<StageId> = self
            .stages
            .iter()
            .filter(|(_, s)| s.state == StageState::Pending)
            .map(|(id, _)| *id)
            .collect();

        for pending_id in pending_stages {
            if self.dependencies_satisfied(pending_id) {
                if let Some(stage) = self.stages.get_mut(&pending_id) {
                    stage.mark_ready();
                }
            }
        }

        // Skip stages that can't be executed due to failed dependencies
        if !succeeded {
            self.skip_unreachable_stages();
        }
    }

    /// Skip stages that can never execute due to failed dependencies
    fn skip_unreachable_stages(&mut self) {
        let mut changed = true;
        while changed {
            changed = false;
            let pending_stages: Vec<StageId> = self
                .stages
                .iter()
                .filter(|(_, s)| s.state == StageState::Pending)
                .map(|(id, _)| *id)
                .collect();

            for stage_id in pending_stages {
                let deps = self.dependencies(stage_id);
                let should_skip = deps.iter().any(|dep_id| {
                    if let Some(parent) = self.stages.get(dep_id) {
                        parent.state == StageState::Failed || parent.state == StageState::Skipped
                    } else {
                        false
                    }
                });

                if should_skip {
                    if let Some(stage) = self.stages.get_mut(&stage_id) {
                        stage.mark_skipped();
                        changed = true;
                    }
                }
            }
        }
    }

    /// Check if the DAG execution is complete
    pub fn is_complete(&self) -> bool {
        self.stages.values().all(|s| s.is_terminal())
    }

    /// Get number of stages
    pub fn stage_count(&self) -> usize {
        self.stages.len()
    }

    /// Get number of dependencies
    pub fn dependency_count(&self) -> usize {
        self.edges.len()
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

        assert_eq!(dag.stage_count(), 5);
        assert_eq!(dag.dependency_count(), 4); // L1 → L2, L3, L4, L5
    }

    #[test]
    fn test_parallel_stages() {
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L3CrossFile,
        ];

        let mut dag = PipelineDAG::build(&stages);

        // Initially, only L1 can run (initialized as Ready)
        let parallel = dag.get_parallel_stages(&[]);
        assert_eq!(parallel, vec![StageId::L1IrBuild]);

        // Mark L1 as completed - this updates L2 and L3 to Ready
        dag.process_completion(
            StageId::L1IrBuild,
            true,
            std::time::Duration::from_millis(100),
        );

        // After L1 completes, L2 and L3 can run in parallel
        let parallel = dag.get_parallel_stages(&[StageId::L1IrBuild]);
        assert_eq!(parallel.len(), 2);
        assert!(parallel.contains(&StageId::L2Chunking));
        assert!(parallel.contains(&StageId::L3CrossFile));
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
        assert_eq!(dag.dependencies(StageId::L1IrBuild), Vec::<StageId>::new());

        // L2 depends on L1
        assert_eq!(
            dag.dependencies(StageId::L2Chunking),
            vec![StageId::L1IrBuild]
        );

        // L1 is depended on by L2 and L3
        let dependents = dag.children(StageId::L1IrBuild);
        assert_eq!(dependents.len(), 2);
        assert!(dependents.contains(&StageId::L2Chunking));
        assert!(dependents.contains(&StageId::L3CrossFile));
    }

    #[test]
    fn test_complex_dag_execution() {
        // Test a complex DAG with multiple dependency levels
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L3CrossFile,
            StageId::L6PointsTo,
            StageId::L13EffectAnalysis,
            StageId::L14TaintAnalysis,
            StageId::L16RepoMap,
        ];

        let mut dag = PipelineDAG::build(&stages);
        let mut completed = vec![];

        // Wave 1: Only L1 is ready
        let wave1 = dag.get_parallel_stages(&completed);
        assert_eq!(wave1, vec![StageId::L1IrBuild]);
        dag.process_completion(
            StageId::L1IrBuild,
            true,
            std::time::Duration::from_millis(100),
        );
        completed.push(StageId::L1IrBuild);

        // Wave 2: L2, L3, L6 can run in parallel (all depend only on L1)
        let wave2 = dag.get_parallel_stages(&completed);
        assert_eq!(wave2.len(), 3);
        assert!(wave2.contains(&StageId::L2Chunking));
        assert!(wave2.contains(&StageId::L3CrossFile));
        assert!(wave2.contains(&StageId::L6PointsTo));

        // Complete L2, L3, L6
        dag.process_completion(
            StageId::L2Chunking,
            true,
            std::time::Duration::from_millis(50),
        );
        completed.push(StageId::L2Chunking);
        dag.process_completion(
            StageId::L3CrossFile,
            true,
            std::time::Duration::from_millis(50),
        );
        completed.push(StageId::L3CrossFile);
        dag.process_completion(
            StageId::L6PointsTo,
            true,
            std::time::Duration::from_millis(50),
        );
        completed.push(StageId::L6PointsTo);

        // Wave 3: L13, L14, L16 can run
        let wave3 = dag.get_parallel_stages(&completed);
        assert!(wave3.len() >= 2); // At least L13 and L16
        assert!(wave3.contains(&StageId::L16RepoMap)); // Depends on L2
        assert!(wave3.contains(&StageId::L13EffectAnalysis)); // Depends on L3

        // L14 depends on both L3 and L6, so it should also be ready
        assert!(wave3.contains(&StageId::L14TaintAnalysis));

        // Complete all
        for stage in wave3 {
            dag.process_completion(stage, true, std::time::Duration::from_millis(50));
            completed.push(stage);
        }

        // All stages complete
        assert!(dag.is_complete());
    }

    #[test]
    fn test_dag_failure_handling() {
        // Test that failed stages skip their dependents
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L16RepoMap, // Depends on L2
        ];

        let mut dag = PipelineDAG::build(&stages);
        let mut completed = vec![];

        // L1 completes successfully
        dag.process_completion(
            StageId::L1IrBuild,
            true,
            std::time::Duration::from_millis(100),
        );
        completed.push(StageId::L1IrBuild);

        // L2 is ready
        let ready = dag.get_parallel_stages(&completed);
        assert_eq!(ready, vec![StageId::L2Chunking]);

        // L2 FAILS
        dag.process_completion(
            StageId::L2Chunking,
            false,
            std::time::Duration::from_millis(50),
        );
        // Don't add to completed - it failed

        // L16 should be skipped because L2 failed
        let stage_l16 = dag.stages.get(&StageId::L16RepoMap).unwrap();
        assert_eq!(stage_l16.state, StageState::Skipped);

        // No more stages can execute
        let ready = dag.get_parallel_stages(&completed);
        assert!(ready.is_empty());
    }

    #[test]
    fn test_independent_stages() {
        // Test that independent stages (like L33 Git History) can run in parallel with others
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L33GitHistory, // Independent - no dependencies
        ];

        let mut dag = PipelineDAG::build(&stages);

        // Both L1 and L33 should be ready initially (L33 is independent)
        let initial_ready = dag.get_parallel_stages(&[]);
        assert_eq!(initial_ready.len(), 2);
        assert!(initial_ready.contains(&StageId::L1IrBuild));
        assert!(initial_ready.contains(&StageId::L33GitHistory));
    }

    #[test]
    fn test_process_completion() {
        let stages = vec![StageId::L1IrBuild, StageId::L2Chunking, StageId::L16RepoMap];

        let mut dag = PipelineDAG::build(&stages);

        // Complete L1
        dag.process_completion(StageId::L1IrBuild, true, Duration::from_secs(1));

        // L2 should now be ready
        assert_eq!(
            dag.stages.get(&StageId::L2Chunking).unwrap().state,
            StageState::Ready
        );

        // Complete L2
        dag.process_completion(StageId::L2Chunking, true, Duration::from_secs(1));

        // L16 should now be ready
        assert_eq!(
            dag.stages.get(&StageId::L16RepoMap).unwrap().state,
            StageState::Ready
        );
    }

    #[test]
    fn test_full_pipeline_simulation() {
        // Simulate a full pipeline execution with all stages
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L2_5Lexical,
            StageId::L3CrossFile,
            StageId::L4Occurrences,
            StageId::L5Symbols,
            StageId::L6PointsTo,
            StageId::L10CloneDetection,
            StageId::L13EffectAnalysis,
            StageId::L14TaintAnalysis,
            StageId::L15CostAnalysis,
            StageId::L16RepoMap,
            StageId::L18ConcurrencyAnalysis,
            StageId::L21SmtVerification,
            StageId::L33GitHistory,
            StageId::L37QueryEngine,
        ];

        let mut dag = PipelineDAG::build(&stages);
        let mut completed = vec![];

        // Track execution waves for debugging
        let mut wave = 0;

        // Execute pipeline until complete
        while !dag.is_complete() {
            wave += 1;
            let ready = dag.get_parallel_stages(&completed);

            if ready.is_empty() {
                break;
            }

            eprintln!(
                "Wave {}: Executing {} stages: {:?}",
                wave,
                ready.len(),
                ready
            );

            // Simulate parallel execution of all ready stages
            for stage_id in ready {
                dag.process_completion(stage_id, true, Duration::from_millis(100));
                completed.push(stage_id);
            }
        }

        // Verify all stages succeeded
        assert!(dag.is_complete());
        assert_eq!(dag.stages.len(), stages.len());

        let succeeded_count = dag
            .stages
            .values()
            .filter(|s| s.state == StageState::Succeeded)
            .count();
        assert_eq!(succeeded_count, stages.len());

        eprintln!("Pipeline completed in {} waves", wave);
        eprintln!("All {} stages succeeded", succeeded_count);
    }

    #[test]
    fn test_partial_failure_recovery() {
        // Test that pipeline can continue after non-critical stage failures
        let stages = vec![
            StageId::L1IrBuild,
            StageId::L2Chunking,
            StageId::L3CrossFile,
            StageId::L16RepoMap,        // Depends on L2
            StageId::L13EffectAnalysis, // Depends on L3
            StageId::L33GitHistory,     // Independent
        ];

        let mut dag = PipelineDAG::build(&stages);
        let mut completed = vec![];

        // L1 succeeds
        dag.process_completion(StageId::L1IrBuild, true, Duration::from_secs(1));
        completed.push(StageId::L1IrBuild);

        // L2 fails
        dag.process_completion(StageId::L2Chunking, false, Duration::from_secs(1));
        // Don't add to completed

        // L3 succeeds
        dag.process_completion(StageId::L3CrossFile, true, Duration::from_secs(1));
        completed.push(StageId::L3CrossFile);

        // L33 succeeds (independent)
        dag.process_completion(StageId::L33GitHistory, true, Duration::from_secs(1));
        completed.push(StageId::L33GitHistory);

        // L16 should be skipped (depends on failed L2)
        assert_eq!(
            dag.stages.get(&StageId::L16RepoMap).unwrap().state,
            StageState::Skipped
        );

        // L13 should be ready (depends on successful L3)
        let ready = dag.get_parallel_stages(&completed);
        assert!(ready.contains(&StageId::L13EffectAnalysis));
    }
}
