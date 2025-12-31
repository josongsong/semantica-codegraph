//! Benchmark configuration
//!
//! Extends PipelineConfig from RFC-001 Config System with benchmark-specific settings.

use crate::config::{PipelineConfig, Preset, ValidatedConfig};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Tolerance settings for Ground Truth validation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tolerance {
    /// Duration tolerance (default: 5%)
    pub duration_pct: f64,

    /// Throughput tolerance (default: 5%)
    pub throughput_pct: f64,

    /// Memory tolerance (default: 10%, more variable)
    pub memory_pct: f64,

    /// Count tolerance for deterministic metrics (default: 0)
    pub count_tolerance: usize,
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

/// Benchmark-specific options
#[derive(Debug, Clone, Serialize, Deserialize)]
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

/// Complete benchmark configuration
///
/// Combines ValidatedConfig from RFC-001 with benchmark-specific settings.
#[derive(Debug, Clone)]
pub struct BenchmarkConfig {
    /// Pipeline configuration (RFC-001 ValidatedConfig)
    pub pipeline_config: ValidatedConfig,

    /// Benchmark-specific options
    pub benchmark_opts: BenchmarkOptions,
}

impl BenchmarkConfig {
    // ═════════════════════════════════════════════════════════════
    // Constructors (Preset-based)
    // ═════════════════════════════════════════════════════════════

    /// Create new benchmark config with default Balanced preset
    pub fn new() -> Self {
        Self::balanced()
    }

    /// Fast preset (CI/CD, 1x baseline, 5s target)
    pub fn fast() -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Fast)
                .build()
                .expect("Fast preset should be valid"),
            benchmark_opts: BenchmarkOptions::default(),
        }
    }

    /// Balanced preset (Development, 2.5x baseline, 30s target)
    pub fn balanced() -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Balanced)
                .build()
                .expect("Balanced preset should be valid"),
            benchmark_opts: BenchmarkOptions::default(),
        }
    }

    /// Thorough preset (Full analysis, 10x baseline, no time limit)
    pub fn thorough() -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Thorough)
                .build()
                .expect("Thorough preset should be valid"),
            benchmark_opts: BenchmarkOptions::default(),
        }
    }

    // ═════════════════════════════════════════════════════════════
    // Custom Constructors
    // ═════════════════════════════════════════════════════════════

    /// Create with custom ValidatedConfig
    pub fn with_pipeline(pipeline_config: ValidatedConfig) -> Self {
        Self {
            pipeline_config,
            benchmark_opts: BenchmarkOptions::default(),
        }
    }

    /// Create with custom options
    pub fn with_options(opts: BenchmarkOptions) -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Balanced)
                .build()
                .expect("Balanced preset should be valid"),
            benchmark_opts: opts,
        }
    }

    /// Create with preset (deprecated, use fast/balanced/thorough instead)
    #[deprecated(
        since = "0.1.0",
        note = "Use BenchmarkConfig::fast(), balanced(), or thorough() instead"
    )]
    pub fn with_preset(preset: Preset) -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(preset)
                .build()
                .expect("Preset config should be valid"),
            benchmark_opts: BenchmarkOptions::default(),
        }
    }

    // ═════════════════════════════════════════════════════════════
    // Builder Methods (Fluent API)
    // ═════════════════════════════════════════════════════════════

    /// Set warmup runs
    pub fn warmup_runs(mut self, n: usize) -> Self {
        self.benchmark_opts.warmup_runs = n;
        self
    }

    /// Set measured runs
    pub fn measured_runs(mut self, n: usize) -> Self {
        self.benchmark_opts.measured_runs = n;
        self
    }

    /// Set output directory
    pub fn output_dir(mut self, dir: PathBuf) -> Self {
        self.benchmark_opts.output_dir = dir;
        self
    }

    /// Disable ground truth validation
    pub fn skip_validation(mut self) -> Self {
        self.benchmark_opts.validate_ground_truth = false;
        self
    }

    /// Override pipeline config with custom builder
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::balanced()
    ///     .with_custom_pipeline(|builder| {
    ///         builder
    ///             .taint(|c| c.max_depth(50))
    ///             .pta(|c| c.auto_threshold(5000))
    ///     });
    /// ```
    pub fn with_custom_pipeline<F>(mut self, f: F) -> Self
    where
        F: FnOnce(PipelineConfig) -> PipelineConfig,
    {
        let preset = self.pipeline_config.as_inner().preset;
        let builder = f(PipelineConfig::preset(preset));
        self.pipeline_config = builder.build().expect("Pipeline config should be valid");
        self
    }

    // ═════════════════════════════════════════════════════════════
    // Stage-Specific Configuration (Convenience Methods)
    // ═════════════════════════════════════════════════════════════

    /// Enable security-focused analysis stages
    ///
    /// Enables: taint, heap, pta, flow_graphs, effects, pdg, concurrency, slicing
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::balanced().enable_security_analysis();
    /// ```
    pub fn enable_security_analysis(self) -> Self {
        self.with_custom_pipeline(|builder| {
            builder.with_stages(|_| crate::config::pipeline_config::StageControl::security())
        })
    }

    /// Enable all analysis stages
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::thorough().enable_all_stages();
    /// ```
    pub fn enable_all_stages(self) -> Self {
        self.with_custom_pipeline(|builder| {
            builder.with_stages(|_| crate::config::pipeline_config::StageControl::all())
        })
    }

    /// Configure taint analysis
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::balanced()
    ///     .with_taint(|t| t
    ///         .max_depth(100)
    ///         .ifds_enabled(true)
    ///         .implicit_flow_enabled(true)
    ///     );
    /// ```
    pub fn with_taint<F>(self, f: F) -> Self
    where
        F: FnOnce(crate::config::stage_configs::TaintConfig) -> crate::config::stage_configs::TaintConfig,
    {
        self.with_custom_pipeline(|builder| builder.taint(f))
    }

    /// Configure heap analysis
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::balanced()
    ///     .with_heap(|h| h
    ///         .enable_memory_safety(true)
    ///         .enable_ownership(true)
    ///         .enable_separation_logic(true)
    ///     );
    /// ```
    pub fn with_heap<F>(self, f: F) -> Self
    where
        F: FnOnce(crate::config::stage_configs::HeapConfig) -> crate::config::stage_configs::HeapConfig,
    {
        self.with_custom_pipeline(|builder| builder.heap(f))
    }

    /// Configure points-to analysis
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::balanced()
    ///     .with_pta(|p| p
    ///         .field_sensitive(true)
    ///         .max_iterations(Some(50))
    ///     );
    /// ```
    pub fn with_pta<F>(self, f: F) -> Self
    where
        F: FnOnce(crate::config::stage_configs::PTAConfig) -> crate::config::stage_configs::PTAConfig,
    {
        self.with_custom_pipeline(|builder| builder.pta(f))
    }

    /// Configure clone detection
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::balanced()
    ///     .with_clone(|c| c.types_enabled(vec![CloneType::Type1, CloneType::Type2]));
    /// ```
    pub fn with_clone_detection<F>(self, f: F) -> Self
    where
        F: FnOnce(crate::config::stage_configs::CloneConfig) -> crate::config::stage_configs::CloneConfig,
    {
        self.with_custom_pipeline(|builder| builder.clone(f))
    }

    /// Enable specific stage
    ///
    /// # Example
    /// ```ignore
    /// let config = BenchmarkConfig::fast()
    ///     .enable_stage(StageId::Taint)
    ///     .enable_stage(StageId::Heap);
    /// ```
    pub fn enable_stage(self, stage: crate::config::pipeline_config::StageId) -> Self {
        self.with_custom_pipeline(|builder| builder.with_stages(|s| s.enable(stage)))
    }

    /// Disable specific stage
    pub fn disable_stage(self, stage: crate::config::pipeline_config::StageId) -> Self {
        self.with_custom_pipeline(|builder| builder.with_stages(|s| s.disable(stage)))
    }

    // ═════════════════════════════════════════════════════════════
    // Accessors
    // ═════════════════════════════════════════════════════════════

    /// Get config name for identification
    pub fn config_name(&self) -> String {
        // Use preset name from inner PipelineConfig
        format!("{:?}", self.pipeline_config.as_inner().preset)
    }

    /// Access inner PipelineConfig
    pub fn as_pipeline_config(&self) -> &ValidatedConfig {
        &self.pipeline_config
    }

    // ═════════════════════════════════════════════════════════════
    // Legacy Stage Override (Deprecated)
    // ═════════════════════════════════════════════════════════════

    /// Stage override builder (deprecated, use with_custom_pipeline instead)
    ///
    /// # Example
    /// ```ignore
    /// // Old way (deprecated):
    /// let config = BenchmarkConfig::balanced()
    ///     .with_stage("taint", true);
    ///
    /// // New way (recommended):
    /// let config = BenchmarkConfig::balanced()
    ///     .with_custom_pipeline(|builder| {
    ///         builder.stages(|s| s.enable(StageId::Taint))
    ///     });
    /// ```
    #[deprecated(
        since = "0.1.0",
        note = "Use with_custom_pipeline() with stages() builder instead"
    )]
    pub fn with_stage(mut self, stage: &str, enabled: bool) -> Self {
        // Rebuild pipeline config with stage override
        let preset = self.pipeline_config.as_inner().preset;
        let stage_id = match stage {
            "parsing" => crate::config::pipeline_config::StageId::Parsing,
            "chunking" => crate::config::pipeline_config::StageId::Chunking,
            "lexical" => crate::config::pipeline_config::StageId::Lexical,
            "cross_file" => crate::config::pipeline_config::StageId::CrossFile,
            "clone" => crate::config::pipeline_config::StageId::Clone,
            "pta" => crate::config::pipeline_config::StageId::Pta,
            "flow_graphs" => crate::config::pipeline_config::StageId::FlowGraphs,
            "type_inference" => crate::config::pipeline_config::StageId::TypeInference,
            "symbols" => crate::config::pipeline_config::StageId::Symbols,
            "effects" => crate::config::pipeline_config::StageId::Effects,
            "taint" => crate::config::pipeline_config::StageId::Taint,
            "repomap" => crate::config::pipeline_config::StageId::RepoMap,
            _ => {
                eprintln!("Warning: Unknown stage '{}', ignoring", stage);
                return self;
            }
        };

        self.pipeline_config = PipelineConfig::preset(preset)
            .stages(|stages| {
                if enabled {
                    stages.enable(stage_id)
                } else {
                    stages.disable(stage_id)
                }
            })
            .build()
            .expect("Stage override should be valid");
        self
    }
}

impl Default for BenchmarkConfig {
    fn default() -> Self {
        Self::new()
    }
}
