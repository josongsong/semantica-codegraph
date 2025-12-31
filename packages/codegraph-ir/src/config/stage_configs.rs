//! Stage-specific configuration types
//!
//! Each pipeline stage has its own configuration struct with validation.
//!
//! ## SOLID Compliance
//! - **S**: Each config struct has single responsibility
//! - **O**: New configs can be added without modifying existing ones
//! - **D**: All configs implement `Validatable` trait for DIP

use super::error::{ConfigError, ConfigResult};
use super::preset::Preset;
use super::validation::Validatable;
use serde::{Deserialize, Serialize};

// ============================================================================
// L14: Taint Analysis Configuration
// ============================================================================

/// L14: Taint Analysis Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct TaintConfig {
    /// Maximum call chain depth (1..=1000)
    pub max_depth: usize,

    /// Maximum taint paths to track (1..=100000)
    pub max_paths: usize,

    /// Use points-to analysis for precision
    pub use_points_to: bool,

    /// Enable field-sensitive tracking
    pub field_sensitive: bool,

    /// Enable SSA-based analysis
    pub use_ssa: bool,

    /// Detect sanitizers (reduces false positives)
    pub detect_sanitizers: bool,

    /// Enable interprocedural analysis
    pub enable_interprocedural: bool,

    /// Worklist solver max iterations (1..=10000)
    pub worklist_max_iterations: usize,

    // ========================================
    // IFDS/IDE Framework Settings (2025-01-01)
    // ========================================
    /// Enable IFDS-based analysis (more precise than worklist)
    #[serde(default = "default_true")]
    pub ifds_enabled: bool,

    /// IFDS maximum iterations (1..=100000)
    #[serde(default = "default_ifds_max_iterations")]
    pub ifds_max_iterations: usize,

    /// IFDS summary edge caching (improves performance)
    #[serde(default = "default_true")]
    pub ifds_summary_cache_enabled: bool,

    /// Enable IDE value propagation (extends IFDS with values)
    #[serde(default = "default_true")]
    pub ide_enabled: bool,

    /// IDE micro-function caching (edge function result reuse)
    #[serde(default = "default_true")]
    pub ide_micro_cache_enabled: bool,

    /// IDE jump-function caching (procedure summary reuse)
    #[serde(default = "default_true")]
    pub ide_jump_cache_enabled: bool,

    /// Enable Sparse IFDS optimization (2-10x speedup)
    #[serde(default)]
    pub sparse_ifds_enabled: bool,

    /// Minimum reduction ratio for Sparse IFDS activation (0.0..=1.0)
    /// Only use sparse mode if (1 - sparse_nodes/total_nodes) >= this value
    #[serde(default = "default_sparse_min_reduction")]
    pub sparse_min_reduction_ratio: f64,

    // ========================================
    // SOTA Extensions (2025-01-01)
    // ========================================
    /// Enable implicit flow analysis (control dependency taint)
    /// Tracks taint through control flow decisions (if/else branches)
    #[serde(default)]
    pub implicit_flow_enabled: bool,

    /// Enable backward taint analysis (sink → source tracing)
    /// Useful for vulnerability investigation
    #[serde(default)]
    pub backward_analysis_enabled: bool,

    /// Enable context-sensitive analysis (call-site sensitivity)
    /// Distinguishes different call contexts for same function
    #[serde(default = "default_true")]
    pub context_sensitive: bool,

    /// Enable path-sensitive analysis (expensive, uses SMT)
    /// Tracks taint along feasible paths only
    #[serde(default)]
    pub path_sensitive: bool,

    /// Analysis timeout in seconds (0 = unlimited)
    #[serde(default = "default_timeout")]
    pub timeout_seconds: u64,
}

fn default_true() -> bool {
    true
}
fn default_ifds_max_iterations() -> usize {
    10000
}
fn default_sparse_min_reduction() -> f64 {
    0.3
}
fn default_timeout() -> u64 {
    60
}

// SOTA defaults (2025-01-01)
fn default_max_symbolic_objects() -> usize {
    10000
}
fn default_concolic_max_depth() -> usize {
    100
}
fn default_concolic_strategy() -> String {
    "dfs".to_string()
}

impl TaintConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if self.max_depth == 0 || self.max_depth > 1000 {
            return Err(ConfigError::range_with_hint(
                "max_depth",
                self.max_depth,
                1,
                1000,
                "Call chain depth must be at least 1",
            ));
        }

        if self.max_paths == 0 || self.max_paths > 100000 {
            return Err(ConfigError::range_with_hint(
                "max_paths",
                self.max_paths,
                1,
                100000,
                "Number of taint paths must be reasonable",
            ));
        }

        if self.worklist_max_iterations == 0 || self.worklist_max_iterations > 10000 {
            return Err(ConfigError::range_with_hint(
                "worklist_max_iterations",
                self.worklist_max_iterations,
                1,
                10000,
                "Worklist iterations must be finite",
            ));
        }

        // IFDS/IDE validation
        if self.ifds_max_iterations == 0 || self.ifds_max_iterations > 100000 {
            return Err(ConfigError::range_with_hint(
                "ifds_max_iterations",
                self.ifds_max_iterations,
                1,
                100000,
                "IFDS iterations must be finite and reasonable",
            ));
        }

        if self.sparse_min_reduction_ratio < 0.0 || self.sparse_min_reduction_ratio > 1.0 {
            return Err(ConfigError::Validation(format!(
                "sparse_min_reduction_ratio must be between 0.0 and 1.0, got {}",
                self.sparse_min_reduction_ratio
            )));
        }

        // SOTA Extensions validation
        if self.timeout_seconds > 3600 {
            return Err(ConfigError::range_with_hint(
                "timeout_seconds",
                self.timeout_seconds as usize,
                0,
                3600,
                "Analysis timeout should be at most 1 hour (3600 seconds)",
            ));
        }

        // Path-sensitive analysis requires context-sensitive
        if self.path_sensitive && !self.context_sensitive {
            return Err(ConfigError::Validation(
                "path_sensitive analysis requires context_sensitive to be enabled".to_string(),
            ));
        }

        // Implicit flow with IFDS is recommended
        if self.implicit_flow_enabled && !self.ifds_enabled {
            // This is a warning-level issue, not an error - allow but log
            // We could add a warnings vector later
        }

        Ok(())
    }

    /// Builder: Set max_depth
    pub fn max_depth(mut self, v: usize) -> Self {
        self.max_depth = v;
        self
    }

    /// Builder: Set max_paths
    pub fn max_paths(mut self, v: usize) -> Self {
        self.max_paths = v;
        self
    }

    /// Builder: Set use_points_to
    pub fn use_points_to(mut self, v: bool) -> Self {
        self.use_points_to = v;
        self
    }

    /// Builder: Set field_sensitive
    pub fn field_sensitive(mut self, v: bool) -> Self {
        self.field_sensitive = v;
        self
    }

    /// Builder: Set use_ssa
    pub fn use_ssa(mut self, v: bool) -> Self {
        self.use_ssa = v;
        self
    }

    /// Builder: Set detect_sanitizers
    pub fn detect_sanitizers(mut self, v: bool) -> Self {
        self.detect_sanitizers = v;
        self
    }

    /// Builder: Set enable_interprocedural
    pub fn enable_interprocedural(mut self, v: bool) -> Self {
        self.enable_interprocedural = v;
        self
    }

    /// Builder: Set worklist_max_iterations
    pub fn worklist_max_iterations(mut self, v: usize) -> Self {
        self.worklist_max_iterations = v;
        self
    }

    // ========================================
    // IFDS/IDE Builder Methods (2025-01-01)
    // ========================================

    /// Builder: Enable/disable IFDS analysis
    pub fn ifds_enabled(mut self, v: bool) -> Self {
        self.ifds_enabled = v;
        self
    }

    /// Builder: Set IFDS max iterations
    pub fn ifds_max_iterations(mut self, v: usize) -> Self {
        self.ifds_max_iterations = v;
        self
    }

    /// Builder: Enable/disable IFDS summary caching
    pub fn ifds_summary_cache_enabled(mut self, v: bool) -> Self {
        self.ifds_summary_cache_enabled = v;
        self
    }

    /// Builder: Enable/disable IDE analysis
    pub fn ide_enabled(mut self, v: bool) -> Self {
        self.ide_enabled = v;
        self
    }

    /// Builder: Enable/disable IDE micro-function caching
    pub fn ide_micro_cache_enabled(mut self, v: bool) -> Self {
        self.ide_micro_cache_enabled = v;
        self
    }

    /// Builder: Enable/disable IDE jump-function caching
    pub fn ide_jump_cache_enabled(mut self, v: bool) -> Self {
        self.ide_jump_cache_enabled = v;
        self
    }

    /// Builder: Enable/disable Sparse IFDS optimization
    pub fn sparse_ifds_enabled(mut self, v: bool) -> Self {
        self.sparse_ifds_enabled = v;
        self
    }

    /// Builder: Set Sparse IFDS minimum reduction ratio
    pub fn sparse_min_reduction_ratio(mut self, v: f64) -> Self {
        self.sparse_min_reduction_ratio = v;
        self
    }

    // ========================================
    // SOTA Builder Methods (2025-01-01)
    // ========================================

    /// Builder: Enable/disable implicit flow analysis
    pub fn implicit_flow_enabled(mut self, v: bool) -> Self {
        self.implicit_flow_enabled = v;
        self
    }

    /// Builder: Enable/disable backward taint analysis
    pub fn backward_analysis_enabled(mut self, v: bool) -> Self {
        self.backward_analysis_enabled = v;
        self
    }

    /// Builder: Enable/disable context-sensitive analysis
    pub fn context_sensitive(mut self, v: bool) -> Self {
        self.context_sensitive = v;
        self
    }

    /// Builder: Enable/disable path-sensitive analysis
    pub fn path_sensitive(mut self, v: bool) -> Self {
        self.path_sensitive = v;
        self
    }

    /// Builder: Set analysis timeout in seconds
    pub fn timeout_seconds(mut self, v: u64) -> Self {
        self.timeout_seconds = v;
        self
    }

    /// Get preset configuration
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                max_depth: 10,
                max_paths: 100,
                use_points_to: false, // Skip for speed
                field_sensitive: false,
                use_ssa: false,
                detect_sanitizers: false,
                enable_interprocedural: false,
                worklist_max_iterations: 100,
                // IFDS/IDE: Disabled for speed
                ifds_enabled: false,
                ifds_max_iterations: 100,
                ifds_summary_cache_enabled: false,
                ide_enabled: false,
                ide_micro_cache_enabled: false,
                ide_jump_cache_enabled: false,
                sparse_ifds_enabled: false,
                sparse_min_reduction_ratio: 0.5,
                // SOTA: Disabled for speed
                implicit_flow_enabled: false,
                backward_analysis_enabled: false,
                context_sensitive: false,
                path_sensitive: false,
                timeout_seconds: 5,
            },
            Preset::Balanced => Self {
                max_depth: 30,
                max_paths: 500,
                use_points_to: true,
                field_sensitive: true,
                use_ssa: true,
                detect_sanitizers: true,
                enable_interprocedural: true,
                worklist_max_iterations: 1000,
                // IFDS/IDE: Enabled with caching
                ifds_enabled: true,
                ifds_max_iterations: 5000,
                ifds_summary_cache_enabled: true,
                ide_enabled: true,
                ide_micro_cache_enabled: true,
                ide_jump_cache_enabled: true,
                sparse_ifds_enabled: false, // Not by default
                sparse_min_reduction_ratio: 0.3,
                // SOTA: Partial (implicit flow is expensive)
                implicit_flow_enabled: false,
                backward_analysis_enabled: true,
                context_sensitive: true,
                path_sensitive: false,
                timeout_seconds: 60,
            },
            Preset::Thorough => Self {
                max_depth: 100,
                max_paths: 5000,
                use_points_to: true,
                field_sensitive: true,
                use_ssa: true,
                detect_sanitizers: true,
                enable_interprocedural: true,
                worklist_max_iterations: 10000,
                // IFDS/IDE: Full precision with Sparse optimization
                ifds_enabled: true,
                ifds_max_iterations: 50000,
                ifds_summary_cache_enabled: true,
                ide_enabled: true,
                ide_micro_cache_enabled: true,
                ide_jump_cache_enabled: true,
                sparse_ifds_enabled: true, // Enable for large codebases
                sparse_min_reduction_ratio: 0.2,
                // SOTA: Full precision
                implicit_flow_enabled: true,
                backward_analysis_enabled: true,
                context_sensitive: true,
                path_sensitive: true,
                timeout_seconds: 300, // 5 minutes for full analysis
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for TaintConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// L6: Points-to Analysis Configuration
// ============================================================================

/// PTA algorithm mode
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PTAMode {
    /// Fast: Steensgaard only (unification-based)
    Fast,
    /// Precise: Andersen always (inclusion-based)
    Precise,
    /// Hybrid: Start with Steensgaard, refine with Andersen for hot paths
    Hybrid,
    /// Auto: Choose based on code size
    Auto,
}

/// L6: Points-to Analysis Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct PTAConfig {
    /// Algorithm selection
    pub mode: PTAMode,

    /// Enable field-sensitive analysis
    pub field_sensitive: bool,

    /// Max iterations for Andersen (None=unlimited)
    pub max_iterations: Option<usize>,

    /// Auto mode threshold: use Precise below this
    pub auto_threshold: usize,

    /// Enable SCC optimization
    pub enable_scc: bool,

    /// Enable wave propagation
    pub enable_wave: bool,

    /// Enable parallel processing
    pub enable_parallel: bool,
}

impl PTAConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if let Some(n) = self.max_iterations {
            if n == 0 || n > 10000 {
                return Err(ConfigError::Validation(
                    "max_iterations must be 1..=10000 or None for unlimited".to_string(),
                ));
            }
        }

        if self.auto_threshold < 100 || self.auto_threshold > 1000000 {
            return Err(ConfigError::range_with_hint(
                "auto_threshold",
                self.auto_threshold,
                100,
                1000000,
                "Auto threshold must be reasonable",
            ));
        }

        Ok(())
    }

    /// Builder: Set mode
    pub fn mode(mut self, v: PTAMode) -> Self {
        self.mode = v;
        self
    }

    /// Builder: Set field_sensitive
    pub fn field_sensitive(mut self, v: bool) -> Self {
        self.field_sensitive = v;
        self
    }

    /// Builder: Set max_iterations
    pub fn max_iterations(mut self, v: Option<usize>) -> Self {
        self.max_iterations = v;
        self
    }

    /// Builder: Set auto_threshold
    pub fn auto_threshold(mut self, v: usize) -> Self {
        self.auto_threshold = v;
        self
    }

    /// Builder: Set enable_scc
    pub fn enable_scc(mut self, v: bool) -> Self {
        self.enable_scc = v;
        self
    }

    /// Builder: Set enable_wave
    pub fn enable_wave(mut self, v: bool) -> Self {
        self.enable_wave = v;
        self
    }

    /// Builder: Set enable_parallel
    pub fn enable_parallel(mut self, v: bool) -> Self {
        self.enable_parallel = v;
        self
    }

    /// Get preset configuration
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                mode: PTAMode::Fast, // Steensgaard only
                field_sensitive: false,
                max_iterations: Some(5),
                auto_threshold: 5000,
                enable_scc: false,
                enable_wave: false,
                enable_parallel: true,
            },
            Preset::Balanced => Self {
                mode: PTAMode::Auto,
                field_sensitive: true,
                max_iterations: Some(10),
                auto_threshold: 10000,
                enable_scc: true,
                enable_wave: true,
                enable_parallel: true,
            },
            Preset::Thorough => Self {
                mode: PTAMode::Precise, // Andersen always
                field_sensitive: true,
                max_iterations: Some(50),
                auto_threshold: 100000,
                enable_scc: true,
                enable_wave: true,
                enable_parallel: true,
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for PTAConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// L10: Clone Detection Configuration
// ============================================================================

/// Clone detection type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CloneType {
    /// Type-1: Exact clones (character-for-character)
    Type1,
    /// Type-2: Renamed clones (identifier renaming)
    Type2,
    /// Type-3: Gapped clones (statement insertion/deletion)
    Type3,
    /// Type-4: Semantic clones (functionally similar)
    Type4,
}

/// Type-1: Exact clones
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Type1Config {
    pub min_tokens: usize,
    pub min_loc: usize,
}

impl Type1Config {
    pub fn validate(&self) -> ConfigResult<()> {
        if self.min_tokens < 5 || self.min_tokens > 1000 {
            return Err(ConfigError::range_with_hint(
                "type1.min_tokens",
                self.min_tokens,
                5,
                1000,
                "Minimum tokens must be reasonable",
            ));
        }
        if self.min_loc < 1 || self.min_loc > 100 {
            return Err(ConfigError::range_with_hint(
                "type1.min_loc",
                self.min_loc,
                1,
                100,
                "Minimum lines of code must be reasonable",
            ));
        }
        Ok(())
    }
}

/// Type-2: Renamed clones
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Type2Config {
    pub min_tokens: usize,
    pub min_loc: usize,
    /// Token sequence similarity (0.5..=1.0)
    pub rename_similarity: f64,
}

impl Type2Config {
    pub fn validate(&self) -> ConfigResult<()> {
        if self.min_tokens < 5 || self.min_tokens > 1000 {
            return Err(ConfigError::range_with_hint(
                "type2.min_tokens",
                self.min_tokens,
                5,
                1000,
                "Minimum tokens must be reasonable",
            ));
        }
        if self.min_loc < 1 || self.min_loc > 100 {
            return Err(ConfigError::range_with_hint(
                "type2.min_loc",
                self.min_loc,
                1,
                100,
                "Minimum lines of code must be reasonable",
            ));
        }
        if self.rename_similarity < 0.5 || self.rename_similarity > 1.0 {
            return Err(ConfigError::range_with_hint(
                "type2.rename_similarity",
                self.rename_similarity,
                0.5,
                1.0,
                "Rename similarity must be between 0.5 and 1.0",
            ));
        }
        Ok(())
    }
}

/// Type-3: Gapped clones
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Type3Config {
    pub min_tokens: usize,
    pub min_loc: usize,
    /// Maximum gap ratio (0.0..=0.5)
    pub gap_threshold: f64,
    /// Overall similarity after gaps (0.5..=1.0)
    pub similarity: f64,
}

impl Type3Config {
    pub fn validate(&self) -> ConfigResult<()> {
        if self.min_tokens < 5 || self.min_tokens > 1000 {
            return Err(ConfigError::range_with_hint(
                "type3.min_tokens",
                self.min_tokens,
                5,
                1000,
                "Minimum tokens must be reasonable",
            ));
        }
        if self.min_loc < 1 || self.min_loc > 100 {
            return Err(ConfigError::range_with_hint(
                "type3.min_loc",
                self.min_loc,
                1,
                100,
                "Minimum lines of code must be reasonable",
            ));
        }
        if self.gap_threshold < 0.0 || self.gap_threshold > 0.5 {
            return Err(ConfigError::range_with_hint(
                "type3.gap_threshold",
                self.gap_threshold,
                0.0,
                0.5,
                "Gap threshold must be between 0.0 and 0.5",
            ));
        }
        if self.similarity < 0.5 || self.similarity > 1.0 {
            return Err(ConfigError::range_with_hint(
                "type3.similarity",
                self.similarity,
                0.5,
                1.0,
                "Similarity must be between 0.5 and 1.0",
            ));
        }
        Ok(())
    }
}

/// Type-4: Semantic clones
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Type4Config {
    pub min_tokens: usize,
    pub min_loc: usize,
    /// PDG (Program Dependence Graph) similarity (0.3..=1.0)
    pub semantic_threshold: f64,
}

impl Type4Config {
    pub fn validate(&self) -> ConfigResult<()> {
        if self.min_tokens < 5 || self.min_tokens > 1000 {
            return Err(ConfigError::range_with_hint(
                "type4.min_tokens",
                self.min_tokens,
                5,
                1000,
                "Minimum tokens must be reasonable",
            ));
        }
        if self.min_loc < 1 || self.min_loc > 100 {
            return Err(ConfigError::range_with_hint(
                "type4.min_loc",
                self.min_loc,
                1,
                100,
                "Minimum lines of code must be reasonable",
            ));
        }
        if self.semantic_threshold < 0.3 || self.semantic_threshold > 1.0 {
            return Err(ConfigError::range_with_hint(
                "type4.semantic_threshold",
                self.semantic_threshold,
                0.3,
                1.0,
                "Semantic threshold must be between 0.3 and 1.0",
            ));
        }
        Ok(())
    }
}

/// L10: Clone Detection Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct CloneConfig {
    /// Enabled clone types
    pub types_enabled: Vec<CloneType>,

    /// Type-1 configuration
    pub type1: Type1Config,

    /// Type-2 configuration
    pub type2: Type2Config,

    /// Type-3 configuration
    pub type3: Type3Config,

    /// Type-4 configuration
    pub type4: Type4Config,
}

impl CloneConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        self.type1.validate()?;
        self.type2.validate()?;
        self.type3.validate()?;
        self.type4.validate()?;
        Ok(())
    }

    /// Get preset configuration
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                types_enabled: vec![CloneType::Type1], // Exact only
                type1: Type1Config {
                    min_tokens: 50,
                    min_loc: 5,
                },
                type2: Type2Config {
                    min_tokens: 50,
                    min_loc: 5,
                    rename_similarity: 0.8,
                },
                type3: Type3Config {
                    min_tokens: 30,
                    min_loc: 3,
                    gap_threshold: 0.3,
                    similarity: 0.6,
                },
                type4: Type4Config {
                    min_tokens: 20,
                    min_loc: 2,
                    semantic_threshold: 0.7,
                },
            },
            Preset::Balanced => Self {
                types_enabled: vec![CloneType::Type1, CloneType::Type2],
                type1: Type1Config {
                    min_tokens: 30,
                    min_loc: 3,
                },
                type2: Type2Config {
                    min_tokens: 30,
                    min_loc: 3,
                    rename_similarity: 0.8,
                },
                type3: Type3Config {
                    min_tokens: 20,
                    min_loc: 2,
                    gap_threshold: 0.3,
                    similarity: 0.6,
                },
                type4: Type4Config {
                    min_tokens: 15,
                    min_loc: 2,
                    semantic_threshold: 0.6,
                },
            },
            Preset::Thorough => Self {
                types_enabled: vec![
                    CloneType::Type1,
                    CloneType::Type2,
                    CloneType::Type3,
                    CloneType::Type4,
                ],
                type1: Type1Config {
                    min_tokens: 20,
                    min_loc: 2,
                },
                type2: Type2Config {
                    min_tokens: 20,
                    min_loc: 2,
                    rename_similarity: 0.8,
                },
                type3: Type3Config {
                    min_tokens: 15,
                    min_loc: 2,
                    gap_threshold: 0.3,
                    similarity: 0.6,
                },
                type4: Type4Config {
                    min_tokens: 10,
                    min_loc: 1,
                    semantic_threshold: 0.5,
                },
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for CloneConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// L2: Chunking Configuration
// ============================================================================

/// L2: Chunking Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct ChunkingConfig {
    /// Maximum chunk size in characters (100..=10000)
    pub max_chunk_size: usize,

    /// Minimum chunk size (50..=5000)
    pub min_chunk_size: usize,

    /// Overlap lines between chunks (0..=10)
    pub overlap_lines: usize,

    /// Enable semantic-aware chunking
    pub enable_semantic: bool,

    /// Respect scope boundaries
    pub respect_scope: bool,
}

impl ChunkingConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if self.max_chunk_size < 100 || self.max_chunk_size > 10000 {
            return Err(ConfigError::range_with_hint(
                "max_chunk_size",
                self.max_chunk_size,
                100,
                10000,
                "Chunk size must be reasonable",
            ));
        }

        if self.min_chunk_size < 50 || self.min_chunk_size > 5000 {
            return Err(ConfigError::range_with_hint(
                "min_chunk_size",
                self.min_chunk_size,
                50,
                5000,
                "Minimum chunk size must be reasonable",
            ));
        }

        if self.min_chunk_size >= self.max_chunk_size {
            return Err(ConfigError::Validation(
                "min_chunk_size must be less than max_chunk_size".to_string(),
            ));
        }

        if self.overlap_lines > 10 {
            return Err(ConfigError::range_with_hint(
                "overlap_lines",
                self.overlap_lines,
                0,
                10,
                "Overlap must be reasonable",
            ));
        }

        Ok(())
    }

    /// Get preset configuration
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                max_chunk_size: 2000,
                min_chunk_size: 200,
                overlap_lines: 0,
                enable_semantic: false,
                respect_scope: false,
            },
            Preset::Balanced => Self {
                max_chunk_size: 1000,
                min_chunk_size: 100,
                overlap_lines: 3,
                enable_semantic: true,
                respect_scope: true,
            },
            Preset::Thorough => Self {
                max_chunk_size: 500,
                min_chunk_size: 100,
                overlap_lines: 5,
                enable_semantic: true,
                respect_scope: true,
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for ChunkingConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// Lexical/Search Configuration
// ============================================================================

/// Lexical/Search Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct LexicalConfig {
    /// Enable fuzzy search
    pub enable_fuzzy: bool,

    /// Fuzzy edit distance (1..=5)
    pub fuzzy_distance: usize,

    /// Maximum search results (1..=10000)
    pub max_results: usize,

    /// Enable n-gram indexing
    pub enable_ngram: bool,

    /// N-gram size (2..=5)
    pub ngram_size: usize,

    /// Enable stemming
    pub enable_stemming: bool,
}

impl LexicalConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if self.fuzzy_distance < 1 || self.fuzzy_distance > 5 {
            return Err(ConfigError::range_with_hint(
                "fuzzy_distance",
                self.fuzzy_distance,
                1,
                5,
                "Fuzzy distance must be reasonable",
            ));
        }

        if self.max_results < 1 || self.max_results > 10000 {
            return Err(ConfigError::range_with_hint(
                "max_results",
                self.max_results,
                1,
                10000,
                "Max results must be reasonable",
            ));
        }

        if self.ngram_size < 2 || self.ngram_size > 5 {
            return Err(ConfigError::range_with_hint(
                "ngram_size",
                self.ngram_size,
                2,
                5,
                "N-gram size must be reasonable",
            ));
        }

        Ok(())
    }

    /// Get preset configuration
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                enable_fuzzy: false,
                fuzzy_distance: 1,
                max_results: 100,
                enable_ngram: false,
                ngram_size: 3,
                enable_stemming: false,
            },
            Preset::Balanced => Self {
                enable_fuzzy: true,
                fuzzy_distance: 2,
                max_results: 100,
                enable_ngram: true,
                ngram_size: 3,
                enable_stemming: false,
            },
            Preset::Thorough => Self {
                enable_fuzzy: true,
                fuzzy_distance: 3,
                max_results: 1000,
                enable_ngram: true,
                ngram_size: 3,
                enable_stemming: true,
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for LexicalConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// Parallelism Configuration
// ============================================================================

/// Parallelism Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct ParallelConfig {
    /// Number of workers (0=auto, 1..=256)
    pub num_workers: usize,

    /// Batch size for parallel processing (1..=10000)
    pub batch_size: usize,

    /// Enable Rayon parallel iterator
    pub enable_rayon: bool,

    /// Thread stack size in MB (1..=64)
    pub stack_size_mb: usize,
}

impl ParallelConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if self.num_workers > 256 {
            return Err(ConfigError::range_with_hint(
                "num_workers",
                self.num_workers,
                0,
                256,
                "Number of workers must be reasonable (0=auto)",
            ));
        }

        if self.batch_size < 1 || self.batch_size > 10000 {
            return Err(ConfigError::range_with_hint(
                "batch_size",
                self.batch_size,
                1,
                10000,
                "Batch size must be reasonable",
            ));
        }

        if self.stack_size_mb < 1 || self.stack_size_mb > 64 {
            return Err(ConfigError::range_with_hint(
                "stack_size_mb",
                self.stack_size_mb,
                1,
                64,
                "Stack size must be reasonable",
            ));
        }

        Ok(())
    }

    /// Get preset configuration
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                num_workers: 0, // Auto
                batch_size: 100,
                enable_rayon: true,
                stack_size_mb: 8,
            },
            Preset::Balanced => Self {
                num_workers: 0, // Auto
                batch_size: 100,
                enable_rayon: true,
                stack_size_mb: 8,
            },
            Preset::Thorough => Self {
                num_workers: 0, // Auto
                batch_size: 50,
                enable_rayon: true,
                stack_size_mb: 16,
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for ParallelConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// L17: PDG (Program Dependence Graph) Configuration
// ============================================================================

/// L17: PDG Configuration
///
/// Controls Program Dependence Graph construction and slicing behavior.
///
/// Reference: Ferrante et al., "The Program Dependence Graph", TOPLAS 1987
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct PDGConfig {
    /// Enable PDG construction (default: true)
    pub enabled: bool,

    /// Include control dependencies (default: true)
    pub include_control: bool,

    /// Include data dependencies (default: true)
    pub include_data: bool,

    /// Maximum PDG nodes per function (1..=100000)
    pub max_nodes: usize,
}

impl PDGConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if self.max_nodes == 0 || self.max_nodes > 100000 {
            return Err(ConfigError::range_with_hint(
                "max_nodes",
                self.max_nodes,
                1,
                100000,
                "PDG node limit must be reasonable",
            ));
        }
        Ok(())
    }

    /// Builder: Set enabled
    pub fn enabled(mut self, v: bool) -> Self {
        self.enabled = v;
        self
    }

    /// Builder: Set include_control
    pub fn include_control(mut self, v: bool) -> Self {
        self.include_control = v;
        self
    }

    /// Builder: Set include_data
    pub fn include_data(mut self, v: bool) -> Self {
        self.include_data = v;
        self
    }

    /// Builder: Set max_nodes
    pub fn max_nodes(mut self, v: usize) -> Self {
        self.max_nodes = v;
        self
    }

    /// Create from preset
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                enabled: false,
                include_control: true,
                include_data: true,
                max_nodes: 1000,
            },
            Preset::Balanced => Self {
                enabled: true,
                include_control: true,
                include_data: true,
                max_nodes: 10000,
            },
            Preset::Thorough => Self {
                enabled: true,
                include_control: true,
                include_data: true,
                max_nodes: 100000,
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for PDGConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// L18: Slicing Configuration
// ============================================================================

/// L18: Slicing Configuration
///
/// Controls program slicing behavior (backward, forward, thin, chop).
///
/// References:
/// - Weiser, "Program Slicing", TSE 1984
/// - Sridharan et al., "Thin Slicing", PLDI 2007
/// - Jackson & Rollins, "Chopping", FSE 1994
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct SlicingConfig {
    /// Enable slicing (default: true when PDG enabled)
    pub enabled: bool,

    /// Maximum slice traversal depth (1..=1000)
    pub max_depth: usize,

    /// Maximum interprocedural depth (1..=100)
    pub max_function_depth: usize,

    /// Include control dependencies (false = Thin Slicing)
    pub include_control: bool,

    /// Include data dependencies
    pub include_data: bool,

    /// Enable interprocedural slicing
    pub interprocedural: bool,

    /// Strict mode: error on missing nodes
    pub strict_mode: bool,

    /// LRU cache capacity (0 = disabled)
    pub cache_capacity: usize,
}

impl SlicingConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if self.max_depth == 0 || self.max_depth > 1000 {
            return Err(ConfigError::range_with_hint(
                "max_depth",
                self.max_depth,
                1,
                1000,
                "Slice depth must be reasonable",
            ));
        }

        if self.max_function_depth == 0 || self.max_function_depth > 100 {
            return Err(ConfigError::range_with_hint(
                "max_function_depth",
                self.max_function_depth,
                1,
                100,
                "Interprocedural depth must be reasonable",
            ));
        }

        Ok(())
    }

    /// Builder: Set enabled
    pub fn enabled(mut self, v: bool) -> Self {
        self.enabled = v;
        self
    }

    /// Builder: Set max_depth
    pub fn max_depth(mut self, v: usize) -> Self {
        self.max_depth = v;
        self
    }

    /// Builder: Set max_function_depth
    pub fn max_function_depth(mut self, v: usize) -> Self {
        self.max_function_depth = v;
        self
    }

    /// Builder: Set include_control (false = Thin Slicing)
    pub fn include_control(mut self, v: bool) -> Self {
        self.include_control = v;
        self
    }

    /// Builder: Set include_data
    pub fn include_data(mut self, v: bool) -> Self {
        self.include_data = v;
        self
    }

    /// Builder: Set interprocedural
    pub fn interprocedural(mut self, v: bool) -> Self {
        self.interprocedural = v;
        self
    }

    /// Builder: Set strict_mode
    pub fn strict_mode(mut self, v: bool) -> Self {
        self.strict_mode = v;
        self
    }

    /// Builder: Set cache_capacity
    pub fn cache_capacity(mut self, v: usize) -> Self {
        self.cache_capacity = v;
        self
    }

    /// Create Thin Slicing config (data dependencies only)
    ///
    /// Reference: Sridharan et al., "Thin Slicing", PLDI 2007
    pub fn thin_slicing() -> Self {
        Self {
            enabled: true,
            include_control: false, // Key: no control deps
            include_data: true,
            ..Self::default()
        }
    }

    /// Create from preset
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                enabled: false,
                max_depth: 20,
                max_function_depth: 1,
                include_control: true,
                include_data: true,
                interprocedural: false,
                strict_mode: false,
                cache_capacity: 100,
            },
            Preset::Balanced => Self {
                enabled: true,
                max_depth: 50,
                max_function_depth: 3,
                include_control: true,
                include_data: true,
                interprocedural: true,
                strict_mode: false,
                cache_capacity: 1000,
            },
            Preset::Thorough => Self {
                enabled: true,
                max_depth: 200,
                max_function_depth: 10,
                include_control: true,
                include_data: true,
                interprocedural: true,
                strict_mode: true,
                cache_capacity: 10000,
            },
            Preset::Custom => Self::default(),
        }
    }
}

impl Default for SlicingConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ============================================================================
// L7: Heap Analysis Configuration
// ============================================================================

/// L7: Heap Analysis Configuration
///
/// Controls heap-based memory safety and security analysis.
///
/// Features:
/// - Memory Safety: Null dereference, UAF, double-free, buffer overflow
/// - **Spatial Memory Safety**: Out-of-bounds pointer arithmetic, type mismatch, sub-object bounds
/// - Ownership Tracking: Rust-style use-after-move, borrow conflicts
/// - Escape Analysis: Object escape behavior (RFC-074)
/// - Security: OWASP Top 10 detection
///
/// References:
/// - Reynolds (2002): "Separation Logic"
/// - Nagarakatte et al. (2009): "SoftBound: Spatial Memory Safety for C"
/// - Weiss et al. (2019): "Oxide: The Essence of Rust"
/// - Choi et al. (1999): "Escape Analysis for Java"
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct HeapConfig {
    /// Enable heap analysis (default: true when PTA enabled)
    pub enabled: bool,

    /// Enable memory safety analysis
    /// Includes: null dereference, UAF, double-free, buffer overflow, spatial memory safety
    /// Spatial: out-of-bounds pointer arithmetic, type mismatch, sub-object bounds
    pub enable_memory_safety: bool,

    /// Enable ownership tracking (use-after-move, borrow conflicts)
    pub enable_ownership: bool,

    /// Enable escape analysis (RFC-074)
    pub enable_escape: bool,

    /// Enable security analysis (OWASP Top 10)
    pub enable_security: bool,

    /// Enable context-sensitive heap analysis (k-CFA)
    pub enable_context_sensitive: bool,

    /// Context sensitivity level (0=insensitive, 1=1-CFA, 2=2-CFA)
    pub context_sensitivity: usize,

    /// Ownership tracking: strict mode (error on moved variables)
    pub ownership_strict_mode: bool,

    /// Maximum heap objects to track (1..=1000000)
    pub max_heap_objects: usize,

    /// Types treated as Copy (space-separated list)
    pub copy_types: Vec<String>,

    /// Types treated as Move (space-separated list)
    pub move_types: Vec<String>,

    // ========================================
    // SOTA Extensions (2025-01-01)
    // ========================================
    /// Enable KLEE-style symbolic memory model
    /// Provides precise heap tracking with path conditions
    #[serde(default)]
    pub enable_symbolic_memory: bool,

    /// Maximum symbolic memory objects (1..=100000)
    #[serde(default = "default_max_symbolic_objects")]
    pub max_symbolic_objects: usize,

    /// Enable path-conditioned state merging
    /// Merges states from different paths with conditional values
    #[serde(default)]
    pub enable_path_merge: bool,

    /// Enable concolic testing (KLEE-style)
    /// Combines concrete + symbolic execution for test generation
    #[serde(default)]
    pub enable_concolic: bool,

    /// Concolic testing maximum exploration depth (1..=1000)
    #[serde(default = "default_concolic_max_depth")]
    pub concolic_max_depth: usize,

    /// Concolic testing search strategy: "dfs", "bfs", "random", "coverage"
    #[serde(default = "default_concolic_strategy")]
    pub concolic_strategy: String,

    /// Enable separation logic entailment checking
    /// Verifies H₁ ⊢ H₂ for heap formulas
    #[serde(default)]
    pub enable_separation_logic: bool,

    /// Enable bi-abduction for compositional verification
    /// Infers frame and anti-frame: H₁ * ?A ⊢ H₂ * ?F
    #[serde(default)]
    pub enable_bi_abduction: bool,
}

impl HeapConfig {
    /// Validate configuration
    pub fn validate(&self) -> ConfigResult<()> {
        if self.context_sensitivity > 3 {
            return Err(ConfigError::range_with_hint(
                "context_sensitivity",
                self.context_sensitivity,
                0,
                3,
                "Context sensitivity must be 0-3 (higher values expensive)",
            ));
        }

        if self.max_heap_objects == 0 || self.max_heap_objects > 1000000 {
            return Err(ConfigError::range_with_hint(
                "max_heap_objects",
                self.max_heap_objects,
                1,
                1000000,
                "Heap object limit must be reasonable",
            ));
        }

        // SOTA: Symbolic memory validation
        if self.max_symbolic_objects == 0 || self.max_symbolic_objects > 100000 {
            return Err(ConfigError::range_with_hint(
                "max_symbolic_objects",
                self.max_symbolic_objects,
                1,
                100000,
                "Symbolic object limit must be 1-100000",
            ));
        }

        // SOTA: Concolic testing validation
        if self.concolic_max_depth == 0 || self.concolic_max_depth > 1000 {
            return Err(ConfigError::range_with_hint(
                "concolic_max_depth",
                self.concolic_max_depth,
                1,
                1000,
                "Concolic depth must be 1-1000",
            ));
        }

        let valid_strategies = ["dfs", "bfs", "random", "coverage"];
        if !valid_strategies.contains(&self.concolic_strategy.as_str()) {
            return Err(ConfigError::Validation(format!(
                "Invalid concolic_strategy '{}'. Valid: {:?}",
                self.concolic_strategy, valid_strategies
            )));
        }

        Ok(())
    }

    /// Builder: Set enabled
    pub fn enabled(mut self, v: bool) -> Self {
        self.enabled = v;
        self
    }

    /// Builder: Set enable_memory_safety
    pub fn enable_memory_safety(mut self, v: bool) -> Self {
        self.enable_memory_safety = v;
        self
    }

    /// Builder: Set enable_ownership
    pub fn enable_ownership(mut self, v: bool) -> Self {
        self.enable_ownership = v;
        self
    }

    /// Builder: Set enable_escape
    pub fn enable_escape(mut self, v: bool) -> Self {
        self.enable_escape = v;
        self
    }

    /// Builder: Set enable_security
    pub fn enable_security(mut self, v: bool) -> Self {
        self.enable_security = v;
        self
    }

    /// Builder: Set enable_context_sensitive
    pub fn enable_context_sensitive(mut self, v: bool) -> Self {
        self.enable_context_sensitive = v;
        self
    }

    /// Builder: Set context_sensitivity
    pub fn context_sensitivity(mut self, v: usize) -> Self {
        self.context_sensitivity = v;
        self
    }

    /// Builder: Set ownership_strict_mode
    pub fn ownership_strict_mode(mut self, v: bool) -> Self {
        self.ownership_strict_mode = v;
        self
    }

    /// Builder: Set max_heap_objects
    pub fn max_heap_objects(mut self, v: usize) -> Self {
        self.max_heap_objects = v;
        self
    }

    /// Builder: Add copy type
    pub fn add_copy_type(mut self, type_name: impl Into<String>) -> Self {
        self.copy_types.push(type_name.into());
        self
    }

    /// Builder: Add move type
    pub fn add_move_type(mut self, type_name: impl Into<String>) -> Self {
        self.move_types.push(type_name.into());
        self
    }

    /// Create from preset
    pub fn from_preset(preset: Preset) -> Self {
        match preset {
            Preset::Fast => Self {
                enabled: false,
                enable_memory_safety: false,
                enable_ownership: false,
                enable_escape: false,
                enable_security: false,
                enable_context_sensitive: false,
                context_sensitivity: 0,
                ownership_strict_mode: false,
                max_heap_objects: 10000,
                copy_types: vec!["int".to_string(), "float".to_string(), "bool".to_string()],
                move_types: vec!["Vec".to_string(), "String".to_string(), "list".to_string()],
                // SOTA: All disabled for speed
                enable_symbolic_memory: false,
                max_symbolic_objects: 1000,
                enable_path_merge: false,
                enable_concolic: false,
                concolic_max_depth: 10,
                concolic_strategy: "dfs".to_string(),
                enable_separation_logic: false,
                enable_bi_abduction: false,
            },
            Preset::Balanced => Self {
                enabled: true,
                enable_memory_safety: true,
                enable_ownership: true,
                enable_escape: true,
                enable_security: true,
                enable_context_sensitive: false,
                context_sensitivity: 0,
                ownership_strict_mode: false,
                max_heap_objects: 100000,
                copy_types: vec![
                    "int".to_string(),
                    "float".to_string(),
                    "bool".to_string(),
                    "char".to_string(),
                    "str".to_string(),
                ],
                move_types: vec![
                    "Vec".to_string(),
                    "String".to_string(),
                    "Box".to_string(),
                    "list".to_string(),
                    "dict".to_string(),
                ],
                // SOTA: Symbolic memory + Concolic enabled (depth 50 is fast enough)
                enable_symbolic_memory: true,
                max_symbolic_objects: 10000,
                enable_path_merge: true,
                enable_concolic: true,
                concolic_max_depth: 50,
                concolic_strategy: "dfs".to_string(),
                enable_separation_logic: false,
                enable_bi_abduction: false,
            },
            Preset::Thorough => Self {
                enabled: true,
                enable_memory_safety: true,
                enable_ownership: true,
                enable_escape: true,
                enable_security: true,
                enable_context_sensitive: true,
                context_sensitivity: 2,
                ownership_strict_mode: true,
                max_heap_objects: 1000000,
                copy_types: vec![
                    "int".to_string(),
                    "float".to_string(),
                    "bool".to_string(),
                    "char".to_string(),
                    "str".to_string(),
                    "i32".to_string(),
                    "i64".to_string(),
                    "f32".to_string(),
                    "f64".to_string(),
                    "usize".to_string(),
                ],
                move_types: vec![
                    "Vec".to_string(),
                    "String".to_string(),
                    "Box".to_string(),
                    "list".to_string(),
                    "dict".to_string(),
                    "File".to_string(),
                    "Connection".to_string(),
                    "Resource".to_string(),
                ],
                // SOTA: Full KLEE-style analysis
                enable_symbolic_memory: true,
                max_symbolic_objects: 100000,
                enable_path_merge: true,
                enable_concolic: true,
                concolic_max_depth: 100,
                concolic_strategy: "coverage".to_string(),
                enable_separation_logic: true,
                enable_bi_abduction: true,
            },
            Preset::Custom => Self {
                enabled: true,
                enable_memory_safety: true,
                enable_ownership: true,
                enable_escape: true,
                enable_security: true,
                enable_context_sensitive: false,
                context_sensitivity: 0,
                ownership_strict_mode: false,
                max_heap_objects: 100000,
                copy_types: vec![],
                move_types: vec![],
                // SOTA defaults
                enable_symbolic_memory: false,
                max_symbolic_objects: default_max_symbolic_objects(),
                enable_path_merge: false,
                enable_concolic: false,
                concolic_max_depth: default_concolic_max_depth(),
                concolic_strategy: default_concolic_strategy(),
                enable_separation_logic: false,
                enable_bi_abduction: false,
            },
        }
    }
}

impl Default for HeapConfig {
    fn default() -> Self {
        Self::from_preset(Preset::Balanced)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Validatable Trait Implementations (DIP - Dependency Inversion Principle)
// ═══════════════════════════════════════════════════════════════════════════

impl Validatable for TaintConfig {
    fn validate(&self) -> ConfigResult<()> {
        TaintConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "TaintConfig"
    }
}

impl Validatable for PTAConfig {
    fn validate(&self) -> ConfigResult<()> {
        PTAConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "PTAConfig"
    }
}

impl Validatable for CloneConfig {
    fn validate(&self) -> ConfigResult<()> {
        CloneConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "CloneConfig"
    }
}

impl Validatable for ChunkingConfig {
    fn validate(&self) -> ConfigResult<()> {
        ChunkingConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "ChunkingConfig"
    }
}

impl Validatable for LexicalConfig {
    fn validate(&self) -> ConfigResult<()> {
        LexicalConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "LexicalConfig"
    }
}

impl Validatable for ParallelConfig {
    fn validate(&self) -> ConfigResult<()> {
        ParallelConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "ParallelConfig"
    }
}

impl Validatable for PDGConfig {
    fn validate(&self) -> ConfigResult<()> {
        PDGConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "PDGConfig"
    }
}

impl Validatable for SlicingConfig {
    fn validate(&self) -> ConfigResult<()> {
        SlicingConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "SlicingConfig"
    }
}

impl Validatable for HeapConfig {
    fn validate(&self) -> ConfigResult<()> {
        HeapConfig::validate(self)
    }

    fn config_name(&self) -> &'static str {
        "HeapConfig"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ==================== HeapConfig Tests ====================

    #[test]
    fn test_heap_config_validation() {
        let config = HeapConfig::from_preset(Preset::Balanced);
        assert!(config.validate().is_ok());

        let mut config = HeapConfig::from_preset(Preset::Fast);
        config.context_sensitivity = 5;
        assert!(config.validate().is_err());

        config.context_sensitivity = 2;
        config.max_heap_objects = 0;
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_heap_config_presets() {
        // Fast: disabled
        let fast = HeapConfig::from_preset(Preset::Fast);
        assert!(!fast.enabled);
        assert!(!fast.enable_memory_safety);
        assert!(!fast.enable_ownership);

        // Balanced: enabled with basic features
        let balanced = HeapConfig::from_preset(Preset::Balanced);
        assert!(balanced.enabled);
        assert!(balanced.enable_memory_safety);
        assert!(balanced.enable_ownership);
        assert!(balanced.enable_escape);
        assert!(balanced.enable_security);
        assert!(!balanced.enable_context_sensitive);

        // Thorough: all features
        let thorough = HeapConfig::from_preset(Preset::Thorough);
        assert!(thorough.enabled);
        assert!(thorough.enable_context_sensitive);
        assert_eq!(thorough.context_sensitivity, 2);
        assert!(thorough.ownership_strict_mode);
    }

    #[test]
    fn test_heap_config_builder() {
        let config = HeapConfig::from_preset(Preset::Balanced)
            .enabled(true)
            .enable_ownership(true)
            .ownership_strict_mode(true)
            .context_sensitivity(1)
            .add_copy_type("MyPrimitive")
            .add_move_type("MyResource");

        assert!(config.enabled);
        assert!(config.enable_ownership);
        assert!(config.ownership_strict_mode);
        assert_eq!(config.context_sensitivity, 1);
        assert!(config.copy_types.contains(&"MyPrimitive".to_string()));
        assert!(config.move_types.contains(&"MyResource".to_string()));
    }

    // ==================== HeapConfig Edge Cases ====================

    #[test]
    fn test_heap_config_validation_edge_cases() {
        // Edge: context_sensitivity = 0 (valid, insensitive)
        let mut config = HeapConfig::from_preset(Preset::Balanced);
        config.context_sensitivity = 0;
        assert!(config.validate().is_ok());

        // Edge: context_sensitivity = 3 (valid, max)
        config.context_sensitivity = 3;
        assert!(config.validate().is_ok());

        // Edge: context_sensitivity = 4 (invalid)
        config.context_sensitivity = 4;
        assert!(config.validate().is_err());

        // Edge: max_heap_objects = 1 (valid, min)
        config.context_sensitivity = 0;
        config.max_heap_objects = 1;
        assert!(config.validate().is_ok());

        // Edge: max_heap_objects = 1000000 (valid, max)
        config.max_heap_objects = 1000000;
        assert!(config.validate().is_ok());

        // Edge: max_heap_objects = 1000001 (invalid)
        config.max_heap_objects = 1000001;
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_heap_config_extreme_all_disabled() {
        let config = HeapConfig::from_preset(Preset::Fast)
            .enabled(false)
            .enable_memory_safety(false)
            .enable_ownership(false)
            .enable_escape(false)
            .enable_security(false)
            .enable_context_sensitive(false);

        assert!(!config.enabled);
        assert!(!config.enable_memory_safety);
        assert!(!config.enable_ownership);
        assert!(!config.enable_escape);
        assert!(!config.enable_security);
        assert!(!config.enable_context_sensitive);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_heap_config_extreme_all_enabled() {
        let config = HeapConfig::from_preset(Preset::Thorough)
            .enabled(true)
            .enable_memory_safety(true)
            .enable_ownership(true)
            .enable_escape(true)
            .enable_security(true)
            .enable_context_sensitive(true)
            .context_sensitivity(3)
            .ownership_strict_mode(true)
            .max_heap_objects(1000000);

        assert!(config.enabled);
        assert!(config.enable_memory_safety);
        assert!(config.enable_ownership);
        assert!(config.enable_escape);
        assert!(config.enable_security);
        assert!(config.enable_context_sensitive);
        assert_eq!(config.context_sensitivity, 3);
        assert!(config.ownership_strict_mode);
        assert_eq!(config.max_heap_objects, 1000000);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_heap_config_empty_type_lists() {
        let mut config = HeapConfig::from_preset(Preset::Balanced);
        config.copy_types = vec![];
        config.move_types = vec![];

        // Empty type lists should be valid (all types treated as unknown)
        assert!(config.validate().is_ok());
        assert!(config.copy_types.is_empty());
        assert!(config.move_types.is_empty());
    }

    #[test]
    fn test_heap_config_large_type_lists() {
        let mut config = HeapConfig::from_preset(Preset::Balanced);

        // Add many copy types
        for i in 0..100 {
            config = config.add_copy_type(format!("CopyType{}", i));
        }

        // Add many move types
        for i in 0..100 {
            config = config.add_move_type(format!("MoveType{}", i));
        }

        assert_eq!(config.copy_types.len(), 100 + 5); // +5 from preset
        assert_eq!(config.move_types.len(), 100 + 5); // +5 from preset
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_heap_config_custom_preset_defaults() {
        let config = HeapConfig::from_preset(Preset::Custom);

        // Custom should use Balanced defaults (as per Default impl)
        assert!(config.enabled);
        assert!(config.enable_memory_safety);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_heap_config_boundary_context_sensitivity() {
        // Test all valid context sensitivity levels
        for level in 0..=3 {
            let config = HeapConfig::from_preset(Preset::Balanced).context_sensitivity(level);
            assert!(config.validate().is_ok(), "Level {} should be valid", level);
        }
    }

    // ==================== TaintConfig Tests ====================

    #[test]
    fn test_taint_config_validation() {
        let mut config = TaintConfig::from_preset(Preset::Fast);
        assert!(config.validate().is_ok());

        config.max_depth = 0;
        assert!(config.validate().is_err());

        config.max_depth = 1001;
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_taint_config_builder() {
        let config = TaintConfig::from_preset(Preset::Fast)
            .max_depth(50)
            .max_paths(1000)
            .use_points_to(true);

        assert_eq!(config.max_depth, 50);
        assert_eq!(config.max_paths, 1000);
        assert!(config.use_points_to);
    }

    // ==================== TaintConfig SOTA Tests ====================

    #[test]
    fn test_taint_config_sota_presets() {
        // Fast: All SOTA features disabled
        let fast = TaintConfig::from_preset(Preset::Fast);
        assert!(!fast.implicit_flow_enabled);
        assert!(!fast.backward_analysis_enabled);
        assert!(!fast.context_sensitive);
        assert!(!fast.path_sensitive);
        assert_eq!(fast.timeout_seconds, 5);

        // Balanced: Partial SOTA features
        let balanced = TaintConfig::from_preset(Preset::Balanced);
        assert!(!balanced.implicit_flow_enabled); // Expensive
        assert!(balanced.backward_analysis_enabled);
        assert!(balanced.context_sensitive);
        assert!(!balanced.path_sensitive); // Expensive
        assert_eq!(balanced.timeout_seconds, 60);

        // Thorough: All SOTA features enabled
        let thorough = TaintConfig::from_preset(Preset::Thorough);
        assert!(thorough.implicit_flow_enabled);
        assert!(thorough.backward_analysis_enabled);
        assert!(thorough.context_sensitive);
        assert!(thorough.path_sensitive);
        assert_eq!(thorough.timeout_seconds, 300);
    }

    #[test]
    fn test_taint_config_sota_builder() {
        let config = TaintConfig::from_preset(Preset::Fast)
            .implicit_flow_enabled(true)
            .backward_analysis_enabled(true)
            .context_sensitive(true)
            .path_sensitive(true)
            .timeout_seconds(120);

        assert!(config.implicit_flow_enabled);
        assert!(config.backward_analysis_enabled);
        assert!(config.context_sensitive);
        assert!(config.path_sensitive);
        assert_eq!(config.timeout_seconds, 120);
    }

    #[test]
    fn test_taint_config_sota_validation() {
        // timeout_seconds > 3600 should fail
        let mut config = TaintConfig::from_preset(Preset::Balanced);
        config.timeout_seconds = 7200; // 2 hours
        assert!(config.validate().is_err());

        // path_sensitive without context_sensitive should fail
        let mut config = TaintConfig::from_preset(Preset::Fast);
        config.path_sensitive = true;
        config.context_sensitive = false;
        assert!(config.validate().is_err());

        // Valid config should pass
        config.context_sensitive = true;
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_taint_config_sota_edge_cases() {
        // timeout_seconds = 0 means unlimited (valid)
        let mut config = TaintConfig::from_preset(Preset::Balanced);
        config.timeout_seconds = 0;
        assert!(config.validate().is_ok());

        // timeout_seconds = 3600 (max) is valid
        config.timeout_seconds = 3600;
        assert!(config.validate().is_ok());

        // All SOTA features enabled with max timeout
        let config = TaintConfig::from_preset(Preset::Thorough)
            .implicit_flow_enabled(true)
            .backward_analysis_enabled(true)
            .context_sensitive(true)
            .path_sensitive(true)
            .timeout_seconds(3600);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_pta_config_validation() {
        let mut config = PTAConfig::from_preset(Preset::Balanced);
        assert!(config.validate().is_ok());

        config.max_iterations = Some(0);
        assert!(config.validate().is_err());

        config.max_iterations = Some(11000);
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_clone_config_validation() {
        let config = CloneConfig::from_preset(Preset::Thorough);
        assert!(config.validate().is_ok());
        assert_eq!(config.types_enabled.len(), 4);
    }

    #[test]
    fn test_chunking_config_validation() {
        let mut config = ChunkingConfig::from_preset(Preset::Balanced);
        assert!(config.validate().is_ok());

        config.min_chunk_size = config.max_chunk_size + 1;
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_lexical_config_validation() {
        let config = LexicalConfig::from_preset(Preset::Balanced);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_parallel_config_validation() {
        let config = ParallelConfig::from_preset(Preset::Fast);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_preset_configurations() {
        // Fast
        let taint_fast = TaintConfig::from_preset(Preset::Fast);
        assert_eq!(taint_fast.max_depth, 10);
        assert!(!taint_fast.use_points_to);

        // Balanced
        let taint_balanced = TaintConfig::from_preset(Preset::Balanced);
        assert_eq!(taint_balanced.max_depth, 30);
        assert!(taint_balanced.use_points_to);

        // Thorough
        let taint_thorough = TaintConfig::from_preset(Preset::Thorough);
        assert_eq!(taint_thorough.max_depth, 100);
        assert!(taint_thorough.use_points_to);
    }

    // ==================== PDGConfig Tests ====================

    #[test]
    fn test_pdg_config_validation() {
        let config = PDGConfig::from_preset(Preset::Balanced);
        assert!(config.validate().is_ok());

        let mut config = PDGConfig::from_preset(Preset::Fast);
        config.max_nodes = 0;
        assert!(config.validate().is_err());

        config.max_nodes = 100001;
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_pdg_config_presets() {
        // Fast: disabled
        let fast = PDGConfig::from_preset(Preset::Fast);
        assert!(!fast.enabled);
        assert_eq!(fast.max_nodes, 1000);

        // Balanced: enabled
        let balanced = PDGConfig::from_preset(Preset::Balanced);
        assert!(balanced.enabled);
        assert!(balanced.include_control);
        assert!(balanced.include_data);
        assert_eq!(balanced.max_nodes, 10000);

        // Thorough: larger limits
        let thorough = PDGConfig::from_preset(Preset::Thorough);
        assert!(thorough.enabled);
        assert_eq!(thorough.max_nodes, 100000);
    }

    #[test]
    fn test_pdg_config_builder() {
        let config = PDGConfig::from_preset(Preset::Balanced)
            .enabled(true)
            .include_control(false) // Data-only (Thin Slicing prep)
            .include_data(true)
            .max_nodes(50000);

        assert!(config.enabled);
        assert!(!config.include_control);
        assert!(config.include_data);
        assert_eq!(config.max_nodes, 50000);
    }

    // ==================== SlicingConfig Tests ====================

    #[test]
    fn test_slicing_config_validation() {
        let config = SlicingConfig::from_preset(Preset::Balanced);
        assert!(config.validate().is_ok());

        let mut config = SlicingConfig::from_preset(Preset::Fast);
        config.max_depth = 0;
        assert!(config.validate().is_err());

        config.max_depth = 50;
        config.max_function_depth = 0;
        assert!(config.validate().is_err());

        config.max_function_depth = 101;
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_slicing_config_presets() {
        // Fast: disabled, limited
        let fast = SlicingConfig::from_preset(Preset::Fast);
        assert!(!fast.enabled);
        assert_eq!(fast.max_depth, 20);
        assert!(!fast.interprocedural);

        // Balanced: enabled
        let balanced = SlicingConfig::from_preset(Preset::Balanced);
        assert!(balanced.enabled);
        assert_eq!(balanced.max_depth, 50);
        assert!(balanced.interprocedural);
        assert!(!balanced.strict_mode);

        // Thorough: full
        let thorough = SlicingConfig::from_preset(Preset::Thorough);
        assert!(thorough.enabled);
        assert_eq!(thorough.max_depth, 200);
        assert!(thorough.strict_mode);
    }

    #[test]
    fn test_slicing_config_builder() {
        let config = SlicingConfig::from_preset(Preset::Balanced)
            .enabled(true)
            .max_depth(100)
            .max_function_depth(5)
            .include_control(false) // Thin Slicing
            .include_data(true)
            .interprocedural(true)
            .strict_mode(false)
            .cache_capacity(5000);

        assert!(config.enabled);
        assert_eq!(config.max_depth, 100);
        assert_eq!(config.max_function_depth, 5);
        assert!(!config.include_control); // Thin Slicing
        assert!(config.include_data);
        assert!(config.interprocedural);
        assert!(!config.strict_mode);
        assert_eq!(config.cache_capacity, 5000);
    }

    #[test]
    fn test_slicing_thin_slicing_preset() {
        // Thin Slicing = data dependencies only
        let config = SlicingConfig::thin_slicing();
        assert!(config.enabled);
        assert!(!config.include_control); // KEY: no control deps
        assert!(config.include_data);
    }
}
