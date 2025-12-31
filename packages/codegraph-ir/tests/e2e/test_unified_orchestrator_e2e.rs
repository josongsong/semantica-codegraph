//! End-to-End Integration Test for UnifiedOrchestrator
//!
//! 실제 Python 파일로 전체 파이프라인 테스트

use codegraph_ir::pipeline::{
    UnifiedOrchestrator, UnifiedOrchestratorConfig,
    E2EPipelineConfig, StageControl,
};
use codegraph_ir::pipeline::dag::StageId;
use std::path::PathBuf;

#[test]
fn test_unified_orchestrator_full_pipeline() {
    eprintln!("\n========================================");
    eprintln!("🧪 TEST: Full Pipeline with Real Python File");
    eprintln!("========================================\n");

    // Get test fixture path
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    // Create orchestrator with minimal config (just L1 + L2)
    let mut config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    );

    // Override to enable only L1 + L2
    config.pipeline_config.stages = StageControl {
        enable_ir_build: true,
        enable_chunking: true,
        enable_cross_file: false,
        enable_lexical: false,
        enable_clone_detection: false,
        enable_flow_graph: false,
        enable_types: false,
        enable_data_flow: false,
        enable_ssa: false,
        enable_symbols: false,
        enable_effect_analysis: false,
        enable_occurrences: false,
        enable_points_to: false,
        enable_taint: false,
        enable_cost_analysis: false,
        enable_repomap: false,
        enable_concurrency_analysis: false,
        enable_smt_verification: false,
        enable_git_history: false,
        enable_query_engine: false,
        enable_heap_analysis: false,
        enable_pdg: false,
        enable_slicing: false,
    };

    let orchestrator = UnifiedOrchestrator::new(config)
        .expect("Failed to create orchestrator");

    eprintln!("✅ Orchestrator created with {} executors",
        orchestrator.get_completed_stages().len());

    // Execute pipeline
    eprintln!("\n🚀 Executing pipeline...\n");
    orchestrator.index_repository()
        .expect("Failed to index repository");

    eprintln!("\n✅ Pipeline completed!\n");

    // Verify results
    assert!(orchestrator.is_completed(), "Pipeline should be completed");
    assert!(orchestrator.is_stage_completed(StageId::L1IrBuild), "L1 should be completed");
    assert!(orchestrator.is_stage_completed(StageId::L2Chunking), "L2 should be completed");

    // Get context (Arc reference - zero copy!)
    let ctx = orchestrator.get_context();

    eprintln!("📊 Results:");
    eprintln!("  - Nodes: {}", ctx.nodes.len());
    eprintln!("  - Edges: {}", ctx.edges.len());
    eprintln!("  - Chunks: {}", ctx.chunks.len());
    eprintln!("  - Occurrences: {}", ctx.occurrences.len());

    // Verify we have data
    assert!(ctx.nodes.len() > 0, "Should have nodes from L1");
    // Note: chunks may be 0 if functions are too small (< min_chunk_size)
    eprintln!("  💡 Chunks: {} (may be 0 if functions < {} lines)",
        ctx.chunks.len(), 5);  // min_chunk_size default is 5

    // Verify Arc is zero-copy
    let ctx2 = orchestrator.get_context();
    let arc_count = std::sync::Arc::strong_count(&ctx);
    eprintln!("\n🔍 Arc strong_count: {} (orchestrator.state + ctx + ctx2)", arc_count);
    assert_eq!(arc_count, 3, "Arc should have 3 references");

    // Get stats
    let stats = orchestrator.get_stats();
    eprintln!("\n📈 Stats:");
    eprintln!("  - Stages completed: {}", stats.stages_completed);
    eprintln!("  - Stages failed: {}", stats.stages_failed);
    eprintln!("  - Total duration: {:.2}s", stats.total_duration.as_secs_f64());
    eprintln!("  - Throughput: {:.0} nodes/sec", stats.throughput());

    assert_eq!(stats.stages_completed, 2, "Should have 2 stages completed (L1 + L2)");
    assert_eq!(stats.stages_failed, 0, "Should have 0 failed stages");

    eprintln!("\n✅ All assertions passed!");
    eprintln!("========================================\n");
}

#[test]
fn test_orchestrator_with_taint_analysis() {
    eprintln!("\n========================================");
    eprintln!("🧪 TEST: Pipeline with L14 Taint Analysis");
    eprintln!("========================================\n");

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let mut config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    );

    // Enable L1, L2, L3, L14
    config.pipeline_config.stages.enable_taint = true;

    let orchestrator = UnifiedOrchestrator::new(config)
        .expect("Failed to create orchestrator");

    eprintln!("🚀 Executing pipeline with L14 Taint...\n");
    orchestrator.index_repository()
        .expect("Failed to index repository");

    // Verify L14 completed
    assert!(orchestrator.is_stage_completed(StageId::L14TaintAnalysis),
        "L14 Taint Analysis should be completed");

    let stats = orchestrator.get_stats();
    eprintln!("\n📊 Stages completed: {} (L1 + L2 + L3 + L14)", stats.stages_completed);
    assert_eq!(stats.stages_completed, 4, "Should have 4 stages");

    eprintln!("✅ Taint analysis test passed!");
    eprintln!("========================================\n");
}

#[test]
fn test_orchestrator_dag_dependencies() {
    eprintln!("\n========================================");
    eprintln!("🧪 TEST: DAG Dependency Resolution");
    eprintln!("========================================\n");

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let mut config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    );

    // Enable L6 (depends on L1 + L3)
    config.pipeline_config.stages.enable_points_to = true;

    let orchestrator = UnifiedOrchestrator::new(config)
        .expect("Failed to create orchestrator");

    eprintln!("🚀 Executing pipeline with L6 Points-to...\n");
    orchestrator.index_repository()
        .expect("Failed to index repository");

    // Verify all dependencies completed
    assert!(orchestrator.is_stage_completed(StageId::L1IrBuild), "L1 should be completed");
    assert!(orchestrator.is_stage_completed(StageId::L2Chunking), "L2 should be completed");
    assert!(orchestrator.is_stage_completed(StageId::L3CrossFile), "L3 should be completed");
    assert!(orchestrator.is_stage_completed(StageId::L6PointsTo), "L6 should be completed");

    let stats = orchestrator.get_stats();
    eprintln!("\n📊 Stages completed: {}", stats.stages_completed);
    assert_eq!(stats.stages_completed, 4, "Should have 4 stages (L1 + L2 + L3 + L6)");

    eprintln!("✅ DAG dependency test passed!");
    eprintln!("========================================\n");
}

#[test]
fn test_zero_copy_memory_sharing() {
    eprintln!("\n========================================");
    eprintln!("🧪 TEST: Zero-Copy Memory Sharing (Arc)");
    eprintln!("========================================\n");

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    );

    let orchestrator = UnifiedOrchestrator::new(config)
        .expect("Failed to create orchestrator");

    orchestrator.index_repository()
        .expect("Failed to index repository");

    // Get context multiple times
    let ctx1 = orchestrator.get_context();
    let ctx2 = orchestrator.get_context();
    let ctx3 = orchestrator.get_context();

    eprintln!("📊 Context info:");
    eprintln!("  - Nodes: {}", ctx1.nodes.len());
    eprintln!("  - Edges: {}", ctx1.edges.len());

    // Check Arc count (orchestrator.state + ctx1 + ctx2 + ctx3)
    let arc_count = std::sync::Arc::strong_count(&ctx1);
    eprintln!("\n🔍 Arc strong_count: {}", arc_count);
    eprintln!("   Expected: 4 (state + ctx1 + ctx2 + ctx3)");

    assert_eq!(arc_count, 4, "Arc should be shared 4 times");

    // Verify all contexts point to same data
    assert!(std::sync::Arc::ptr_eq(&ctx1, &ctx2), "ctx1 and ctx2 should point to same Arc");
    assert!(std::sync::Arc::ptr_eq(&ctx2, &ctx3), "ctx2 and ctx3 should point to same Arc");

    eprintln!("✅ Zero-copy verified! All contexts share same Arc.");
    eprintln!("========================================\n");
}
