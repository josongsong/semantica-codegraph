//! Ground Truth management
//!
//! Stores expected performance baselines and validates against them.

use crate::benchmark::{BenchmarkError, BenchmarkResult, BenchmarkResult2};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Validation status
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum ValidationStatus {
    Pass,
    Fail,
    Skip,
}

/// Expected performance metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExpectedMetrics {
    /// Core metrics
    pub duration_sec: f64,
    pub throughput_loc_per_sec: f64,
    pub memory_mb: f64,

    /// Deterministic metrics (exact match expected)
    pub total_nodes: usize,
    pub total_edges: usize,
    pub total_chunks: usize,
    pub total_symbols: usize,

    /// Cache metrics (informational, not validated)
    pub cache_hit_rate: f64,
}

/// Ground Truth: Expected performance for (Config, Repo)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroundTruth {
    /// Unique identifier: "{repo_id}_{config_name}"
    pub id: String,

    pub repo_id: String,
    pub config_name: String,

    /// Expected values
    pub expected: ExpectedMetrics,

    /// Metadata
    pub established_at: u64,
    pub established_by: String,
    pub last_updated_at: u64,
    pub last_updated_by: String,
    pub update_reason: String,

    /// Validation history
    pub validation_count: usize,
    pub last_validated_at: u64,
    pub last_validation_status: ValidationStatus,
}

impl GroundTruth {
    /// Create from benchmark results (average of N runs)
    pub fn from_results(
        repo_id: String,
        config_name: String,
        results: &[BenchmarkResult],
        reason: String,
    ) -> Self {
        assert!(!results.is_empty(), "Need at least 1 result");

        let n = results.len() as f64;

        let avg_duration = results
            .iter()
            .map(|r| r.duration.as_secs_f64())
            .sum::<f64>()
            / n;

        let avg_throughput = results
            .iter()
            .map(|r| r.throughput_loc_per_sec)
            .sum::<f64>()
            / n;

        let avg_memory = results.iter().map(|r| r.memory_mb).sum::<f64>() / n;

        // Deterministic metrics: use first result (should be same)
        let first = &results[0];

        let git_commit = Self::get_git_commit();

        Self {
            id: format!("{}_{}", repo_id, config_name),
            repo_id,
            config_name,
            expected: ExpectedMetrics {
                duration_sec: avg_duration,
                throughput_loc_per_sec: avg_throughput,
                memory_mb: avg_memory,
                total_nodes: first.total_nodes,
                total_edges: first.total_edges,
                total_chunks: first.total_chunks,
                total_symbols: first.total_symbols,
                cache_hit_rate: first.cache_hit_rate,
            },
            established_at: Self::now(),
            established_by: git_commit.clone(),
            last_updated_at: Self::now(),
            last_updated_by: git_commit,
            update_reason: reason,
            validation_count: 0,
            last_validated_at: 0,
            last_validation_status: ValidationStatus::Skip,
        }
    }

    fn now() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
    }

    pub fn get_git_commit() -> String {
        std::process::Command::new("git")
            .args(["rev-parse", "HEAD"])
            .output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|| "unknown".to_string())
    }
}

/// Ground Truth store (file-based)
pub struct GroundTruthStore {
    /// Storage directory
    pub root_dir: PathBuf,
}

impl GroundTruthStore {
    pub fn new(root_dir: PathBuf) -> Self {
        std::fs::create_dir_all(&root_dir).ok();
        Self { root_dir }
    }

    /// Load ground truth by ID
    pub fn load(&self, id: &str) -> BenchmarkResult2<GroundTruth> {
        let path = self.root_dir.join(format!("{}.json", id));
        let content = std::fs::read_to_string(&path)?;
        let gt: GroundTruth = serde_json::from_str(&content)?;
        Ok(gt)
    }

    /// Save ground truth
    pub fn save(&self, gt: &GroundTruth) -> BenchmarkResult2<()> {
        let path = self.root_dir.join(format!("{}.json", gt.id));
        let content = serde_json::to_string_pretty(gt)?;
        std::fs::write(&path, content)?;
        Ok(())
    }

    /// List all ground truths
    pub fn list(&self) -> BenchmarkResult2<Vec<GroundTruth>> {
        let mut gts = Vec::new();
        for entry in std::fs::read_dir(&self.root_dir)? {
            let entry = entry?;
            if entry.path().extension().and_then(|s| s.to_str()) == Some("json") {
                let content = std::fs::read_to_string(entry.path())?;
                let gt: GroundTruth = serde_json::from_str(&content)?;
                gts.push(gt);
            }
        }
        Ok(gts)
    }

    /// Find ground truth for repo + config
    pub fn find(&self, repo_id: &str, config_name: &str) -> Option<GroundTruth> {
        let id = format!("{}_{}", repo_id, config_name);
        self.load(&id).ok()
    }
}

impl Default for GroundTruthStore {
    fn default() -> Self {
        Self::new(PathBuf::from("benchmark/ground_truth"))
    }
}
