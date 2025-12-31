//! Large Repository Benchmark - SOTA IndexingService API
//!
//! 최신 IndexingService 트리거별 API를 사용하여 대규모 리포지토리를 벤치마크합니다.
//! 실제 프로덕션 환경에서 사용되는 API와 동일한 방식으로 테스트합니다.
//!
//! # Features
//! - ✅ 최신 IndexingService API 사용 (trigger-specific methods)
//! - ✅ IRIndexingOrchestrator (L1-L37 DAG pipeline)
//! - ✅ IndexingResult 통일된 결과 형식
//! - ✅ Waterfall 리포트 생성 (stage-by-stage 타이밍)
//! - ✅ CSV 결과 저장
//!
//! # Usage
//! ```bash
//! # Basic benchmark (default stages)
//! cargo run --package codegraph-ir --example benchmark_large_repos --release -- /path/to/repo
//!
//! # Full benchmark (all stages enabled)
//! cargo run --package codegraph-ir --example benchmark_large_repos --release -- /path/to/repo --all-stages
//!
//! # Benchmark typer (small repo)
//! cargo run --package codegraph-ir --example benchmark_large_repos --release -- tools/benchmark/repo-test/small/typer
//!
//! # Benchmark rich (medium repo)
//! cargo run --package codegraph-ir --example benchmark_large_repos --release -- tools/benchmark/repo-test/medium/rich
//! ```

use codegraph_ir::usecases::IndexingService;
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// 스테이지 실행 결과
#[derive(Debug, Clone)]
struct StageResult {
    stage_name: String,
    duration: Duration,
    start_offset: Duration, // From benchmark start
    success: bool,
}

/// 벤치마크 결과
#[derive(Debug, Clone)]
struct BenchmarkResult {
    repo_name: String,
    repo_size_mb: f64,
    file_count: usize,

    // Benchmark configuration
    analysis_mode: String, // "BASIC" or "FULL"

    // IndexingResult fields
    files_processed: usize,
    files_cached: usize,
    files_failed: usize,
    total_loc: usize,
    loc_per_second: f64,
    cache_hit_rate: f64,

    // Aggregated from E2EPipelineResult
    total_nodes: usize,
    total_edges: usize,
    total_chunks: usize,
    total_symbols: usize,

    // Performance metrics
    indexing_duration: Duration,
    throughput_nodes_per_sec: f64,
    throughput_files_per_sec: f64,

    // Stage-level details
    stage_results: Vec<StageResult>,
    errors: Vec<String>,

    // Points-to Analysis info
    pta_mode: Option<String>, // e.g., "Fast (Steensgaard)"
    pta_variables: Option<usize>,
    pta_constraints: Option<usize>,
    pta_alias_pairs: Option<usize>,
}

impl BenchmarkResult {
    fn print_summary(&self) {
        println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("📊 Benchmark: {}", self.repo_name);
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("Configuration:");
        println!("  Analysis Mode: {}", self.analysis_mode);
        if self.analysis_mode == "BASIC" {
            println!("  Stages: L1-L5 (Fast indexing)");
        } else {
            println!("  Stages: L1-L37 (Full analysis with L6, L14, L16)");
        }
        println!();
        println!("Repository:");
        println!("  Size: {:.2} MB", self.repo_size_mb);
        println!(
            "  Files: {} (processed: {}, cached: {}, failed: {})",
            self.file_count, self.files_processed, self.files_cached, self.files_failed
        );
        println!();
        println!("Results:");
        println!("  Total LOC: {}", self.total_loc);
        println!("  Nodes: {}", self.total_nodes);
        println!("  Edges: {}", self.total_edges);
        println!("  Chunks: {}", self.total_chunks);
        println!("  Symbols: {}", self.total_symbols);
        println!();
        println!("Performance:");
        println!("  Duration: {:.2}s", self.indexing_duration.as_secs_f64());
        println!("  Throughput: {:.0} LOC/sec", self.loc_per_second);
        println!(
            "  Throughput: {:.0} nodes/sec",
            self.throughput_nodes_per_sec
        );
        println!(
            "  Throughput: {:.0} files/sec",
            self.throughput_files_per_sec
        );
        println!("  Cache hit rate: {:.1}%", self.cache_hit_rate * 100.0);
        println!();
        println!("Pipeline:");
        println!("  Stages completed: {}", self.stage_results.len());
        println!("  Errors: {}", self.errors.len());
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    }

    /// 워터폴 리포트를 텍스트 파일로 생성
    fn generate_waterfall_report(&self, output_path: &PathBuf) -> std::io::Result<()> {
        let mut file = fs::File::create(output_path)?;

        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();

        writeln!(
            file,
            "═══════════════════════════════════════════════════════════════════════════════"
        )?;
        writeln!(
            file,
            "  IndexingService Benchmark - Detailed Waterfall Report"
        )?;
        writeln!(
            file,
            "═══════════════════════════════════════════════════════════════════════════════"
        )?;
        writeln!(file)?;
        writeln!(file, "Repository: {}", self.repo_name)?;
        writeln!(file, "Generated: {}", timestamp)?;
        writeln!(file)?;

        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(file, "BENCHMARK CONFIGURATION")?;
        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(file, "  Analysis Mode:      {}", self.analysis_mode)?;
        if self.analysis_mode == "BASIC" {
            writeln!(
                file,
                "  Stages Enabled:     L1-L5 (IR Build, Chunking, CrossFile, Occurrences, Symbols)"
            )?;
            writeln!(
                file,
                "  Use Case:           Fast indexing, real-time updates"
            )?;
        } else {
            writeln!(file, "  Stages Enabled:     L1-L37 (All stages including L6 PTA, L14 Taint, L16 RepoMap)")?;
            writeln!(
                file,
                "  Use Case:           Comprehensive analysis, scheduled nightly runs"
            )?;
        }
        writeln!(file)?;

        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(file, "REPOSITORY INFO")?;
        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(file, "  Size:               {:.2} MB", self.repo_size_mb)?;
        writeln!(file, "  Files:              {}", self.file_count)?;
        writeln!(file, "  Files Processed:    {}", self.files_processed)?;
        writeln!(file, "  Files Cached:       {}", self.files_cached)?;
        writeln!(file, "  Files Failed:       {}", self.files_failed)?;
        writeln!(file)?;

        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(file, "INDEXING RESULTS")?;
        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(file, "  Total LOC:          {}", self.total_loc)?;
        writeln!(file, "  Total Nodes:        {}", self.total_nodes)?;
        writeln!(file, "  Total Edges:        {}", self.total_edges)?;
        writeln!(file, "  Total Chunks:       {}", self.total_chunks)?;
        writeln!(file, "  Total Symbols:      {}", self.total_symbols)?;
        writeln!(file)?;

        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(file, "PERFORMANCE SUMMARY")?;
        writeln!(
            file,
            "───────────────────────────────────────────────────────────────────────────────"
        )?;
        writeln!(
            file,
            "  Total Duration:     {:.4}s",
            self.indexing_duration.as_secs_f64()
        )?;
        writeln!(file, "  LOC/sec:            {:.0}", self.loc_per_second)?;
        writeln!(
            file,
            "  Nodes/sec:          {:.0}",
            self.throughput_nodes_per_sec
        )?;
        writeln!(
            file,
            "  Files/sec:          {:.0}",
            self.throughput_files_per_sec
        )?;
        writeln!(
            file,
            "  Cache Hit Rate:     {:.1}%",
            self.cache_hit_rate * 100.0
        )?;
        writeln!(file, "  Stages Completed:   {}", self.stage_results.len())?;
        writeln!(file, "  Errors:             {}", self.errors.len())?;
        writeln!(file)?;

        // Add Points-to Analysis details if available
        if let Some(ref pta_mode) = self.pta_mode {
            writeln!(
                file,
                "───────────────────────────────────────────────────────────────────────────────"
            )?;
            writeln!(file, "POINTS-TO ANALYSIS (L6)")?;
            writeln!(
                file,
                "───────────────────────────────────────────────────────────────────────────────"
            )?;
            writeln!(file, "  Algorithm:          {}", pta_mode)?;
            if let Some(vars) = self.pta_variables {
                writeln!(file, "  Variables:          {}", vars)?;
            }
            if let Some(constraints) = self.pta_constraints {
                writeln!(file, "  Constraints:        {}", constraints)?;
            }
            if let Some(aliases) = self.pta_alias_pairs {
                writeln!(file, "  Alias Pairs:        {}", aliases)?;
            }
            writeln!(file)?;
        }

        writeln!(
            file,
            "═══════════════════════════════════════════════════════════════════════════════"
        )?;
        writeln!(file, "STAGE-BY-STAGE WATERFALL")?;
        writeln!(
            file,
            "═══════════════════════════════════════════════════════════════════════════════"
        )?;
        writeln!(file)?;

        // 타임라인 헤더
        writeln!(file, "Timeline (ms):")?;
        writeln!(
            file,
            "  0ms{:─>70}{}ms",
            "",
            self.indexing_duration.as_millis()
        )?;
        writeln!(file)?;

        // 각 스테이지 상세
        for (idx, stage) in self.stage_results.iter().enumerate() {
            let stage_num = idx + 1;
            let start_ms = stage.start_offset.as_millis();
            let duration_ms = stage.duration.as_millis();
            let end_ms = start_ms + duration_ms;
            let duration_pct =
                (stage.duration.as_secs_f64() / self.indexing_duration.as_secs_f64()) * 100.0;

            writeln!(
                file,
                "┌─────────────────────────────────────────────────────────────────────────────┐"
            )?;
            writeln!(file, "│ Stage {}: {:<67} │", stage_num, stage.stage_name)?;
            writeln!(
                file,
                "├─────────────────────────────────────────────────────────────────────────────┤"
            )?;

            // 시각적 타임라인 바
            let bar_width = 70;
            let total_duration = self.indexing_duration.as_millis() as f64;
            let start_pos = ((start_ms as f64 / total_duration) * bar_width as f64) as usize;
            let bar_len = std::cmp::max(
                1,
                ((duration_ms as f64 / total_duration) * bar_width as f64) as usize,
            );

            write!(file, "│ ")?;
            for i in 0..bar_width {
                if i >= start_pos && i < start_pos + bar_len {
                    write!(file, "█")?;
                } else if i == start_pos + bar_len && duration_ms > 0 {
                    write!(file, "▌")?;
                } else {
                    write!(file, " ")?;
                }
            }
            writeln!(file, " │")?;

            writeln!(
                file,
                "│                                                                             │"
            )?;
            writeln!(file, "│  Start:          {}ms from beginning", start_ms)?;
            writeln!(
                file,
                "│  Duration:       {}ms ({:.1}% of total)",
                duration_ms, duration_pct
            )?;
            writeln!(file, "│  End:            {}ms", end_ms)?;
            writeln!(
                file,
                "│  Status:         {}",
                if stage.success {
                    "✅ SUCCESS"
                } else {
                    "❌ FAILED"
                }
            )?;

            writeln!(
                file,
                "└─────────────────────────────────────────────────────────────────────────────┘"
            )?;
            writeln!(file)?;
        }

        // Print errors if any
        if !self.errors.is_empty() {
            writeln!(
                file,
                "═══════════════════════════════════════════════════════════════════════════════"
            )?;
            writeln!(file, "ERRORS ({} total)", self.errors.len())?;
            writeln!(
                file,
                "═══════════════════════════════════════════════════════════════════════════════"
            )?;
            for (idx, error) in self.errors.iter().enumerate() {
                writeln!(file, "{}. {}", idx + 1, error)?;
            }
            writeln!(file)?;
        }

        writeln!(
            file,
            "═══════════════════════════════════════════════════════════════════════════════"
        )?;
        writeln!(file, "END OF REPORT")?;
        writeln!(
            file,
            "═══════════════════════════════════════════════════════════════════════════════"
        )?;

        Ok(())
    }
}

/// 디렉토리 크기 계산 (MB)
fn calculate_dir_size(path: &PathBuf) -> f64 {
    fn walk_dir(path: &PathBuf, total: &mut u64) {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                if let Ok(metadata) = entry.metadata() {
                    if metadata.is_file() {
                        *total += metadata.len();
                    } else if metadata.is_dir() {
                        let name = entry.file_name();
                        let name_str = name.to_string_lossy();
                        // Skip common ignore patterns
                        if !name_str.starts_with('.')
                            && name_str != "node_modules"
                            && name_str != "__pycache__"
                            && name_str != "target"
                            && name_str != "venv"
                        {
                            walk_dir(&entry.path(), total);
                        }
                    }
                }
            }
        }
    }

    let mut total_size = 0u64;
    walk_dir(path, &mut total_size);
    total_size as f64 / 1_048_576.0 // Convert to MB
}

/// 파일 개수 계산
fn count_files(path: &PathBuf) -> usize {
    fn walk_dir(path: &PathBuf, count: &mut usize) {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                if let Ok(metadata) = entry.metadata() {
                    if metadata.is_file() {
                        // Only count supported file types
                        if let Some(ext) = entry.path().extension() {
                            let ext_str = ext.to_string_lossy();
                            if ext_str == "py"
                                || ext_str == "rs"
                                || ext_str == "js"
                                || ext_str == "ts"
                                || ext_str == "go"
                                || ext_str == "java"
                                || ext_str == "kt"
                            {
                                *count += 1;
                            }
                        }
                    } else if metadata.is_dir() {
                        let name = entry.file_name();
                        let name_str = name.to_string_lossy();
                        if !name_str.starts_with('.')
                            && name_str != "node_modules"
                            && name_str != "__pycache__"
                            && name_str != "target"
                            && name_str != "venv"
                        {
                            walk_dir(&entry.path(), count);
                        }
                    }
                }
            }
        }
    }

    let mut count = 0;
    walk_dir(path, &mut count);
    count
}

/// 단일 리포지토리 벤치마크
fn benchmark_repository(
    repo_path: PathBuf,
    repo_name: String,
    enable_all_stages: bool,
) -> Result<BenchmarkResult, Box<dyn std::error::Error>> {
    println!("\n🚀 Starting benchmark: {}", repo_name);
    println!("   Path: {:?}", repo_path);

    if !repo_path.exists() {
        return Err(format!("Repository not found: {:?}", repo_path).into());
    }

    // Repository info
    println!("   Calculating repo size...");
    let repo_size_mb = calculate_dir_size(&repo_path);
    let file_count = count_files(&repo_path);
    println!("   ✓ Size: {:.2} MB, Files: {}", repo_size_mb, file_count);

    // Create IndexingService
    let service = IndexingService::new();

    // Run indexing based on configuration
    println!(
        "   🔥 Indexing with {} stages...",
        if enable_all_stages { "ALL" } else { "DEFAULT" }
    );
    let bench_start = Instant::now();

    let indexing_result = if enable_all_stages {
        // Use scheduled_index with full analysis enabled
        service.scheduled_index(
            repo_path.clone(),
            repo_name.clone(),
            true, // with_full_analysis = true (L1-L37 with L6, L14, L16)
        )?
    } else {
        // Use manual_trigger_full for basic indexing
        service.manual_trigger_full(
            repo_path.clone(),
            repo_name.clone(),
            false, // force = false (L1-L5 basic stages)
        )?
    };

    let indexing_duration = bench_start.elapsed();

    // Extract results from IndexingResult
    let files_processed = indexing_result.files_processed;
    let files_cached = indexing_result.files_cached;
    let files_failed = indexing_result.files_failed;
    let total_loc = indexing_result.total_loc;
    let loc_per_second = indexing_result.loc_per_second;
    let cache_hit_rate = indexing_result.cache_hit_rate;

    // Extract from full_result (E2EPipelineResult)
    let total_nodes = indexing_result.full_result.nodes.len();
    let total_edges = indexing_result.full_result.edges.len();
    let total_chunks = indexing_result.full_result.chunks.len();
    let total_symbols = indexing_result.full_result.symbols.len();
    let errors = indexing_result.errors.clone();

    let throughput_nodes_per_sec = if indexing_duration.as_secs_f64() > 0.0 {
        total_nodes as f64 / indexing_duration.as_secs_f64()
    } else {
        0.0
    };

    let throughput_files_per_sec = if indexing_duration.as_secs_f64() > 0.0 {
        files_processed as f64 / indexing_duration.as_secs_f64()
    } else {
        0.0
    };

    println!("   ✓ Completed in {:.2}s", indexing_duration.as_secs_f64());

    // Extract Points-to Analysis info
    let (pta_mode, pta_variables, pta_constraints, pta_alias_pairs) =
        if let Some(ref pta) = indexing_result.full_result.points_to_summary {
            (
                Some(pta.mode_used.clone()),
                Some(pta.variables_count),
                Some(pta.constraints_count),
                Some(pta.alias_pairs),
            )
        } else {
            (None, None, None, None)
        };

    // Convert stage_durations to StageResult
    // Sort stages by their logical execution order (L1 → L2 → L3 → ...)
    let stage_order = vec![
        "L1_IR_Build",
        "L2_Chunking",
        "L3_CrossFile",
        "L4_Occurrences",
        "L5_Symbols",
        "L6_PointsTo",
        "L14_TaintAnalysis",
        "L16_RepoMap",
    ];

    let mut stage_results = Vec::new();
    let mut cumulative_offset = Duration::ZERO;

    // Iterate in correct stage order
    for stage_name in &stage_order {
        if let Some(duration) = indexing_result.stage_durations.get(*stage_name) {
            stage_results.push(StageResult {
                stage_name: stage_name.to_string(),
                duration: *duration,
                start_offset: cumulative_offset,
                success: true,
            });
            cumulative_offset += *duration;
        }
    }

    // Add any remaining stages not in the predefined order
    for (stage_name, duration) in &indexing_result.stage_durations {
        if !stage_order.contains(&stage_name.as_str()) {
            stage_results.push(StageResult {
                stage_name: stage_name.clone(),
                duration: *duration,
                start_offset: cumulative_offset,
                success: true,
            });
            cumulative_offset += *duration;
        }
    }

    Ok(BenchmarkResult {
        repo_name,
        repo_size_mb,
        file_count,
        analysis_mode: if enable_all_stages {
            "FULL".to_string()
        } else {
            "BASIC".to_string()
        },
        files_processed,
        files_cached,
        files_failed,
        total_loc,
        loc_per_second,
        cache_hit_rate,
        total_nodes,
        total_edges,
        total_chunks,
        total_symbols,
        indexing_duration,
        throughput_nodes_per_sec,
        throughput_files_per_sec,
        stage_results,
        errors,
        pta_mode,
        pta_variables,
        pta_constraints,
        pta_alias_pairs,
    })
}

/// CSV 저장
/// Save results to specific path
fn save_results_csv_to_path(results: &[BenchmarkResult], path: &PathBuf) {
    let mut csv_content = String::from(
        "repo_name,analysis_mode,size_mb,file_count,files_processed,files_cached,files_failed,total_loc,loc_per_sec,nodes,edges,chunks,symbols,duration_sec,throughput_nodes_sec,throughput_files_sec,cache_hit_rate,stages_completed,errors\n"
    );

    for r in results {
        csv_content.push_str(&format!(
            "{},{},{:.2},{},{},{},{},{},{:.0},{},{},{},{},{:.4},{:.2},{:.2},{:.4},{},{}\n",
            r.repo_name,
            r.analysis_mode,
            r.repo_size_mb,
            r.file_count,
            r.files_processed,
            r.files_cached,
            r.files_failed,
            r.total_loc,
            r.loc_per_second,
            r.total_nodes,
            r.total_edges,
            r.total_chunks,
            r.total_symbols,
            r.indexing_duration.as_secs_f64(),
            r.throughput_nodes_per_sec,
            r.throughput_files_per_sec,
            r.cache_hit_rate,
            r.stage_results.len(),
            r.errors.len()
        ));
    }

    if let Err(e) = fs::write(path, csv_content) {
        eprintln!("⚠️  Failed to save CSV: {}", e);
    } else {
        println!("📄 CSV summary saved to: {:?}", path);
    }
}

/// Save results to legacy location (target/benchmark_results.csv)
fn save_results_csv(results: &[BenchmarkResult]) {
    let csv_path = PathBuf::from("target/benchmark_results.csv");
    save_results_csv_to_path(results, &csv_path);
}

fn print_usage() {
    println!("\nIndexingService Benchmark (Latest API)");
    println!("\nUsage:");
    println!("  cargo run --example benchmark_large_repos --release -- <repo_path> [--all-stages]");
    println!();
    println!("Arguments:");
    println!("  <repo_path>     Path to repository to benchmark");
    println!("  --all-stages    Enable full analysis (L1-L37 with L6 PTA, L14 Taint, L16 RepoMap)");
    println!();
    println!("Examples:");
    println!("  # Basic benchmark (default stages: L1-L5)");
    println!("  cargo run --example benchmark_large_repos --release -- /path/to/repo");
    println!();
    println!("  # Full benchmark (L1-L37 with full analysis)");
    println!("  cargo run --example benchmark_large_repos --release -- /path/to/repo --all-stages");
    println!();
    println!("  # Benchmark typer (small repo)");
    println!("  cargo run --example benchmark_large_repos --release -- tools/benchmark/repo-test/small/typer");
    println!();
    println!("  # Benchmark rich (medium repo)");
    println!("  cargo run --example benchmark_large_repos --release -- tools/benchmark/repo-test/medium/rich");
    println!();
}

fn main() {
    // Suppress debug logs for cleaner benchmark output
    std::env::set_var("RUST_LOG", "warn");

    // Parse CLI arguments
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 2 {
        print_usage();
        std::process::exit(1);
    }

    let repo_path = PathBuf::from(&args[1]);

    if !repo_path.exists() {
        eprintln!("❌ Error: Repository not found: {:?}", repo_path);
        eprintln!();
        print_usage();
        std::process::exit(1);
    }

    // Extract repo name from path
    let repo_name = repo_path
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .to_string();

    // Check for --all-stages flag
    let enable_all_stages = args.len() > 2 && args[2] == "--all-stages";

    // Single repository benchmark
    println!("\n╔══════════════════════════════════════════════════════════╗");
    println!("║  IndexingService Benchmark - Latest Trigger API         ║");
    println!("╚══════════════════════════════════════════════════════════╝");
    println!();
    println!("Repository: {:?}", repo_path);
    println!("Name: {}", repo_name);
    println!(
        "Mode: {}",
        if enable_all_stages {
            "FULL ANALYSIS (L1-L37 with L6, L14, L16)"
        } else {
            "BASIC INDEXING (L1-L5)"
        }
    );
    println!();

    match benchmark_repository(repo_path, repo_name.clone(), enable_all_stages) {
        Ok(result) => {
            result.print_summary();

            // Create benchmark results directory: target/benchmark_results/{repo_name}/
            let timestamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs();
            let results_dir = PathBuf::from(format!("target/benchmark_results/{}", repo_name));
            if let Err(e) = std::fs::create_dir_all(&results_dir) {
                eprintln!("⚠️  Failed to create results directory: {}", e);
            }

            // Save waterfall report: target/benchmark_results/{repo_name}/waterfall_{timestamp}.txt
            let waterfall_path = results_dir.join(format!("waterfall_{}.txt", timestamp));
            match result.generate_waterfall_report(&waterfall_path) {
                Ok(_) => {
                    println!("📊 Waterfall report saved to: {:?}", waterfall_path);
                }
                Err(e) => {
                    eprintln!("⚠️  Failed to save waterfall report: {}", e);
                }
            }

            // Save CSV summary: target/benchmark_results/{repo_name}/summary_{timestamp}.csv
            let csv_path = results_dir.join(format!("summary_{}.csv", timestamp));
            save_results_csv_to_path(&[result.clone()], &csv_path);

            // Legacy: Also save to old location for compatibility
            save_results_csv(&[result.clone()]);

            println!("\n✅ Benchmark complete!");

            // Print key metrics
            println!("\n🎯 Key Metrics:");
            println!("   LOC/sec: {:.0}", result.loc_per_second);
            println!("   Nodes/sec: {:.0}", result.throughput_nodes_per_sec);
            println!("   Target: 78,000 LOC/sec");
            println!("   Speedup: {:.1}x", result.loc_per_second / 78000.0);
        }
        Err(e) => {
            eprintln!("\n❌ Benchmark failed: {}", e);
            std::process::exit(1);
        }
    }
}
