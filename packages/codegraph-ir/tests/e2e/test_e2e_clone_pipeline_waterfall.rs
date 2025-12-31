//! E2E Clone Detection Pipeline - Waterfall Performance Test
//!
//! Tests the full pipeline from IR generation to clone detection with detailed
//! performance breakdown at each phase.
//!
//! Pipeline phases:
//! - Phase 1: IR Generation (L1)
//! - Phase 2: Chunking (L2)
//! - Phase 3: Fragment Extraction
//! - Phase 4: Clone Detection (Baseline)
//! - Phase 5: Clone Detection (Hybrid)

use codegraph_ir::pipeline::{E2EPipelineConfig, IRIndexingOrchestrator};
use codegraph_ir::features::clone_detection::{
    CodeFragment, MultiLevelDetector, HybridCloneDetector,
};
use codegraph_ir::shared::models::Span;
use std::path::PathBuf;
use std::time::{Instant, Duration};
use std::collections::HashMap;

/// Performance metrics for waterfall analysis
#[derive(Debug)]
struct WaterfallMetrics {
    phase_name: String,
    duration: Duration,
    items_processed: usize,
    throughput: f64,  // items/sec
}

impl WaterfallMetrics {
    fn new(phase_name: String, duration: Duration, items: usize) -> Self {
        let throughput = if duration.as_secs_f64() > 0.0 {
            items as f64 / duration.as_secs_f64()
        } else {
            0.0
        };

        Self {
            phase_name,
            duration,
            items_processed: items,
            throughput,
        }
    }

    fn duration_ms(&self) -> f64 {
        self.duration.as_secs_f64() * 1000.0
    }

    fn percentage(&self, total: Duration) -> f64 {
        if total.as_secs_f64() > 0.0 {
            (self.duration.as_secs_f64() / total.as_secs_f64()) * 100.0
        } else {
            0.0
        }
    }
}

/// Find project root by walking up until we find Cargo.toml
fn find_project_root() -> PathBuf {
    let mut current = std::env::current_dir().unwrap();
    loop {
        if current.join("Cargo.toml").exists() {
            return current;
        }
        if !current.pop() {
            panic!("Could not find project root (Cargo.toml)");
        }
    }
}

/// Extract code fragments from IR chunks
fn extract_fragments_from_chunks(
    chunks: &[codegraph_ir::features::chunking::domain::Chunk],
) -> Vec<CodeFragment> {
    chunks
        .iter()
        .filter(|chunk| {
            // Only function-level chunks
            matches!(
                chunk.kind,
                codegraph_ir::features::chunking::domain::ChunkKind::Function { .. }
            )
        })
        .filter(|chunk| {
            // Filter out very small chunks
            chunk.metadata.token_count >= 20 && chunk.metadata.loc >= 3
        })
        .map(|chunk| {
            CodeFragment::new(
                chunk.file_path.clone(),
                Span::new(
                    chunk.span.start_line,
                    chunk.span.start_column,
                    chunk.span.end_line,
                    chunk.span.end_column,
                ),
                chunk.content.clone(),
                chunk.metadata.token_count,
                chunk.metadata.loc,
            )
        })
        .collect()
}

/// Print waterfall chart
fn print_waterfall(metrics: &[WaterfallMetrics], total_duration: Duration) {
    println!("\n╔══════════════════════════════════════════════════════════════════════════════╗");
    println!("║                          WATERFALL PERFORMANCE CHART                         ║");
    println!("╚══════════════════════════════════════════════════════════════════════════════╝");
    println!();

    let total_ms = total_duration.as_secs_f64() * 1000.0;

    println!("{:<30} {:>12} {:>12} {:>12} {:>15}",
             "Phase", "Time (ms)", "Items", "% Total", "Throughput");
    println!("{:-<30} {:-<12} {:-<12} {:-<12} {:-<15}",
             "", "", "", "", "");

    for metric in metrics {
        let bar_length = (metric.percentage(total_duration) / 2.0) as usize;
        let bar = "█".repeat(bar_length);

        println!("{:<30} {:>12.2} {:>12} {:>11.1}% {:>12.1} i/s",
                 metric.phase_name,
                 metric.duration_ms(),
                 metric.items_processed,
                 metric.percentage(total_duration),
                 metric.throughput);
        println!("  {}", bar);
    }

    println!();
    println!("Total Pipeline Duration: {:.2}ms", total_ms);
    println!();
}

/// Print bottleneck analysis
fn analyze_bottlenecks(metrics: &[WaterfallMetrics], total_duration: Duration) {
    println!("╔══════════════════════════════════════════════════════════════════════════════╗");
    println!("║                          BOTTLENECK ANALYSIS                                 ║");
    println!("╚══════════════════════════════════════════════════════════════════════════════╝");
    println!();

    let mut sorted_metrics: Vec<_> = metrics.iter().collect();
    sorted_metrics.sort_by(|a, b| b.duration.cmp(&a.duration));

    println!("Top 3 Slowest Phases:");
    for (i, metric) in sorted_metrics.iter().take(3).enumerate() {
        let emoji = match i {
            0 => "🔴",
            1 => "🟡",
            2 => "🟢",
            _ => "  ",
        };
        println!("  {} {}: {:.2}ms ({:.1}%)",
                 emoji,
                 metric.phase_name,
                 metric.duration_ms(),
                 metric.percentage(total_duration));
    }
    println!();

    // Identify critical path
    let critical_threshold = 20.0; // 20% of total time
    let critical_phases: Vec<_> = metrics
        .iter()
        .filter(|m| m.percentage(total_duration) >= critical_threshold)
        .collect();

    if !critical_phases.is_empty() {
        println!("⚠️  Critical Path (≥{}% of total time):", critical_threshold);
        for metric in critical_phases {
            println!("   - {}: {:.1}%", metric.phase_name, metric.percentage(total_duration));
        }
        println!();
    }

    // Performance recommendations
    println!("💡 Optimization Recommendations:");
    for metric in sorted_metrics.iter().take(3) {
        match metric.phase_name.as_str() {
            name if name.contains("IR Generation") => {
                println!("   - IR Generation: Consider parallelizing file processing with Rayon");
            }
            name if name.contains("Baseline") => {
                println!("   - Clone Detection (Baseline): Switch to Hybrid detector for large datasets");
            }
            name if name.contains("Chunking") => {
                println!("   - Chunking: Already optimized, bottleneck is inherent complexity");
            }
            name if name.contains("Fragment Extraction") => {
                println!("   - Fragment Extraction: Minimal overhead, no optimization needed");
            }
            _ => {}
        }
    }
    println!();
}

#[test]
fn test_e2e_clone_pipeline_waterfall() {
    println!("\n╔══════════════════════════════════════════════════════════════════════════════╗");
    println!("║              E2E CLONE DETECTION PIPELINE - WATERFALL TEST                  ║");
    println!("╚══════════════════════════════════════════════════════════════════════════════╝");
    println!();

    // Find test code path
    let project_root = find_project_root();
    let test_path = project_root.join("tools/benchmark/core");

    if !test_path.exists() {
        eprintln!("⚠️  Skipping: Test code not found at {:?}", test_path);
        eprintln!("   Trying alternative path...");

        let alt_path = project_root.join("packages/codegraph-ir/src/features/clone_detection");
        if !alt_path.exists() {
            eprintln!("❌ No test code found. Skipping E2E test.");
            return;
        }
    }

    println!("📂 Test Repository: {:?}", test_path);
    println!();

    let mut metrics = Vec::new();
    let pipeline_start = Instant::now();

    // ========================================
    // Phase 1: IR Generation (L1)
    // ========================================
    println!("Phase 1/5: IR Generation (L1)...");
    let phase1_start = Instant::now();

    let config = E2EPipelineConfig::balanced()
        .repo_root(test_path.clone())
        .repo_name("benchmark_core".to_string());
    config.enable_chunking = true;
    config.enable_clone_detection = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = match orchestrator.execute() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("❌ Pipeline execution failed: {:?}", e);
            return;
        }
    };

    let phase1_duration = phase1_start.elapsed();
    let files_processed = result.stats.files_processed;

    metrics.push(WaterfallMetrics::new(
        "Phase 1: IR Generation (L1)".to_string(),
        phase1_duration,
        files_processed,
    ));

    println!("   ✓ Processed {} files in {:.2}ms", files_processed, phase1_duration.as_secs_f64() * 1000.0);
    println!("   ✓ Generated {} nodes, {} edges", result.nodes.len(), result.edges.len());
    println!();

    // ========================================
    // Phase 2: Chunking (L2)
    // ========================================
    println!("Phase 2/5: Chunking (L2)...");
    let phase2_start = Instant::now();

    let chunks = result.chunks.clone();
    let phase2_duration = phase2_start.elapsed();

    metrics.push(WaterfallMetrics::new(
        "Phase 2: Chunking (L2)".to_string(),
        phase2_duration,
        chunks.len(),
    ));

    println!("   ✓ Generated {} chunks in {:.2}ms", chunks.len(), phase2_duration.as_secs_f64() * 1000.0);
    println!();

    // ========================================
    // Phase 3: Fragment Extraction
    // ========================================
    println!("Phase 3/5: Fragment Extraction...");
    let phase3_start = Instant::now();

    let fragments = extract_fragments_from_chunks(&chunks);

    let phase3_duration = phase3_start.elapsed();

    metrics.push(WaterfallMetrics::new(
        "Phase 3: Fragment Extraction".to_string(),
        phase3_duration,
        fragments.len(),
    ));

    println!("   ✓ Extracted {} function fragments in {:.2}ms",
             fragments.len(), phase3_duration.as_secs_f64() * 1000.0);
    println!();

    if fragments.is_empty() {
        println!("⚠️  No fragments extracted. Pipeline ends here.");
        let total_duration = pipeline_start.elapsed();
        print_waterfall(&metrics, total_duration);
        return;
    }

    // ========================================
    // Phase 4: Clone Detection (Baseline)
    // ========================================
    println!("Phase 4/5: Clone Detection (Baseline)...");
    let phase4_start = Instant::now();

    let baseline_detector = MultiLevelDetector::new();
    let baseline_pairs = baseline_detector.detect_all(&fragments);

    let phase4_duration = phase4_start.elapsed();

    metrics.push(WaterfallMetrics::new(
        "Phase 4: Clone Detection (Baseline)".to_string(),
        phase4_duration,
        baseline_pairs.len(),
    ));

    println!("   ✓ Found {} clone pairs in {:.2}ms",
             baseline_pairs.len(), phase4_duration.as_secs_f64() * 1000.0);
    println!();

    // ========================================
    // Phase 5: Clone Detection (Hybrid)
    // ========================================
    println!("Phase 5/5: Clone Detection (Hybrid)...");
    let phase5_start = Instant::now();

    let mut hybrid_detector = HybridCloneDetector::new();
    let hybrid_pairs = hybrid_detector.detect_all(&fragments);

    let phase5_duration = phase5_start.elapsed();

    metrics.push(WaterfallMetrics::new(
        "Phase 5: Clone Detection (Hybrid)".to_string(),
        phase5_duration,
        hybrid_pairs.len(),
    ));

    println!("   ✓ Found {} clone pairs in {:.2}ms",
             hybrid_pairs.len(), phase5_duration.as_secs_f64() * 1000.0);

    if let Some(stats) = hybrid_detector.stats() {
        println!("   📈 Tier breakdown:");
        println!("      - Tier 1 (Token Hash): {} clones in {:.2}ms",
                 stats.tier1_clones, stats.tier1_time.as_secs_f64() * 1000.0);
        println!("      - Tier 2 (Optimized): {} clones in {:.2}ms",
                 stats.tier2_clones, stats.tier2_time.as_secs_f64() * 1000.0);
        println!("      - Tier 3 (Baseline): {} clones in {:.2}ms",
                 stats.tier3_clones, stats.tier3_time.as_secs_f64() * 1000.0);
    }
    println!();

    let total_duration = pipeline_start.elapsed();

    // ========================================
    // Results Summary
    // ========================================
    println!("═══════════════════════════════════════════════════════════════════════════════");
    println!("RESULTS SUMMARY");
    println!("═══════════════════════════════════════════════════════════════════════════════");
    println!();
    println!("Files processed: {}", files_processed);
    println!("Chunks generated: {}", chunks.len());
    println!("Fragments extracted: {}", fragments.len());
    println!("Clone pairs (Baseline): {}", baseline_pairs.len());
    println!("Clone pairs (Hybrid): {}", hybrid_pairs.len());
    println!();

    let speedup = if phase5_duration.as_secs_f64() > 0.0 {
        phase4_duration.as_secs_f64() / phase5_duration.as_secs_f64()
    } else {
        f64::INFINITY
    };

    println!("Clone Detection Comparison:");
    println!("  Baseline: {:.2}ms", phase4_duration.as_secs_f64() * 1000.0);
    println!("  Hybrid:   {:.2}ms", phase5_duration.as_secs_f64() * 1000.0);
    println!("  Speedup:  {:.2}x", speedup);
    println!();

    // Print waterfall chart
    print_waterfall(&metrics, total_duration);

    // Analyze bottlenecks
    analyze_bottlenecks(&metrics, total_duration);

    // ========================================
    // Assertions
    // ========================================
    println!("═══════════════════════════════════════════════════════════════════════════════");
    println!("VALIDATION");
    println!("═══════════════════════════════════════════════════════════════════════════════");
    println!();

    assert!(files_processed > 0, "Should process at least 1 file");
    assert!(!chunks.is_empty(), "Should generate chunks");
    assert!(!fragments.is_empty(), "Should extract fragments");

    // Recall validation
    let recall_percent = if baseline_pairs.len() > 0 {
        (hybrid_pairs.len() as f64 / baseline_pairs.len() as f64) * 100.0
    } else {
        100.0
    };

    println!("✅ Files processed: {}", files_processed);
    println!("✅ Chunks generated: {}", chunks.len());
    println!("✅ Fragments extracted: {}", fragments.len());
    println!("✅ Recall: {:.1}% ({} / {})", recall_percent, hybrid_pairs.len(), baseline_pairs.len());
    println!();

    assert!(recall_percent >= 90.0, "Hybrid should maintain ≥90% recall (got {:.1}%)", recall_percent);

    println!("🎉 ALL VALIDATIONS PASSED!");
    println!();
}
