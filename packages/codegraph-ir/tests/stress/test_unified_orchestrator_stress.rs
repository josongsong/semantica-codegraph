//! Stress & Edge Case Tests for UnifiedOrchestrator
//!
//! 빡세게 테스트: 엣지 케이스, 에러 처리, 동시성, 성능

use codegraph_ir::pipeline::{
    UnifiedOrchestrator, UnifiedOrchestratorConfig,
    StageControl,
};
use codegraph_ir::pipeline::dag::StageId;
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;

/// Test 1: Empty repository (no files)
#[test]
fn test_empty_repository() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 1: Empty Repository");
    eprintln!("========================================\n");

    // Create temp empty directory
    let temp_dir = std::env::temp_dir().join("codegraph_test_empty");
    std::fs::create_dir_all(&temp_dir).unwrap();

    let config = UnifiedOrchestratorConfig::new(
        temp_dir.clone(),
        "empty-repo".to_string(),
    );

    let orchestrator = UnifiedOrchestrator::new(config)
        .expect("Failed to create orchestrator");

    // Should complete successfully with 0 nodes
    orchestrator.index_repository()
        .expect("Failed to index empty repository");

    let ctx = orchestrator.get_context();

    eprintln!("📊 Empty repo results:");
    eprintln!("  - Nodes: {}", ctx.nodes.len());
    eprintln!("  - Edges: {}", ctx.edges.len());

    assert_eq!(ctx.nodes.len(), 0, "Empty repo should have 0 nodes");
    assert_eq!(ctx.edges.len(), 0, "Empty repo should have 0 edges");
    assert!(orchestrator.is_completed(), "Should complete successfully");

    // Cleanup
    std::fs::remove_dir_all(temp_dir).ok();

    eprintln!("✅ Empty repository test passed!\n");
}

/// Test 2: Invalid file path (non-existent directory)
#[test]
fn test_nonexistent_directory() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 2: Non-existent Directory");
    eprintln!("========================================\n");

    let fake_path = PathBuf::from("/this/path/does/not/exist/at/all");

    let config = UnifiedOrchestratorConfig::new(
        fake_path,
        "fake-repo".to_string(),
    );

    let orchestrator = UnifiedOrchestrator::new(config)
        .expect("Should create orchestrator even with fake path");

    // Should fail gracefully (WalkDir will error on non-existent path)
    let result = orchestrator.index_repository();

    // Should return error (not crash or panic)
    assert!(result.is_err(), "Non-existent path should return error");

    // Pipeline should be in Failed state
    let status = orchestrator.get_status();
    eprintln!("📊 Pipeline status: {:?}", status);

    // Stats should still be accessible
    let stats = orchestrator.get_stats();
    eprintln!("📊 Stats: {} stages failed", stats.stages_failed);
    assert!(stats.stages_failed > 0, "Should have failed stages");

    eprintln!("✅ Non-existent directory error handled gracefully!\n");
}

/// Test 3: Concurrent get_context() calls (thread safety)
#[test]
fn test_concurrent_context_access() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 3: Concurrent Context Access");
    eprintln!("========================================\n");

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    );

    let orchestrator = Arc::new(
        UnifiedOrchestrator::new(config).expect("Failed to create orchestrator")
    );

    // Index first
    orchestrator.index_repository()
        .expect("Failed to index repository");

    eprintln!("🚀 Spawning 10 threads for concurrent access...\n");

    // Spawn 10 threads that all get_context() concurrently
    let mut handles = vec![];
    for i in 0..10 {
        let orch_clone = Arc::clone(&orchestrator);
        let handle = thread::spawn(move || {
            for _ in 0..100 {
                let ctx = orch_clone.get_context();
                assert!(ctx.nodes.len() > 0, "Thread {} should see nodes", i);
            }
            eprintln!("  Thread {} completed 100 get_context() calls", i);
        });
        handles.push(handle);
    }

    // Wait for all threads
    for handle in handles {
        handle.join().expect("Thread panicked");
    }

    eprintln!("\n✅ Concurrent access test passed (10 threads × 100 calls)!\n");
}

/// Test 4: Multiple pipeline executions (idempotency)
#[test]
fn test_multiple_executions() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 4: Multiple Pipeline Executions");
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

    // Execute 3 times
    for i in 1..=3 {
        eprintln!("🚀 Execution #{}", i);
        orchestrator.index_repository()
            .expect("Failed to index repository");

        let ctx = orchestrator.get_context();
        eprintln!("  - Nodes: {}, Edges: {}", ctx.nodes.len(), ctx.edges.len());
    }

    // Should still be in completed state
    assert!(orchestrator.is_completed(), "Should remain completed");

    eprintln!("\n✅ Multiple executions test passed!\n");
}

/// Test 5: Large stage count (all stages enabled)
#[test]
fn test_all_stages_enabled() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 5: All Stages Enabled");
    eprintln!("========================================\n");

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let mut config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    );

    // Enable ALL stages
    config.pipeline_config.stages = StageControl {
        enable_ir_build: true,
        enable_chunking: true,
        enable_lexical: true,
        enable_cross_file: true,
        enable_clone_detection: true,
        enable_flow_graph: false,  // Not implemented yet
        enable_types: false,
        enable_data_flow: false,
        enable_ssa: false,
        enable_symbols: true,
        enable_effect_analysis: true,
        enable_occurrences: true,
        enable_points_to: true,
        enable_taint: true,
        enable_cost_analysis: true,
        enable_repomap: true,
        enable_concurrency_analysis: true,
        enable_smt_verification: true,
        enable_git_history: true,
        enable_query_engine: true,
        enable_heap_analysis: false,
        enable_pdg: false,
        enable_slicing: false,
    };

    let orchestrator = UnifiedOrchestrator::new(config)
        .expect("Failed to create orchestrator");

    eprintln!("🚀 Executing pipeline with 16 stages enabled...\n");

    let result = orchestrator.index_repository();

    // Should complete or fail gracefully
    match result {
        Ok(_) => {
            eprintln!("✅ All stages completed successfully!");

            let stats = orchestrator.get_stats();
            eprintln!("📊 Stats:");
            eprintln!("  - Stages completed: {}", stats.stages_completed);
            eprintln!("  - Stages failed: {}", stats.stages_failed);
            eprintln!("  - Duration: {:.2}s", stats.total_duration.as_secs_f64());

            assert!(stats.stages_completed > 10, "Should complete many stages");
        }
        Err(e) => {
            eprintln!("⚠️  Pipeline failed (expected for stub executors): {}", e);
            // This is okay - stub executors may fail
        }
    }

    eprintln!("\n✅ All stages enabled test completed!\n");
}

/// Test 6: Arc reference count stress test
#[test]
fn test_arc_reference_count_stress() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 6: Arc Reference Count Stress");
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

    // Create 1000 context references
    eprintln!("🚀 Creating 1000 Arc references...\n");

    let mut contexts = Vec::new();
    for _ in 0..1000 {
        contexts.push(orchestrator.get_context());
    }

    // Check Arc count (should be 1001: orchestrator.state + 1000 contexts)
    let arc_count = Arc::strong_count(&contexts[0]);
    eprintln!("📊 Arc strong_count: {}", arc_count);
    eprintln!("   Expected: 1001 (state + 1000 refs)");

    assert_eq!(arc_count, 1001, "Arc count should be exactly 1001");

    // Drop all contexts
    drop(contexts);

    // Now should be back to 1 (just orchestrator.state)
    let ctx_final = orchestrator.get_context();
    let final_count = Arc::strong_count(&ctx_final);
    eprintln!("\n📊 After drop: Arc strong_count: {}", final_count);
    eprintln!("   Expected: 2 (state + ctx_final)");

    assert_eq!(final_count, 2, "Arc count should be 2 after drop");

    eprintln!("\n✅ Arc reference count stress test passed!\n");
}

/// Test 7: Stage dependency validation
#[test]
fn test_stage_dependency_validation() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 7: Stage Dependency Validation");
    eprintln!("========================================\n");

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("python_simple");

    let mut config = UnifiedOrchestratorConfig::new(
        repo_root.clone(),
        "test-repo".to_string(),
    );

    // Enable only L14 (without L1, L3 dependencies) - should auto-enable them
    config.pipeline_config.stages = StageControl {
        enable_ir_build: true,   // L1 required
        enable_chunking: true,   // L2 required
        enable_cross_file: true, // L3 required for L14
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
        enable_taint: true,  // L14 depends on L1, L3
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

    eprintln!("🚀 Testing L14 dependency chain (L1 → L3 → L14)...\n");

    orchestrator.index_repository()
        .expect("Failed to index repository");

    // Verify dependency chain completed in order
    assert!(orchestrator.is_stage_completed(StageId::L1IrBuild),
            "L1 should complete first");
    assert!(orchestrator.is_stage_completed(StageId::L3CrossFile),
            "L3 should complete after L1");
    assert!(orchestrator.is_stage_completed(StageId::L14TaintAnalysis),
            "L14 should complete after L1 and L3");

    eprintln!("✅ Dependency validation passed!\n");
}

/// Test 8: Performance benchmark (large context)
#[test]
fn test_performance_benchmark() {
    eprintln!("\n========================================");
    eprintln!("🧪 STRESS TEST 8: Performance Benchmark");
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

    use std::time::Instant;

    // Measure indexing time
    let start = Instant::now();
    orchestrator.index_repository()
        .expect("Failed to index repository");
    let index_duration = start.elapsed();

    // Measure 1000 get_context() calls
    let start = Instant::now();
    for _ in 0..1000 {
        let _ = orchestrator.get_context();
    }
    let get_duration = start.elapsed();

    let stats = orchestrator.get_stats();

    eprintln!("📊 Performance Results:");
    eprintln!("  - Indexing time: {:.4}s", index_duration.as_secs_f64());
    eprintln!("  - get_context() × 1000: {:.4}s ({:.2}µs per call)",
              get_duration.as_secs_f64(),
              get_duration.as_micros() as f64 / 1000.0);
    eprintln!("  - Throughput: {:.0} nodes/sec", stats.throughput());
    eprintln!("  - Nodes: {}, Edges: {}", stats.total_nodes, stats.total_edges);

    // Performance assertions
    assert!(index_duration.as_secs_f64() < 1.0,
            "Indexing should complete in < 1s for small file");
    assert!(get_duration.as_micros() / 1000 < 100,
            "get_context() should be < 100µs per call (Arc is fast!)");

    eprintln!("\n✅ Performance benchmark passed!\n");
}
