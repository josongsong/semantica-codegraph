//! Pipeline configuration with StageControl
//!
//! Main configuration struct with preset-based defaults and override support.

use super::{
    error::{ConfigError, ConfigResult},
    performance::PerformanceProfile,
    preset::Preset,
    provenance::{ConfigProvenance, ConfigSource},
    stage_configs::*,
};
use serde::{Deserialize, Serialize};

// Optional imports (conditionally compiled)
use super::CacheConfig;
use super::PageRankConfig;

/// Stage identifier for L1-L37 pipeline stages
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StageId {
    // Phase 1: Basic IR (L1-L3)
    Parsing,  // L1
    Chunking, // L2
    Lexical,  // L3

    // Phase 2: Analysis (L4-L8)
    CrossFile,     // L4
    Clone,         // L5 (L10 in RFC)
    Pta,           // L6
    FlowGraphs,    // L7 (CFG/DFG)
    TypeInference, // L8

    // Phase 3: Advanced (L9+)
    Symbols,     // L9
    Effects,     // L11
    Taint,       // L14
    RepoMap,     // L16
    Concurrency, // L18
}

/// Stage control (on/off switches for pipeline stages)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct StageControl {
    // Phase 1: Basic (default on)
    #[serde(default = "default_true")]
    pub parsing: bool,
    #[serde(default = "default_true")]
    pub chunking: bool,
    #[serde(default = "default_true")]
    pub lexical: bool,

    // Phase 2: Analysis (default off - expensive)
    #[serde(default)]
    pub cross_file: bool,
    #[serde(default)]
    pub clone: bool,
    #[serde(default)]
    pub pta: bool,
    #[serde(default)]
    pub flow_graphs: bool,
    #[serde(default)]
    pub type_inference: bool,

    // Phase 3: Advanced (default off - very expensive)
    #[serde(default)]
    pub symbols: bool,
    #[serde(default)]
    pub effects: bool,
    #[serde(default)]
    pub taint: bool,
    #[serde(default)]
    pub repomap: bool,

    // L7: Heap Analysis (default off - depends on PTA)
    #[serde(default)]
    pub heap: bool,

    // L17: PDG (Program Dependence Graph)
    #[serde(default)]
    pub pdg: bool,

    // L18: Concurrency Analysis (race detection, deadlock)
    #[serde(default)]
    pub concurrency: bool,

    // L19: Slicing (backward, forward, thin, chop)
    #[serde(default)]
    pub slicing: bool,
}

fn default_true() -> bool {
    true
}

impl Default for StageControl {
    fn default() -> Self {
        Self {
            // Phase 1: Basic
            parsing: true,
            chunking: true,
            lexical: true,

            // Phase 2: Analysis
            cross_file: false,
            clone: false,
            pta: false,
            flow_graphs: false,
            type_inference: false,

            // Phase 3: Advanced
            symbols: false,
            effects: false,
            taint: false,
            repomap: false,

            // L7: Heap Analysis
            heap: false,

            // L17-L19: PDG, Concurrency, Slicing
            pdg: false,
            concurrency: false,
            slicing: false,
        }
    }
}

impl StageControl {
    /// All stages enabled
    pub fn all() -> Self {
        Self {
            parsing: true,
            chunking: true,
            lexical: true,
            cross_file: true,
            clone: true,
            pta: true,
            flow_graphs: true,
            type_inference: true,
            symbols: true,
            effects: true,
            taint: true,
            repomap: true,
            heap: true,
            pdg: true,
            concurrency: true,
            slicing: true,
        }
    }

    /// Security-focused stages
    pub fn security() -> Self {
        Self {
            parsing: true,
            chunking: true,
            lexical: true,
            cross_file: true,
            clone: false,
            pta: true,         // Needed for taint
            flow_graphs: true, // Needed for taint
            type_inference: false,
            symbols: false,
            effects: true, // For effect analysis
            taint: true,   // Core security analysis
            repomap: false,
            heap: true,        // Memory safety + ownership tracking
            pdg: true,         // Program Dependence Graph for slicing
            concurrency: true, // Race condition detection
            slicing: true,     // Thin slicing for bug localization
        }
    }

    /// Enable a specific stage
    pub fn enable(mut self, stage: StageId) -> Self {
        self.set(stage, true);
        self
    }

    /// Disable a specific stage
    pub fn disable(mut self, stage: StageId) -> Self {
        self.set(stage, false);
        self
    }

    /// Set stage state
    pub fn set(&mut self, stage: StageId, enabled: bool) {
        match stage {
            StageId::Parsing => self.parsing = enabled,
            StageId::Chunking => self.chunking = enabled,
            StageId::Lexical => self.lexical = enabled,
            StageId::CrossFile => self.cross_file = enabled,
            StageId::Clone => self.clone = enabled,
            StageId::Pta => self.pta = enabled,
            StageId::FlowGraphs => self.flow_graphs = enabled,
            StageId::TypeInference => self.type_inference = enabled,
            StageId::Symbols => self.symbols = enabled,
            StageId::Effects => self.effects = enabled,
            StageId::Taint => self.taint = enabled,
            StageId::RepoMap => self.repomap = enabled,
            StageId::Concurrency => self.concurrency = enabled,
        }
    }

    /// Get stage state
    pub fn is_enabled(&self, stage: StageId) -> bool {
        match stage {
            StageId::Parsing => self.parsing,
            StageId::Chunking => self.chunking,
            StageId::Lexical => self.lexical,
            StageId::CrossFile => self.cross_file,
            StageId::Clone => self.clone,
            StageId::Pta => self.pta,
            StageId::FlowGraphs => self.flow_graphs,
            StageId::TypeInference => self.type_inference,
            StageId::Symbols => self.symbols,
            StageId::Effects => self.effects,
            StageId::Taint => self.taint,
            StageId::RepoMap => self.repomap,
            StageId::Concurrency => self.concurrency,
        }
    }
}

/// Pipeline configuration (builder)
#[derive(Debug, Clone)]
pub struct PipelineConfig {
    /// Base preset
    pub(crate) preset: Preset,

    /// Stage control (on/off switches)
    pub stages: StageControl,

    /// Strict mode: error on disabled stage overrides (default: false)
    /// - true: build() fails with ConfigError::DisabledStageOverride
    /// - false: build() warns and ignores disabled stage overrides
    pub(crate) strict_mode: bool,

    /// Stage-specific overrides
    pub(crate) taint: Option<TaintConfig>,
    pub(crate) pta: Option<PTAConfig>,
    pub(crate) clone: Option<CloneConfig>,
    pub(crate) chunking: Option<ChunkingConfig>,
    pub(crate) lexical: Option<LexicalConfig>,
    pub(crate) parallel: Option<ParallelConfig>,
    pub(crate) pagerank: Option<PageRankConfig>,
    pub(crate) cache: Option<CacheConfig>,
    pub(crate) heap: Option<HeapConfig>,
    pub(crate) pdg: Option<PDGConfig>,
    pub(crate) slicing: Option<SlicingConfig>,

    /// Provenance tracking (field-level)
    pub(crate) provenance: ConfigProvenance,
}

impl PipelineConfig {
    /// Level 1: Create from preset
    pub fn preset(preset: Preset) -> Self {
        Self {
            preset,
            stages: StageControl::default(),
            strict_mode: false, // Lenient by default
            taint: None,
            pta: None,
            clone: None,
            chunking: None,
            lexical: None,
            parallel: None,
            pagerank: None,
            cache: None,
            heap: None,
            pdg: None,
            slicing: None,
            provenance: ConfigProvenance::from_preset(preset),
        }
    }

    /// Enable strict mode (errors on disabled stage overrides)
    pub fn strict_mode(mut self, enabled: bool) -> Self {
        self.strict_mode = enabled;
        self
    }

    /// Configure stage control (closure-based)
    pub fn with_stages<F>(mut self, f: F) -> Self
    where
        F: FnOnce(StageControl) -> StageControl,
    {
        self.stages = f(self.stages);
        self
    }

    /// Alias for with_stages
    pub fn stages<F>(self, f: F) -> Self
    where
        F: FnOnce(StageControl) -> StageControl,
    {
        self.with_stages(f)
    }

    /// Level 2: Override taint stage (Rust closure convenience)
    pub fn taint<F>(mut self, f: F) -> Self
    where
        F: FnOnce(TaintConfig) -> TaintConfig,
    {
        let base = TaintConfig::from_preset(self.preset);
        self.taint = Some(f(base));
        self.provenance
            .track_field("taint.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override PTA stage
    pub fn pta<F>(mut self, f: F) -> Self
    where
        F: FnOnce(PTAConfig) -> PTAConfig,
    {
        let base = PTAConfig::from_preset(self.preset);
        self.pta = Some(f(base));
        self.provenance.track_field("pta.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override clone detection stage
    pub fn clone<F>(mut self, f: F) -> Self
    where
        F: FnOnce(CloneConfig) -> CloneConfig,
    {
        let base = CloneConfig::from_preset(self.preset);
        self.clone = Some(f(base));
        self.provenance
            .track_field("clone.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override chunking stage
    pub fn chunking<F>(mut self, f: F) -> Self
    where
        F: FnOnce(ChunkingConfig) -> ChunkingConfig,
    {
        let base = ChunkingConfig::from_preset(self.preset);
        self.chunking = Some(f(base));
        self.provenance
            .track_field("chunking.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override lexical stage
    pub fn lexical<F>(mut self, f: F) -> Self
    where
        F: FnOnce(LexicalConfig) -> LexicalConfig,
    {
        let base = LexicalConfig::from_preset(self.preset);
        self.lexical = Some(f(base));
        self.provenance
            .track_field("lexical.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override parallel config
    pub fn parallel<F>(mut self, f: F) -> Self
    where
        F: FnOnce(ParallelConfig) -> ParallelConfig,
    {
        let base = ParallelConfig::from_preset(self.preset);
        self.parallel = Some(f(base));
        self.provenance
            .track_field("parallel.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override pagerank config
    pub fn pagerank<F>(mut self, f: F) -> Self
    where
        F: FnOnce(PageRankConfig) -> PageRankConfig,
    {
        let base = PageRankConfig::default();
        self.pagerank = Some(f(base));
        self.provenance
            .track_field("pagerank.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override cache config
    pub fn cache<F>(mut self, f: F) -> Self
    where
        F: FnOnce(CacheConfig) -> CacheConfig,
    {
        let base = CacheConfig::default();
        self.cache = Some(f(base));
        self.provenance
            .track_field("cache.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override heap analysis config
    pub fn heap<F>(mut self, f: F) -> Self
    where
        F: FnOnce(HeapConfig) -> HeapConfig,
    {
        let base = HeapConfig::from_preset(self.preset);
        self.heap = Some(f(base));
        self.provenance.track_field("heap.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override PDG config
    ///
    /// # Example
    /// ```ignore
    /// let config = PipelineConfig::preset(Preset::Balanced)
    ///     .pdg(|c| c.max_nodes(50000))
    ///     .build()?;
    /// ```
    pub fn pdg(mut self, f: impl FnOnce(PDGConfig) -> PDGConfig) -> Self {
        let base = PDGConfig::from_preset(self.preset);
        self.pdg = Some(f(base));
        self.provenance.track_field("pdg.*", ConfigSource::Builder);
        self
    }

    /// Level 2: Override Slicing config
    ///
    /// # Example
    /// ```ignore
    /// let config = PipelineConfig::preset(Preset::Balanced)
    ///     .slicing(|c| c.max_depth(100).include_control(false)) // Thin Slicing
    ///     .build()?;
    /// ```
    pub fn slicing(mut self, f: impl FnOnce(SlicingConfig) -> SlicingConfig) -> Self {
        let base = SlicingConfig::from_preset(self.preset);
        self.slicing = Some(f(base));
        self.provenance
            .track_field("slicing.*", ConfigSource::Builder);
        self
    }

    /// Build and validate
    pub fn build(self) -> ConfigResult<ValidatedConfig> {
        // Step 1: Validate individual stage configs
        if let Some(ref cfg) = self.taint {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.pta {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.clone {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.chunking {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.lexical {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.parallel {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.pdg {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.slicing {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.heap {
            cfg.validate()?;
        }

        // Step 2: Check StageControl consistency
        self.validate_stage_control()?;

        // Step 3: Cross-stage validation
        self.cross_validate()?;

        Ok(ValidatedConfig(self))
    }

    /// StageControl consistency validation
    fn validate_stage_control(&self) -> ConfigResult<()> {
        // Check for disabled stage with overrides
        if !self.stages.taint && self.taint.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "taint".to_string(),
                    hint: "Remove .taint() override or enable the stage with .with_stages(|s| s.enable(StageId::Taint))".to_string(),
                });
            } else {
                eprintln!("WARNING: Taint config ignored (stage disabled). Enable strict_mode to error on this.");
            }
        }

        if !self.stages.pta && self.pta.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "pta".to_string(),
                    hint: "Remove .pta() override or enable the stage".to_string(),
                });
            } else {
                eprintln!("WARNING: PTA config ignored (stage disabled).");
            }
        }

        if !self.stages.clone && self.clone.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "clone".to_string(),
                    hint: "Remove .clone() override or enable the stage".to_string(),
                });
            } else {
                eprintln!("WARNING: Clone config ignored (stage disabled).");
            }
        }

        if !self.stages.chunking && self.chunking.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "chunking".to_string(),
                    hint: "Remove .chunking() override or enable the stage".to_string(),
                });
            } else {
                eprintln!("WARNING: Chunking config ignored (stage disabled).");
            }
        }

        if !self.stages.lexical && self.lexical.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "lexical".to_string(),
                    hint: "Remove .lexical() override or enable the stage".to_string(),
                });
            } else {
                eprintln!("WARNING: Lexical config ignored (stage disabled).");
            }
        }

        if !self.stages.pdg && self.pdg.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "pdg".to_string(),
                    hint: "Remove .pdg() override or enable the stage".to_string(),
                });
            } else {
                eprintln!("WARNING: PDG config ignored (stage disabled).");
            }
        }

        if !self.stages.slicing && self.slicing.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "slicing".to_string(),
                    hint: "Remove .slicing() override or enable the stage".to_string(),
                });
            } else {
                eprintln!("WARNING: Slicing config ignored (stage disabled).");
            }
        }

        Ok(())
    }

    /// Cross-stage validation
    fn cross_validate(&self) -> ConfigResult<()> {
        let taint = self.effective_taint();
        let pta = self.effective_pta();

        // 1. Taint requires PTA if use_points_to is enabled
        if self.stages.taint && taint.use_points_to && !self.stages.pta {
            return Err(ConfigError::CrossStageConflict {
                issue: "Taint analysis requires Points-to analysis".to_string(),
                fix: "Enable PTA with .with_stages(|s| s.enable(StageId::Pta)) or set taint.use_points_to=false".to_string(),
            });
        }

        // 2. Taint field-sensitive with PTA Fast mode warning
        if self.stages.taint && self.stages.pta {
            if taint.field_sensitive && pta.mode == PTAMode::Fast {
                eprintln!("WARNING: Taint field_sensitive=true with PTA mode=Fast may produce inaccurate results");
                eprintln!("RECOMMENDATION: Use PTAMode::Precise or PTAMode::Auto for field-sensitive analysis");
            }
        }

        // 3. Slicing requires PDG
        if self.stages.slicing && !self.stages.pdg {
            return Err(ConfigError::CrossStageConflict {
                issue: "Slicing requires PDG (Program Dependence Graph)".to_string(),
                fix: "Enable PDG with .stages(|s| { s.pdg = true; s }) or disable slicing"
                    .to_string(),
            });
        }

        // 4. PDG requires flow_graphs (CFG/DFG)
        if self.stages.pdg && !self.stages.flow_graphs {
            return Err(ConfigError::CrossStageConflict {
                issue: "PDG requires flow graphs (CFG/DFG)".to_string(),
                fix: "Enable flow_graphs with .stages(|s| { s.flow_graphs = true; s }) or disable pdg".to_string(),
            });
        }

        Ok(())
    }

    /// Get effective taint config (preset or override)
    fn effective_taint(&self) -> TaintConfig {
        self.taint
            .clone()
            .unwrap_or_else(|| TaintConfig::from_preset(self.preset))
    }

    /// Get effective PTA config (preset or override)
    fn effective_pta(&self) -> PTAConfig {
        self.pta
            .clone()
            .unwrap_or_else(|| PTAConfig::from_preset(self.preset))
    }

    /// Get performance profile
    pub fn performance_profile(&self) -> PerformanceProfile {
        self.preset.performance_profile()
    }

    /// Get base preset
    pub fn get_preset(&self) -> Preset {
        self.preset
    }

    /// Get provenance
    pub fn provenance(&self) -> &ConfigProvenance {
        &self.provenance
    }

    /// Load from YAML file (v1 schema)
    pub fn from_yaml(path: &str) -> ConfigResult<ValidatedConfig> {
        use crate::config::io::ConfigExportV1;

        let content = std::fs::read_to_string(path)?;
        let export: ConfigExportV1 = serde_yaml::from_str(&content)?;

        // Version check
        if export.version != 1 {
            return Err(ConfigError::UnsupportedVersion {
                found: export.version,
                supported: vec![1],
            });
        }

        // Parse preset
        let preset = Preset::from_str(&export.preset)
            .map_err(|_| ConfigError::UnknownPreset(export.preset.clone()))?;

        let mut config = Self::preset(preset);

        // Apply StageControl
        if let Some(stages) = export.stages {
            config.stages = stages;
        }

        // Apply overrides with provenance tracking
        if let Some(overrides) = export.overrides {
            if let Some(taint) = overrides.taint {
                config.taint = Some(taint);
                config.provenance.track_field(
                    "taint.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(pta) = overrides.pta {
                config.pta = Some(pta);
                config.provenance.track_field(
                    "pta.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(clone) = overrides.clone {
                config.clone = Some(clone);
                config.provenance.track_field(
                    "clone.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(chunking) = overrides.chunking {
                config.chunking = Some(chunking);
                config.provenance.track_field(
                    "chunking.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(lexical) = overrides.lexical {
                config.lexical = Some(lexical);
                config.provenance.track_field(
                    "lexical.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(parallel) = overrides.parallel {
                config.parallel = Some(parallel);
                config.provenance.track_field(
                    "parallel.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(pagerank) = overrides.pagerank {
                config.pagerank = Some(pagerank);
                config.provenance.track_field(
                    "pagerank.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(cache) = overrides.cache {
                config.cache = Some(cache);
                config.provenance.track_field(
                    "cache.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
            if let Some(heap) = overrides.heap {
                config.heap = Some(heap);
                config.provenance.track_field(
                    "heap.*",
                    ConfigSource::Yaml {
                        path: path.to_string(),
                    },
                );
            }
        }

        config.build()
    }

    /// Export to YAML
    pub fn to_yaml(&self) -> ConfigResult<String> {
        use crate::config::io::{ConfigExportV1, ConfigOverrides};

        let export = ConfigExportV1 {
            version: 1,
            preset: self.get_preset().to_string(),
            stages: Some(self.stages.clone()),
            overrides: Some(ConfigOverrides {
                taint: self.taint.clone(),
                pta: self.pta.clone(),
                clone: self.clone.clone(),
                pagerank: self.pagerank.clone(),
                chunking: self.chunking.clone(),
                lexical: self.lexical.clone(),
                parallel: self.parallel.clone(),
                cache: self.cache.clone(),
                heap: self.heap.clone(),
            }),
        };

        serde_yaml::to_string(&export).map_err(|e| ConfigError::Yaml(e))
    }

    /// Get a human-readable description of the configuration
    pub fn describe(&self) -> String {
        let preset_name = self.get_preset().to_string();
        let enabled_stages: Vec<String> = vec![
            (self.stages.parsing, "Parsing"),
            (self.stages.chunking, "Chunking"),
            (self.stages.lexical, "Lexical"),
            (self.stages.clone, "Clone"),
            (self.stages.pta, "PTA"),
            (self.stages.flow_graphs, "FlowGraphs"),
            (self.stages.type_inference, "TypeInference"),
            (self.stages.symbols, "Symbols"),
            (self.stages.effects, "Effects"),
            (self.stages.taint, "Taint"),
            (self.stages.repomap, "RepoMap"),
        ]
        .into_iter()
        .filter_map(|(enabled, name)| {
            if enabled {
                Some(name.to_string())
            } else {
                None
            }
        })
        .collect();

        if enabled_stages.is_empty() {
            format!("{} (no stages enabled)", preset_name)
        } else {
            format!("{} [{}]", preset_name, enabled_stages.join(", "))
        }
    }
}

/// Validated configuration (immutable, safe to use)
#[derive(Debug, Clone)]
pub struct ValidatedConfig(PipelineConfig);

impl ValidatedConfig {
    /// Unwrap the validated config to get the inner PipelineConfig
    pub fn into_inner(self) -> PipelineConfig {
        self.0
    }

    /// Get a reference to the inner PipelineConfig
    pub fn as_inner(&self) -> &PipelineConfig {
        &self.0
    }

    /// Get a human-readable description of the configuration
    pub fn describe(&self) -> String {
        self.0.describe()
    }

    /// Get effective taint config (None if stage disabled)
    pub fn taint(&self) -> Option<TaintConfig> {
        if !self.0.stages.taint {
            return None;
        }
        Some(
            self.0
                .taint
                .clone()
                .unwrap_or_else(|| TaintConfig::from_preset(self.0.preset)),
        )
    }

    /// Get effective PTA config (None if stage disabled)
    pub fn pta(&self) -> Option<PTAConfig> {
        if !self.0.stages.pta {
            return None;
        }
        Some(
            self.0
                .pta
                .clone()
                .unwrap_or_else(|| PTAConfig::from_preset(self.0.preset)),
        )
    }

    /// Get effective clone config (None if stage disabled)
    pub fn clone(&self) -> Option<CloneConfig> {
        if !self.0.stages.clone {
            return None;
        }
        Some(
            self.0
                .clone
                .clone()
                .unwrap_or_else(|| CloneConfig::from_preset(self.0.preset)),
        )
    }

    /// Get effective chunking config (None if stage disabled)
    pub fn chunking(&self) -> Option<ChunkingConfig> {
        if !self.0.stages.chunking {
            return None;
        }
        Some(
            self.0
                .chunking
                .clone()
                .unwrap_or_else(|| ChunkingConfig::from_preset(self.0.preset)),
        )
    }

    /// Get effective lexical config (None if stage disabled)
    pub fn lexical(&self) -> Option<LexicalConfig> {
        if !self.0.stages.lexical {
            return None;
        }
        Some(
            self.0
                .lexical
                .clone()
                .unwrap_or_else(|| LexicalConfig::from_preset(self.0.preset)),
        )
    }

    /// Get effective parallel config
    pub fn parallel(&self) -> ParallelConfig {
        self.0
            .parallel
            .clone()
            .unwrap_or_else(|| ParallelConfig::from_preset(self.0.preset))
    }

    /// Get effective pagerank config (None if stage disabled)
    pub fn pagerank(&self) -> Option<PageRankConfig> {
        if !self.0.stages.repomap {
            return None;
        }
        Some(
            self.0
                .pagerank
                .clone()
                .unwrap_or_else(|| PageRankConfig::default()),
        )
    }

    /// Get effective cache config
    pub fn cache(&self) -> CacheConfig {
        self.0
            .cache
            .clone()
            .unwrap_or_else(|| CacheConfig::default())
    }

    /// Get effective heap analysis config (None if stage disabled)
    pub fn heap(&self) -> Option<HeapConfig> {
        if !self.0.stages.heap {
            return None;
        }
        Some(
            self.0
                .heap
                .clone()
                .unwrap_or_else(|| HeapConfig::from_preset(self.0.preset)),
        )
    }

    /// Get effective PDG config (None if stage disabled)
    pub fn pdg(&self) -> Option<PDGConfig> {
        if !self.0.stages.pdg {
            return None;
        }
        Some(
            self.0
                .pdg
                .clone()
                .unwrap_or_else(|| PDGConfig::from_preset(self.0.preset)),
        )
    }

    /// Get effective slicing config (None if stage disabled)
    pub fn slicing(&self) -> Option<SlicingConfig> {
        if !self.0.stages.slicing {
            return None;
        }
        Some(
            self.0
                .slicing
                .clone()
                .unwrap_or_else(|| SlicingConfig::from_preset(self.0.preset)),
        )
    }

    /// Get stage control
    pub fn stages(&self) -> &StageControl {
        &self.0.stages
    }

    /// Get performance profile
    pub fn performance_profile(&self) -> PerformanceProfile {
        self.0.performance_profile()
    }

    /// Get provenance summary
    pub fn provenance_summary(&self) -> String {
        self.0.provenance.summary()
    }

    /// Get configuration summary
    pub fn summary(&self) -> String {
        let profile = self.performance_profile();
        let prov = self.provenance_summary();

        format!(
            r#"
Configuration Summary
=====================
{}

Performance Profile:
  - Cost class: {:?}
  - Expected latency: {:?}
  - Expected memory: {:?}
  - Production ready: {}

Stages:
  - Parsing: {}
  - Chunking: {}
  - Lexical: {}
  - Cross-file: {}
  - Clone: {}
  - PTA: {}
  - Taint: {}
  - RepoMap: {}

Effective Configuration:
├─ Taint Analysis
│  ├─ enabled: {}
│  ├─ max_depth: {}
│  ├─ max_paths: {}
│  └─ use_points_to: {}
├─ Points-to Analysis
│  ├─ enabled: {}
│  ├─ mode: {:?}
│  └─ max_iterations: {:?}
└─ Clone Detection
   ├─ enabled: {}
   └─ types: {:?}
"#,
            prov,
            profile.cost_class,
            profile.expected_latency,
            profile.expected_memory,
            if profile.production_ready {
                "Yes ✅"
            } else {
                "No ⚠️"
            },
            self.0.stages.parsing,
            self.0.stages.chunking,
            self.0.stages.lexical,
            self.0.stages.cross_file,
            self.0.stages.clone,
            self.0.stages.pta,
            self.0.stages.taint,
            self.0.stages.repomap,
            self.0.stages.taint,
            self.taint().as_ref().map(|c| c.max_depth).unwrap_or(0),
            self.taint().as_ref().map(|c| c.max_paths).unwrap_or(0),
            self.taint()
                .as_ref()
                .map(|c| c.use_points_to)
                .unwrap_or(false),
            self.0.stages.pta,
            self.pta().as_ref().map(|c| c.mode),
            self.pta().as_ref().and_then(|c| c.max_iterations),
            self.0.stages.clone,
            self.clone().as_ref().map(|c| c.types_enabled.clone()),
        )
    }

    /// Export to YAML
    pub fn to_yaml(&self) -> ConfigResult<String> {
        self.0.to_yaml()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stage_control_default() {
        let stages = StageControl::default();
        assert!(stages.parsing);
        assert!(stages.chunking);
        assert!(stages.lexical);
        assert!(!stages.taint);
        assert!(!stages.pta);
    }

    #[test]
    fn test_stage_control_builder() {
        let stages = StageControl::default()
            .enable(StageId::Taint)
            .enable(StageId::Pta);

        assert!(stages.taint);
        assert!(stages.pta);
    }

    #[test]
    fn test_pipeline_config_simple() {
        let config = PipelineConfig::preset(Preset::Fast).build().unwrap();

        assert_eq!(
            config.performance_profile().cost_class,
            super::super::performance::CostClass::Low
        );
    }

    #[test]
    fn test_pipeline_config_override() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .with_stages(|s| s.enable(StageId::Taint).enable(StageId::Pta)) // Enable taint + PTA
            .taint(|c| c.max_depth(50).max_paths(1000))
            .build()
            .unwrap();

        let taint = config.taint().unwrap();
        assert_eq!(taint.max_depth, 50);
        assert_eq!(taint.max_paths, 1000);
    }

    #[test]
    fn test_strict_mode_disabled_stage_override() {
        let result = PipelineConfig::preset(Preset::Balanced)
            .taint(|c| c.max_depth(100))
            .with_stages(|s| s.disable(StageId::Taint))
            .strict_mode(true)
            .build();

        assert!(result.is_err());
        assert!(matches!(
            result.unwrap_err(),
            ConfigError::DisabledStageOverride { .. }
        ));
    }

    #[test]
    fn test_lenient_mode_disabled_stage_override() {
        // Should succeed but emit warning
        let config = PipelineConfig::preset(Preset::Balanced)
            .taint(|c| c.max_depth(100))
            .with_stages(|s| s.disable(StageId::Taint))
            .strict_mode(false)
            .build()
            .unwrap();

        // Taint should be None because stage is disabled
        assert!(config.taint().is_none());
    }

    #[test]
    fn test_cross_stage_validation_taint_requires_pta() {
        let result = PipelineConfig::preset(Preset::Balanced)
            .with_stages(|s| s.enable(StageId::Taint).disable(StageId::Pta))
            .taint(|c| c.use_points_to(true))
            .build();

        assert!(result.is_err());
        assert!(matches!(
            result.unwrap_err(),
            ConfigError::CrossStageConflict { .. }
        ));
    }

    #[test]
    fn test_performance_profile() {
        let config = PipelineConfig::preset(Preset::Thorough).build().unwrap();

        let profile = config.performance_profile();
        assert_eq!(
            profile.cost_class,
            super::super::performance::CostClass::High
        );
        assert!(!profile.production_ready);
    }

    #[test]
    fn test_provenance_tracking() {
        let config = PipelineConfig::preset(Preset::Fast)
            .taint(|c| c.max_depth(50))
            .build()
            .unwrap();

        let prov = config.provenance_summary();
        assert!(prov.contains("Fast"));
        assert!(prov.contains("taint.*"));
        assert!(prov.contains("builder API"));
    }
}
#[cfg(test)]
mod cache_integration_tests {
    use super::*;

    #[test]
    fn test_cache_config_basic_access() {
        use crate::config::{PipelineConfig, Preset};

        let config = PipelineConfig::preset(Preset::Balanced).build().unwrap();

        let cache = config.cache();

        // L0 defaults (from cache/config.rs:46-52)
        assert_eq!(cache.l0.max_entries, 10_000);
        assert!(cache.l0.enable_bloom_filter);
        assert_eq!(cache.l0.bloom_capacity, 10_000);
        assert_eq!(cache.l0.bloom_fp_rate, 0.01);

        // L1 defaults (from cache/config.rs:74-82)
        assert_eq!(cache.l1.max_entries, 1_000);
        assert_eq!(cache.l1.max_bytes, 512 * 1024 * 1024);
        assert_eq!(cache.l1.ttl.as_secs(), 3600);
        assert!(!cache.l1.enable_eviction_listener);

        // L2 defaults (from cache/config.rs:99-112)
        assert!(cache.l2.enable_compression);
        assert!(!cache.l2.enable_rocksdb);

        // Tiered defaults (from cache/config.rs:128-136)
        assert!(cache.enable_background_l2_writes);
    }

    #[test]
    fn test_cache_config_builder() {
        use crate::config::{PipelineConfig, Preset};

        let config = PipelineConfig::preset(Preset::Fast)
            .cache(|mut c| {
                c.l0.max_entries = 5000;
                c.l1.max_entries = 500;
                c.l1.max_bytes = 256 * 1024 * 1024;
                c.l2.enable_compression = false;
                c
            })
            .build()
            .unwrap();

        let cache = config.cache();
        assert_eq!(cache.l0.max_entries, 5000);
        assert_eq!(cache.l1.max_entries, 500);
        assert_eq!(cache.l1.max_bytes, 256 * 1024 * 1024);
        assert!(!cache.l2.enable_compression);
    }

    #[test]
    fn test_cache_yaml_roundtrip() {
        use crate::config::{PipelineConfig, Preset};

        let config = PipelineConfig::preset(Preset::Balanced)
            .cache(|mut c| {
                c.l0.max_entries = 20_000;
                c.l1.max_entries = 2_000;
                c
            })
            .build()
            .unwrap();

        // Export to YAML
        let yaml = config.to_yaml().unwrap();

        // Verify YAML contains cache config
        assert!(yaml.contains("preset: balanced"));
        assert!(yaml.contains("cache:"));
        assert!(yaml.contains("l0:"));
        assert!(yaml.contains("max_entries: 20000"));
        assert!(yaml.contains("l1:"));

        println!("✅ YAML export successful:\n{}", yaml);
    }

    #[test]
    fn test_cache_all_presets() {
        use crate::config::{PipelineConfig, Preset};

        for preset in [Preset::Fast, Preset::Balanced, Preset::Thorough] {
            let config = PipelineConfig::preset(preset).build().unwrap();

            let cache = config.cache();

            // All presets should have same cache defaults
            assert_eq!(cache.l0.max_entries, 10_000);
            assert_eq!(cache.l1.max_entries, 1_000);

            println!("✅ Preset {:?}: cache config OK", preset);
        }
    }

    #[test]
    fn test_cache_serde_duration() {
        use crate::features::cache::config::AdaptiveCacheConfig;
        use serde_json;

        let config = AdaptiveCacheConfig::default();

        // Serialize to JSON
        let json = serde_json::to_string(&config).unwrap();
        assert!(json.contains("\"ttl\":3600")); // Duration as seconds

        // Deserialize back
        let config2: AdaptiveCacheConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(config2.ttl.as_secs(), 3600);

        println!("✅ Duration serde works: {}", json);
    }
}
