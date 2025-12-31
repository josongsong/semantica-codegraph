//! Benchmark orchestration
//!
//! Coordinates the entire benchmark workflow: warmup, measurement, validation, reporting.
//! Integrates with IndexingService for actual analysis execution.

use crate::benchmark::ground_truth::{GroundTruth, GroundTruthStore};
use crate::benchmark::validator::{GroundTruthValidator, ValidationResult};
use crate::benchmark::{
    BenchmarkConfig, BenchmarkError, BenchmarkResult, BenchmarkResult2, PTASummary, RepoMapSummary,
    Repository, TaintSummary,
};
use crate::usecases::indexing_service::{IndexingRequest, IndexingService};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// Complete benchmark report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BenchmarkReport {
    pub repo: Repository,
    pub config_name: String,
    pub results: Vec<BenchmarkResult>,
    pub avg_result: BenchmarkResult,
    pub validation: Option<ValidationResult>,
    pub timestamp: u64,
}

/// Benchmark orchestrator
pub struct BenchmarkRunner {
    pub config: BenchmarkConfig,
    pub repo: Repository,
    pub ground_truth_store: GroundTruthStore,
    pub validator: GroundTruthValidator,
}

impl BenchmarkRunner {
    pub fn new(config: BenchmarkConfig, repo: Repository) -> Self {
        let validator = GroundTruthValidator::new(config.benchmark_opts.tolerance.clone());

        Self {
            config,
            repo,
            ground_truth_store: GroundTruthStore::default(),
            validator,
        }
    }

    /// Run complete benchmark workflow
    pub fn run(&self) -> BenchmarkResult2<BenchmarkReport> {
        println!("╔══════════════════════════════════════════════════════════╗");
        println!("║  Codegraph Benchmark (Rust-Only, Ground Truth)          ║");
        println!("╚══════════════════════════════════════════════════════════╝");
        println!();
        println!("Repository: {}", self.repo.name);
        println!(
            "Category:   {:?} ({} LOC)",
            self.repo.category, self.repo.total_loc
        );
        println!("Config:     {}", self.config.config_name());
        println!();

        // Step 1: Warmup runs
        println!(
            "Step 1: Warmup ({} runs)...",
            self.config.benchmark_opts.warmup_runs
        );
        for i in 0..self.config.benchmark_opts.warmup_runs {
            println!(
                "  Warmup run {}/{}...",
                i + 1,
                self.config.benchmark_opts.warmup_runs
            );
            self.run_single_benchmark()?;
        }
        println!();

        // Step 2: Measured runs
        println!(
            "Step 2: Measured runs ({})...",
            self.config.benchmark_opts.measured_runs
        );
        let mut results = Vec::new();
        for i in 0..self.config.benchmark_opts.measured_runs {
            println!(
                "  Run {}/{}...",
                i + 1,
                self.config.benchmark_opts.measured_runs
            );
            let result = self.run_single_benchmark()?;
            results.push(result);
        }
        println!();

        // Step 3: Aggregate results
        let avg_result = Self::aggregate_results(&results);

        // Step 4: Ground Truth validation
        let validation = if self.config.benchmark_opts.validate_ground_truth {
            println!("Step 3: Ground Truth Validation...");
            let gt = self
                .ground_truth_store
                .find(&self.repo.id, &self.config.config_name());

            if let Some(gt) = gt {
                let validation = self.validator.validate(&avg_result, &gt);
                println!("{}", validation.summary);
                println!();
                Some(validation)
            } else {
                println!(
                    "  ⚠️  No ground truth found for {}_{}",
                    self.repo.id,
                    self.config.config_name()
                );
                println!("  Run with --save-ground-truth to establish baseline");
                println!();
                None
            }
        } else {
            None
        };

        // Step 5: Generate report
        let report = BenchmarkReport {
            repo: self.repo.clone(),
            config_name: self.config.config_name(),
            results,
            avg_result,
            validation,
            timestamp: Self::now(),
        };

        Ok(report)
    }

    /// Run single benchmark with IndexingService integration
    ///
    /// Uses PipelineConfig from BenchmarkConfig to control which stages run.
    /// This allows benchmarking with different configurations.
    fn run_single_benchmark(&self) -> BenchmarkResult2<BenchmarkResult> {
        let start = Instant::now();

        // Create IndexingService and execute analysis
        let service = IndexingService::new();

        // Get stage controls from RFC-001 pipeline config
        let stages = &self.config.pipeline_config.as_inner().stages;

        // Get taint config from RFC-001 pipeline config (use preset default if not set)
        let taint_config = self
            .config
            .pipeline_config
            .as_inner()
            .taint
            .clone()
            .unwrap_or_else(|| crate::config::stage_configs::TaintConfig::default());

        // Get heap config from RFC-001 pipeline config (use preset default if not set)
        let heap_config = self
            .config
            .pipeline_config
            .heap()
            .unwrap_or_else(|| crate::config::stage_configs::HeapConfig::default());

        // Build indexing request FROM pipeline config (not hardcoded!)
        let request = IndexingRequest {
            repo_root: self.repo.path.clone(),
            repo_name: self.repo.id.clone(),
            // Stage enablement from PipelineConfig
            enable_taint: stages.taint,
            enable_points_to: stages.pta,
            enable_repomap: stages.repomap,
            enable_chunking: stages.chunking,
            enable_cross_file: stages.cross_file,
            enable_symbols: stages.symbols,
            enable_heap: stages.heap,
            enable_effects: stages.effects,
            enable_clone: stages.clone,
            enable_flow_graphs: stages.flow_graphs,
            ..Default::default()
        };

        // Execute full indexing with RFC-001 config
        let indexing_result = service
            .full_reindex_with_config(request)
            .map_err(|e| BenchmarkError::Indexing(e.to_string()))?;

        let duration = start.elapsed();

        // Extract taint summary from pipeline result
        let taint_summary = self.extract_taint_summary(&indexing_result, &taint_config, duration);

        // Extract PTA summary
        let pta_summary = indexing_result
            .full_result
            .points_to_summary
            .as_ref()
            .map(|pts| PTASummary {
                mode_used: pts.mode_used.clone(),
                variables_count: pts.variables_count,
                constraints_count: pts.constraints_count,
                alias_pairs: pts.alias_pairs,
            });

        // Extract RepoMap summary
        let repomap_summary = indexing_result
            .full_result
            .repomap_snapshot
            .as_ref()
            .map(|rms| {
                // Get top symbols by importance score
                let top_symbols: Vec<String> =
                    rms.nodes.iter().take(10).map(|n| n.name.clone()).collect();

                RepoMapSummary {
                    total_nodes: rms.total_nodes,
                    pagerank_iterations: 0, // Not stored in snapshot summary
                    top_10_symbols: top_symbols,
                }
            });

        // Calculate throughput safely
        let throughput = if duration.as_secs_f64() > 0.0 {
            self.repo.total_loc as f64 / duration.as_secs_f64()
        } else {
            0.0
        };

        let result = BenchmarkResult {
            repo_id: self.repo.id.clone(),
            config_name: self.config.config_name(),
            timestamp: Self::now(),
            git_commit: Some(GroundTruth::get_git_commit()),
            repo_category: self.repo.category,
            total_loc: self.repo.total_loc,
            files_count: self.repo.files.len(),
            duration,
            throughput_loc_per_sec: throughput,
            memory_mb: self.estimate_memory_mb(&indexing_result),
            files_processed: indexing_result.files_processed,
            files_cached: indexing_result.files_cached,
            files_failed: indexing_result.files_failed,
            cache_hit_rate: indexing_result.cache_hit_rate,
            total_nodes: indexing_result.full_result.nodes.len(),
            total_edges: indexing_result.full_result.edges.len(),
            total_chunks: indexing_result.full_result.chunks.len(),
            total_symbols: indexing_result.full_result.symbols.len(),
            stage_durations: indexing_result.stage_durations.clone(),
            pta_summary,
            taint_summary: Some(taint_summary),
            repomap_summary,
            errors: indexing_result.errors.clone(),
        };

        Ok(result)
    }

    /// Extract taint summary from pipeline result with SOTA metrics
    fn extract_taint_summary(
        &self,
        indexing_result: &crate::usecases::indexing_service::IndexingResult,
        taint_config: &crate::config::stage_configs::TaintConfig,
        duration: Duration,
    ) -> TaintSummary {
        let taint_results = &indexing_result.full_result.taint_results;

        // Aggregate metrics from all functions
        let sources_found: usize = taint_results.iter().map(|t| t.sources_found).sum();
        let sinks_found: usize = taint_results.iter().map(|t| t.sinks_found).sum();
        let paths_found: usize = taint_results.iter().map(|t| t.taint_flows).sum();
        let max_path_length = taint_results
            .iter()
            .map(|t| t.taint_flows)
            .max()
            .unwrap_or(0);

        // Check if SOTA features were enabled
        let sota_enabled = taint_config.ifds_enabled
            || taint_config.implicit_flow_enabled
            || taint_config.backward_analysis_enabled;

        // Sanitized paths from taint config (detect_sanitizers)
        let sanitized_paths = if taint_config.detect_sanitizers {
            // Estimate: roughly 10-20% of paths are sanitized
            paths_found / 10
        } else {
            0
        };

        TaintSummary {
            sources_found,
            sinks_found,
            paths_found,
            max_path_length,
            sota_enabled,
            sanitized_paths,
            implicit_flows_found: 0, // TODO: Extract from implicit flow analyzer
            backward_paths_found: 0, // TODO: Extract from backward analyzer
            context_sensitive: taint_config.context_sensitive,
            path_sensitive: taint_config.path_sensitive,
            timeout_hit: false, // TODO: Track timeout
            taint_duration_ms: duration.as_millis() as u64,
        }
    }

    /// Estimate memory usage (MB)
    fn estimate_memory_mb(
        &self,
        result: &crate::usecases::indexing_service::IndexingResult,
    ) -> f64 {
        // Simple estimation based on data size
        let nodes_mb = result.full_result.nodes.len() as f64 * 0.001; // ~1KB per node
        let edges_mb = result.full_result.edges.len() as f64 * 0.0001; // ~100B per edge
        let chunks_mb = result.full_result.chunks.len() as f64 * 0.01; // ~10KB per chunk
        let symbols_mb = result.full_result.symbols.len() as f64 * 0.0005; // ~500B per symbol

        nodes_mb + edges_mb + chunks_mb + symbols_mb + 10.0 // +10MB base overhead
    }

    fn aggregate_results(results: &[BenchmarkResult]) -> BenchmarkResult {
        let n = results.len() as f64;
        let mut avg = results[0].clone();

        avg.duration = Duration::from_secs_f64(
            results
                .iter()
                .map(|r| r.duration.as_secs_f64())
                .sum::<f64>()
                / n,
        );
        avg.throughput_loc_per_sec = results
            .iter()
            .map(|r| r.throughput_loc_per_sec)
            .sum::<f64>()
            / n;
        avg.memory_mb = results.iter().map(|r| r.memory_mb).sum::<f64>() / n;

        avg
    }

    fn now() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
    }
}
