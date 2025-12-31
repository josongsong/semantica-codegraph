//! Real-World Integration Tests
//!
//! Tests 23-level pipeline on actual Python code from the project.

use codegraph_ir::pipeline::{E2EPipelineConfig, IRIndexingOrchestrator};
use std::path::PathBuf;

/// Test on real benchmark code
#[test]
fn test_real_world_benchmark_code() {
    let project_root = find_project_root();
    let benchmark_path = project_root.join("tools/benchmark/core");

    if !benchmark_path.exists() {
        eprintln!("Skipping: benchmark code not found at {:?}", benchmark_path);
        return;
    }

    let config = E2EPipelineConfig::balanced()
        .repo_root(benchmark_path.clone())
        .repo_name("benchmark_core".to_string());

    println!("\n========================================");
    println!("Testing Real-World Code: Benchmark Core");
    println!("Path: {:?}", benchmark_path);
    println!("========================================\n");

    let start = std::time::Instant::now();
    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed on real code");
    let duration = start.elapsed();

    println!("\n========================================");
    println!("Pipeline Results");
    println!("========================================");
    println!("Duration: {:?}", duration);
    println!("Files processed: {}", result.stats.files_processed);
    println!("Total LOC: {}", result.stats.total_loc);
    println!("\nIR Statistics:");
    println!("  Nodes: {}", result.nodes.len());
    println!("  Edges: {}", result.edges.len());
    println!("  Chunks: {}", result.chunks.len());
    println!("  Symbols: {}", result.symbols.len());
    println!("  Occurrences: {}", result.occurrences.len());

    println!("\nAnalysis Results:");
    println!("  L10 Clone pairs: {}", result.clone_pairs.len());
    println!("  L13 Effect results: {}", result.effect_results.len());
    println!("  L18 Concurrency issues: {}", result.concurrency_results.len());
    println!("  L21 SMT results: {}", result.smt_results.len());
    println!("  L33 Git history: {}", result.git_history_results.len());

    if let Some(qe_stats) = result.query_engine_stats {
        println!("  L37 Query engine: {} nodes, {} edges",
            qe_stats.node_count, qe_stats.edge_count);
    }

    println!("\nStage Timings:");
    for (stage, duration) in &result.stats.stage_durations {
        println!("  {}: {:?}", stage, duration);
    }

    // Validate results
    assert!(result.stats.files_processed > 0, "Should process files");
    assert!(!result.nodes.is_empty(), "Should have IR nodes");
    assert!(!result.chunks.is_empty(), "Should have chunks");

    // Should have found some functions
    assert!(!result.symbols.is_empty(), "Should have symbols");

    // Effect analysis should run
    assert!(!result.effect_results.is_empty(), "Should have effect analysis results");
}

/// Test on packages/codegraph-engine source code
#[test]
fn test_real_world_codegraph_engine() {
    let project_root = find_project_root();
    let engine_path = project_root.join("packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir");

    if !engine_path.exists() {
        eprintln!("Skipping: codegraph-engine not found at {:?}", engine_path);
        return;
    }

    let config = E2EPipelineConfig::balanced()
        .repo_root(engine_path.clone())
        .repo_name("codegraph_engine_ir".to_string());

    println!("\n========================================");
    println!("Testing Real-World Code: Codegraph Engine IR");
    println!("Path: {:?}", engine_path);
    println!("========================================\n");

    let start = std::time::Instant::now();
    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed on engine code");
    let duration = start.elapsed();

    println!("\n========================================");
    println!("Pipeline Results");
    println!("========================================");
    println!("Duration: {:?}", duration);
    println!("Files processed: {}", result.stats.files_processed);
    println!("Total LOC: {}", result.stats.total_loc);
    println!("\nIR Statistics:");
    println!("  Nodes: {}", result.nodes.len());
    println!("  Edges: {}", result.edges.len());
    println!("  Chunks: {}", result.chunks.len());
    println!("  Symbols: {}", result.symbols.len());

    println!("\nAnalysis Results:");
    println!("  L10 Clone pairs: {}", result.clone_pairs.len());
    println!("  L13 Effect results: {}", result.effect_results.len());

    // Should find some pure functions
    let pure_count = result.effect_results.iter().filter(|e| e.is_pure).count();
    let impure_count = result.effect_results.iter().filter(|e| !e.is_pure).count();
    println!("    Pure functions: {}", pure_count);
    println!("    Impure functions: {}", impure_count);

    println!("  L18 Concurrency issues: {}", result.concurrency_results.len());

    if !result.concurrency_results.is_empty() {
        println!("\n  Concurrency Issues Found:");
        for issue in result.concurrency_results.iter().take(5) {
            println!("    - {} on '{}' ({})",
                issue.issue_type, issue.shared_variable, issue.severity);
        }
    }

    println!("  L21 SMT results: {}", result.smt_results.len());

    // Clone detection
    if !result.clone_pairs.is_empty() {
        println!("\n  Clone Pairs Found:");
        for pair in result.clone_pairs.iter().take(5) {
            println!("    - {} (similarity: {:.2}%)",
                pair.clone_type, pair.similarity * 100.0);
        }
    }

    // Validate
    assert!(result.stats.files_processed > 5, "Should process multiple files");
    assert!(result.nodes.len() > 100, "Should have many IR nodes");
    assert!(result.effect_results.len() > 10, "Should analyze many functions");
}

/// Stress test: Process larger directory
#[test]
#[ignore] // Run with --ignored flag
fn test_real_world_full_package() {
    let project_root = find_project_root();
    let package_path = project_root.join("packages/codegraph-engine/codegraph_engine");

    if !package_path.exists() {
        eprintln!("Skipping: codegraph-engine package not found");
        return;
    }

    let config = E2EPipelineConfig::balanced()
        .repo_root(package_path.clone())
        .repo_name("codegraph_engine_full".to_string());

    println!("\n========================================");
    println!("STRESS TEST: Full Codegraph Engine Package");
    println!("Path: {:?}", package_path);
    println!("========================================\n");

    let start = std::time::Instant::now();
    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed on full package");
    let duration = start.elapsed();

    println!("\n========================================");
    println!("STRESS TEST Results");
    println!("========================================");
    println!("Duration: {:?}", duration);
    println!("Files processed: {}", result.stats.files_processed);
    println!("Total LOC: {}", result.stats.total_loc);
    println!("\nIR Statistics:");
    println!("  Nodes: {}", result.nodes.len());
    println!("  Edges: {}", result.edges.len());
    println!("  Chunks: {}", result.chunks.len());
    println!("  Symbols: {}", result.symbols.len());
    println!("  Occurrences: {}", result.occurrences.len());

    println!("\nAnalysis Results:");
    println!("  L10 Clone pairs: {}", result.clone_pairs.len());
    println!("  L13 Effect results: {}", result.effect_results.len());
    println!("  L18 Concurrency issues: {}", result.concurrency_results.len());
    println!("  L21 SMT results: {}", result.smt_results.len());
    println!("  L33 Git history: {}", result.git_history_results.len());

    println!("\nPerformance Metrics:");
    let loc_per_sec = result.stats.total_loc as f64 / duration.as_secs_f64();
    println!("  Throughput: {:.0} LOC/sec", loc_per_sec);
    println!("  Avg per file: {:?}", duration / result.stats.files_processed as u32);

    // Should handle large codebase
    assert!(result.stats.files_processed > 20, "Should process many files");
    assert!(result.stats.total_loc > 5000, "Should process significant LOC");
    assert!(duration.as_secs() < 60, "Should complete within 60 seconds");
}

// ============================================================================
// Helper Functions
// ============================================================================

fn find_project_root() -> PathBuf {
    // Try to find the project root by looking for Cargo.toml
    let mut current = std::env::current_dir().expect("Failed to get current dir");

    loop {
        let cargo_toml = current.join("Cargo.toml");
        if cargo_toml.exists() {
            // Check if this is the codegraph-ir package
            if current.ends_with("codegraph-ir") {
                // Go up to find the monorepo root
                if let Some(parent) = current.parent() {
                    if let Some(grandparent) = parent.parent() {
                        if let Some(root) = grandparent.parent() {
                            return root.to_path_buf();
                        }
                    }
                }
            }
            return current;
        }

        if let Some(parent) = current.parent() {
            current = parent.to_path_buf();
        } else {
            // Fallback: assume we're in tests/
            return PathBuf::from("../../../..");
        }
    }
}
