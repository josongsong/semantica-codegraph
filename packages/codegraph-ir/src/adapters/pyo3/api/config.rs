//! Python bindings for RFC-001 Configuration System
//!
//! Provides full Python control over the Rust analysis pipeline configuration.
//!
//! ## Usage from Python
//!
//! ```python
//! from codegraph_ir import PipelineConfig, StageControl, run_pipeline_with_config
//!
//! # Level 1: Preset (90% use cases)
//! config = PipelineConfig.preset("balanced")
//!
//! # Level 2: Stage Override (9% use cases)
//! config = PipelineConfig.preset("fast") \
//!     .with_taint(max_depth=50, max_paths=1000, use_points_to=True) \
//!     .with_pta(mode="precise", field_sensitive=True) \
//!     .with_stages(taint=True, pta=True, slicing=True)
//!
//! # Execute pipeline
//! result = run_pipeline_with_config("/path/to/repo", "my-repo", config)
//! ```

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;
use std::path::PathBuf;

use crate::config::{
    preset::Preset, ChunkingConfig, HeapConfig, PDGConfig,
    PTAConfig, PTAMode, ParallelConfig, PipelineConfig, SlicingConfig, StageControl, TaintConfig,
};

// ═══════════════════════════════════════════════════════════════════════════
// PyStageControl - Stage on/off switches
// ═══════════════════════════════════════════════════════════════════════════

/// Python wrapper for StageControl
///
/// Controls which pipeline stages are enabled.
///
/// Example:
/// ```python
/// stages = StageControl()
/// stages.taint = True
/// stages.pta = True
/// stages.slicing = True
/// ```
#[pyclass(name = "StageControl")]
#[derive(Clone)]
pub struct PyStageControl {
    inner: StageControl,
}

#[pymethods]
impl PyStageControl {
    /// Create default stage control (parsing, chunking, lexical enabled)
    #[new]
    fn new() -> Self {
        Self {
            inner: StageControl::default(),
        }
    }

    /// Create with all stages enabled
    #[staticmethod]
    fn all() -> Self {
        Self {
            inner: StageControl::all(),
        }
    }

    /// Create security-focused stages (taint, pta, heap, slicing, concurrency)
    #[staticmethod]
    fn security() -> Self {
        Self {
            inner: StageControl::security(),
        }
    }

    // Phase 1: Basic
    #[getter]
    fn parsing(&self) -> bool {
        self.inner.parsing
    }
    #[setter]
    fn set_parsing(&mut self, v: bool) {
        self.inner.parsing = v;
    }

    #[getter]
    fn chunking(&self) -> bool {
        self.inner.chunking
    }
    #[setter]
    fn set_chunking(&mut self, v: bool) {
        self.inner.chunking = v;
    }

    #[getter]
    fn lexical(&self) -> bool {
        self.inner.lexical
    }
    #[setter]
    fn set_lexical(&mut self, v: bool) {
        self.inner.lexical = v;
    }

    // Phase 2: Analysis
    #[getter]
    fn cross_file(&self) -> bool {
        self.inner.cross_file
    }
    #[setter]
    fn set_cross_file(&mut self, v: bool) {
        self.inner.cross_file = v;
    }

    #[getter]
    fn clone(&self) -> bool {
        self.inner.clone
    }
    #[setter]
    fn set_clone(&mut self, v: bool) {
        self.inner.clone = v;
    }

    #[getter]
    fn pta(&self) -> bool {
        self.inner.pta
    }
    #[setter]
    fn set_pta(&mut self, v: bool) {
        self.inner.pta = v;
    }

    #[getter]
    fn flow_graphs(&self) -> bool {
        self.inner.flow_graphs
    }
    #[setter]
    fn set_flow_graphs(&mut self, v: bool) {
        self.inner.flow_graphs = v;
    }

    #[getter]
    fn type_inference(&self) -> bool {
        self.inner.type_inference
    }
    #[setter]
    fn set_type_inference(&mut self, v: bool) {
        self.inner.type_inference = v;
    }

    // Phase 3: Advanced
    #[getter]
    fn symbols(&self) -> bool {
        self.inner.symbols
    }
    #[setter]
    fn set_symbols(&mut self, v: bool) {
        self.inner.symbols = v;
    }

    #[getter]
    fn effects(&self) -> bool {
        self.inner.effects
    }
    #[setter]
    fn set_effects(&mut self, v: bool) {
        self.inner.effects = v;
    }

    #[getter]
    fn taint(&self) -> bool {
        self.inner.taint
    }
    #[setter]
    fn set_taint(&mut self, v: bool) {
        self.inner.taint = v;
    }

    #[getter]
    fn repomap(&self) -> bool {
        self.inner.repomap
    }
    #[setter]
    fn set_repomap(&mut self, v: bool) {
        self.inner.repomap = v;
    }

    #[getter]
    fn heap(&self) -> bool {
        self.inner.heap
    }
    #[setter]
    fn set_heap(&mut self, v: bool) {
        self.inner.heap = v;
    }

    #[getter]
    fn pdg(&self) -> bool {
        self.inner.pdg
    }
    #[setter]
    fn set_pdg(&mut self, v: bool) {
        self.inner.pdg = v;
    }

    #[getter]
    fn concurrency(&self) -> bool {
        self.inner.concurrency
    }
    #[setter]
    fn set_concurrency(&mut self, v: bool) {
        self.inner.concurrency = v;
    }

    #[getter]
    fn slicing(&self) -> bool {
        self.inner.slicing
    }
    #[setter]
    fn set_slicing(&mut self, v: bool) {
        self.inner.slicing = v;
    }

    fn __repr__(&self) -> String {
        let enabled: Vec<&str> = vec![
            if self.inner.parsing { "parsing" } else { "" },
            if self.inner.chunking { "chunking" } else { "" },
            if self.inner.lexical { "lexical" } else { "" },
            if self.inner.cross_file { "cross_file" } else { "" },
            if self.inner.clone { "clone" } else { "" },
            if self.inner.pta { "pta" } else { "" },
            if self.inner.flow_graphs { "flow_graphs" } else { "" },
            if self.inner.taint { "taint" } else { "" },
            if self.inner.heap { "heap" } else { "" },
            if self.inner.pdg { "pdg" } else { "" },
            if self.inner.slicing { "slicing" } else { "" },
        ]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect();

        format!("StageControl({})", enabled.join(", "))
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// PyPipelineConfig - Main configuration
// ═══════════════════════════════════════════════════════════════════════════

/// Python wrapper for PipelineConfig
///
/// Main configuration for the analysis pipeline.
///
/// Example:
/// ```python
/// # Level 1: Preset
/// config = PipelineConfig.preset("balanced")
///
/// # Level 2: Override stages
/// config = PipelineConfig.preset("fast") \
///     .with_taint(max_depth=50, use_points_to=True) \
///     .with_pta(mode="precise") \
///     .with_stages(taint=True, pta=True)
///
/// # Build and validate
/// validated = config.build()
/// ```
#[pyclass(name = "PipelineConfig")]
#[derive(Clone)]
pub struct PyPipelineConfig {
    preset: String,
    stages: PyStageControl,
    strict_mode: bool,
    // Stage-specific overrides (stored as Python dicts, converted on build)
    taint_override: Option<HashMap<String, PyObject>>,
    pta_override: Option<HashMap<String, PyObject>>,
    heap_override: Option<HashMap<String, PyObject>>,
    pdg_override: Option<HashMap<String, PyObject>>,
    slicing_override: Option<HashMap<String, PyObject>>,
    chunking_override: Option<HashMap<String, PyObject>>,
    parallel_override: Option<HashMap<String, PyObject>>,
}

#[pymethods]
impl PyPipelineConfig {
    /// Create configuration from preset
    ///
    /// Args:
    ///     preset_name: "fast", "balanced", or "thorough"
    ///
    /// Returns:
    ///     PipelineConfig instance
    #[staticmethod]
    fn preset(preset_name: &str) -> PyResult<Self> {
        let preset = match preset_name.to_lowercase().as_str() {
            "fast" => "fast",
            "balanced" => "balanced",
            "thorough" => "thorough",
            "custom" => "custom",
            _ => {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Unknown preset: {}. Use 'fast', 'balanced', or 'thorough'",
                    preset_name
                )));
            }
        };

        Ok(Self {
            preset: preset.to_string(),
            stages: PyStageControl::new(),
            strict_mode: false,
            taint_override: None,
            pta_override: None,
            heap_override: None,
            pdg_override: None,
            slicing_override: None,
            chunking_override: None,
            parallel_override: None,
        })
    }

    /// Enable strict mode (errors on disabled stage overrides)
    fn set_strict_mode(&mut self, enabled: bool) {
        self.strict_mode = enabled;
    }

    /// Configure stage control (modifies in place)
    ///
    /// Example:
    /// ```python
    /// config.set_stages(taint=True, pta=True, slicing=True)
    /// ```
    #[pyo3(signature = (**kwargs))]
    fn set_stages(&mut self, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            // Apply kwargs to stages
            if let Ok(Some(v)) = kw.get_item("parsing") {
                self.stages.inner.parsing = v.extract().unwrap_or(true);
            }
            if let Ok(Some(v)) = kw.get_item("chunking") {
                self.stages.inner.chunking = v.extract().unwrap_or(true);
            }
            if let Ok(Some(v)) = kw.get_item("lexical") {
                self.stages.inner.lexical = v.extract().unwrap_or(true);
            }
            if let Ok(Some(v)) = kw.get_item("cross_file") {
                self.stages.inner.cross_file = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("clone") {
                self.stages.inner.clone = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("pta") {
                self.stages.inner.pta = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("flow_graphs") {
                self.stages.inner.flow_graphs = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("type_inference") {
                self.stages.inner.type_inference = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("symbols") {
                self.stages.inner.symbols = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("effects") {
                self.stages.inner.effects = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("taint") {
                self.stages.inner.taint = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("repomap") {
                self.stages.inner.repomap = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("heap") {
                self.stages.inner.heap = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("pdg") {
                self.stages.inner.pdg = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("concurrency") {
                self.stages.inner.concurrency = v.extract().unwrap_or(false);
            }
            if let Ok(Some(v)) = kw.get_item("slicing") {
                self.stages.inner.slicing = v.extract().unwrap_or(false);
            }
        }
    }

    /// Set stages from StageControl instance
    fn set_stages_from(&mut self, stages: &PyStageControl) {
        self.stages = Clone::clone(stages);
    }

    /// Override taint analysis configuration
    ///
    /// Args:
    ///     max_depth: Maximum call chain depth (1-1000)
    ///     max_paths: Maximum taint paths (1-100000)
    ///     use_points_to: Use PTA for precision
    ///     field_sensitive: Track field-level taint
    ///     use_ssa: Use SSA form
    ///     detect_sanitizers: Detect sanitizer functions
    ///     enable_interprocedural: Cross-function analysis
    ///     ifds_enabled: Use IFDS framework
    ///     implicit_flow_enabled: Track control flow taint
    ///     context_sensitive: Call-site sensitivity
    ///     path_sensitive: Path-conditioned analysis
    ///     timeout_seconds: Analysis timeout (0=unlimited)
    #[pyo3(signature = (**kwargs))]
    fn set_taint(&mut self, py: Python, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            let mut override_map = HashMap::new();
            for (k, v) in kw.iter() {
                if let Ok(key) = k.extract::<String>() {
                    override_map.insert(key, v.into_py(py));
                }
            }
            self.taint_override = Some(override_map);
        }
    }

    /// Override points-to analysis configuration
    ///
    /// Args:
    ///     mode: "fast", "precise", "hybrid", or "auto"
    ///     field_sensitive: Field-sensitive analysis
    ///     max_iterations: Max Andersen iterations
    ///     auto_threshold: Size threshold for Auto mode
    ///     enable_scc: SCC optimization
    ///     enable_wave: Wave propagation
    ///     enable_parallel: Parallel processing
    #[pyo3(signature = (**kwargs))]
    fn set_pta(&mut self, py: Python, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            let mut override_map = HashMap::new();
            for (k, v) in kw.iter() {
                if let Ok(key) = k.extract::<String>() {
                    override_map.insert(key, v.into_py(py));
                }
            }
            self.pta_override = Some(override_map);
        }
    }

    /// Override heap analysis configuration
    ///
    /// Args:
    ///     enable_memory_safety: Null/UAF/double-free detection
    ///     enable_ownership: Use-after-move detection
    ///     enable_escape: Escape analysis (RFC-074)
    ///     enable_security: OWASP Top 10
    ///     enable_context_sensitive: k-CFA analysis
    ///     context_sensitivity: k value (0-3)
    ///     ownership_strict_mode: Strict move checking
    ///     max_heap_objects: Heap object limit
    ///     enable_symbolic_memory: KLEE-style symbolic
    ///     enable_concolic: Concolic testing
    #[pyo3(signature = (**kwargs))]
    fn set_heap(&mut self, py: Python, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            let mut override_map = HashMap::new();
            for (k, v) in kw.iter() {
                if let Ok(key) = k.extract::<String>() {
                    override_map.insert(key, v.into_py(py));
                }
            }
            self.heap_override = Some(override_map);
        }
    }

    /// Override PDG configuration
    ///
    /// Args:
    ///     include_control: Include control dependencies
    ///     include_data: Include data dependencies
    ///     max_nodes: Maximum PDG nodes per function
    #[pyo3(signature = (**kwargs))]
    fn set_pdg(&mut self, py: Python, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            let mut override_map = HashMap::new();
            for (k, v) in kw.iter() {
                if let Ok(key) = k.extract::<String>() {
                    override_map.insert(key, v.into_py(py));
                }
            }
            self.pdg_override = Some(override_map);
        }
    }

    /// Override slicing configuration
    ///
    /// Args:
    ///     max_depth: Maximum slice traversal depth
    ///     max_function_depth: Interprocedural depth
    ///     include_control: Include control deps (False = Thin Slicing)
    ///     include_data: Include data dependencies
    ///     interprocedural: Cross-function slicing
    ///     strict_mode: Error on missing nodes
    ///     cache_capacity: LRU cache size
    #[pyo3(signature = (**kwargs))]
    fn set_slicing(&mut self, py: Python, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            let mut override_map = HashMap::new();
            for (k, v) in kw.iter() {
                if let Ok(key) = k.extract::<String>() {
                    override_map.insert(key, v.into_py(py));
                }
            }
            self.slicing_override = Some(override_map);
        }
    }

    /// Override chunking configuration
    ///
    /// Args:
    ///     max_chunk_size: Maximum chunk characters
    ///     min_chunk_size: Minimum chunk characters
    ///     overlap_lines: Overlap between chunks
    ///     enable_semantic: Semantic-aware chunking
    ///     respect_scope: Respect scope boundaries
    #[pyo3(signature = (**kwargs))]
    fn set_chunking(&mut self, py: Python, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            let mut override_map = HashMap::new();
            for (k, v) in kw.iter() {
                if let Ok(key) = k.extract::<String>() {
                    override_map.insert(key, v.into_py(py));
                }
            }
            self.chunking_override = Some(override_map);
        }
    }

    /// Override parallel configuration
    ///
    /// Args:
    ///     num_workers: Worker count (0=auto)
    ///     batch_size: Parallel batch size
    ///     enable_rayon: Use Rayon
    ///     stack_size_mb: Thread stack size
    #[pyo3(signature = (**kwargs))]
    fn set_parallel(&mut self, py: Python, kwargs: Option<&PyDict>) {
        if let Some(kw) = kwargs {
            let mut override_map = HashMap::new();
            for (k, v) in kw.iter() {
                if let Ok(key) = k.extract::<String>() {
                    override_map.insert(key, v.into_py(py));
                }
            }
            self.parallel_override = Some(override_map);
        }
    }

    /// Get stages
    #[getter]
    fn get_stages(&self) -> PyStageControl {
        Clone::clone(&self.stages)
    }

    /// Get preset name
    #[getter]
    fn preset_name(&self) -> &str {
        &self.preset
    }

    /// Build and validate the configuration (returns validated config bytes)
    ///
    /// Returns:
    ///     Validated configuration (msgpack bytes for internal use)
    fn build(&self, py: Python) -> PyResult<Vec<u8>> {
        let rust_config = self.to_rust_config(py)?;

        // Validate
        let validated = rust_config.build().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Configuration validation failed: {}",
                e
            ))
        })?;

        // Serialize to msgpack
        rmp_serde::to_vec(&validated.to_yaml().unwrap_or_default()).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Configuration serialization failed: {}",
                e
            ))
        })
    }

    /// Export configuration to YAML string
    fn to_yaml(&self, py: Python) -> PyResult<String> {
        let rust_config = self.to_rust_config(py)?;
        rust_config.to_yaml().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "YAML export failed: {}",
                e
            ))
        })
    }

    /// Get a human-readable summary
    fn describe(&self, py: Python) -> PyResult<String> {
        let rust_config = self.to_rust_config(py)?;
        Ok(rust_config.describe())
    }

    fn __repr__(&self) -> String {
        format!(
            "PipelineConfig(preset='{}', stages={})",
            self.preset,
            self.stages.__repr__()
        )
    }
}

impl PyPipelineConfig {
    /// Convert to Rust PipelineConfig
    fn to_rust_config(&self, py: Python) -> PyResult<PipelineConfig> {
        let preset = match self.preset.as_str() {
            "fast" => Preset::Fast,
            "balanced" => Preset::Balanced,
            "thorough" => Preset::Thorough,
            "custom" => Preset::Custom,
            _ => Preset::Balanced,
        };

        let mut config = PipelineConfig::preset(preset)
            .strict_mode(self.strict_mode)
            .with_stages(|_| self.stages.inner.clone());

        // Apply taint overrides
        if let Some(ref overrides) = self.taint_override {
            config = config.taint(|mut c| {
                Self::apply_taint_overrides(py, &mut c, overrides);
                c
            });
        }

        // Apply PTA overrides
        if let Some(ref overrides) = self.pta_override {
            config = config.pta(|mut c| {
                Self::apply_pta_overrides(py, &mut c, overrides);
                c
            });
        }

        // Apply Heap overrides
        if let Some(ref overrides) = self.heap_override {
            config = config.heap(|mut c| {
                Self::apply_heap_overrides(py, &mut c, overrides);
                c
            });
        }

        // Apply PDG overrides
        if let Some(ref overrides) = self.pdg_override {
            config = config.pdg(|mut c| {
                Self::apply_pdg_overrides(py, &mut c, overrides);
                c
            });
        }

        // Apply Slicing overrides
        if let Some(ref overrides) = self.slicing_override {
            config = config.slicing(|mut c| {
                Self::apply_slicing_overrides(py, &mut c, overrides);
                c
            });
        }

        // Apply Chunking overrides
        if let Some(ref overrides) = self.chunking_override {
            config = config.chunking(|mut c| {
                Self::apply_chunking_overrides(py, &mut c, overrides);
                c
            });
        }

        // Apply Parallel overrides
        if let Some(ref overrides) = self.parallel_override {
            config = config.parallel(|mut c| {
                Self::apply_parallel_overrides(py, &mut c, overrides);
                c
            });
        }

        Ok(config)
    }

    fn apply_taint_overrides(py: Python, cfg: &mut TaintConfig, overrides: &HashMap<String, PyObject>) {
        if let Some(v) = overrides.get("max_depth") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.max_depth = n;
            }
        }
        if let Some(v) = overrides.get("max_paths") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.max_paths = n;
            }
        }
        if let Some(v) = overrides.get("use_points_to") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.use_points_to = b;
            }
        }
        if let Some(v) = overrides.get("field_sensitive") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.field_sensitive = b;
            }
        }
        if let Some(v) = overrides.get("use_ssa") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.use_ssa = b;
            }
        }
        if let Some(v) = overrides.get("detect_sanitizers") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.detect_sanitizers = b;
            }
        }
        if let Some(v) = overrides.get("enable_interprocedural") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_interprocedural = b;
            }
        }
        if let Some(v) = overrides.get("ifds_enabled") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.ifds_enabled = b;
            }
        }
        if let Some(v) = overrides.get("implicit_flow_enabled") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.implicit_flow_enabled = b;
            }
        }
        if let Some(v) = overrides.get("context_sensitive") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.context_sensitive = b;
            }
        }
        if let Some(v) = overrides.get("path_sensitive") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.path_sensitive = b;
            }
        }
        if let Some(v) = overrides.get("timeout_seconds") {
            if let Ok(n) = v.extract::<u64>(py) {
                cfg.timeout_seconds = n;
            }
        }
    }

    fn apply_pta_overrides(py: Python, cfg: &mut PTAConfig, overrides: &HashMap<String, PyObject>) {
        if let Some(v) = overrides.get("mode") {
            if let Ok(s) = v.extract::<String>(py) {
                cfg.mode = match s.to_lowercase().as_str() {
                    "fast" => PTAMode::Fast,
                    "precise" => PTAMode::Precise,
                    "hybrid" => PTAMode::Hybrid,
                    "auto" => PTAMode::Auto,
                    _ => cfg.mode,
                };
            }
        }
        if let Some(v) = overrides.get("field_sensitive") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.field_sensitive = b;
            }
        }
        if let Some(v) = overrides.get("max_iterations") {
            if let Ok(n) = v.extract::<Option<usize>>(py) {
                cfg.max_iterations = n;
            }
        }
        if let Some(v) = overrides.get("auto_threshold") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.auto_threshold = n;
            }
        }
        if let Some(v) = overrides.get("enable_scc") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_scc = b;
            }
        }
        if let Some(v) = overrides.get("enable_wave") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_wave = b;
            }
        }
        if let Some(v) = overrides.get("enable_parallel") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_parallel = b;
            }
        }
    }

    fn apply_heap_overrides(py: Python, cfg: &mut HeapConfig, overrides: &HashMap<String, PyObject>) {
        if let Some(v) = overrides.get("enable_memory_safety") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_memory_safety = b;
            }
        }
        if let Some(v) = overrides.get("enable_ownership") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_ownership = b;
            }
        }
        if let Some(v) = overrides.get("enable_escape") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_escape = b;
            }
        }
        if let Some(v) = overrides.get("enable_security") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_security = b;
            }
        }
        if let Some(v) = overrides.get("enable_context_sensitive") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_context_sensitive = b;
            }
        }
        if let Some(v) = overrides.get("context_sensitivity") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.context_sensitivity = n;
            }
        }
        if let Some(v) = overrides.get("ownership_strict_mode") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.ownership_strict_mode = b;
            }
        }
        if let Some(v) = overrides.get("max_heap_objects") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.max_heap_objects = n;
            }
        }
        if let Some(v) = overrides.get("enable_symbolic_memory") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_symbolic_memory = b;
            }
        }
        if let Some(v) = overrides.get("enable_concolic") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_concolic = b;
            }
        }
    }

    fn apply_pdg_overrides(py: Python, cfg: &mut PDGConfig, overrides: &HashMap<String, PyObject>) {
        if let Some(v) = overrides.get("include_control") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.include_control = b;
            }
        }
        if let Some(v) = overrides.get("include_data") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.include_data = b;
            }
        }
        if let Some(v) = overrides.get("max_nodes") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.max_nodes = n;
            }
        }
    }

    fn apply_slicing_overrides(py: Python, cfg: &mut SlicingConfig, overrides: &HashMap<String, PyObject>) {
        if let Some(v) = overrides.get("max_depth") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.max_depth = n;
            }
        }
        if let Some(v) = overrides.get("max_function_depth") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.max_function_depth = n;
            }
        }
        if let Some(v) = overrides.get("include_control") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.include_control = b;
            }
        }
        if let Some(v) = overrides.get("include_data") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.include_data = b;
            }
        }
        if let Some(v) = overrides.get("interprocedural") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.interprocedural = b;
            }
        }
        if let Some(v) = overrides.get("strict_mode") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.strict_mode = b;
            }
        }
        if let Some(v) = overrides.get("cache_capacity") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.cache_capacity = n;
            }
        }
    }

    fn apply_chunking_overrides(py: Python, cfg: &mut ChunkingConfig, overrides: &HashMap<String, PyObject>) {
        if let Some(v) = overrides.get("max_chunk_size") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.max_chunk_size = n;
            }
        }
        if let Some(v) = overrides.get("min_chunk_size") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.min_chunk_size = n;
            }
        }
        if let Some(v) = overrides.get("overlap_lines") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.overlap_lines = n;
            }
        }
        if let Some(v) = overrides.get("enable_semantic") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_semantic = b;
            }
        }
        if let Some(v) = overrides.get("respect_scope") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.respect_scope = b;
            }
        }
    }

    fn apply_parallel_overrides(py: Python, cfg: &mut ParallelConfig, overrides: &HashMap<String, PyObject>) {
        if let Some(v) = overrides.get("num_workers") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.num_workers = n;
            }
        }
        if let Some(v) = overrides.get("batch_size") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.batch_size = n;
            }
        }
        if let Some(v) = overrides.get("enable_rayon") {
            if let Ok(b) = v.extract::<bool>(py) {
                cfg.enable_rayon = b;
            }
        }
        if let Some(v) = overrides.get("stack_size_mb") {
            if let Ok(n) = v.extract::<usize>(py) {
                cfg.stack_size_mb = n;
            }
        }
    }

    /// Get Rust PipelineConfig for internal use
    pub fn get_rust_config(&self, py: Python) -> PyResult<PipelineConfig> {
        self.to_rust_config(py)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// run_pipeline_with_config - Main entry point for config-based execution
// ═══════════════════════════════════════════════════════════════════════════

/// Run IR indexing pipeline with custom configuration
///
/// This is the SOTA entry point for full control over the analysis pipeline.
/// The Rust engine is unchanged - Python controls everything via config.
///
/// Args:
///     repo_root: Repository root path
///     repo_name: Repository name
///     config: PipelineConfig instance
///     file_paths: Optional list of specific files to process
///
/// Returns:
///     Pipeline result dict (nodes, edges, chunks, symbols, analysis results)
///
/// Example:
/// ```python
/// from codegraph_ir import PipelineConfig, run_pipeline_with_config
///
/// # Create custom config
/// config = PipelineConfig.preset("balanced") \
///     .with_stages(taint=True, pta=True, slicing=True, pdg=True, flow_graphs=True) \
///     .with_taint(max_depth=100, use_points_to=True, ifds_enabled=True) \
///     .with_pta(mode="precise", field_sensitive=True) \
///     .with_slicing(include_control=False)  # Thin Slicing
///
/// # Run pipeline
/// result = run_pipeline_with_config("/path/to/repo", "my-repo", config)
///
/// # Access results
/// print(f"Nodes: {len(result['nodes'])}")
/// print(f"Taint flows: {result['taint_results']}")
/// ```
#[pyfunction]
#[pyo3(signature = (repo_root, repo_name, config, file_paths = None))]
pub fn run_pipeline_with_config(
    py: Python,
    repo_root: String,
    repo_name: String,
    config: &PyPipelineConfig,
    file_paths: Option<Vec<String>>,
) -> PyResult<Py<PyDict>> {
    use crate::pipeline::{
        E2EPipelineConfig, IRIndexingOrchestrator, IndexingMode, RepoInfo,
    };
    use std::time::Instant;

    // Initialize Rayon
    crate::init_rayon();

    let total_start = Instant::now();

    // Convert PyPipelineConfig to Rust config
    let rust_config = config.get_rust_config(py)?;

    // Build validated config
    let validated = rust_config.build().map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Configuration validation failed: {}",
            e
        ))
    })?;

    // Build E2E pipeline config using RFC-001 ValidatedConfig
    let e2e_config = E2EPipelineConfig::with_config(Clone::clone(&validated))
        .repo_root(PathBuf::from(&repo_root))
        .repo_name(repo_name.clone())
        .indexing_mode(IndexingMode::Full)
        .mmap_threshold(1024 * 1024);

    // Set file paths if provided
    let e2e_config = if let Some(fps) = file_paths {
        e2e_config.file_paths(fps.into_iter().map(PathBuf::from).collect())
    } else {
        e2e_config
    };

    // Execute pipeline with GIL released
    let result = py
        .allow_threads(|| {
            let orchestrator = IRIndexingOrchestrator::new(e2e_config);
            orchestrator.execute()
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.message))?;

    let process_time = total_start.elapsed();

    // Convert result to Python dict
    let convert_start = Instant::now();
    let py_result = convert_pipeline_result_to_python(py, result, &validated)?;
    let convert_time = convert_start.elapsed();

    let total_time = total_start.elapsed();

    // PROFILING
    eprintln!(
        "[run_pipeline_with_config] Total: {:.2}ms",
        total_time.as_secs_f64() * 1000.0
    );
    eprintln!(
        "  ├─ Rust Processing: {:.2}ms ({:.1}%)",
        process_time.as_secs_f64() * 1000.0,
        process_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );
    eprintln!(
        "  └─ Convert Rust→Python: {:.2}ms ({:.1}%)",
        convert_time.as_secs_f64() * 1000.0,
        convert_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );

    Ok(py_result)
}

/// Convert pipeline result to Python dict
fn convert_pipeline_result_to_python(
    py: Python,
    result: crate::pipeline::E2EPipelineResult,
    validated: &crate::config::ValidatedConfig,
) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);

    // Config info
    let config_dict = PyDict::new(py);
    config_dict.set_item("description", validated.describe())?;
    dict.set_item("config", config_dict)?;

    // Convert nodes
    let py_nodes = PyList::new(
        py,
        result.nodes.iter().map(|n| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &n.id);
            let _ = d.set_item("kind", format!("{:?}", n.kind));
            let _ = d.set_item("fqn", &n.fqn);
            let _ = d.set_item("file_path", &n.file_path);
            let _ = d.set_item("name", &n.name);

            let span_dict = PyDict::new(py);
            let _ = span_dict.set_item("start_line", n.span.start_line);
            let _ = span_dict.set_item("start_col", n.span.start_col);
            let _ = span_dict.set_item("end_line", n.span.end_line);
            let _ = span_dict.set_item("end_col", n.span.end_col);
            let _ = d.set_item("span", span_dict);
            d
        }),
    );
    dict.set_item("nodes", py_nodes)?;

    // Convert edges
    let py_edges = PyList::new(
        py,
        result.edges.iter().map(|e| {
            let d = PyDict::new(py);
            let _ = d.set_item("source_id", &e.source_id);
            let _ = d.set_item("target_id", &e.target_id);
            let _ = d.set_item("kind", format!("{:?}", e.kind));
            d
        }),
    );
    dict.set_item("edges", py_edges)?;

    // Convert chunks
    let py_chunks = PyList::new(
        py,
        result.chunks.iter().map(|c| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &c.id);
            let _ = d.set_item("file_path", &c.file_path);
            let _ = d.set_item("content", &c.content);
            let _ = d.set_item("start_line", c.start_line);
            let _ = d.set_item("end_line", c.end_line);
            let _ = d.set_item("chunk_type", &c.chunk_type);
            let _ = d.set_item("symbol_id", &c.symbol_id);
            d
        }),
    );
    dict.set_item("chunks", py_chunks)?;

    // Convert symbols
    let py_symbols = PyList::new(
        py,
        result.symbols.iter().map(|s| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &s.id);
            let _ = d.set_item("name", &s.name);
            let _ = d.set_item("kind", &s.kind);
            let _ = d.set_item("file_path", &s.file_path);
            let _ = d.set_item("definition", (s.definition.0, s.definition.1));
            let _ = d.set_item("documentation", &s.documentation);
            d
        }),
    );
    dict.set_item("symbols", py_symbols)?;

    // Convert occurrences
    let py_occurrences = PyList::new(
        py,
        result.occurrences.iter().map(|o| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &o.id);
            let _ = d.set_item("symbol_id", &o.symbol_id);
            let _ = d.set_item("file_path", &o.file_path);
            let _ = d.set_item("roles", o.roles);
            let _ = d.set_item("importance_score", o.importance_score);

            let span_dict = PyDict::new(py);
            let _ = span_dict.set_item("start_line", o.span.start_line);
            let _ = span_dict.set_item("start_col", o.span.start_col);
            let _ = span_dict.set_item("end_line", o.span.end_line);
            let _ = span_dict.set_item("end_col", o.span.end_col);
            let _ = d.set_item("span", span_dict);
            d
        }),
    );
    dict.set_item("occurrences", py_occurrences)?;

    // Convert taint results
    let py_taint_results = PyList::new(
        py,
        result.taint_results.iter().map(|t| {
            let d = PyDict::new(py);
            let _ = d.set_item("function_id", &t.function_id);
            let _ = d.set_item("sources_found", t.sources_found);
            let _ = d.set_item("sinks_found", t.sinks_found);
            let _ = d.set_item("taint_flows", t.taint_flows);
            d
        }),
    );
    dict.set_item("taint_results", py_taint_results)?;

    // Convert stats
    let py_stats = PyDict::new(py);
    py_stats.set_item("total_duration_ms", result.stats.total_duration.as_millis())?;
    py_stats.set_item("files_processed", result.stats.files_processed)?;
    py_stats.set_item("files_cached", result.stats.files_cached)?;
    py_stats.set_item("files_failed", result.stats.files_failed)?;
    py_stats.set_item("total_loc", result.stats.total_loc)?;
    py_stats.set_item("loc_per_second", result.stats.loc_per_second)?;
    py_stats.set_item("cache_hit_rate", result.stats.cache_hit_rate)?;

    let py_stage_durations = PyDict::new(py);
    for (stage, duration) in &result.stats.stage_durations {
        py_stage_durations.set_item(stage, duration.as_millis())?;
    }
    py_stats.set_item("stage_durations", py_stage_durations)?;

    let py_errors = PyList::new(py, result.stats.errors.iter().map(|e| e.as_str()));
    py_stats.set_item("errors", py_errors)?;

    dict.set_item("stats", py_stats)?;

    // Points-to summary
    if let Some(ref pts) = result.points_to_summary {
        let py_pts = PyDict::new(py);
        py_pts.set_item("variables_count", pts.variables_count)?;
        py_pts.set_item("allocations_count", pts.allocations_count)?;
        py_pts.set_item("constraints_count", pts.constraints_count)?;
        py_pts.set_item("alias_pairs", pts.alias_pairs)?;
        py_pts.set_item("mode_used", &pts.mode_used)?;
        py_pts.set_item("duration_ms", pts.duration_ms)?;
        dict.set_item("points_to_summary", py_pts)?;
    } else {
        dict.set_item("points_to_summary", py.None())?;
    }

    // RepoMap snapshot
    if let Some(ref snapshot) = result.repomap_snapshot {
        let py_snapshot = PyDict::new(py);
        py_snapshot.set_item("repo_id", &snapshot.repo_id)?;
        py_snapshot.set_item("snapshot_id", &snapshot.snapshot_id)?;
        py_snapshot.set_item("total_nodes", snapshot.total_nodes)?;
        py_snapshot.set_item("total_loc", snapshot.total_loc)?;
        py_snapshot.set_item("total_symbols", snapshot.total_symbols)?;
        py_snapshot.set_item("total_files", snapshot.total_files)?;
        dict.set_item("repomap_snapshot", py_snapshot)?;
    } else {
        dict.set_item("repomap_snapshot", py.None())?;
    }

    Ok(dict.into())
}

// ═══════════════════════════════════════════════════════════════════════════
// Python API Registration
// ═══════════════════════════════════════════════════════════════════════════

/// Register config classes and functions
pub fn register_config_api(m: &PyModule) -> PyResult<()> {
    m.add_class::<PyStageControl>()?;
    m.add_class::<PyPipelineConfig>()?;
    m.add_function(pyo3::wrap_pyfunction!(run_pipeline_with_config, m)?)?;
    Ok(())
}
