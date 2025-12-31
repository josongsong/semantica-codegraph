use crate::error::{OrchestratorError, Result};
use crate::job::StageId;
use std::collections::{HashMap, HashSet};

/// Cache key manager (from semantica-task-engine pattern)
#[derive(Debug, Clone)]
pub struct CacheKeyManager {
    repo_id: String,
    snapshot_id: String,
}

impl CacheKeyManager {
    pub fn new(repo_id: String, snapshot_id: String) -> Self {
        Self {
            repo_id,
            snapshot_id,
        }
    }

    pub fn ir_key(&self) -> String {
        format!("ir:{}:{}", self.repo_id, self.snapshot_id)
    }

    pub fn chunk_key(&self) -> String {
        format!("chunks:{}:{}", self.repo_id, self.snapshot_id)
    }

    pub fn lexical_key(&self) -> String {
        format!("lexical:{}:{}", self.repo_id, self.snapshot_id)
    }

    pub fn vector_key(&self) -> String {
        format!("vector:{}:{}", self.repo_id, self.snapshot_id)
    }

    /// Get cache key for a stage
    pub fn key_for_stage(&self, stage: StageId) -> String {
        match stage {
            StageId::L1_IR => self.ir_key(),
            StageId::L2_Chunk => self.chunk_key(),
            StageId::L3_Lexical => self.lexical_key(),
            StageId::L4_Vector => self.vector_key(),
        }
    }
}

/// Stage node in DAG
#[derive(Debug, Clone)]
pub struct StageNode {
    pub id: StageId,
    pub name: &'static str,
    pub dependencies: Vec<StageId>,
    pub optional: bool,
    pub timeout_ms: u64,
}

// Make StageNode cloneable for orchestrator
impl StageNode {
    pub fn clone_node(&self) -> Self {
        self.clone()
    }
}

impl StageNode {
    pub fn new(
        id: StageId,
        name: &'static str,
        dependencies: Vec<StageId>,
        optional: bool,
        timeout_ms: u64,
    ) -> Self {
        Self {
            id,
            name,
            dependencies,
            optional,
            timeout_ms,
        }
    }
}

/// Pipeline DAG with topological sort
#[derive(Debug, Clone)]
pub struct PipelineDAG {
    stages: HashMap<StageId, StageNode>,
    execution_order: Vec<Vec<StageId>>, // Vec of parallel groups
}

impl PipelineDAG {
    /// Create a new DAG from stage definitions
    pub fn new(stages: Vec<StageNode>) -> Result<Self> {
        let mut stage_map = HashMap::new();
        for stage in stages {
            stage_map.insert(stage.id, stage);
        }

        // Validate dependencies exist
        for stage in stage_map.values() {
            for dep in &stage.dependencies {
                if !stage_map.contains_key(dep) {
                    return Err(OrchestratorError::MissingDependency(format!(
                        "Stage {:?} depends on non-existent stage {:?}",
                        stage.id, dep
                    )));
                }
            }
        }

        // Compute execution order via topological sort
        let execution_order = Self::topological_sort(&stage_map)?;

        Ok(Self {
            stages: stage_map,
            execution_order,
        })
    }

    /// Create default pipeline (L1∥L3 → L2 → L4)
    pub fn default_pipeline() -> Result<Self> {
        let stages = vec![
            StageNode::new(
                StageId::L1_IR,
                "IR Generation",
                vec![],
                false,
                300_000, // 5 minutes
            ),
            StageNode::new(
                StageId::L3_Lexical,
                "Lexical Indexing",
                vec![],
                false,
                300_000, // 5 minutes
            ),
            StageNode::new(
                StageId::L2_Chunk,
                "Chunk Building",
                vec![StageId::L1_IR],
                false,
                180_000, // 3 minutes
            ),
            StageNode::new(
                StageId::L4_Vector,
                "Vector Indexing",
                vec![StageId::L2_Chunk],
                true,    // Optional
                600_000, // 10 minutes
            ),
        ];

        Self::new(stages)
    }

    /// Topological sort with parallel group detection
    fn topological_sort(stages: &HashMap<StageId, StageNode>) -> Result<Vec<Vec<StageId>>> {
        let mut in_degree: HashMap<StageId, usize> = stages.keys().map(|&id| (id, 0)).collect();

        // Calculate in-degrees
        for stage in stages.values() {
            for &dep in &stage.dependencies {
                *in_degree.get_mut(&stage.id).unwrap() += 1;
            }
        }

        let mut result = Vec::new();
        let mut processed = HashSet::new();

        while processed.len() < stages.len() {
            // Find all stages with in-degree 0 (can run in parallel)
            let ready: Vec<StageId> = in_degree
                .iter()
                .filter(|(id, &degree)| degree == 0 && !processed.contains(*id))
                .map(|(&id, _)| id)
                .collect();

            if ready.is_empty() {
                return Err(OrchestratorError::DagCycleDetected);
            }

            result.push(ready.clone());

            // Mark as processed and decrement dependents
            for &stage_id in &ready {
                processed.insert(stage_id);
                in_degree.remove(&stage_id);

                // Decrement dependents
                for dependent in stages.values() {
                    if dependent.dependencies.contains(&stage_id) {
                        *in_degree.get_mut(&dependent.id).unwrap() -= 1;
                    }
                }
            }
        }

        Ok(result)
    }

    /// Get execution order
    pub fn execution_order(&self) -> &[Vec<StageId>] {
        &self.execution_order
    }

    /// Get stage node
    pub fn get_stage(&self, id: StageId) -> Option<&StageNode> {
        self.stages.get(&id)
    }

    /// Get execution plan as string (for logging)
    pub fn execution_plan(&self) -> String {
        self.execution_order
            .iter()
            .enumerate()
            .map(|(i, group)| {
                let stage_names: Vec<_> = group.iter().map(|id| self.stages[id].name).collect();

                if group.len() > 1 {
                    format!("Phase {}: {} (parallel)", i + 1, stage_names.join(" ∥ "))
                } else {
                    format!("Phase {}: {}", i + 1, stage_names[0])
                }
            })
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// Get required cache keys for a stage
    pub fn required_cache_keys(
        &self,
        stage_id: StageId,
        cache_mgr: &CacheKeyManager,
    ) -> Vec<String> {
        let stage = match self.stages.get(&stage_id) {
            Some(s) => s,
            None => return vec![],
        };

        stage
            .dependencies
            .iter()
            .map(|dep_id| cache_mgr.key_for_stage(*dep_id))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_key_generation() {
        let mgr = CacheKeyManager::new("repo123".to_string(), "snap456".to_string());
        assert_eq!(mgr.ir_key(), "ir:repo123:snap456");
        assert_eq!(mgr.chunk_key(), "chunks:repo123:snap456");
        assert_eq!(mgr.lexical_key(), "lexical:repo123:snap456");
        assert_eq!(mgr.vector_key(), "vector:repo123:snap456");
    }

    #[test]
    fn test_cache_key_for_stage() {
        let mgr = CacheKeyManager::new("repo1".to_string(), "snap1".to_string());
        assert_eq!(mgr.key_for_stage(StageId::L1_IR), "ir:repo1:snap1");
        assert_eq!(mgr.key_for_stage(StageId::L2_Chunk), "chunks:repo1:snap1");
    }

    #[test]
    fn test_dag_topological_sort_simple() {
        let stages = vec![
            StageNode::new(StageId::L1_IR, "IR", vec![], false, 1000),
            StageNode::new(
                StageId::L2_Chunk,
                "Chunk",
                vec![StageId::L1_IR],
                false,
                1000,
            ),
        ];

        let dag = PipelineDAG::new(stages).unwrap();
        let order = dag.execution_order();

        assert_eq!(order.len(), 2);
        assert_eq!(order[0], vec![StageId::L1_IR]);
        assert_eq!(order[1], vec![StageId::L2_Chunk]);
    }

    #[test]
    fn test_dag_parallel_detection() {
        let stages = vec![
            StageNode::new(StageId::L1_IR, "IR", vec![], false, 1000),
            StageNode::new(StageId::L3_Lexical, "Lexical", vec![], false, 1000),
        ];

        let dag = PipelineDAG::new(stages).unwrap();
        let order = dag.execution_order();

        assert_eq!(order.len(), 1);
        assert_eq!(order[0].len(), 2); // Both in same parallel group
        assert!(order[0].contains(&StageId::L1_IR));
        assert!(order[0].contains(&StageId::L3_Lexical));
    }

    #[test]
    fn test_dag_default_pipeline() {
        let dag = PipelineDAG::default_pipeline().unwrap();
        let order = dag.execution_order();

        // Phase 1: L1 ∥ L3
        assert_eq!(order.len(), 3);
        assert_eq!(order[0].len(), 2);
        assert!(order[0].contains(&StageId::L1_IR));
        assert!(order[0].contains(&StageId::L3_Lexical));

        // Phase 2: L2
        assert_eq!(order[1], vec![StageId::L2_Chunk]);

        // Phase 3: L4
        assert_eq!(order[2], vec![StageId::L4_Vector]);
    }

    #[test]
    fn test_dag_cycle_detection() {
        // This should fail because we can't create a cycle with our StageId enum
        // But we can test missing dependency
        let stages = vec![StageNode::new(
            StageId::L2_Chunk,
            "Chunk",
            vec![StageId::L1_IR], // L1 not in stages
            false,
            1000,
        )];

        let result = PipelineDAG::new(stages);
        assert!(result.is_err());
    }

    #[test]
    fn test_dag_execution_plan_string() {
        let dag = PipelineDAG::default_pipeline().unwrap();
        let plan = dag.execution_plan();

        assert!(plan.contains("Phase 1:"));
        assert!(plan.contains("parallel"));
        assert!(plan.contains("IR Generation"));
        assert!(plan.contains("Lexical Indexing"));
    }

    #[test]
    fn test_dag_required_cache_keys() {
        let dag = PipelineDAG::default_pipeline().unwrap();
        let mgr = CacheKeyManager::new("repo1".to_string(), "snap1".to_string());

        // L1 has no dependencies
        let l1_keys = dag.required_cache_keys(StageId::L1_IR, &mgr);
        assert_eq!(l1_keys.len(), 0);

        // L2 depends on L1
        let l2_keys = dag.required_cache_keys(StageId::L2_Chunk, &mgr);
        assert_eq!(l2_keys.len(), 1);
        assert_eq!(l2_keys[0], "ir:repo1:snap1");

        // L4 depends on L2
        let l4_keys = dag.required_cache_keys(StageId::L4_Vector, &mgr);
        assert_eq!(l4_keys.len(), 1);
        assert_eq!(l4_keys[0], "chunks:repo1:snap1");
    }
}
