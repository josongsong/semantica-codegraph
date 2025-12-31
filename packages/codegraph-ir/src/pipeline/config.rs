//! Pipeline configuration

#[derive(Debug, Clone)]
pub struct PipelineConfig {
    /// Enable BFG/CFG generation
    pub enable_flow_graph: bool,
    /// Enable type resolution
    pub enable_type_resolution: bool,
    /// Enable DFG generation
    pub enable_dfg: bool,
    /// Enable SSA construction
    pub enable_ssa: bool,
    /// Enable occurrence generation (SCIP-compatible)
    /// When enabled, occurrences are generated during IR build (L1)
    /// instead of in a separate Python pass (L2)
    pub enable_occurrences: bool,
    /// Number of parallel workers
    pub parallel_workers: usize,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            enable_flow_graph: true,
            enable_type_resolution: true,
            enable_dfg: true,
            enable_ssa: true,
            enable_occurrences: true, // 🚀 Default: generate in Rust
            parallel_workers: num_cpus::get() * 3 / 4,
        }
    }
}

impl PipelineConfig {
    pub fn minimal() -> Self {
        Self {
            enable_flow_graph: false,
            enable_type_resolution: false,
            enable_dfg: false,
            enable_ssa: false,
            enable_occurrences: false,
            parallel_workers: 1,
        }
    }

    pub fn full() -> Self {
        Self::default()
    }

    /// Enable only occurrence generation (for L2 optimization)
    pub fn occurrences_only() -> Self {
        Self {
            enable_flow_graph: false,
            enable_type_resolution: false,
            enable_dfg: false,
            enable_ssa: false,
            enable_occurrences: true,
            parallel_workers: num_cpus::get() * 3 / 4,
        }
    }
}
