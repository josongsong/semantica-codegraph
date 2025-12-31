//! End-to-End Pipeline Configuration
//!
//! Configuration for repository-wide indexing pipeline (L1-L37)
//!
//! Integrates RFC-001 Config System with E2E-specific settings.

use crate::config::{PipelineConfig, Preset, ValidatedConfig};
use std::path::PathBuf;

/// Indexing mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IndexingMode {
    /// Full repository scan
    Full,
    /// Incremental (changed files only)
    Incremental,
    /// Smart mode with auto-escalation
    Smart,
}

/// Pipeline configuration for end-to-end repository processing
///
/// Integrates RFC-001 PipelineConfig with E2E-specific settings.
#[derive(Debug, Clone)]
pub struct E2EPipelineConfig {
    /// RFC-001 Pipeline configuration (stages, taint, pta, clone, etc.)
    pub pipeline_config: ValidatedConfig,

    /// Repository information
    pub repo_info: RepoInfo,

    /// Indexing mode
    pub mode: IndexingMode,

    /// Memory-mapped IO threshold (files larger than this use mmap)
    pub mmap_threshold_bytes: usize,
}

/// Repository information
#[derive(Debug, Clone)]
pub struct RepoInfo {
    /// Repository root path
    pub repo_root: PathBuf,

    /// Repository name/identifier
    pub repo_name: String,

    /// List of file paths to process (if None, scan all files)
    pub file_paths: Option<Vec<PathBuf>>,

    /// Language filter (if None, process all supported languages)
    pub language_filter: Option<Vec<String>>,
}

impl Default for E2EPipelineConfig {
    fn default() -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Balanced)
                .build()
                .expect("Balanced preset should be valid"),
            repo_info: RepoInfo {
                repo_root: PathBuf::from("."),
                repo_name: "unknown".to_string(),
                file_paths: None,
                language_filter: None,
            },
            mode: IndexingMode::Smart,
            mmap_threshold_bytes: 1024 * 1024, // 1MB
        }
    }
}

impl E2EPipelineConfig {
    // ═════════════════════════════════════════════════════════════
    // Constructors (Builder Pattern)
    // ═════════════════════════════════════════════════════════════

    /// Create new config with Balanced preset (default)
    pub fn new() -> Self {
        Self::default()
    }

    /// Create config with Fast preset (CI/CD, 1x baseline, 5s target)
    pub fn fast() -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Fast)
                .build()
                .expect("Fast preset should be valid"),
            ..Self::default()
        }
    }

    /// Create config with Balanced preset (Development, 2.5x baseline, 30s target)
    pub fn balanced() -> Self {
        Self::default()
    }

    /// Create config with Thorough preset (Full analysis, 10x baseline, no time limit)
    pub fn thorough() -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Thorough)
                .build()
                .expect("Thorough preset should be valid"),
            ..Self::default()
        }
    }

    /// Create config with custom ValidatedConfig
    pub fn with_config(pipeline_config: ValidatedConfig) -> Self {
        Self {
            pipeline_config,
            ..Self::default()
        }
    }

    /// Create minimal config (IR build only)
    pub fn minimal() -> Self {
        Self {
            pipeline_config: PipelineConfig::preset(Preset::Fast)
                .stages(|mut s| {
                    // Disable all non-essential stages
                    s.chunking = false;
                    s.lexical = false;
                    s.cross_file = false;
                    s.clone = false;
                    s.pta = false;
                    s.flow_graphs = false;
                    s.type_inference = false;
                    s.symbols = false;
                    s.effects = false;
                    s.taint = false;
                    s.repomap = false;
                    s
                })
                .build()
                .expect("Minimal config should be valid"),
            ..Self::default()
        }
    }

    /// Create full config (all stages enabled)
    pub fn full() -> Self {
        Self::thorough()
    }

    /// Load config from YAML file
    ///
    /// # Example
    /// ```ignore
    /// let config = E2EPipelineConfig::from_yaml("config.yaml")?;
    /// ```
    pub fn from_yaml(path: &str) -> Result<Self, crate::config::ConfigError> {
        Ok(Self {
            pipeline_config: PipelineConfig::from_yaml(path)?,
            ..Self::default()
        })
    }

    // ═════════════════════════════════════════════════════════════
    // Accessor Methods (Convenience API)
    // ═════════════════════════════════════════════════════════════

    /// Access inner PipelineConfig
    pub fn as_pipeline_config(&self) -> &ValidatedConfig {
        &self.pipeline_config
    }

    /// Access cache configuration from RFC-001
    /// Returns default config if not overridden
    pub fn cache(&self) -> crate::config::CacheConfig {
        self.pipeline_config
            .as_inner()
            .cache
            .clone()
            .unwrap_or_default()
    }

    /// Access parallel configuration from RFC-001
    /// Returns default config if not overridden
    pub fn parallel(&self) -> crate::config::ParallelConfig {
        self.pipeline_config
            .as_inner()
            .parallel
            .clone()
            .unwrap_or_else(|| {
                crate::config::ParallelConfig::from_preset(self.pipeline_config.as_inner().preset)
            })
    }

    /// Access pagerank configuration from RFC-001
    /// Returns default config if not overridden
    pub fn pagerank(&self) -> crate::config::PageRankConfig {
        self.pipeline_config
            .as_inner()
            .pagerank
            .clone()
            .unwrap_or_default()
    }

    /// Get effective number of workers
    pub fn effective_workers(&self) -> usize {
        let parallel = self.parallel();
        parallel.num_workers
    }

    /// Check if specific stage is enabled
    pub fn is_stage_enabled(&self, stage: crate::config::pipeline_config::StageId) -> bool {
        self.pipeline_config.as_inner().stages.is_enabled(stage)
    }

    // ═════════════════════════════════════════════════════════════
    // Legacy Compatibility Methods (for UnifiedOrchestrator)
    // ═════════════════════════════════════════════════════════════

    /// Get stages (for backward compatibility)
    pub fn stages(&self) -> &crate::config::StageControl {
        &self.pipeline_config.as_inner().stages
    }

    /// Check if IR build is enabled (parsing)
    pub fn enable_ir_build(&self) -> bool {
        self.stages().parsing
    }

    /// Check if chunking is enabled
    pub fn enable_chunking(&self) -> bool {
        self.stages().chunking
    }

    /// Check if lexical indexing is enabled
    pub fn enable_lexical(&self) -> bool {
        self.stages().lexical
    }

    /// Check if cross-file analysis is enabled
    pub fn enable_cross_file(&self) -> bool {
        self.stages().cross_file
    }

    /// Check if clone detection is enabled
    pub fn enable_clone_detection(&self) -> bool {
        self.stages().clone
    }

    /// Check if points-to analysis is enabled
    pub fn enable_points_to(&self) -> bool {
        self.stages().pta
    }

    /// Check if effect analysis is enabled
    pub fn enable_effect_analysis(&self) -> bool {
        self.stages().effects
    }

    /// Check if taint analysis is enabled
    pub fn enable_taint(&self) -> bool {
        self.stages().taint
    }

    /// Check if repomap is enabled
    pub fn enable_repomap(&self) -> bool {
        self.stages().repomap
    }

    /// Check if heap analysis is enabled
    pub fn enable_heap_analysis(&self) -> bool {
        self.stages().heap
    }

    /// Check if concurrency analysis is enabled
    pub fn enable_concurrency_analysis(&self) -> bool {
        self.stages().concurrency
    }

    /// Check if flow graphs are enabled
    pub fn enable_flow_graph(&self) -> bool {
        self.stages().flow_graphs
    }

    /// Check if type inference is enabled
    pub fn enable_types(&self) -> bool {
        self.stages().type_inference
    }

    /// Check if symbols analysis is enabled
    pub fn enable_symbols(&self) -> bool {
        self.stages().symbols
    }

    /// Get number of workers from parallel config
    pub fn num_workers(&self) -> Option<usize> {
        Some(self.parallel().num_workers)
    }

    // ═════════════════════════════════════════════════════════════
    // Builder Methods (Fluent API)
    // ═════════════════════════════════════════════════════════════

    /// Set repository root path
    pub fn repo_root(mut self, path: PathBuf) -> Self {
        self.repo_info.repo_root = path;
        self
    }

    /// Set repository name
    pub fn repo_name(mut self, name: String) -> Self {
        self.repo_info.repo_name = name;
        self
    }

    /// Set file paths to process
    pub fn file_paths(mut self, paths: Vec<PathBuf>) -> Self {
        self.repo_info.file_paths = Some(paths);
        self
    }

    /// Set language filter
    pub fn language_filter(mut self, languages: Vec<String>) -> Self {
        self.repo_info.language_filter = Some(languages);
        self
    }

    /// Set indexing mode
    pub fn indexing_mode(mut self, mode: IndexingMode) -> Self {
        self.mode = mode;
        self
    }

    /// Set mmap threshold
    pub fn mmap_threshold(mut self, threshold: usize) -> Self {
        self.mmap_threshold_bytes = threshold;
        self
    }

    /// Override pipeline config with custom builder
    ///
    /// # Example
    /// ```ignore
    /// let config = E2EPipelineConfig::balanced()
    ///     .with_pipeline(|builder| {
    ///         builder
    ///             .taint(|c| c.max_depth(50))
    ///             .pta(|c| c.auto_threshold(5000))
    ///     });
    /// ```
    pub fn with_pipeline<F>(mut self, f: F) -> Self
    where
        F: FnOnce(PipelineConfig) -> PipelineConfig,
    {
        let preset = self.pipeline_config.as_inner().preset;
        let builder = f(PipelineConfig::preset(preset));
        self.pipeline_config = builder.build().expect("Pipeline config should be valid");
        self
    }
}
