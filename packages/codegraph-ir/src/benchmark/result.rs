//! Benchmark result types

use crate::benchmark::repository::RepoCategory;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;

/// Points-to Analysis summary
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PTASummary {
    pub mode_used: String,
    pub variables_count: usize,
    pub constraints_count: usize,
    pub alias_pairs: usize,
}

/// Taint Analysis summary (RFC-001 SOTA integrated)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintSummary {
    // ═══════════════════════════════════════════════════════════════════
    // Basic Metrics
    // ═══════════════════════════════════════════════════════════════════
    pub sources_found: usize,
    pub sinks_found: usize,
    pub paths_found: usize,
    pub max_path_length: usize,

    // ═══════════════════════════════════════════════════════════════════
    // SOTA Extensions (RFC-001 TaintConfig)
    // ═══════════════════════════════════════════════════════════════════
    /// Whether SOTA analyzer was enabled
    pub sota_enabled: bool,

    /// Number of paths filtered by sanitizer detection
    pub sanitized_paths: usize,

    /// Implicit flow vulnerabilities found (control dependency taint)
    pub implicit_flows_found: usize,

    /// Backward analysis paths (sink → source tracing)
    pub backward_paths_found: usize,

    /// Context-sensitive analysis was used
    pub context_sensitive: bool,

    /// Path-sensitive analysis was used
    pub path_sensitive: bool,

    // ═══════════════════════════════════════════════════════════════════
    // Performance Metrics
    // ═══════════════════════════════════════════════════════════════════
    /// Analysis timeout hit (if true, results may be incomplete)
    pub timeout_hit: bool,

    /// Taint analysis duration (milliseconds)
    pub taint_duration_ms: u64,
}

/// RepoMap/PageRank summary
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepoMapSummary {
    pub total_nodes: usize,
    pub pagerank_iterations: usize,
    pub top_10_symbols: Vec<String>,
}

/// Single benchmark run result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BenchmarkResult {
    /// Metadata
    pub repo_id: String,
    pub config_name: String,
    pub timestamp: u64,
    pub git_commit: Option<String>,

    /// Repository info
    pub repo_category: RepoCategory,
    pub total_loc: usize,
    pub files_count: usize,

    /// Performance metrics
    #[serde(with = "duration_serde")]
    pub duration: Duration,
    pub throughput_loc_per_sec: f64,
    pub memory_mb: f64,

    /// Indexing results
    pub files_processed: usize,
    pub files_cached: usize,
    pub files_failed: usize,
    pub cache_hit_rate: f64,

    /// IR metrics
    pub total_nodes: usize,
    pub total_edges: usize,
    pub total_chunks: usize,
    pub total_symbols: usize,

    /// Stage-level breakdown
    #[serde(with = "stage_durations_serde")]
    pub stage_durations: HashMap<String, Duration>,

    /// Analysis-specific metrics
    pub pta_summary: Option<PTASummary>,
    pub taint_summary: Option<TaintSummary>,
    pub repomap_summary: Option<RepoMapSummary>,

    /// Errors
    pub errors: Vec<String>,
}

impl BenchmarkResult {
    /// Compare with another result (for regression detection)
    pub fn diff(&self, other: &Self) -> BenchmarkDiff {
        BenchmarkDiff {
            duration_change_pct: Self::pct_change(
                self.duration.as_secs_f64(),
                other.duration.as_secs_f64(),
            ),
            throughput_change_pct: Self::pct_change(
                self.throughput_loc_per_sec,
                other.throughput_loc_per_sec,
            ),
            memory_change_pct: Self::pct_change(self.memory_mb, other.memory_mb),
            nodes_change_pct: Self::pct_change(self.total_nodes as f64, other.total_nodes as f64),
        }
    }

    fn pct_change(before: f64, after: f64) -> f64 {
        ((after - before) / before) * 100.0
    }
}

/// Difference between two benchmark results
#[derive(Debug, Clone)]
pub struct BenchmarkDiff {
    pub duration_change_pct: f64,
    pub throughput_change_pct: f64,
    pub memory_change_pct: f64,
    pub nodes_change_pct: f64,
}

// Serde helpers for Duration
mod duration_serde {
    use serde::{Deserialize, Deserializer, Serialize, Serializer};
    use std::time::Duration;

    pub fn serialize<S>(duration: &Duration, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        duration.as_secs_f64().serialize(serializer)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<Duration, D::Error>
    where
        D: Deserializer<'de>,
    {
        let secs = f64::deserialize(deserializer)?;
        Ok(Duration::from_secs_f64(secs))
    }
}

mod stage_durations_serde {
    use serde::{Deserialize, Deserializer, Serialize, Serializer};
    use std::collections::HashMap;
    use std::time::Duration;

    pub fn serialize<S>(map: &HashMap<String, Duration>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut converted = HashMap::new();
        for (k, v) in map {
            converted.insert(k.clone(), v.as_secs_f64());
        }
        converted.serialize(serializer)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<HashMap<String, Duration>, D::Error>
    where
        D: Deserializer<'de>,
    {
        let map: HashMap<String, f64> = HashMap::deserialize(deserializer)?;
        let mut converted = HashMap::new();
        for (k, v) in map {
            converted.insert(k, Duration::from_secs_f64(v));
        }
        Ok(converted)
    }
}
