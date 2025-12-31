//! FFI-friendly Patch types
//!
//! Patch types with all-optional fields for Python/C bindings

use super::{pipeline_config::PipelineConfig, provenance::ConfigSource, stage_configs::*};
use serde::{Deserialize, Serialize};

/// Patch type for TaintConfig (all fields optional)
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TaintConfigPatch {
    pub max_depth: Option<usize>,
    pub max_paths: Option<usize>,
    pub use_points_to: Option<bool>,
    pub field_sensitive: Option<bool>,
    pub use_ssa: Option<bool>,
    pub detect_sanitizers: Option<bool>,
    pub enable_interprocedural: Option<bool>,
    pub worklist_max_iterations: Option<usize>,
}

impl PipelineConfig {
    /// Apply taint patch (FFI-friendly alternative to closure)
    pub fn taint_patch(mut self, patch: TaintConfigPatch) -> Self {
        let mut base = TaintConfig::from_preset(self.preset);

        if let Some(v) = patch.max_depth {
            base.max_depth = v;
        }
        if let Some(v) = patch.max_paths {
            base.max_paths = v;
        }
        if let Some(v) = patch.use_points_to {
            base.use_points_to = v;
        }
        if let Some(v) = patch.field_sensitive {
            base.field_sensitive = v;
        }
        if let Some(v) = patch.use_ssa {
            base.use_ssa = v;
        }
        if let Some(v) = patch.detect_sanitizers {
            base.detect_sanitizers = v;
        }
        if let Some(v) = patch.enable_interprocedural {
            base.enable_interprocedural = v;
        }
        if let Some(v) = patch.worklist_max_iterations {
            base.worklist_max_iterations = v;
        }

        self.taint = Some(base);
        self.provenance
            .track_field("taint.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for PTAConfig
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PTAConfigPatch {
    pub mode: Option<PTAMode>,
    pub field_sensitive: Option<bool>,
    pub max_iterations: Option<Option<usize>>,
    pub auto_threshold: Option<usize>,
    pub enable_scc: Option<bool>,
    pub enable_wave: Option<bool>,
    pub enable_parallel: Option<bool>,
}

impl PipelineConfig {
    /// Apply PTA patch
    pub fn pta_patch(mut self, patch: PTAConfigPatch) -> Self {
        let mut base = PTAConfig::from_preset(self.preset);

        if let Some(v) = patch.mode {
            base.mode = v;
        }
        if let Some(v) = patch.field_sensitive {
            base.field_sensitive = v;
        }
        if let Some(v) = patch.max_iterations {
            base.max_iterations = v;
        }
        if let Some(v) = patch.auto_threshold {
            base.auto_threshold = v;
        }
        if let Some(v) = patch.enable_scc {
            base.enable_scc = v;
        }
        if let Some(v) = patch.enable_wave {
            base.enable_wave = v;
        }
        if let Some(v) = patch.enable_parallel {
            base.enable_parallel = v;
        }

        self.pta = Some(base);
        self.provenance.track_field("pta.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for CloneConfig
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CloneConfigPatch {
    pub types_enabled: Option<Vec<CloneType>>,
    pub type1_min_tokens: Option<usize>,
    pub type1_min_loc: Option<usize>,
    pub type2_min_tokens: Option<usize>,
    pub type2_min_loc: Option<usize>,
    pub type2_rename_similarity: Option<f64>,
    pub type3_min_tokens: Option<usize>,
    pub type3_min_loc: Option<usize>,
    pub type3_gap_threshold: Option<f64>,
    pub type3_similarity: Option<f64>,
    pub type4_min_tokens: Option<usize>,
    pub type4_min_loc: Option<usize>,
    pub type4_semantic_threshold: Option<f64>,
}

impl PipelineConfig {
    /// Apply clone patch
    pub fn clone_patch(mut self, patch: CloneConfigPatch) -> Self {
        let mut base = CloneConfig::from_preset(self.preset);

        if let Some(v) = patch.types_enabled {
            base.types_enabled = v;
        }
        if let Some(v) = patch.type1_min_tokens {
            base.type1.min_tokens = v;
        }
        if let Some(v) = patch.type1_min_loc {
            base.type1.min_loc = v;
        }
        if let Some(v) = patch.type2_min_tokens {
            base.type2.min_tokens = v;
        }
        if let Some(v) = patch.type2_min_loc {
            base.type2.min_loc = v;
        }
        if let Some(v) = patch.type2_rename_similarity {
            base.type2.rename_similarity = v;
        }
        if let Some(v) = patch.type3_min_tokens {
            base.type3.min_tokens = v;
        }
        if let Some(v) = patch.type3_min_loc {
            base.type3.min_loc = v;
        }
        if let Some(v) = patch.type3_gap_threshold {
            base.type3.gap_threshold = v;
        }
        if let Some(v) = patch.type3_similarity {
            base.type3.similarity = v;
        }
        if let Some(v) = patch.type4_min_tokens {
            base.type4.min_tokens = v;
        }
        if let Some(v) = patch.type4_min_loc {
            base.type4.min_loc = v;
        }
        if let Some(v) = patch.type4_semantic_threshold {
            base.type4.semantic_threshold = v;
        }

        self.clone = Some(base);
        self.provenance
            .track_field("clone.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for ChunkingConfig
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ChunkingConfigPatch {
    pub max_chunk_size: Option<usize>,
    pub min_chunk_size: Option<usize>,
    pub overlap_lines: Option<usize>,
    pub enable_semantic: Option<bool>,
    pub respect_scope: Option<bool>,
}

impl PipelineConfig {
    /// Apply chunking patch
    pub fn chunking_patch(mut self, patch: ChunkingConfigPatch) -> Self {
        let mut base = ChunkingConfig::from_preset(self.preset);

        if let Some(v) = patch.max_chunk_size {
            base.max_chunk_size = v;
        }
        if let Some(v) = patch.min_chunk_size {
            base.min_chunk_size = v;
        }
        if let Some(v) = patch.overlap_lines {
            base.overlap_lines = v;
        }
        if let Some(v) = patch.enable_semantic {
            base.enable_semantic = v;
        }
        if let Some(v) = patch.respect_scope {
            base.respect_scope = v;
        }

        self.chunking = Some(base);
        self.provenance
            .track_field("chunking.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for LexicalConfig
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LexicalConfigPatch {
    pub enable_fuzzy: Option<bool>,
    pub fuzzy_distance: Option<usize>,
    pub max_results: Option<usize>,
    pub enable_ngram: Option<bool>,
    pub ngram_size: Option<usize>,
    pub enable_stemming: Option<bool>,
}

impl PipelineConfig {
    /// Apply lexical patch
    pub fn lexical_patch(mut self, patch: LexicalConfigPatch) -> Self {
        let mut base = LexicalConfig::from_preset(self.preset);

        if let Some(v) = patch.enable_fuzzy {
            base.enable_fuzzy = v;
        }
        if let Some(v) = patch.fuzzy_distance {
            base.fuzzy_distance = v;
        }
        if let Some(v) = patch.max_results {
            base.max_results = v;
        }
        if let Some(v) = patch.enable_ngram {
            base.enable_ngram = v;
        }
        if let Some(v) = patch.ngram_size {
            base.ngram_size = v;
        }
        if let Some(v) = patch.enable_stemming {
            base.enable_stemming = v;
        }

        self.lexical = Some(base);
        self.provenance
            .track_field("lexical.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for ParallelConfig
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ParallelConfigPatch {
    pub num_workers: Option<usize>,
    pub batch_size: Option<usize>,
    pub enable_rayon: Option<bool>,
    pub stack_size_mb: Option<usize>,
}

impl PipelineConfig {
    /// Apply parallel patch
    pub fn parallel_patch(mut self, patch: ParallelConfigPatch) -> Self {
        let mut base = ParallelConfig::from_preset(self.preset);

        if let Some(v) = patch.num_workers {
            base.num_workers = v;
        }
        if let Some(v) = patch.batch_size {
            base.batch_size = v;
        }
        if let Some(v) = patch.enable_rayon {
            base.enable_rayon = v;
        }
        if let Some(v) = patch.stack_size_mb {
            base.stack_size_mb = v;
        }

        self.parallel = Some(base);
        self.provenance
            .track_field("parallel.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for PDGConfig (L17)
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PDGConfigPatch {
    pub enabled: Option<bool>,
    pub include_control: Option<bool>,
    pub include_data: Option<bool>,
    pub max_nodes: Option<usize>,
}

impl PipelineConfig {
    /// Apply PDG patch (FFI-friendly alternative to closure)
    pub fn pdg_patch(mut self, patch: PDGConfigPatch) -> Self {
        let mut base = PDGConfig::from_preset(self.preset);

        if let Some(v) = patch.enabled {
            base.enabled = v;
        }
        if let Some(v) = patch.include_control {
            base.include_control = v;
        }
        if let Some(v) = patch.include_data {
            base.include_data = v;
        }
        if let Some(v) = patch.max_nodes {
            base.max_nodes = v;
        }

        self.pdg = Some(base);
        self.provenance.track_field("pdg.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for SlicingConfig (L18)
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SlicingConfigPatch {
    pub enabled: Option<bool>,
    pub max_depth: Option<usize>,
    pub max_function_depth: Option<usize>,
    pub include_control: Option<bool>,
    pub include_data: Option<bool>,
    pub interprocedural: Option<bool>,
    pub strict_mode: Option<bool>,
    pub cache_capacity: Option<usize>,
}

impl PipelineConfig {
    /// Apply slicing patch (FFI-friendly alternative to closure)
    pub fn slicing_patch(mut self, patch: SlicingConfigPatch) -> Self {
        let mut base = SlicingConfig::from_preset(self.preset);

        if let Some(v) = patch.enabled {
            base.enabled = v;
        }
        if let Some(v) = patch.max_depth {
            base.max_depth = v;
        }
        if let Some(v) = patch.max_function_depth {
            base.max_function_depth = v;
        }
        if let Some(v) = patch.include_control {
            base.include_control = v;
        }
        if let Some(v) = patch.include_data {
            base.include_data = v;
        }
        if let Some(v) = patch.interprocedural {
            base.interprocedural = v;
        }
        if let Some(v) = patch.strict_mode {
            base.strict_mode = v;
        }
        if let Some(v) = patch.cache_capacity {
            base.cache_capacity = v;
        }

        self.slicing = Some(base);
        self.provenance
            .track_field("slicing.*", ConfigSource::Builder);
        self
    }
}

/// Patch type for HeapConfig (L7)
///
/// FFI-friendly configuration patch for heap analysis settings.
/// All fields are optional - only specified fields will be applied.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct HeapConfigPatch {
    pub enabled: Option<bool>,
    pub enable_memory_safety: Option<bool>,
    pub enable_ownership: Option<bool>,
    pub enable_escape: Option<bool>,
    pub enable_security: Option<bool>,
    pub enable_context_sensitive: Option<bool>,
    pub context_sensitivity: Option<usize>,
    pub ownership_strict_mode: Option<bool>,
    pub max_heap_objects: Option<usize>,
    /// Types treated as Copy semantics (replaces existing list)
    pub copy_types: Option<Vec<String>>,
    /// Types treated as Move semantics (replaces existing list)
    pub move_types: Option<Vec<String>>,
}

impl PipelineConfig {
    /// Apply heap patch (FFI-friendly alternative to closure)
    ///
    /// # Example (Python via PyO3)
    /// ```python
    /// config = (PipelineConfig.preset(Preset.BALANCED)
    ///     .heap_patch(HeapConfigPatch(
    ///         enable_ownership=True,
    ///         ownership_strict_mode=True,
    ///         copy_types=["int", "float", "MyPrimitive"],
    ///         move_types=["Vec", "String", "MyResource"]
    ///     ))
    ///     .build())
    /// ```
    pub fn heap_patch(mut self, patch: HeapConfigPatch) -> Self {
        let mut base = HeapConfig::from_preset(self.preset);

        if let Some(v) = patch.enabled {
            base.enabled = v;
        }
        if let Some(v) = patch.enable_memory_safety {
            base.enable_memory_safety = v;
        }
        if let Some(v) = patch.enable_ownership {
            base.enable_ownership = v;
        }
        if let Some(v) = patch.enable_escape {
            base.enable_escape = v;
        }
        if let Some(v) = patch.enable_security {
            base.enable_security = v;
        }
        if let Some(v) = patch.enable_context_sensitive {
            base.enable_context_sensitive = v;
        }
        if let Some(v) = patch.context_sensitivity {
            base.context_sensitivity = v;
        }
        if let Some(v) = patch.ownership_strict_mode {
            base.ownership_strict_mode = v;
        }
        if let Some(v) = patch.max_heap_objects {
            base.max_heap_objects = v;
        }
        if let Some(v) = patch.copy_types {
            base.copy_types = v;
        }
        if let Some(v) = patch.move_types {
            base.move_types = v;
        }

        self.heap = Some(base);
        self.provenance.track_field("heap.*", ConfigSource::Builder);
        self
    }
}

#[cfg(test)]
mod tests {
    use super::super::preset::Preset;
    use super::*;

    #[test]
    fn test_taint_patch() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|s| {
                s.enable(super::super::pipeline_config::StageId::Taint)
                    .enable(super::super::pipeline_config::StageId::Pta)
            }) // Taint requires PTA
            .taint_patch(TaintConfigPatch {
                max_depth: Some(50),
                max_paths: Some(1000),
                ..Default::default()
            })
            .build()
            .unwrap();

        let taint = config.taint().unwrap();
        assert_eq!(taint.max_depth, 50);
        assert_eq!(taint.max_paths, 1000);
        // Other fields should have Balanced preset values
        assert!(taint.use_points_to);
    }

    #[test]
    fn test_pta_patch() {
        let config = PipelineConfig::preset(Preset::Fast)
            .stages(|s| s.enable(super::super::pipeline_config::StageId::Pta))
            .pta_patch(PTAConfigPatch {
                mode: Some(PTAMode::Precise),
                ..Default::default()
            })
            .build()
            .unwrap();

        let pta = config.pta().unwrap();
        assert_eq!(pta.mode, PTAMode::Precise);
    }

    #[test]
    fn test_partial_patch() {
        // Only patch specific fields, keep others from preset
        let config = PipelineConfig::preset(Preset::Thorough)
            .stages(|s| {
                s.enable(super::super::pipeline_config::StageId::Taint)
                    .enable(super::super::pipeline_config::StageId::Pta)
            }) // Taint requires PTA
            .taint_patch(TaintConfigPatch {
                max_depth: Some(200),
                // All other fields: None (use preset)
                ..Default::default()
            })
            .build()
            .unwrap();

        let taint = config.taint().unwrap();
        assert_eq!(taint.max_depth, 200);
        // Other fields from Thorough preset
        assert_eq!(taint.max_paths, 5000);
        assert!(taint.use_points_to);
    }

    #[test]
    fn test_clone_patch() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.clone = true;
                s
            })
            .clone_patch(CloneConfigPatch {
                type1_min_tokens: Some(100),
                type1_min_loc: Some(10),
                ..Default::default()
            })
            .build()
            .unwrap();

        let clone_cfg = config.as_inner().clone.as_ref().unwrap();
        assert_eq!(clone_cfg.type1.min_tokens, 100);
        assert_eq!(clone_cfg.type1.min_loc, 10);
    }

    #[test]
    fn test_chunking_patch() {
        let config = PipelineConfig::preset(Preset::Fast)
            .chunking_patch(ChunkingConfigPatch {
                max_chunk_size: Some(1024),
                overlap_lines: Some(10),
                ..Default::default()
            })
            .build()
            .unwrap();

        let chunking = config.as_inner().chunking.as_ref().unwrap();
        assert_eq!(chunking.max_chunk_size, 1024);
        assert_eq!(chunking.overlap_lines, 10);
    }

    #[test]
    fn test_lexical_patch() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .lexical_patch(LexicalConfigPatch {
                enable_fuzzy: Some(false),
                fuzzy_distance: Some(1),
                ..Default::default()
            })
            .build()
            .unwrap();

        let lexical = config.lexical().unwrap();
        assert!(!lexical.enable_fuzzy);
        assert_eq!(lexical.fuzzy_distance, 1);
    }

    #[test]
    fn test_parallel_patch() {
        let config = PipelineConfig::preset(Preset::Thorough)
            .parallel_patch(ParallelConfigPatch {
                num_workers: Some(16),
                enable_rayon: Some(true),
                ..Default::default()
            })
            .build()
            .unwrap();

        let parallel = config.as_inner().parallel.as_ref().unwrap();
        assert_eq!(parallel.num_workers, 16);
        assert!(parallel.enable_rayon);
    }

    #[test]
    fn test_multiple_patches() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.taint = true;
                s.pta = true;
                s.clone = true;
                s
            })
            .taint_patch(TaintConfigPatch {
                max_depth: Some(50),
                ..Default::default()
            })
            .pta_patch(PTAConfigPatch {
                mode: Some(PTAMode::Precise),
                ..Default::default()
            })
            .clone_patch(CloneConfigPatch {
                type1_min_tokens: Some(80),
                ..Default::default()
            })
            .build()
            .unwrap();

        assert_eq!(config.as_inner().taint.as_ref().unwrap().max_depth, 50);
        assert_eq!(
            config.as_inner().pta.as_ref().unwrap().mode,
            PTAMode::Precise
        );
        assert_eq!(
            config.as_inner().clone.as_ref().unwrap().type1.min_tokens,
            80
        );
    }

    #[test]
    fn test_patch_with_all_none() {
        // Patch with all None fields should keep preset values
        let config = PipelineConfig::preset(Preset::Fast)
            .stages(|s| s.enable(super::super::pipeline_config::StageId::Taint))
            .taint_patch(TaintConfigPatch::default())
            .build()
            .unwrap();

        let taint = config.taint().unwrap();
        // Should have Fast preset values
        assert_eq!(taint.max_depth, 10);
    }

    #[test]
    fn test_taint_patch_all_fields() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|s| {
                s.enable(super::super::pipeline_config::StageId::Taint)
                    .enable(super::super::pipeline_config::StageId::Pta)
            })
            .taint_patch(TaintConfigPatch {
                max_depth: Some(75),
                max_paths: Some(2000),
                use_points_to: Some(true),
                field_sensitive: Some(true),
                use_ssa: Some(true),
                detect_sanitizers: Some(true),
                enable_interprocedural: Some(true),
                worklist_max_iterations: Some(200),
            })
            .build()
            .unwrap();

        let taint = config.taint().unwrap();
        assert_eq!(taint.max_depth, 75);
        assert_eq!(taint.max_paths, 2000);
        assert!(taint.use_points_to);
        assert!(taint.field_sensitive);
        assert!(taint.use_ssa);
        assert!(taint.detect_sanitizers);
        assert!(taint.enable_interprocedural);
        assert_eq!(taint.worklist_max_iterations, 200);
    }

    // ==================== PDGConfigPatch Tests ====================

    #[test]
    fn test_pdg_patch_partial() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.flow_graphs = true;
                s.pdg = true;
                s
            })
            .pdg_patch(PDGConfigPatch {
                max_nodes: Some(50000),
                ..Default::default()
            })
            .build()
            .unwrap();

        let pdg = config.pdg().unwrap();
        assert_eq!(pdg.max_nodes, 50000);
        assert!(pdg.include_control); // Default from preset
        assert!(pdg.include_data); // Default from preset
    }

    #[test]
    fn test_pdg_patch_all_fields() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.flow_graphs = true;
                s.pdg = true;
                s
            })
            .pdg_patch(PDGConfigPatch {
                enabled: Some(true),
                include_control: Some(false), // Data-only
                include_data: Some(true),
                max_nodes: Some(75000),
            })
            .build()
            .unwrap();

        let pdg = config.pdg().unwrap();
        assert!(pdg.enabled);
        assert!(!pdg.include_control); // Data-only
        assert!(pdg.include_data);
        assert_eq!(pdg.max_nodes, 75000);
    }

    // ==================== SlicingConfigPatch Tests ====================

    #[test]
    fn test_slicing_patch_partial() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.flow_graphs = true;
                s.pdg = true;
                s.slicing = true;
                s
            })
            .slicing_patch(SlicingConfigPatch {
                max_depth: Some(100),
                ..Default::default()
            })
            .build()
            .unwrap();

        let slicing = config.slicing().unwrap();
        assert_eq!(slicing.max_depth, 100);
        assert!(slicing.include_control); // Default from preset
    }

    #[test]
    fn test_slicing_patch_thin_slicing() {
        // Thin Slicing via patch: include_control=false
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.flow_graphs = true;
                s.pdg = true;
                s.slicing = true;
                s
            })
            .slicing_patch(SlicingConfigPatch {
                include_control: Some(false), // KEY: Thin Slicing
                include_data: Some(true),
                max_depth: Some(100),
                ..Default::default()
            })
            .build()
            .unwrap();

        let slicing = config.slicing().unwrap();
        assert!(!slicing.include_control); // Thin Slicing
        assert!(slicing.include_data);
        assert_eq!(slicing.max_depth, 100);
    }

    #[test]
    fn test_slicing_patch_all_fields() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.flow_graphs = true;
                s.pdg = true;
                s.slicing = true;
                s
            })
            .slicing_patch(SlicingConfigPatch {
                enabled: Some(true),
                max_depth: Some(150),
                max_function_depth: Some(7),
                include_control: Some(false),
                include_data: Some(true),
                interprocedural: Some(true),
                strict_mode: Some(true),
                cache_capacity: Some(8000),
            })
            .build()
            .unwrap();

        let slicing = config.slicing().unwrap();
        assert!(slicing.enabled);
        assert_eq!(slicing.max_depth, 150);
        assert_eq!(slicing.max_function_depth, 7);
        assert!(!slicing.include_control);
        assert!(slicing.include_data);
        assert!(slicing.interprocedural);
        assert!(slicing.strict_mode);
        assert_eq!(slicing.cache_capacity, 8000);
    }

    // ==================== HeapConfigPatch Tests ====================

    #[test]
    fn test_heap_patch_partial() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.pta = true;
                s.heap = true;
                s
            })
            .heap_patch(HeapConfigPatch {
                max_heap_objects: Some(500000),
                ..Default::default()
            })
            .build()
            .unwrap();

        let heap = config.heap().unwrap();
        assert_eq!(heap.max_heap_objects, 500000);
        assert!(heap.enable_memory_safety); // Default from preset
    }

    #[test]
    fn test_heap_patch_all_fields() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.pta = true;
                s.heap = true;
                s
            })
            .heap_patch(HeapConfigPatch {
                enabled: Some(true),
                enable_memory_safety: Some(true),
                enable_ownership: Some(true),
                enable_escape: Some(true),
                enable_security: Some(true),
                enable_context_sensitive: Some(true),
                context_sensitivity: Some(2),
                ownership_strict_mode: Some(true),
                max_heap_objects: Some(750000),
                copy_types: Some(vec!["int".to_string(), "bool".to_string()]),
                move_types: Some(vec!["Vec".to_string(), "String".to_string()]),
            })
            .build()
            .unwrap();

        let heap = config.heap().unwrap();
        assert!(heap.enabled);
        assert!(heap.enable_memory_safety);
        assert!(heap.enable_ownership);
        assert!(heap.enable_escape);
        assert!(heap.enable_security);
        assert!(heap.enable_context_sensitive);
        assert_eq!(heap.context_sensitivity, 2);
        assert!(heap.ownership_strict_mode);
        assert_eq!(heap.max_heap_objects, 750000);
        assert_eq!(heap.copy_types, vec!["int", "bool"]);
        assert_eq!(heap.move_types, vec!["Vec", "String"]);
    }

    // ==================== HeapConfigPatch Edge/Extreme Cases ====================

    #[test]
    fn test_heap_patch_type_lists_only() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.pta = true;
                s.heap = true;
                s
            })
            .heap_patch(HeapConfigPatch {
                copy_types: Some(vec!["MyPrimitive".to_string()]),
                move_types: Some(vec!["MyResource".to_string()]),
                ..Default::default()
            })
            .build()
            .unwrap();

        let heap = config.heap().unwrap();
        // copy_types should be replaced, not merged
        assert_eq!(heap.copy_types, vec!["MyPrimitive"]);
        assert_eq!(heap.move_types, vec!["MyResource"]);
        // Other fields should be from preset
        assert!(heap.enable_memory_safety);
    }

    #[test]
    fn test_heap_patch_empty_type_lists() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.pta = true;
                s.heap = true;
                s
            })
            .heap_patch(HeapConfigPatch {
                copy_types: Some(vec![]),
                move_types: Some(vec![]),
                ..Default::default()
            })
            .build()
            .unwrap();

        let heap = config.heap().unwrap();
        assert!(heap.copy_types.is_empty());
        assert!(heap.move_types.is_empty());
    }

    #[test]
    fn test_heap_patch_extreme_values() {
        // Test boundary values via patch
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.pta = true;
                s.heap = true;
                s
            })
            .heap_patch(HeapConfigPatch {
                context_sensitivity: Some(3),    // max valid
                max_heap_objects: Some(1000000), // max valid
                ..Default::default()
            })
            .build()
            .unwrap();

        let heap = config.heap().unwrap();
        assert_eq!(heap.context_sensitivity, 3);
        assert_eq!(heap.max_heap_objects, 1000000);
    }

    #[test]
    fn test_heap_patch_disable_all_features() {
        let config = PipelineConfig::preset(Preset::Thorough)
            .stages(|mut s| {
                s.pta = true;
                s.heap = true;
                s
            })
            .heap_patch(HeapConfigPatch {
                enabled: Some(false),
                enable_memory_safety: Some(false),
                enable_ownership: Some(false),
                enable_escape: Some(false),
                enable_security: Some(false),
                enable_context_sensitive: Some(false),
                ownership_strict_mode: Some(false),
                ..Default::default()
            })
            .build()
            .unwrap();

        let heap = config.heap().unwrap();
        assert!(!heap.enabled);
        assert!(!heap.enable_memory_safety);
        assert!(!heap.enable_ownership);
        assert!(!heap.enable_escape);
        assert!(!heap.enable_security);
        assert!(!heap.enable_context_sensitive);
        assert!(!heap.ownership_strict_mode);
    }

    #[test]
    fn test_heap_patch_with_large_type_list() {
        let large_copy_types: Vec<String> = (0..50).map(|i| format!("CopyType{}", i)).collect();
        let large_move_types: Vec<String> = (0..50).map(|i| format!("MoveType{}", i)).collect();

        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|mut s| {
                s.pta = true;
                s.heap = true;
                s
            })
            .heap_patch(HeapConfigPatch {
                copy_types: Some(large_copy_types.clone()),
                move_types: Some(large_move_types.clone()),
                ..Default::default()
            })
            .build()
            .unwrap();

        let heap = config.heap().unwrap();
        assert_eq!(heap.copy_types.len(), 50);
        assert_eq!(heap.move_types.len(), 50);
        assert_eq!(heap.copy_types[0], "CopyType0");
        assert_eq!(heap.move_types[49], "MoveType49");
    }
}
