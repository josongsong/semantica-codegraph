# R002: SOTA Benchmark System - Rust-Only with Ground Truth Regression

**Status**: Draft
**Author**: Codegraph Team
**Created**: 2025-12-29
**Updated**: 2025-12-29
**RFC Number**: R002
**Goal**: Rust 전용 벤치마킹 시스템 + Ground Truth 기반 성능 회귀 방지

---

## Executive Summary

**현재 문제:**
- 30+ 벤치마크 파일 산재 (Rust + Python)
- 통일된 리포트 형식 없음
- **성능 회귀 감지 불가** (Ground Truth 없음)
- RFC-CONFIG-SYSTEM과 통합 안됨
- 히스토리 추적 불가

**제안:**
```rust
// 90% Use Case: 한 줄로 벤치마크 + 자동 회귀 검사
cargo bench-codegraph --repo typer --preset balanced

// 9% Use Case: 특정 설정으로 벤치마크
cargo bench-codegraph --repo django --config security-audit.yaml

// 1% Use Case: Ground Truth 생성 (릴리스 전)
cargo bench-codegraph --repo typer --preset balanced --save-ground-truth
```

**핵심 개선사항:**
- ✅ Rust 전용 (일관된 측정, 낮은 오버헤드)
- ✅ RFC-CONFIG-SYSTEM 완벽 통합 (Preset + YAML)
- ✅ Ground Truth 기반 회귀 테스트 (±5% 허용)
- ✅ 통일된 리포트 형식 (JSON + Markdown + HTML)
- ✅ 히스토리 추적 (Git 커밋별)
- ✅ CI/CD 통합 (자동 회귀 검사)
- ✅ 다중 리포지토리 비교 (Small/Medium/Large)

---

## Part 1: Ground Truth Philosophy

### 1.1. What is Ground Truth?

**정의**: 특정 설정 + 특정 리포지토리에서 **검증된 성능 기준값**

```
Ground Truth = (Config, Repo, Expected Performance)

Example:
  Config:   Preset::Balanced
  Repo:     typer (small, 8k LOC)
  Expected:
    - Duration: 2.5s ± 5%
    - Throughput: 3200 LOC/sec ± 5%
    - Memory: 150MB ± 10%
```

### 1.2. Why Ground Truth?

| Without Ground Truth | With Ground Truth |
|---------------------|-------------------|
| ❌ "성능이 느려진 것 같은데?" | ✅ **회귀 검출**: "Duration 2.1s → 3.2s (+52%, FAIL)" |
| ❌ 수동으로 과거 결과 비교 | ✅ **자동 검증**: CI에서 즉시 실패 |
| ❌ 최적화 효과 불명확 | ✅ **개선 추적**: "Throughput +15% (2800 → 3220)" |
| ❌ 설정 변경 영향 알 수 없음 | ✅ **설정 영향 측정**: "Fast vs Balanced: 2.5x 차이" |

### 1.3. Ground Truth Lifecycle

```
┌──────────────────────────────────────────────────────────┐
│ Phase 1: Initial Establishment (릴리스 전)                │
│   - Preset별 Ground Truth 생성                           │
│   - 3회 실행 평균 (안정성 확보)                            │
│   - Tolerance 설정 (Duration ±5%, Memory ±10%)          │
└─────────────────┬────────────────────────────────────────┘
                  ▼
┌──────────────────────────────────────────────────────────┐
│ Phase 2: Continuous Validation (매 PR)                  │
│   - CI에서 Ground Truth 대비 검증                        │
│   - 허용 범위 초과 시 PR 블록                             │
│   - 성능 저하 원인 요구 (코멘트)                          │
└─────────────────┬────────────────────────────────────────┘
                  ▼
┌──────────────────────────────────────────────────────────┐
│ Phase 3: Periodic Update (월 1회 or 릴리스)              │
│   - 의도적 최적화 후 Ground Truth 갱신                    │
│   - 변경 로그 필수: "Why updated? +15% by ..."          │
│   - Team review 필수                                    │
└──────────────────────────────────────────────────────────┘
```

### 1.4. Tolerance Strategy

**Why Tolerance?**
- ❌ 0% Tolerance: 노이즈(CPU throttling, GC)로 False Positive
- ✅ ±5% Tolerance: 실제 회귀만 검출

**Tolerance by Metric:**
```rust
pub struct Tolerance {
    /// Duration tolerance (default: 5%)
    /// - Too strict (<2%): False positives from system noise
    /// - Too loose (>10%): Miss real regressions
    pub duration_pct: f64,  // 5%

    /// Throughput tolerance (default: 5%)
    pub throughput_pct: f64,  // 5%

    /// Memory tolerance (default: 10%)
    /// - Memory more variable than CPU
    pub memory_pct: f64,  // 10%

    /// Node/edge count tolerance (default: 0%)
    /// - Deterministic, should be exact
    pub count_tolerance: usize,  // 0
}
```

**Adaptive Tolerance (Future):**
```rust
// Small repo: 엄격한 tolerance (노이즈 적음)
if repo.loc < 10_000 {
    tolerance.duration_pct = 3.0;
}

// Large repo: 느슨한 tolerance (노이즈 많음)
if repo.loc > 100_000 {
    tolerance.duration_pct = 10.0;
}
```

---

## Part 2: Architecture

### 2.1. Overall Design

```
┌─────────────────────────────────────────────────────────────┐
│                  CLI: cargo bench-codegraph                 │
│  (Thin wrapper, parses args, calls BenchmarkRunner)        │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   BenchmarkRunner (Core)                    │
│  1. Load BenchmarkConfig (from RFC-CONFIG)                  │
│  2. Discover repos (small/medium/large)                     │
│  3. Run benchmarks (single or multi-repo)                   │
│  4. Collect BenchmarkResult                                 │
│  5. Validate against Ground Truth                           │
│  6. Generate Reports (JSON + MD + HTML)                     │
└────┬──────────────────┬──────────────────┬─────────────────┘
     │                  │                  │
     ▼                  ▼                  ▼
┌─────────┐   ┌──────────────┐   ┌────────────────┐
│ Config  │   │ Ground Truth │   │ Report Gen     │
│ (R001)  │   │ Store        │   │ (Multi-format) │
└─────────┘   └──────────────┘   └────────────────┘
```

### 2.2. Module Structure

```
packages/codegraph-ir/src/benchmark/
├── mod.rs                      # Re-exports
├── config.rs                   # BenchmarkConfig (RFC-CONFIG 통합)
├── runner.rs                   # BenchmarkRunner (orchestrator)
├── repository.rs               # Repository (repo metadata)
├── result.rs                   # BenchmarkResult (single run)
├── ground_truth.rs             # GroundTruth (expected values)
├── validator.rs                # GroundTruthValidator (회귀 검사)
├── report/
│   ├── mod.rs
│   ├── json.rs                 # JSON report
│   ├── markdown.rs             # Markdown report
│   ├── html.rs                 # HTML report (waterfall chart)
│   └── terminal.rs             # Terminal output (pretty)
└── repos/
    ├── mod.rs
    ├── discovery.rs            # Auto-discover repos
    └── presets.rs              # Well-known repos (typer, django, etc.)
```

### 2.3. CLI Tool

```bash
# Install as cargo subcommand
cargo install --path packages/codegraph-ir --bin bench-codegraph

# Usage
cargo bench-codegraph --help
```

---

## Part 3: Core Types

### 3.1. BenchmarkConfig (RFC-CONFIG 통합)

```rust
use crate::config::PipelineConfig;  // From RFC-CONFIG

/// Benchmark configuration (extends PipelineConfig)
#[derive(Debug, Clone)]
pub struct BenchmarkConfig {
    /// Pipeline configuration (from RFC-CONFIG)
    pub pipeline: PipelineConfig,

    /// Benchmark-specific settings
    pub benchmark_opts: BenchmarkOptions,
}

#[derive(Debug, Clone)]
pub struct BenchmarkOptions {
    /// Number of warmup runs (default: 1)
    pub warmup_runs: usize,

    /// Number of measured runs (default: 3)
    pub measured_runs: usize,

    /// Enable memory profiling (default: true)
    pub profile_memory: bool,

    /// Enable stage-level timing (default: true)
    pub profile_stages: bool,

    /// Save results to disk (default: true)
    pub save_results: bool,

    /// Output directory (default: "target/benchmark_results")
    pub output_dir: PathBuf,

    /// Ground Truth validation (default: true)
    pub validate_ground_truth: bool,

    /// Tolerance settings
    pub tolerance: Tolerance,
}

impl Default for BenchmarkOptions {
    fn default() -> Self {
        Self {
            warmup_runs: 1,
            measured_runs: 3,
            profile_memory: true,
            profile_stages: true,
            save_results: true,
            output_dir: PathBuf::from("target/benchmark_results"),
            validate_ground_truth: true,
            tolerance: Tolerance::default(),
        }
    }
}

impl BenchmarkConfig {
    /// Create from preset (simplest)
    pub fn from_preset(preset: Preset) -> Self {
        Self {
            pipeline: PipelineConfig::preset(preset).build().unwrap(),
            benchmark_opts: BenchmarkOptions::default(),
        }
    }

    /// Create from YAML (advanced)
    pub fn from_yaml(path: &str) -> Result<Self, BenchmarkError> {
        let pipeline = PipelineConfig::from_yaml(path)?;
        Ok(Self {
            pipeline,
            benchmark_opts: BenchmarkOptions::default(),
        })
    }
}
```

### 3.2. Repository

```rust
/// Repository metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Repository {
    /// Unique identifier (e.g., "typer", "django")
    pub id: String,

    /// Display name
    pub name: String,

    /// Path to repository
    pub path: PathBuf,

    /// Size category
    pub category: RepoCategory,

    /// Source files (auto-discovered)
    pub files: Vec<PathBuf>,

    /// Total LOC
    pub total_loc: usize,

    /// Primary language
    pub language: Language,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum RepoCategory {
    Small,   // < 10k LOC
    Medium,  // 10k - 100k LOC
    Large,   // > 100k LOC
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum Language {
    Python,
    Rust,
    JavaScript,
    TypeScript,
    Go,
    Java,
    Kotlin,
}

impl Repository {
    /// Auto-discover repository from path
    pub fn from_path(path: PathBuf) -> Result<Self, BenchmarkError> {
        let id = path.file_name()
            .ok_or(BenchmarkError::InvalidRepo)?
            .to_string_lossy()
            .to_string();

        // Scan files
        let files = Self::scan_files(&path)?;
        let total_loc = Self::count_loc(&files)?;

        let category = match total_loc {
            0..=10_000 => RepoCategory::Small,
            10_001..=100_000 => RepoCategory::Medium,
            _ => RepoCategory::Large,
        };

        Ok(Self {
            id: id.clone(),
            name: id,
            path,
            category,
            files,
            total_loc,
            language: Language::Python,  // TODO: detect
        })
    }

    fn scan_files(path: &PathBuf) -> Result<Vec<PathBuf>, BenchmarkError> {
        // Similar to benchmark_large_repos.rs count_files()
        // ...
    }

    fn count_loc(files: &[PathBuf]) -> Result<usize, BenchmarkError> {
        // ...
    }
}
```

### 3.3. BenchmarkResult

```rust
use std::time::Duration;
use std::collections::HashMap;

/// Single benchmark run result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BenchmarkResult {
    /// Metadata
    pub repo_id: String,
    pub config_name: String,  // e.g., "Preset::Balanced"
    pub timestamp: u64,       // Unix timestamp
    pub git_commit: Option<String>,  // Current HEAD

    /// Repository info
    pub repo_category: RepoCategory,
    pub total_loc: usize,
    pub files_count: usize,

    /// Performance metrics
    pub duration: Duration,
    pub throughput_loc_per_sec: f64,
    pub memory_mb: f64,

    /// Indexing results (from IndexingResult)
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
    pub stage_durations: HashMap<String, Duration>,

    /// Analysis-specific metrics
    pub pta_summary: Option<PTASummary>,
    pub taint_summary: Option<TaintSummary>,
    pub repomap_summary: Option<RepoMapSummary>,

    /// Errors
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PTASummary {
    pub mode_used: String,       // "Fast (Steensgaard)" or "Precise (Andersen)"
    pub variables_count: usize,
    pub constraints_count: usize,
    pub alias_pairs: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintSummary {
    pub sources_found: usize,
    pub sinks_found: usize,
    pub paths_found: usize,
    pub max_path_length: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepoMapSummary {
    pub total_nodes: usize,
    pub pagerank_iterations: usize,
    pub top_10_symbols: Vec<String>,
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
            memory_change_pct: Self::pct_change(
                self.memory_mb,
                other.memory_mb,
            ),
            // ... other fields
        }
    }

    fn pct_change(before: f64, after: f64) -> f64 {
        ((after - before) / before) * 100.0
    }
}

#[derive(Debug, Clone)]
pub struct BenchmarkDiff {
    pub duration_change_pct: f64,     // -10.5 = 10.5% faster
    pub throughput_change_pct: f64,   // +15.2 = 15.2% faster
    pub memory_change_pct: f64,       // +5.0 = 5% more memory
}
```

### 3.4. Ground Truth

```rust
/// Ground Truth: Expected performance for (Config, Repo)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroundTruth {
    /// Unique identifier: "{repo_id}_{config_name}"
    pub id: String,

    pub repo_id: String,
    pub config_name: String,

    /// Expected values (from N runs average)
    pub expected: ExpectedMetrics,

    /// Metadata
    pub established_at: u64,       // Unix timestamp
    pub established_by: String,    // Git commit SHA
    pub last_updated_at: u64,
    pub last_updated_by: String,
    pub update_reason: String,     // "Initial baseline" or "Optimized X by Y%"

    /// Validation history
    pub validation_count: usize,   // How many times validated
    pub last_validated_at: u64,
    pub last_validation_status: ValidationStatus,
}

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

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum ValidationStatus {
    Pass,
    Fail,
    Skip,
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

        let avg_duration = results.iter()
            .map(|r| r.duration.as_secs_f64())
            .sum::<f64>() / n;

        let avg_throughput = results.iter()
            .map(|r| r.throughput_loc_per_sec)
            .sum::<f64>() / n;

        let avg_memory = results.iter()
            .map(|r| r.memory_mb)
            .sum::<f64>() / n;

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

    fn get_git_commit() -> String {
        // Use git2 crate or shell command
        std::process::Command::new("git")
            .args(&["rev-parse", "HEAD"])
            .output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|| "unknown".to_string())
    }
}
```

### 3.5. Ground Truth Storage

```rust
/// Ground Truth store (file-based)
pub struct GroundTruthStore {
    /// Storage directory (default: "benchmark/ground_truth")
    pub root_dir: PathBuf,
}

impl GroundTruthStore {
    pub fn new(root_dir: PathBuf) -> Self {
        std::fs::create_dir_all(&root_dir).ok();
        Self { root_dir }
    }

    /// Load ground truth by ID
    pub fn load(&self, id: &str) -> Result<GroundTruth, BenchmarkError> {
        let path = self.root_dir.join(format!("{}.json", id));
        let content = std::fs::read_to_string(&path)?;
        let gt: GroundTruth = serde_json::from_str(&content)?;
        Ok(gt)
    }

    /// Save ground truth
    pub fn save(&self, gt: &GroundTruth) -> Result<(), BenchmarkError> {
        let path = self.root_dir.join(format!("{}.json", gt.id));
        let content = serde_json::to_string_pretty(gt)?;
        std::fs::write(&path, content)?;
        Ok(())
    }

    /// List all ground truths
    pub fn list(&self) -> Result<Vec<GroundTruth>, BenchmarkError> {
        let mut gts = Vec::new();
        for entry in std::fs::read_dir(&self.root_dir)? {
            let entry = entry?;
            if entry.path().extension() == Some("json".as_ref()) {
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
```

### 3.6. Ground Truth Validator

```rust
/// Validates benchmark results against ground truth
pub struct GroundTruthValidator {
    pub tolerance: Tolerance,
}

#[derive(Debug, Clone)]
pub struct Tolerance {
    pub duration_pct: f64,      // 5.0 = ±5%
    pub throughput_pct: f64,    // 5.0 = ±5%
    pub memory_pct: f64,        // 10.0 = ±10%
    pub count_tolerance: usize, // 0 = exact match
}

impl Default for Tolerance {
    fn default() -> Self {
        Self {
            duration_pct: 5.0,
            throughput_pct: 5.0,
            memory_pct: 10.0,
            count_tolerance: 0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ValidationResult {
    pub status: ValidationStatus,
    pub violations: Vec<Violation>,
    pub summary: String,
}

#[derive(Debug, Clone)]
pub struct Violation {
    pub metric: String,
    pub expected: f64,
    pub actual: f64,
    pub diff_pct: f64,
    pub tolerance_pct: f64,
    pub severity: Severity,
}

#[derive(Debug, Clone, Copy)]
pub enum Severity {
    Critical,  // >20% regression
    High,      // 10-20% regression
    Medium,    // 5-10% regression (outside tolerance)
    Low,       // Within tolerance but worth noting
}

impl GroundTruthValidator {
    pub fn new(tolerance: Tolerance) -> Self {
        Self { tolerance }
    }

    /// Validate benchmark result against ground truth
    pub fn validate(
        &self,
        result: &BenchmarkResult,
        ground_truth: &GroundTruth,
    ) -> ValidationResult {
        let mut violations = Vec::new();

        // 1. Duration check
        let duration_diff_pct = Self::pct_diff(
            ground_truth.expected.duration_sec,
            result.duration.as_secs_f64(),
        );
        if duration_diff_pct.abs() > self.tolerance.duration_pct {
            violations.push(Violation {
                metric: "duration".to_string(),
                expected: ground_truth.expected.duration_sec,
                actual: result.duration.as_secs_f64(),
                diff_pct: duration_diff_pct,
                tolerance_pct: self.tolerance.duration_pct,
                severity: Self::classify_severity(duration_diff_pct.abs()),
            });
        }

        // 2. Throughput check
        let throughput_diff_pct = Self::pct_diff(
            ground_truth.expected.throughput_loc_per_sec,
            result.throughput_loc_per_sec,
        );
        if throughput_diff_pct.abs() > self.tolerance.throughput_pct {
            violations.push(Violation {
                metric: "throughput".to_string(),
                expected: ground_truth.expected.throughput_loc_per_sec,
                actual: result.throughput_loc_per_sec,
                diff_pct: throughput_diff_pct,
                tolerance_pct: self.tolerance.throughput_pct,
                severity: Self::classify_severity(throughput_diff_pct.abs()),
            });
        }

        // 3. Memory check
        let memory_diff_pct = Self::pct_diff(
            ground_truth.expected.memory_mb,
            result.memory_mb,
        );
        if memory_diff_pct.abs() > self.tolerance.memory_pct {
            violations.push(Violation {
                metric: "memory".to_string(),
                expected: ground_truth.expected.memory_mb,
                actual: result.memory_mb,
                diff_pct: memory_diff_pct,
                tolerance_pct: self.tolerance.memory_pct,
                severity: Self::classify_severity(memory_diff_pct.abs()),
            });
        }

        // 4. Deterministic metrics (exact match)
        if result.total_nodes != ground_truth.expected.total_nodes {
            violations.push(Violation {
                metric: "total_nodes".to_string(),
                expected: ground_truth.expected.total_nodes as f64,
                actual: result.total_nodes as f64,
                diff_pct: Self::pct_diff(
                    ground_truth.expected.total_nodes as f64,
                    result.total_nodes as f64,
                ),
                tolerance_pct: 0.0,
                severity: Severity::Critical,
            });
        }

        // ... similar for edges, chunks, symbols

        // Determine overall status
        let status = if violations.is_empty() {
            ValidationStatus::Pass
        } else {
            ValidationStatus::Fail
        };

        // Generate summary
        let summary = if violations.is_empty() {
            "✅ All metrics within tolerance".to_string()
        } else {
            format!(
                "❌ {} violation(s) detected:\n{}",
                violations.len(),
                violations.iter()
                    .map(|v| format!(
                        "  - {}: {:.1}% (expected: {:.2}, actual: {:.2}, tolerance: ±{:.1}%)",
                        v.metric, v.diff_pct, v.expected, v.actual, v.tolerance_pct
                    ))
                    .collect::<Vec<_>>()
                    .join("\n")
            )
        };

        ValidationResult {
            status,
            violations,
            summary,
        }
    }

    fn pct_diff(expected: f64, actual: f64) -> f64 {
        ((actual - expected) / expected) * 100.0
    }

    fn classify_severity(diff_pct: f64) -> Severity {
        match diff_pct {
            d if d > 20.0 => Severity::Critical,
            d if d > 10.0 => Severity::High,
            d if d > 5.0 => Severity::Medium,
            _ => Severity::Low,
        }
    }
}
```

---

## Part 4: BenchmarkRunner

```rust
/// Orchestrates the entire benchmark process
pub struct BenchmarkRunner {
    pub config: BenchmarkConfig,
    pub repo: Repository,
    pub ground_truth_store: GroundTruthStore,
    pub validator: GroundTruthValidator,
}

impl BenchmarkRunner {
    pub fn new(
        config: BenchmarkConfig,
        repo: Repository,
    ) -> Self {
        let ground_truth_store = GroundTruthStore::new(
            PathBuf::from("benchmark/ground_truth")
        );

        let validator = GroundTruthValidator::new(
            config.benchmark_opts.tolerance.clone()
        );

        Self {
            config,
            repo,
            ground_truth_store,
            validator,
        }
    }

    /// Run complete benchmark workflow
    pub fn run(&self) -> Result<BenchmarkReport, BenchmarkError> {
        println!("╔══════════════════════════════════════════════════════════╗");
        println!("║  Codegraph Benchmark (Rust-Only, Ground Truth)          ║");
        println!("╚══════════════════════════════════════════════════════════╝");
        println!();
        println!("Repository: {}", self.repo.name);
        println!("Category:   {:?} ({} LOC)", self.repo.category, self.repo.total_loc);
        println!("Config:     {}", self.config_name());
        println!();

        // Step 1: Warmup runs
        println!("Step 1: Warmup ({} runs)...", self.config.benchmark_opts.warmup_runs);
        for i in 0..self.config.benchmark_opts.warmup_runs {
            println!("  Warmup run {}/{}...", i + 1, self.config.benchmark_opts.warmup_runs);
            self.run_single_benchmark()?;
        }
        println!();

        // Step 2: Measured runs
        println!("Step 2: Measured runs ({})...", self.config.benchmark_opts.measured_runs);
        let mut results = Vec::new();
        for i in 0..self.config.benchmark_opts.measured_runs {
            println!("  Run {}/{}...", i + 1, self.config.benchmark_opts.measured_runs);
            let result = self.run_single_benchmark()?;
            results.push(result);
        }
        println!();

        // Step 3: Aggregate results
        let avg_result = Self::aggregate_results(&results);

        // Step 4: Ground Truth validation
        let validation = if self.config.benchmark_opts.validate_ground_truth {
            println!("Step 3: Ground Truth Validation...");
            let gt = self.ground_truth_store.find(
                &self.repo.id,
                &self.config_name(),
            );

            if let Some(gt) = gt {
                let validation = self.validator.validate(&avg_result, &gt);
                println!("{}", validation.summary);
                println!();
                Some(validation)
            } else {
                println!("  ⚠️  No ground truth found for {}_{}", self.repo.id, self.config_name());
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
            config_name: self.config_name(),
            results,
            avg_result,
            validation,
            timestamp: Self::now(),
        };

        // Step 6: Save reports
        if self.config.benchmark_opts.save_results {
            self.save_reports(&report)?;
        }

        Ok(report)
    }

    /// Run single benchmark
    fn run_single_benchmark(&self) -> Result<BenchmarkResult, BenchmarkError> {
        let service = IndexingService::new();

        let start = std::time::Instant::now();

        // Use IndexingService API from RFC-CONFIG
        let indexing_result = service.scheduled_index(
            self.repo.path.clone(),
            self.repo.id.clone(),
            true,  // with_full_analysis based on config
        )?;

        let duration = start.elapsed();

        // Collect memory stats (basic, can be enhanced)
        let memory_mb = Self::estimate_memory_mb();

        // Build BenchmarkResult from IndexingResult
        let result = BenchmarkResult {
            repo_id: self.repo.id.clone(),
            config_name: self.config_name(),
            timestamp: Self::now(),
            git_commit: GroundTruth::get_git_commit().into(),
            repo_category: self.repo.category,
            total_loc: self.repo.total_loc,
            files_count: self.repo.files.len(),
            duration,
            throughput_loc_per_sec: self.repo.total_loc as f64 / duration.as_secs_f64(),
            memory_mb,
            files_processed: indexing_result.files_processed,
            files_cached: indexing_result.files_cached,
            files_failed: indexing_result.files_failed,
            cache_hit_rate: indexing_result.cache_hit_rate,
            total_nodes: indexing_result.full_result.nodes.len(),
            total_edges: indexing_result.full_result.edges.len(),
            total_chunks: indexing_result.full_result.chunks.len(),
            total_symbols: indexing_result.full_result.symbols.len(),
            stage_durations: indexing_result.stage_durations,
            pta_summary: indexing_result.full_result.points_to_summary.map(|pta| PTASummary {
                mode_used: pta.mode_used,
                variables_count: pta.variables_count,
                constraints_count: pta.constraints_count,
                alias_pairs: pta.alias_pairs,
            }),
            taint_summary: None,  // TODO: add to IndexingResult
            repomap_summary: None,  // TODO: add to IndexingResult
            errors: indexing_result.errors,
        };

        Ok(result)
    }

    fn aggregate_results(results: &[BenchmarkResult]) -> BenchmarkResult {
        let n = results.len() as f64;
        let mut avg = results[0].clone();

        avg.duration = Duration::from_secs_f64(
            results.iter().map(|r| r.duration.as_secs_f64()).sum::<f64>() / n
        );
        avg.throughput_loc_per_sec = results.iter()
            .map(|r| r.throughput_loc_per_sec).sum::<f64>() / n;
        avg.memory_mb = results.iter()
            .map(|r| r.memory_mb).sum::<f64>() / n;

        avg
    }

    fn config_name(&self) -> String {
        format!("Preset::{:?}", self.config.pipeline.preset)
        // Or extract from PipelineConfig metadata
    }

    fn now() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
    }

    fn estimate_memory_mb() -> f64 {
        // TODO: Use jemalloc stats or /proc/self/status
        100.0
    }

    fn save_reports(&self, report: &BenchmarkReport) -> Result<(), BenchmarkError> {
        // Create output directory
        let output_dir = self.config.benchmark_opts.output_dir
            .join(&self.repo.id)
            .join(&self.config_name());
        std::fs::create_dir_all(&output_dir)?;

        // Save JSON
        let json_path = output_dir.join("result.json");
        let json = serde_json::to_string_pretty(report)?;
        std::fs::write(&json_path, json)?;
        println!("📄 JSON saved: {:?}", json_path);

        // Save Markdown
        let md_path = output_dir.join("report.md");
        let md = self.generate_markdown_report(report);
        std::fs::write(&md_path, md)?;
        println!("📄 Markdown saved: {:?}", md_path);

        // TODO: Save HTML waterfall

        Ok(())
    }

    fn generate_markdown_report(&self, report: &BenchmarkReport) -> String {
        format!(
            r#"# Benchmark Report: {}

**Repository**: {} ({:?}, {} LOC)
**Configuration**: {}
**Timestamp**: {}
**Git Commit**: {}

## Summary

| Metric | Value |
|--------|-------|
| Duration | {:.2}s |
| Throughput | {:.0} LOC/sec |
| Memory | {:.1} MB |
| Nodes | {} |
| Edges | {} |
| Chunks | {} |
| Symbols | {} |

## Ground Truth Validation

{}

## Stage Breakdown

| Stage | Duration | % of Total |
|-------|----------|------------|
{}

"#,
            self.repo.name,
            self.repo.id,
            self.repo.category,
            self.repo.total_loc,
            report.config_name,
            report.timestamp,
            report.avg_result.git_commit.as_ref().unwrap_or(&"N/A".to_string()),
            report.avg_result.duration.as_secs_f64(),
            report.avg_result.throughput_loc_per_sec,
            report.avg_result.memory_mb,
            report.avg_result.total_nodes,
            report.avg_result.total_edges,
            report.avg_result.total_chunks,
            report.avg_result.total_symbols,
            report.validation.as_ref()
                .map(|v| v.summary.clone())
                .unwrap_or_else(|| "N/A".to_string()),
            report.avg_result.stage_durations.iter()
                .map(|(stage, dur)| {
                    let pct = (dur.as_secs_f64() / report.avg_result.duration.as_secs_f64()) * 100.0;
                    format!("| {} | {:.2}s | {:.1}% |", stage, dur.as_secs_f64(), pct)
                })
                .collect::<Vec<_>>()
                .join("\n")
        )
    }
}

#[derive(Debug, Clone)]
pub struct BenchmarkReport {
    pub repo: Repository,
    pub config_name: String,
    pub results: Vec<BenchmarkResult>,
    pub avg_result: BenchmarkResult,
    pub validation: Option<ValidationResult>,
    pub timestamp: u64,
}
```

---

## Part 5: CLI Interface

### 5.1. Command Structure

```bash
# packages/codegraph-ir/src/bin/bench-codegraph.rs

cargo bench-codegraph [OPTIONS] <SUBCOMMAND>

Subcommands:
  run           Run benchmark
  save-gt       Save ground truth
  list-gt       List all ground truths
  update-gt     Update existing ground truth
  compare       Compare multiple benchmarks
  regression    Run regression test suite

Global Options:
  --repo <PATH>         Repository path
  --preset <PRESET>     Preset: fast|balanced|thorough
  --config <YAML>       Custom config YAML
  --output <DIR>        Output directory
```

### 5.2. Subcommand Examples

```bash
# 1. Run benchmark with preset
cargo bench-codegraph run --repo tools/benchmark/repo-test/small/typer --preset balanced

# 2. Run with custom config
cargo bench-codegraph run --repo /path/to/django --config security-audit.yaml

# 3. Save ground truth (after verifying results)
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/small/typer --preset balanced

# 4. List all ground truths
cargo bench-codegraph list-gt

# 5. Update ground truth (requires --reason)
cargo bench-codegraph update-gt \
  --repo typer \
  --preset balanced \
  --reason "Optimized cross-file resolution by 15%"

# 6. Compare presets
cargo bench-codegraph compare \
  --repo typer \
  --presets fast,balanced,thorough

# 7. Regression test (validate all ground truths)
cargo bench-codegraph regression
```

---

## Part 6: Ground Truth Management Workflow

### 6.1. Initial Setup (Release v1.0.0)

```bash
# 1. Establish ground truth for all presets × all repos

# Small repo (typer)
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/small/typer --preset fast
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/small/typer --preset balanced
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/small/typer --preset thorough

# Medium repo (rich)
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/medium/rich --preset fast
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/medium/rich --preset balanced

# Large repo (django)
# (omit thorough preset for large repos - too slow)
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/large/django --preset fast
cargo bench-codegraph save-gt --repo tools/benchmark/repo-test/large/django --preset balanced

# Result: benchmark/ground_truth/
#   - typer_Preset::Fast.json
#   - typer_Preset::Balanced.json
#   - typer_Preset::Thorough.json
#   - rich_Preset::Fast.json
#   - rich_Preset::Balanced.json
#   - django_Preset::Fast.json
#   - django_Preset::Balanced.json
```

### 6.2. Daily Development (PR Workflow)

```yaml
# .github/workflows/benchmark-regression.yml
name: Benchmark Regression Test

on:
  pull_request:
    paths:
      - 'packages/codegraph-ir/**'
      - 'packages/codegraph-storage/**'

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install Rust
        uses: actions-rust-lang/setup-rust-toolchain@v1

      - name: Run regression test
        run: |
          cargo bench-codegraph regression --fail-fast

      - name: Post comment on failure
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '❌ **Performance regression detected!**\n\nPlease investigate or update ground truth with `--reason`.'
            })
```

**Developer Experience:**
1. PR 생성
2. CI가 자동으로 `regression` 실행
3. Ground Truth 대비 ±5% 초과 시 → ❌ Fail
4. 두 가지 선택:
   - **Option A**: 성능 저하 수정 (코드 최적화)
   - **Option B**: 의도적 변경이면 Ground Truth 업데이트 (이유 명시)

### 6.3. Monthly Review (Ground Truth Update)

```bash
# Scenario: Cross-file resolution 최적화로 15% 성능 향상

# 1. 최적화 작업 후 벤치마크 실행
cargo bench-codegraph run --repo typer --preset balanced
# Result: Throughput 3200 → 3680 LOC/sec (+15%)

# 2. Ground Truth 업데이트 (이유 필수)
cargo bench-codegraph update-gt \
  --repo typer \
  --preset balanced \
  --reason "RFC-042: Optimized cross-file resolution with caching (+15%)"

# 3. Git commit
git add benchmark/ground_truth/typer_Preset::Balanced.json
git commit -m "chore: Update ground truth for typer/balanced (+15% by RFC-042)"

# 4. Team review 필수 (PR)
```

**Update Log (in GroundTruth):**
```json
{
  "id": "typer_Preset::Balanced",
  "last_updated_at": 1735488000,
  "last_updated_by": "a1b2c3d4...",
  "update_reason": "RFC-042: Optimized cross-file resolution with caching (+15%)",
  "history": [
    {
      "timestamp": 1735401600,
      "commit": "abc123...",
      "reason": "Initial baseline"
    },
    {
      "timestamp": 1735488000,
      "commit": "a1b2c3d4...",
      "reason": "RFC-042: Optimized cross-file resolution with caching (+15%)"
    }
  ]
}
```

---

## Part 7: Report Formats

### 7.1. Terminal Output (Pretty)

```
╔══════════════════════════════════════════════════════════╗
║  Codegraph Benchmark - typer (Preset::Balanced)         ║
╚══════════════════════════════════════════════════════════╝

Repository: typer (Small, 8,234 LOC)
Configuration: Preset::Balanced
Runs: 3 (after 1 warmup)

┌──────────────────────────────────────────────────────────┐
│ Performance Summary                                      │
├──────────────────────────────────────────────────────────┤
│  Duration:     2.45s                                     │
│  Throughput:   3,362 LOC/sec                             │
│  Memory:       148 MB                                    │
│  Nodes:        12,456                                    │
│  Edges:        8,921                                     │
│  Chunks:       234                                       │
│  Symbols:      1,089                                     │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ Ground Truth Validation                                  │
├──────────────────────────────────────────────────────────┤
│  ✅ All metrics within tolerance                         │
│                                                          │
│  Duration:     2.45s vs 2.50s expected (-2.0%, ✓)       │
│  Throughput:   3,362 vs 3,200 expected (+5.1%, ✓)       │
│  Memory:       148 MB vs 150 MB expected (-1.3%, ✓)     │
│  Nodes:        12,456 vs 12,456 expected (exact, ✓)     │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ Stage Breakdown                                          │
├──────────────────────────────────────────────────────────┤
│  L1_IR_Build          0.45s  ██████░░░░░░░░░░  18.4%    │
│  L2_Chunking          0.12s  ██░░░░░░░░░░░░░░   4.9%    │
│  L3_CrossFile         0.68s  ███████████░░░░░  27.8%    │
│  L4_Occurrences       0.34s  █████░░░░░░░░░░░  13.9%    │
│  L5_Symbols           0.21s  ███░░░░░░░░░░░░░   8.6%    │
│  L6_PointsTo          0.52s  ████████░░░░░░░░  21.2%    │
│  L14_TaintAnalysis    0.08s  █░░░░░░░░░░░░░░░   3.3%    │
│  L16_RepoMap          0.05s  █░░░░░░░░░░░░░░░   2.0%    │
└──────────────────────────────────────────────────────────┘

Reports saved:
  📄 target/benchmark_results/typer/Preset::Balanced/result.json
  📄 target/benchmark_results/typer/Preset::Balanced/report.md
```

### 7.2. JSON Output

```json
{
  "repo": {
    "id": "typer",
    "name": "typer",
    "category": "Small",
    "total_loc": 8234,
    "files_count": 45
  },
  "config_name": "Preset::Balanced",
  "timestamp": 1735488000,
  "avg_result": {
    "duration_sec": 2.45,
    "throughput_loc_per_sec": 3362,
    "memory_mb": 148,
    "total_nodes": 12456,
    "total_edges": 8921,
    "stage_durations": {
      "L1_IR_Build": 0.45,
      "L2_Chunking": 0.12,
      "L3_CrossFile": 0.68
    }
  },
  "validation": {
    "status": "Pass",
    "violations": [],
    "summary": "✅ All metrics within tolerance"
  }
}
```

### 7.3. Markdown Report

(Already shown in BenchmarkRunner::generate_markdown_report)

### 7.4. HTML Waterfall (Future)

```html
<!-- Interactive waterfall chart with:
     - Timeline visualization
     - Hover tooltips
     - Stage filtering
     - Multi-run comparison
-->
```

---

## Part 8: Integration with RFC-CONFIG

```rust
// Perfect integration example

// 1. Use PipelineConfig from RFC-CONFIG
let pipeline_config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50))
    .build()?;

// 2. Wrap in BenchmarkConfig
let bench_config = BenchmarkConfig {
    pipeline: pipeline_config,
    benchmark_opts: BenchmarkOptions::default(),
};

// 3. Run benchmark
let repo = Repository::from_path(PathBuf::from("tools/benchmark/repo-test/small/typer"))?;
let runner = BenchmarkRunner::new(bench_config, repo);
let report = runner.run()?;

// 4. Validate against ground truth
if let Some(validation) = report.validation {
    if validation.status == ValidationStatus::Fail {
        eprintln!("❌ Performance regression detected!");
        std::process::exit(1);
    }
}
```

---

## Part 9: Migration Plan

### Phase 1: Core Infrastructure (Week 1)

**Goal**: Basic benchmark framework

- [ ] Create `packages/codegraph-ir/src/benchmark/` module
- [ ] Implement core types:
  - [ ] `BenchmarkConfig`
  - [ ] `Repository`
  - [ ] `BenchmarkResult`
  - [ ] `GroundTruth`
  - [ ] `GroundTruthStore`
  - [ ] `GroundTruthValidator`
- [ ] Implement `BenchmarkRunner::run()`
- [ ] Basic terminal output

### Phase 2: CLI Tool (Week 2)

**Goal**: Usable CLI

- [ ] Create `packages/codegraph-ir/src/bin/bench-codegraph.rs`
- [ ] Implement subcommands:
  - [ ] `run`
  - [ ] `save-gt`
  - [ ] `list-gt`
- [ ] Integrate with RFC-CONFIG `PipelineConfig`
- [ ] Repository auto-discovery

### Phase 3: Reports (Week 3)

**Goal**: Rich reporting

- [ ] JSON export
- [ ] Markdown report
- [ ] Terminal pretty-print
- [ ] HTML waterfall (optional)

### Phase 4: CI Integration (Week 4)

**Goal**: Automated regression testing

- [ ] Implement `regression` subcommand
- [ ] GitHub Actions workflow
- [ ] Ground Truth initial baselines
- [ ] Documentation

---

## Part 10: Success Metrics

### Quantitative

- [ ] **30+ scattered benchmarks → 1 unified tool**
- [ ] **0 ground truths → 7+ baselines** (3 repos × 2-3 presets)
- [ ] **0% regression detection → 100%** (CI blocks bad PRs)
- [ ] **Manual comparison → Automated validation**

### Qualitative

- [ ] "Ground Truth로 성능 회귀 즉시 발견" (DevOps)
- [ ] "RFC-CONFIG와 완벽 통합" (Dev)
- [ ] "CI에서 자동으로 성능 보장" (QA)
- [ ] "리포트가 읽기 쉽고 이해하기 쉬움" (PM)

---

## Appendix A: Well-Known Repositories

```rust
// benchmark/repos/presets.rs

/// Curated list of well-known repositories for benchmarking
pub struct WellKnownRepos;

impl WellKnownRepos {
    pub fn list() -> Vec<Repository> {
        vec![
            // Small (< 10k LOC)
            Self::typer(),
            Self::attrs(),

            // Medium (10k - 100k LOC)
            Self::rich(),
            Self::fastapi(),

            // Large (> 100k LOC)
            Self::django(),
            Self::pandas(),
        ]
    }

    fn typer() -> Repository {
        Repository::from_path(
            PathBuf::from("tools/benchmark/repo-test/small/typer")
        ).expect("typer repo not found")
    }

    // ... similar for others
}
```

---

## Appendix B: Tolerance Tuning Guide

```
┌─────────────────────────────────────────────────────────┐
│ Metric         │ Default │ Rationale                    │
├─────────────────────────────────────────────────────────┤
│ Duration       │  ±5%    │ CPU throttling, GC noise     │
│ Throughput     │  ±5%    │ Inverse of duration          │
│ Memory         │  ±10%   │ More variable than CPU       │
│ Nodes/Edges    │  0      │ Deterministic, exact match   │
└─────────────────────────────────────────────────────────┘

Tuning Tips:
1. Start with default (5% / 10%)
2. Run 10 benchmarks, check stddev
3. If stddev > tolerance → increase tolerance
4. If stddev << tolerance → decrease tolerance
5. Re-run after tuning to validate
```

---

## Appendix C: Comparison with Existing Tools

| Feature | benchmark_large_repos.rs | bench_indexing.py | RFC-002 (This) |
|---------|--------------------------|-------------------|----------------|
| **Language** | Rust | Python | Rust |
| **Ground Truth** | ❌ | ❌ | ✅ |
| **Regression Test** | ❌ | ❌ | ✅ |
| **Config Integration** | ❌ | ❌ | ✅ (RFC-CONFIG) |
| **Multi-repo** | ❌ | ❌ | ✅ |
| **Reports** | CSV, Waterfall | Text | JSON, MD, HTML |
| **CI Integration** | ❌ | ❌ | ✅ |
| **Overhead** | Low | High | Low |

---

## Appendix D: Python Bindings (PyO3)

### D.1. Problem: Rust Build Time

**현재 문제:**
- Rust full build: 2-5분 (clean build)
- Incremental build: 30초-1분
- 설정 변경마다 재빌드 필요 → DX 저하

**해결책 2가지:**

#### Solution A: Python Bindings (PyO3) - 빠른 반복

```python
# Python에서 직접 벤치마크 실행 (Rust 재빌드 불필요)
from codegraph_ir import BenchmarkRunner, PipelineConfig, Preset

# 1. Preset 사용
config = PipelineConfig.preset(Preset.BALANCED)
runner = BenchmarkRunner(config, repo_path="tools/benchmark/repo-test/small/typer")
report = runner.run()

# 2. 설정 동적 변경 (Rust 재빌드 없음!)
config = PipelineConfig.preset(Preset.BALANCED)
config.taint.max_depth = 50
config.taint.max_paths = 1000
report = runner.run()

# 3. YAML 로드
config = PipelineConfig.from_yaml("my-config.yaml")
report = runner.run()

# 4. 여러 설정 비교 (한 번 실행)
for preset in [Preset.FAST, Preset.BALANCED, Preset.THOROUGH]:
    config = PipelineConfig.preset(preset)
    runner = BenchmarkRunner(config, repo_path="typer")
    report = runner.run()
    print(f"{preset}: {report.avg_result.duration_sec:.2f}s")
```

**장점:**
- ✅ Rust 재빌드 불필요
- ✅ 빠른 반복 (설정 변경 즉시 실행)
- ✅ Jupyter Notebook 지원
- ✅ Pandas/Matplotlib로 분석 가능

**단점:**
- ⚠️ 초기 maturin build 필요 (1회만)
- ⚠️ PyO3 바인딩 유지보수

#### Solution B: Rust Incremental Build 최적화

**B.1. Cargo Workspace 분리**

```toml
# Current (monolithic):
packages/codegraph-ir/Cargo.toml  # 1개 큰 crate → 변경 시 전체 재빌드

# Optimized (split):
packages/codegraph-ir/
├── codegraph-ir-core/       # 핵심 로직 (변경 적음)
├── codegraph-ir-config/     # RFC-CONFIG (변경 많음)
├── codegraph-ir-benchmark/  # 벤치마크 (변경 많음)
└── codegraph-ir/            # 통합 (re-export)
```

**효과:**
- Config 변경 시 `codegraph-ir-config`만 재빌드 (5초)
- Core 로직은 캐시 사용

**B.2. Feature Flags로 빌드 시간 단축**

```toml
# Cargo.toml
[features]
default = ["benchmark"]
benchmark = []
full-analysis = ["pta", "taint", "repomap"]
pta = []
taint = []
repomap = []

# 벤치마크만 빌드 (PTA/Taint 제외)
cargo build --no-default-features --features benchmark
# → 빌드 시간 50% 감소
```

**B.3. sccache로 빌드 캐시**

```bash
# 설치
cargo install sccache

# 환경변수 설정
export RUSTC_WRAPPER=sccache

# 빌드 (최초: 2분, 이후: 10초)
cargo build --release

# 캐시 통계 확인
sccache --show-stats
```

**효과:**
- CI/로컬 간 캐시 공유
- Clean build도 10-20초

**B.4. mold 링커 (Linux) or lld (Mac)**

```toml
# .cargo/config.toml
[target.x86_64-unknown-linux-gnu]
linker = "clang"
rustflags = ["-C", "link-arg=-fuse-ld=mold"]

[target.x86_64-apple-darwin]
rustflags = ["-C", "link-arg=-fuse-ld=/usr/local/opt/llvm/bin/ld64.lld"]
```

**효과:**
- 링킹 시간 80% 감소 (10초 → 2초)

---

### D.2. Recommended Approach (Hybrid)

**For Development (빠른 반복):**
```python
# tools/benchmark/bench_quick.py
from codegraph_ir import BenchmarkRunner, PipelineConfig, Preset

# 설정만 바꿔가며 빠르게 테스트
configs = [
    PipelineConfig.preset(Preset.FAST),
    PipelineConfig.preset(Preset.BALANCED),
    PipelineConfig.preset(Preset.BALANCED).with_taint(max_depth=100),
]

for i, config in enumerate(configs):
    print(f"\n=== Config {i+1} ===")
    runner = BenchmarkRunner(config, repo_path="typer")
    report = runner.run()
    print(f"Duration: {report.avg_result.duration_sec:.2f}s")
```

**For CI/Production (정확한 측정):**
```bash
# Rust CLI로 Ground Truth 검증
cargo bench-codegraph regression --fail-fast
```

---

### D.3. PyO3 Implementation Plan

**Phase 1: Core Bindings**

```rust
// packages/codegraph-ir/src/python/mod.rs

use pyo3::prelude::*;

#[pyclass]
pub struct PyPipelineConfig {
    inner: crate::config::PipelineConfig,
}

#[pymethods]
impl PyPipelineConfig {
    #[staticmethod]
    fn preset(preset: &str) -> PyResult<Self> {
        let preset = match preset {
            "fast" => crate::config::Preset::Fast,
            "balanced" => crate::config::Preset::Balanced,
            "thorough" => crate::config::Preset::Thorough,
            _ => return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Unknown preset: {}", preset)
            )),
        };

        Ok(Self {
            inner: crate::config::PipelineConfig::preset(preset)
                .build()
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                    format!("{:?}", e)
                ))?,
        })
    }

    #[staticmethod]
    fn from_yaml(path: &str) -> PyResult<Self> {
        Ok(Self {
            inner: crate::config::PipelineConfig::from_yaml(path)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                    format!("{:?}", e)
                ))?,
        })
    }

    // Getter/Setter for dynamic modification
    #[getter]
    fn taint_max_depth(&self) -> usize {
        self.inner.effective_taint().max_depth
    }

    #[setter]
    fn set_taint_max_depth(&mut self, value: usize) {
        // TODO: Implement mutable config
        // self.inner.taint.max_depth = value;
    }
}

#[pyclass]
pub struct PyBenchmarkRunner {
    config: crate::benchmark::BenchmarkConfig,
    repo_path: PathBuf,
}

#[pymethods]
impl PyBenchmarkRunner {
    #[new]
    fn new(config: PyPipelineConfig, repo_path: &str) -> PyResult<Self> {
        let repo = crate::benchmark::Repository::from_path(
            PathBuf::from(repo_path)
        ).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("{:?}", e)
        ))?;

        Ok(Self {
            config: crate::benchmark::BenchmarkConfig {
                pipeline: config.inner,
                benchmark_opts: Default::default(),
            },
            repo_path: PathBuf::from(repo_path),
        })
    }

    fn run(&self) -> PyResult<PyBenchmarkReport> {
        let repo = crate::benchmark::Repository::from_path(
            self.repo_path.clone()
        ).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("{:?}", e)
        ))?;

        let runner = crate::benchmark::BenchmarkRunner::new(
            self.config.clone(),
            repo,
        );

        let report = runner.run()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                format!("{:?}", e)
            ))?;

        Ok(PyBenchmarkReport { inner: report })
    }
}

#[pyclass]
pub struct PyBenchmarkReport {
    inner: crate::benchmark::BenchmarkReport,
}

#[pymethods]
impl PyBenchmarkReport {
    #[getter]
    fn duration_sec(&self) -> f64 {
        self.inner.avg_result.duration.as_secs_f64()
    }

    #[getter]
    fn throughput_loc_per_sec(&self) -> f64 {
        self.inner.avg_result.throughput_loc_per_sec
    }

    #[getter]
    fn memory_mb(&self) -> f64 {
        self.inner.avg_result.memory_mb
    }

    fn to_dict(&self) -> PyResult<HashMap<String, PyObject>> {
        Python::with_gil(|py| {
            let mut map = HashMap::new();
            map.insert("duration_sec".to_string(), self.duration_sec().to_object(py));
            map.insert("throughput".to_string(), self.throughput_loc_per_sec().to_object(py));
            map.insert("memory_mb".to_string(), self.memory_mb().to_object(py));
            // ... add more fields
            Ok(map)
        })
    }

    fn __repr__(&self) -> String {
        format!(
            "BenchmarkReport(duration={:.2}s, throughput={:.0} LOC/sec, memory={:.1} MB)",
            self.duration_sec(),
            self.throughput_loc_per_sec(),
            self.memory_mb()
        )
    }
}

#[pymodule]
fn codegraph_ir_benchmark(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyPipelineConfig>()?;
    m.add_class::<PyBenchmarkRunner>()?;
    m.add_class::<PyBenchmarkReport>()?;
    Ok(())
}
```

**Build with maturin:**

```toml
# pyproject.toml
[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"

[project]
name = "codegraph-ir-benchmark"
requires-python = ">=3.10"
```

```bash
# Development build (incremental, 5-10초)
maturin develop

# Release build (최초 1회만, 2분)
maturin build --release
pip install target/wheels/*.whl
```

---

### D.4. Python Benchmark Script Example

```python
#!/usr/bin/env python3
"""
Quick benchmark script using Python bindings (no Rust rebuild needed)

Usage:
    python tools/benchmark/bench_quick.py --repo typer --preset balanced
    python tools/benchmark/bench_quick.py --repo typer --config my-config.yaml
    python tools/benchmark/bench_quick.py --repo typer --compare-presets
"""

import argparse
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

from codegraph_ir_benchmark import (
    BenchmarkRunner,
    PipelineConfig,
    Preset,
)


def run_single(repo_path: str, config: PipelineConfig):
    """Run single benchmark"""
    runner = BenchmarkRunner(config, repo_path=repo_path)
    report = runner.run()

    print(f"\n{'='*60}")
    print(f"Duration:    {report.duration_sec:.2f}s")
    print(f"Throughput:  {report.throughput_loc_per_sec:.0f} LOC/sec")
    print(f"Memory:      {report.memory_mb:.1f} MB")
    print(f"{'='*60}\n")

    return report


def compare_presets(repo_path: str):
    """Compare all presets"""
    presets = [Preset.FAST, Preset.BALANCED, Preset.THOROUGH]
    results = []

    for preset in presets:
        print(f"\n🔥 Running {preset}...")
        config = PipelineConfig.preset(preset)
        runner = BenchmarkRunner(config, repo_path=repo_path)
        report = runner.run()

        results.append({
            'preset': preset,
            'duration_sec': report.duration_sec,
            'throughput': report.throughput_loc_per_sec,
            'memory_mb': report.memory_mb,
        })

    # Create DataFrame
    df = pd.DataFrame(results)
    print("\n" + "="*60)
    print("Comparison Summary:")
    print("="*60)
    print(df.to_string(index=False))

    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    axes[0].bar(df['preset'], df['duration_sec'])
    axes[0].set_title('Duration (lower is better)')
    axes[0].set_ylabel('Seconds')

    axes[1].bar(df['preset'], df['throughput'])
    axes[1].set_title('Throughput (higher is better)')
    axes[1].set_ylabel('LOC/sec')

    axes[2].bar(df['preset'], df['memory_mb'])
    axes[2].set_title('Memory Usage')
    axes[2].set_ylabel('MB')

    plt.tight_layout()
    plt.savefig('benchmark_comparison.png')
    print("\n📊 Chart saved: benchmark_comparison.png")


def sweep_taint_depth(repo_path: str):
    """Sweep taint max_depth parameter"""
    depths = [10, 20, 30, 50, 100, 200]
    results = []

    for depth in depths:
        print(f"\n🔥 Running with taint.max_depth={depth}...")
        config = PipelineConfig.preset(Preset.BALANCED)
        # TODO: Add setter for taint.max_depth
        # config.taint.max_depth = depth

        runner = BenchmarkRunner(config, repo_path=repo_path)
        report = runner.run()

        results.append({
            'max_depth': depth,
            'duration_sec': report.duration_sec,
        })

    df = pd.DataFrame(results)
    print("\n" + "="*60)
    print("Taint Depth Sweep:")
    print("="*60)
    print(df.to_string(index=False))

    # Plot
    plt.figure(figsize=(10, 6))
    plt.plot(df['max_depth'], df['duration_sec'], marker='o')
    plt.xlabel('Taint Max Depth')
    plt.ylabel('Duration (seconds)')
    plt.title('Impact of Taint Max Depth on Performance')
    plt.grid(True)
    plt.savefig('taint_depth_sweep.png')
    print("\n📊 Chart saved: taint_depth_sweep.png")


def main():
    parser = argparse.ArgumentParser(description='Quick benchmark (Python)')
    parser.add_argument('--repo', required=True, help='Repository path')
    parser.add_argument('--preset', choices=['fast', 'balanced', 'thorough'], help='Preset')
    parser.add_argument('--config', help='YAML config path')
    parser.add_argument('--compare-presets', action='store_true', help='Compare all presets')
    parser.add_argument('--sweep-taint-depth', action='store_true', help='Sweep taint depth')

    args = parser.parse_args()

    if args.compare_presets:
        compare_presets(args.repo)
    elif args.sweep_taint_depth:
        sweep_taint_depth(args.repo)
    elif args.preset:
        config = PipelineConfig.preset(args.preset.upper())
        run_single(args.repo, config)
    elif args.config:
        config = PipelineConfig.from_yaml(args.config)
        run_single(args.repo, config)
    else:
        parser.error("Specify --preset, --config, --compare-presets, or --sweep-taint-depth")


if __name__ == '__main__':
    main()
```

**Usage:**

```bash
# 1. Initial build (1회만, 2분)
maturin develop --release

# 2. 이후 설정 변경은 Rust 재빌드 불필요!
python tools/benchmark/bench_quick.py --repo tools/benchmark/repo-test/small/typer --preset balanced

# 3. 모든 Preset 비교 (3번 실행, Rust 재빌드 0초)
python tools/benchmark/bench_quick.py --repo typer --compare-presets

# 4. Taint depth sweep (6번 실행, Rust 재빌드 0초)
python tools/benchmark/bench_quick.py --repo typer --sweep-taint-depth
```

---

### D.5. Build Time Comparison

| Approach | Initial Build | Config Change | Total (10 iterations) |
|----------|---------------|---------------|----------------------|
| **Rust CLI only** | 2분 | 30초 | 2분 + 10×30초 = 7분 |
| **Python + maturin** | 2분 (1회) | **0초** | 2분 + 10×0초 = **2분** |
| **Rust + sccache + workspace split** | 2분 (1회) | 5초 | 2분 + 10×5초 = 2분 50초 |

**Winner**: Python bindings (3.5배 빠름)

---

### D.6. Migration Strategy

**Week 1-2: Rust-only (RFC-002 Phase 1-2)**
- Ground Truth 시스템 구축
- CLI 기본 기능

**Week 3: Python Bindings**
- PyO3 바인딩 추가
- `bench_quick.py` 스크립트

**Week 4: Both Available**
- Python: 개발/실험용 (빠른 반복)
- Rust CLI: CI/프로덕션용 (정확한 측정)

---

## Decision

**Approve**: [ ]
**Revise**: [ ]
**Reject**: [ ]

**Reviewers**: _____________
**Date**: _____________

---

**RFC End**
