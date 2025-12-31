//! UnifiedOrchestrator Benchmark Suite
//!
//! 실제 대규모 리포지토리로 인덱싱 성능 측정
//!
//! Usage:
//!   cargo bench --package codegraph-ir --bench unified_orchestrator_bench

use codegraph_ir::config::{PipelineConfig, Preset, StageControl, ValidatedConfig};
use codegraph_ir::pipeline::{E2EPipelineConfig, UnifiedOrchestrator, UnifiedOrchestratorConfig};
use std::fs;
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// 벤치마크 결과
#[derive(Debug, Clone)]
pub struct BenchmarkResult {
    pub repo_name: String,
    pub repo_size_mb: f64,
    pub file_count: usize,
    pub total_nodes: usize,
    pub total_edges: usize,
    pub total_chunks: usize,
    pub indexing_duration: Duration,
    pub throughput_nodes_per_sec: f64,
    pub throughput_mb_per_sec: f64,
    pub stages_completed: usize,
    pub stages_failed: usize,
}

impl BenchmarkResult {
    pub fn print_summary(&self) {
        println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("📊 Benchmark Results: {}", self.repo_name);
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("Repository Info:");
        println!("  - Size: {:.2} MB", self.repo_size_mb);
        println!("  - Files: {}", self.file_count);
        println!();
        println!("Indexing Results:");
        println!("  - Nodes: {}", self.total_nodes);
        println!("  - Edges: {}", self.total_edges);
        println!("  - Chunks: {}", self.total_chunks);
        println!();
        println!("Performance:");
        println!("  - Duration: {:.2}s", self.indexing_duration.as_secs_f64());
        println!(
            "  - Throughput: {:.0} nodes/sec",
            self.throughput_nodes_per_sec
        );
        println!("  - Throughput: {:.2} MB/sec", self.throughput_mb_per_sec);
        println!();
        println!("Pipeline:");
        println!("  - Stages completed: {}", self.stages_completed);
        println!("  - Stages failed: {}", self.stages_failed);
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
    }

    pub fn to_csv_row(&self) -> String {
        format!(
            "{},{:.2},{},{},{},{},{:.4},{:.2},{:.2},{},{}",
            self.repo_name,
            self.repo_size_mb,
            self.file_count,
            self.total_nodes,
            self.total_edges,
            self.total_chunks,
            self.indexing_duration.as_secs_f64(),
            self.throughput_nodes_per_sec,
            self.throughput_mb_per_sec,
            self.stages_completed,
            self.stages_failed
        )
    }
}

/// 벤치마크 러너
pub struct BenchmarkRunner {
    /// 벤치마크 결과 저장 디렉토리
    output_dir: PathBuf,
}

impl BenchmarkRunner {
    pub fn new(output_dir: PathBuf) -> Self {
        fs::create_dir_all(&output_dir).expect("Failed to create output dir");
        Self { output_dir }
    }

    /// 디렉토리 크기 계산 (MB)
    fn calculate_dir_size(&self, path: &PathBuf) -> f64 {
        let mut total_size = 0u64;

        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                if let Ok(metadata) = entry.metadata() {
                    if metadata.is_file() {
                        total_size += metadata.len();
                    } else if metadata.is_dir() {
                        let subpath = entry.path();
                        total_size += (self.calculate_dir_size(&subpath) * 1_048_576.0) as u64;
                    }
                }
            }
        }

        total_size as f64 / 1_048_576.0 // Convert to MB
    }

    /// 파일 개수 계산
    fn count_files(&self, path: &PathBuf) -> usize {
        let mut count = 0;

        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                if let Ok(metadata) = entry.metadata() {
                    if metadata.is_file() {
                        count += 1;
                    } else if metadata.is_dir() {
                        count += self.count_files(&entry.path());
                    }
                }
            }
        }

        count
    }

    /// 단일 리포지토리 벤치마크 실행
    ///
    /// # Arguments
    /// * `repo_path` - 리포지토리 경로
    /// * `repo_name` - 리포지토리 이름
    /// * `preset` - RFC-001 Preset (Fast/Balanced/Thorough)
    /// * `custom_config` - Optional: 커스텀 ValidatedConfig (설정 변경 시 사용)
    pub fn benchmark_repository(
        &self,
        repo_path: PathBuf,
        repo_name: String,
        preset: Preset,
        custom_config: Option<ValidatedConfig>,
    ) -> Result<BenchmarkResult, String> {
        println!("\n🚀 Benchmarking: {}", repo_name);
        println!("   Path: {:?}", repo_path);
        println!("   Preset: {:?}", preset);

        // Repository info
        let repo_size_mb = self.calculate_dir_size(&repo_path);
        let file_count = self.count_files(&repo_path);
        println!("   Size: {:.2} MB, Files: {}", repo_size_mb, file_count);

        // Create config using RFC-001 preset or custom config
        let config = if let Some(validated) = custom_config {
            // Use custom config (for benchmarking with different settings)
            let e2e_config = E2EPipelineConfig::with_config(validated)
                .repo_root(repo_path.clone())
                .repo_name(repo_name.clone());
            UnifiedOrchestratorConfig::new(repo_path.clone(), repo_name.clone())
                .with_pipeline_config(e2e_config)
        } else {
            // Use preset
            UnifiedOrchestratorConfig::with_preset(repo_path.clone(), repo_name.clone(), preset)
        };

        // Create orchestrator
        let orchestrator = UnifiedOrchestrator::new(config)
            .map_err(|e| format!("Failed to create orchestrator: {}", e))?;

        // Benchmark indexing
        println!("   Indexing...");
        let start = Instant::now();

        orchestrator
            .index_repository()
            .map_err(|e| format!("Indexing failed: {}", e))?;

        let indexing_duration = start.elapsed();

        // Get results
        let ctx = orchestrator.get_context();
        let stats = orchestrator.get_stats();

        let total_nodes = ctx.nodes.len();
        let total_edges = ctx.edges.len();
        let total_chunks = ctx.chunks.len();

        let throughput_nodes_per_sec = if indexing_duration.as_secs_f64() > 0.0 {
            total_nodes as f64 / indexing_duration.as_secs_f64()
        } else {
            0.0
        };

        let throughput_mb_per_sec = if indexing_duration.as_secs_f64() > 0.0 {
            repo_size_mb / indexing_duration.as_secs_f64()
        } else {
            0.0
        };

        Ok(BenchmarkResult {
            repo_name,
            repo_size_mb,
            file_count,
            total_nodes,
            total_edges,
            total_chunks,
            indexing_duration,
            throughput_nodes_per_sec,
            throughput_mb_per_sec,
            stages_completed: stats.stages_completed,
            stages_failed: stats.stages_failed,
        })
    }

    /// 여러 리포지토리 벤치마크 실행 (default: Balanced preset)
    pub fn benchmark_suite(&self, repos: Vec<(PathBuf, String)>) -> Vec<BenchmarkResult> {
        self.benchmark_suite_with_preset(repos, Preset::Balanced)
    }

    /// 여러 리포지토리 벤치마크 실행 (지정된 preset 사용)
    pub fn benchmark_suite_with_preset(
        &self,
        repos: Vec<(PathBuf, String)>,
        preset: Preset,
    ) -> Vec<BenchmarkResult> {
        let mut results = Vec::new();

        println!("\n╔══════════════════════════════════════════════════════════╗");
        println!("║  UnifiedOrchestrator Benchmark Suite                    ║");
        println!("║  Preset: {:?}                                         ║", preset);
        println!("╚══════════════════════════════════════════════════════════╝");

        for (repo_path, repo_name) in repos {
            match self.benchmark_repository(repo_path, repo_name, preset, None) {
                Ok(result) => {
                    result.print_summary();
                    results.push(result);
                }
                Err(e) => {
                    eprintln!("❌ Benchmark failed: {}", e);
                }
            }
        }

        // Save results to CSV
        self.save_results_csv(&results);

        // Print comparison
        self.print_comparison(&results);

        results
    }

    /// 설정값을 변경하면서 벤치마크 (A/B 테스트용)
    ///
    /// # Example
    /// ```rust,ignore
    /// let configs = vec![
    ///     ("fast", PipelineConfig::preset(Preset::Fast).build().unwrap()),
    ///     ("balanced", PipelineConfig::preset(Preset::Balanced).build().unwrap()),
    ///     ("thorough", PipelineConfig::preset(Preset::Thorough).build().unwrap()),
    /// ];
    /// runner.benchmark_config_comparison(repo_path, configs);
    /// ```
    pub fn benchmark_config_comparison(
        &self,
        repo_path: PathBuf,
        configs: Vec<(&str, ValidatedConfig)>,
    ) -> Vec<BenchmarkResult> {
        let mut results = Vec::new();

        println!("\n╔══════════════════════════════════════════════════════════╗");
        println!("║  Config Comparison Benchmark                             ║");
        println!("╚══════════════════════════════════════════════════════════╝");

        for (config_name, config) in configs {
            let repo_name = format!("{}_{}", repo_path.file_name().unwrap().to_str().unwrap(), config_name);
            match self.benchmark_repository(repo_path.clone(), repo_name, Preset::Custom, Some(config)) {
                Ok(result) => {
                    result.print_summary();
                    results.push(result);
                }
                Err(e) => {
                    eprintln!("❌ Benchmark failed: {}", e);
                }
            }
        }

        self.print_comparison(&results);
        results
    }

    /// 결과를 CSV로 저장
    fn save_results_csv(&self, results: &[BenchmarkResult]) {
        let csv_path = self.output_dir.join("benchmark_results.csv");

        let mut csv_content = String::from(
            "repo_name,size_mb,file_count,nodes,edges,chunks,duration_sec,throughput_nodes_sec,throughput_mb_sec,stages_completed,stages_failed\n"
        );

        for result in results {
            csv_content.push_str(&result.to_csv_row());
            csv_content.push('\n');
        }

        fs::write(&csv_path, csv_content).expect("Failed to write CSV");

        println!("📄 Results saved to: {:?}", csv_path);
    }

    /// 결과 비교 출력
    fn print_comparison(&self, results: &[BenchmarkResult]) {
        if results.is_empty() {
            return;
        }

        println!("\n╔══════════════════════════════════════════════════════════╗");
        println!("║  Benchmark Comparison                                    ║");
        println!("╚══════════════════════════════════════════════════════════╝\n");

        // Find fastest
        let fastest = results
            .iter()
            .max_by(|a, b| {
                a.throughput_nodes_per_sec
                    .partial_cmp(&b.throughput_nodes_per_sec)
                    .unwrap()
            })
            .unwrap();

        // Find largest
        let largest = results
            .iter()
            .max_by(|a, b| a.total_nodes.partial_cmp(&b.total_nodes).unwrap())
            .unwrap();

        println!(
            "🏆 Fastest: {} ({:.0} nodes/sec)",
            fastest.repo_name, fastest.throughput_nodes_per_sec
        );
        println!(
            "📦 Largest: {} ({} nodes)",
            largest.repo_name, largest.total_nodes
        );

        // Average throughput
        let avg_throughput = results
            .iter()
            .map(|r| r.throughput_nodes_per_sec)
            .sum::<f64>()
            / results.len() as f64;

        println!("📊 Average throughput: {:.0} nodes/sec\n", avg_throughput);
    }
}

// ============================================================================
// Benchmark Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// Test with small fixture
    #[test]
    fn bench_small_fixture() {
        let fixture_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join("python_simple");

        if !fixture_path.exists() {
            eprintln!("⚠️  Fixture not found, skipping benchmark");
            return;
        }

        let output_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join("benchmark_results");

        let runner = BenchmarkRunner::new(output_dir);

        let result = runner
            .benchmark_repository(fixture_path, "python_simple".to_string(), Preset::Fast, None)
            .expect("Benchmark failed");

        result.print_summary();

        assert!(result.total_nodes > 0, "Should have nodes");
        assert!(
            result.throughput_nodes_per_sec > 0.0,
            "Should have throughput"
        );
    }

    /// Benchmark suite with multiple repos
    #[test]
    #[ignore] // Run with: cargo test --package codegraph-ir --bench unified_orchestrator_bench -- --ignored
    fn bench_suite() {
        let benchmark_repos_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .join("tools")
            .join("benchmark")
            .join("repo-test");

        if !benchmark_repos_dir.exists() {
            eprintln!("⚠️  Benchmark repos not found at {:?}", benchmark_repos_dir);
            eprintln!("   Run: git clone <repos> into tools/benchmark/repo-test/");
            return;
        }

        let output_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join("benchmark_results");

        let runner = BenchmarkRunner::new(output_dir);

        // Define repos to benchmark
        let repos = vec![
            (benchmark_repos_dir.join("small/typer"), "typer".to_string()),
            (benchmark_repos_dir.join("medium/rich"), "rich".to_string()),
            (
                benchmark_repos_dir.join("large/django"),
                "django".to_string(),
            ),
        ];

        let results = runner.benchmark_suite(repos);

        // Verify all succeeded
        for result in results {
            assert!(result.stages_failed == 0, "No stages should fail");
            assert!(result.total_nodes > 0, "Should have nodes");
        }
    }
}

// ============================================================================
// Main (for standalone execution)
// ============================================================================

fn main() {
    println!("UnifiedOrchestrator Benchmark Suite");
    println!("Run with: cargo bench --package codegraph-ir --bench unified_orchestrator_bench");
    println!();
    println!("Or run tests: cargo test --package codegraph-ir --bench unified_orchestrator_bench");
}
