//! Integration Test for UnifiedOrchestrator
//!
//! Tests the complete pipeline from start to finish.

use codegraph_ir::pipeline::unified_orchestrator::{
    UnifiedOrchestrator, UnifiedOrchestratorConfig,
};
use codegraph_ir::pipeline::E2EPipelineConfig;
use std::path::PathBuf;

#[test]
fn test_unified_orchestrator_basic() {
    // Create config with minimal stages
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let pipeline_config = E2EPipelineConfig {
        root_path: repo_root.to_string_lossy().to_string(),
        parallel_workers: 2,
        stages: codegraph_ir::pipeline::StageConfig {
            enable_ir_build: true,
            enable_chunking: true,
            enable_cross_file: false,
            enable_occurrences: false,
            enable_symbols: false,
            enable_points_to: false,
            enable_clone_detection: false,
            enable_effect_analysis: false,
            enable_taint: false,
            enable_cost_analysis: false,
            enable_repomap: false,
            enable_concurrency_analysis: false,
            enable_smt_verification: false,
            enable_lexical: false,
            enable_git_history: false,
            enable_query_engine: false,
        },
        ..Default::default()
    };

    let config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    ).with_pipeline_config(pipeline_config);

    // Create orchestrator
    let orchestrator = UnifiedOrchestrator::new(config).expect("Failed to create orchestrator");

    // Index repository
    orchestrator.index_repository().expect("Failed to index repository");

    // Verify completion
    assert!(orchestrator.is_completed());

    // Get context (Arc reference, zero-copy!)
    let context = orchestrator.get_context();

    // Verify data
    eprintln!("[Test] Context nodes: {}", context.nodes.len());
    eprintln!("[Test] Context edges: {}", context.edges.len());
    eprintln!("[Test] Context chunks: {}", context.chunks.len());

    assert!(context.nodes.len() > 0, "Should have nodes from L1");
    assert!(context.chunks.len() > 0, "Should have chunks from L2");

    // Get stats
    let stats = orchestrator.get_stats();
    eprintln!("[Test] Stats: {:?}", stats);
    assert_eq!(stats.stages_completed, 2); // L1 + L2
    assert_eq!(stats.stages_failed, 0);

    // Verify Arc is zero-copy
    let context2 = orchestrator.get_context();
    assert_eq!(
        std::sync::Arc::strong_count(&context),
        3 // orchestrator.state + context + context2
    );
}

#[test]
fn test_unified_orchestrator_with_taint() {
    // Test with L14 Taint Analysis enabled (important for TRCR!)
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let pipeline_config = E2EPipelineConfig {
        root_path: repo_root.to_string_lossy().to_string(),
        parallel_workers: 2,
        stages: codegraph_ir::pipeline::StageConfig {
            enable_ir_build: true,
            enable_chunking: true,
            enable_cross_file: true,
            enable_taint: true, // Enable L14 Taint!
            ..Default::default()
        },
        ..Default::default()
    };

    let config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    ).with_pipeline_config(pipeline_config);

    let orchestrator = UnifiedOrchestrator::new(config).expect("Failed to create orchestrator");

    // Index repository
    orchestrator.index_repository().expect("Failed to index repository");

    // Verify L14 completed
    assert!(orchestrator.is_stage_completed(codegraph_ir::pipeline::dag::StageId::L14TaintAnalysis));

    let stats = orchestrator.get_stats();
    eprintln!("[Test] Stages completed: {}", stats.stages_completed);
    assert_eq!(stats.stages_completed, 4); // L1 + L2 + L3 + L14
}

#[test]
fn test_unified_orchestrator_dag_dependencies() {
    // Test that DAG correctly enforces dependencies
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let pipeline_config = E2EPipelineConfig {
        root_path: repo_root.to_string_lossy().to_string(),
        parallel_workers: 2,
        stages: codegraph_ir::pipeline::StageConfig {
            enable_ir_build: true,
            enable_chunking: true,
            enable_cross_file: true,
            enable_points_to: true, // L6 depends on L1 + L3
            ..Default::default()
        },
        ..Default::default()
    };

    let config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    ).with_pipeline_config(pipeline_config);

    let orchestrator = UnifiedOrchestrator::new(config).expect("Failed to create orchestrator");

    // Index repository
    orchestrator.index_repository().expect("Failed to index repository");

    // Verify all dependencies completed
    use codegraph_ir::pipeline::dag::StageId;
    assert!(orchestrator.is_stage_completed(StageId::L1IrBuild));
    assert!(orchestrator.is_stage_completed(StageId::L2Chunking));
    assert!(orchestrator.is_stage_completed(StageId::L3CrossFile));
    assert!(orchestrator.is_stage_completed(StageId::L6PointsTo));

    let stats = orchestrator.get_stats();
    assert_eq!(stats.stages_completed, 4);
}
