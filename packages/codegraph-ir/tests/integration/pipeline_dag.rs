//! Integration tests for Stage DAG
//!
//! Tests the SOTA pipeline orchestration with Petgraph

use codegraph_ir::pipeline::stage_dag::{PipelineDAG, StageId};

#[test]
fn test_full_pipeline_dag() {
    // Enable all stages
    let stages = vec![
        StageId::L1IrBuild,
        StageId::L2Chunking,
        StageId::L3CrossFile,
        StageId::L4Occurrences,
        StageId::L5Symbols,
    ];

    let dag = PipelineDAG::build(&stages);

    // Verify DAG structure
    assert_eq!(dag.stage_count(), 5, "Should have 5 stages");
    assert_eq!(dag.dependency_count(), 4, "Should have 4 dependencies");

    // Verify execution order: L1 must be first
    let order = dag.execution_order();
    assert_eq!(order[0], StageId::L1IrBuild, "L1 should execute first");

    // L2/L3/L4/L5 can be in any order after L1 (all depend on L1 only)
    assert!(order[1..].contains(&StageId::L2Chunking));
    assert!(order[1..].contains(&StageId::L3CrossFile));
    assert!(order[1..].contains(&StageId::L4Occurrences));
    assert!(order[1..].contains(&StageId::L5Symbols));
}

#[test]
fn test_partial_pipeline() {
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
fn test_parallel_execution_planning() {
    let stages = vec![
        StageId::L1IrBuild,
        StageId::L2Chunking,
        StageId::L3CrossFile,
        StageId::L4Occurrences,
    ];

    let dag = PipelineDAG::build(&stages);

    // Phase 1: Nothing completed yet, only L1 can run
    let runnable = dag.get_parallel_stages(&[]);
    assert_eq!(runnable, vec![StageId::L1IrBuild]);

    // Phase 2: L1 completed, L2/L3/L4 can run in parallel
    let completed = vec![StageId::L1IrBuild];
    let runnable = dag.get_parallel_stages(&completed);

    assert_eq!(runnable.len(), 3, "Three stages should be runnable");
    assert!(runnable.contains(&StageId::L2Chunking));
    assert!(runnable.contains(&StageId::L3CrossFile));
    assert!(runnable.contains(&StageId::L4Occurrences));

    // Phase 3: All completed
    let completed = vec![
        StageId::L1IrBuild,
        StageId::L2Chunking,
        StageId::L3CrossFile,
        StageId::L4Occurrences,
    ];
    let runnable = dag.get_parallel_stages(&completed);
    assert_eq!(runnable.len(), 0, "No more stages to run");
}

#[test]
fn test_dependency_queries() {
    let stages = vec![
        StageId::L1IrBuild,
        StageId::L2Chunking,
        StageId::L3CrossFile,
    ];

    let dag = PipelineDAG::build(&stages);

    // L1 has no dependencies
    let deps = dag.get_dependencies(&StageId::L1IrBuild);
    assert_eq!(deps.len(), 0, "L1 should have no dependencies");

    // L2 depends on L1
    let deps = dag.get_dependencies(&StageId::L2Chunking);
    assert_eq!(deps, vec![StageId::L1IrBuild]);

    // L1 is depended on by L2 and L3
    let dependents = dag.get_dependents(&StageId::L1IrBuild);
    assert_eq!(dependents.len(), 2);
    assert!(dependents.contains(&StageId::L2Chunking));
    assert!(dependents.contains(&StageId::L3CrossFile));
}

#[test]
fn test_stage_metadata() {
    // Test StageId enum methods
    assert_eq!(StageId::L1IrBuild.name(), "L1_IR_Build");
    assert_eq!(StageId::L2Chunking.name(), "L2_Chunking");
    assert_eq!(StageId::L3CrossFile.name(), "L3_CrossFile");
    assert_eq!(StageId::L4Occurrences.name(), "L4_Occurrences");
    assert_eq!(StageId::L5Symbols.name(), "L5_Symbols");

    // Descriptions should be non-empty
    assert!(!StageId::L1IrBuild.description().is_empty());
    assert!(!StageId::L2Chunking.description().is_empty());
}

#[test]
fn test_dag_is_acyclic() {
    // This should never panic - DAG construction ensures no cycles
    let stages = vec![
        StageId::L1IrBuild,
        StageId::L2Chunking,
        StageId::L3CrossFile,
        StageId::L4Occurrences,
        StageId::L5Symbols,
    ];

    // Should not panic
    let _dag = PipelineDAG::build(&stages);
}
