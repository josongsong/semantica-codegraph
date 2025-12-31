//! SOTA Configuration System
//!
//! RFC-001: Maximal Extensibility with Progressive Disclosure
//!
//! This module provides a 3-tier configuration system:
//! - Level 1: Preset (90% users) - Simple one-liner
//! - Level 2: Stage Override (9% users) - Partial adjustment
//! - Level 3: YAML/Advanced (1% users) - Complete control
//!
//! # Examples
//!
//! ```rust,ignore
//! use codegraph_ir::config::{PipelineConfig, Preset};
//!
//! // Level 1: Simple preset (90% use case)
//! let config = PipelineConfig::preset(Preset::Fast).build()?;
//!
//! // Level 2: Override specific stage (9% use case)
//! let config = PipelineConfig::preset(Preset::Balanced)
//!     .taint(|c| c.max_depth(50).max_paths(1000))
//!     .build()?;
//!
//! // Level 3: Complete control via YAML (1% use case)
//! let config = PipelineConfig::from_yaml("team-security.yaml")?;
//! ```
//!
//! # Features
//!
//! - **Type Safety**: Compile-time validation
//! - **Runtime Validation**: Range checks + cross-stage consistency
//! - **Field-level Provenance**: Track where each setting came from
//! - **Performance Profiles**: Qualitative cost/latency/memory bands
//! - **FFI Compatible**: Dual API (closures + Patch types)
//! - **Versioned Schema**: YAML v1 with migration path
//! - **IDE Support**: JSON Schema for autocomplete

pub mod error;
pub mod io;
pub mod patch;
pub mod performance;
pub mod pipeline_config;
pub mod preset;
pub mod provenance;
pub mod stage_configs;
pub mod validation;

// Re-exports
pub use error::{ConfigError, ConfigResult};
pub use io::{ConfigExportV1, ConfigOverrides};
pub use patch::{
    ChunkingConfigPatch,
    CloneConfigPatch,
    HeapConfigPatch, // L7, L17, L18
    LexicalConfigPatch,
    PDGConfigPatch,
    PTAConfigPatch,
    ParallelConfigPatch,
    SlicingConfigPatch,
    TaintConfigPatch,
};
pub use performance::{CostClass, LatencyBand, MemoryBand, PerformanceProfile};
pub use pipeline_config::{PipelineConfig, StageControl, ValidatedConfig};
pub use preset::Preset;
pub use provenance::{ConfigProvenance, ConfigSource};
pub use stage_configs::{
    ChunkingConfig,
    CloneConfig,
    CloneType,
    HeapConfig, // L7: Heap Analysis config (memory safety, ownership, escape)
    LexicalConfig,
    PDGConfig,
    PTAConfig,
    PTAMode,
    ParallelConfig,
    SlicingConfig, // L17-L18 configs
    TaintConfig,
    Type1Config,
    Type2Config,
    Type3Config,
    Type4Config,
};
pub use validation::{ConfigValidator, CrossStageValidator, Validatable, ValidatableCollection};

// Re-export existing cache and pagerank configs
// Note: These are optional - not all features may be compiled

// Cache config (re-enabled after adding Serialize/Deserialize and module export)
pub type CacheConfig = crate::features::cache::config::TieredCacheConfig;

// PageRank config (re-enabled after adding Serialize/Deserialize)
pub type PageRankConfig = crate::features::repomap::infrastructure::PageRankSettings;
