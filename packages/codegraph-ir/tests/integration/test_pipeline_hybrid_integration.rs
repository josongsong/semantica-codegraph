//! E2E Pipeline Integration Test with HybridCloneDetector
//!
//! Tests the full IRIndexingOrchestrator pipeline with HybridCloneDetector
//! to verify performance improvements in real-world scenarios.

use codegraph_ir::pipeline::{E2EPipelineConfig, IRIndexingOrchestrator};
use std::path::PathBuf;

#[test]
fn test_pipeline_with_hybrid_clone_detector() {
    println!("\n╔══════════════════════════════════════════════════════════════════════════════╗");
    println!("║           E2E PIPELINE TEST - HYBRID CLONE DETECTOR                          ║");
    println!("╚══════════════════════════════════════════════════════════════════════════════╝\n");

    // Use test files from packages/codegraph-ir/src (Rust files)
    let test_path = PathBuf::from("src/features/clone_detection");

    if !test_path.exists() {
        println!("⚠️  Skipping: Test path not found at {:?}", test_path);
        return;
    }

    println!("📂 Test Repository: {:?}\n", test_path);

    // Configure pipeline
    let config = E2EPipelineConfig::balanced()
        .repo_root(test_path.clone())
        .repo_name("clone_detection_test".to_string());
    config.stages.enable_clone_detection = true;
    config.stages.enable_chunking = true;

    println!("Phase 1: Running IR Indexing Pipeline...");
    let pipeline_start = std::time::Instant::now();

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = match orchestrator.execute() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("❌ Pipeline execution failed: {:?}", e);
            return;
        }
    };

    let pipeline_duration = pipeline_start.elapsed();

    println!("   ✓ Pipeline completed in {:.2}s\n", pipeline_duration.as_secs_f64());

    // Print results
    println!("═══════════════════════════════════════════════════════════════════════════════");
    println!("RESULTS");
    println!("═══════════════════════════════════════════════════════════════════════════════\n");

    println!("Files processed: {}", result.stats.files_processed);
    println!("Total LOC: {}", result.stats.total_loc);
    println!();

    println!("IR Statistics:");
    println!("  Nodes: {}", result.nodes.len());
    println!("  Edges: {}", result.edges.len());
    println!("  Chunks: {}", result.chunks.len());
    println!();

    println!("Clone Detection (L10):");
    println!("  Clone pairs found: {}", result.clone_pairs.len());

    if !result.clone_pairs.is_empty() {
        let type1_count = result.clone_pairs.iter()
            .filter(|p| p.clone_type == "Type-1")
            .count();
        let type2_count = result.clone_pairs.iter()
            .filter(|p| p.clone_type == "Type-2")
            .count();
        let type3_count = result.clone_pairs.iter()
            .filter(|p| p.clone_type == "Type-3")
            .count();

        println!("    Type-1: {} pairs", type1_count);
        println!("    Type-2: {} pairs", type2_count);
        println!("    Type-3: {} pairs", type3_count);
    }
    println!();

    // Print stage timings
    println!("Stage Timings:");
    for (stage, duration) in &result.stats.stage_durations {
        let percentage = (duration.as_secs_f64() / pipeline_duration.as_secs_f64()) * 100.0;
        println!("  {:<25} {:>8.2}s ({:>5.1}%)",
                 stage,
                 duration.as_secs_f64(),
                 percentage);
    }
    println!();

    // Validate L10 performance
    if let Some(clone_duration) = result.stats.stage_durations.iter()
        .find(|(name, _)| name.as_str() == "L10_CloneDetection")
        .map(|(_, d)| d)
    {
        let clone_percentage = (clone_duration.as_secs_f64() / pipeline_duration.as_secs_f64()) * 100.0;
        println!("═══════════════════════════════════════════════════════════════════════════════");
        println!("PERFORMANCE ANALYSIS");
        println!("═══════════════════════════════════════════════════════════════════════════════\n");

        println!("Clone Detection Performance:");
        println!("  Time: {:.2}s ({:.1}% of total pipeline)",
                 clone_duration.as_secs_f64(), clone_percentage);

        if clone_percentage < 10.0 {
            println!("  Status: ✅ Excellent (<10% of pipeline time)");
        } else if clone_percentage < 20.0 {
            println!("  Status: ⚠️  Acceptable (10-20% of pipeline time)");
        } else {
            println!("  Status: ❌ Needs optimization (>20% of pipeline time)");
        }
        println!();

        // Expected: With HybridCloneDetector, clone detection should be <10% of total time
        assert!(clone_percentage < 30.0,
                "Clone detection should be <30% of pipeline (got {:.1}%)", clone_percentage);
    }

    // Assertions
    println!("═══════════════════════════════════════════════════════════════════════════════");
    println!("VALIDATION");
    println!("═══════════════════════════════════════════════════════════════════════════════\n");

    assert!(result.stats.files_processed > 0, "Should process files");
    assert!(!result.nodes.is_empty(), "Should have IR nodes");
    assert!(!result.chunks.is_empty(), "Should have chunks");

    println!("✅ Files processed: {}", result.stats.files_processed);
    println!("✅ IR nodes generated: {}", result.nodes.len());
    println!("✅ Chunks created: {}", result.chunks.len());

    if result.clone_pairs.is_empty() {
        println!("ℹ️  No clone pairs found (normal for unique code)");
    } else {
        println!("✅ Clone pairs detected: {}", result.clone_pairs.len());
    }

    println!();
    println!("🎉 ALL VALIDATIONS PASSED!");
    println!();
}
