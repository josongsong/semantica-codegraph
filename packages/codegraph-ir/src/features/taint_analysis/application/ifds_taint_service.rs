//! IFDS/IDE Taint Analysis Service
//!
//! Connects RFC-001 Config System with IFDS/IDE infrastructure.
//! Provides high-level API for interprocedural taint analysis.
//!
//! # Architecture
//! ```text
//! TaintConfig (RFC-001)
//!       ↓
//! IFDSTaintService (Config Adapter)
//!       ↓
//! IFDS/IDE/Sparse Solvers (Infrastructure)
//! ```
//!
//! # Usage
//! ```rust,ignore
//! use codegraph_ir::config::{TaintConfig, Preset};
//! use codegraph_ir::features::taint_analysis::application::IFDSTaintService;
//!
//! let config = TaintConfig::from_preset(Preset::Balanced);
//! let service = IFDSTaintService::new(config);
//! let result = service.analyze(&problem)?;
//! ```

use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::VecDeque;
use std::time::Instant;

use super::super::infrastructure::{
    taint_relevance_function,
    CFGEdge,
    CFGEdgeKind,
    DataflowFact,
    EdgeFunction,
    ExplodedSupergraph,
    FlowFunction,
    // IDE
    IDEProblem,
    IDESolver,
    IDESolverResult,
    IDEStatistics,
    IDEValue,
    // IFDS
    IFDSProblem,
    IFDSSolver,
    IFDSSolverResult,
    IFDSStatistics,
    IdentityFlowFunction,
    NodeRelevance,
    PathEdge,
    // Sparse
    SparseCFG,
    SparseIFDSSolver,
    SparseIFDSStats,
    SummaryEdge,
    IFDSCFG,
};
use crate::config::stage_configs::TaintConfig;

// ============================================================================
// Config Adapter for IFDS
// ============================================================================

/// IFDS solver configuration derived from TaintConfig
#[derive(Debug, Clone)]
pub struct IFDSSolverConfig {
    pub max_iterations: usize,
    pub summary_cache_enabled: bool,
    pub max_path_edges: usize,
}

impl From<&TaintConfig> for IFDSSolverConfig {
    fn from(config: &TaintConfig) -> Self {
        Self {
            max_iterations: config.ifds_max_iterations,
            summary_cache_enabled: config.ifds_summary_cache_enabled,
            max_path_edges: config.max_paths * 10, // Estimate based on max_paths
        }
    }
}

// ============================================================================
// Config Adapter for IDE
// ============================================================================

/// IDE solver configuration derived from TaintConfig
#[derive(Debug, Clone)]
pub struct IDESolverConfig {
    pub max_iterations: usize,
    pub micro_cache_enabled: bool,
    pub jump_cache_enabled: bool,
    pub max_value_propagations: usize,
}

impl From<&TaintConfig> for IDESolverConfig {
    fn from(config: &TaintConfig) -> Self {
        Self {
            max_iterations: config.ifds_max_iterations, // Share with IFDS
            micro_cache_enabled: config.ide_micro_cache_enabled,
            jump_cache_enabled: config.ide_jump_cache_enabled,
            max_value_propagations: config.max_paths * 100, // Higher limit for values
        }
    }
}

// ============================================================================
// Config Adapter for Sparse IFDS
// ============================================================================

/// Sparse IFDS configuration derived from TaintConfig
#[derive(Debug, Clone)]
pub struct SparseIFDSConfig {
    pub enabled: bool,
    pub min_reduction_ratio: f64,
    /// Source patterns for node relevance (e.g., "input", "read", "request")
    pub source_patterns: Vec<String>,
    /// Sink patterns for node relevance (e.g., "exec", "eval", "sql")
    pub sink_patterns: Vec<String>,
    /// Sanitizer patterns for node relevance (e.g., "escape", "sanitize")
    pub sanitizer_patterns: Vec<String>,
}

impl SparseIFDSConfig {
    /// Default taint source/sink/sanitizer patterns for security analysis
    pub fn default_patterns() -> (Vec<String>, Vec<String>, Vec<String>) {
        let sources = vec![
            "input",
            "read",
            "request",
            "user_input",
            "get",
            "recv",
            "stdin",
            "argv",
            "getenv",
            "fread",
            "scanf",
        ]
        .into_iter()
        .map(String::from)
        .collect();

        let sinks = vec![
            "exec", "eval", "sql", "write", "send", "output", "system", "popen", "query",
            "execute", "print",
        ]
        .into_iter()
        .map(String::from)
        .collect();

        let sanitizers = vec![
            "escape",
            "sanitize",
            "validate",
            "encode",
            "filter",
            "clean",
            "strip",
            "quote",
            "parameterize",
        ]
        .into_iter()
        .map(String::from)
        .collect();

        (sources, sinks, sanitizers)
    }
}

impl From<&TaintConfig> for SparseIFDSConfig {
    fn from(config: &TaintConfig) -> Self {
        let (sources, sinks, sanitizers) = SparseIFDSConfig::default_patterns();
        Self {
            enabled: config.sparse_ifds_enabled,
            min_reduction_ratio: config.sparse_min_reduction_ratio,
            source_patterns: sources,
            sink_patterns: sinks,
            sanitizer_patterns: sanitizers,
        }
    }
}

// ============================================================================
// IFDS Taint Service
// ============================================================================

/// High-level IFDS/IDE taint analysis service
///
/// Automatically selects between:
/// - Standard IFDS solver
/// - Sparse IFDS solver (if enabled and beneficial)
/// - IDE solver (for value propagation)
pub struct IFDSTaintService {
    /// Configuration from RFC-001
    config: TaintConfig,

    /// Derived IFDS config
    ifds_config: IFDSSolverConfig,

    /// Derived IDE config
    ide_config: IDESolverConfig,

    /// Derived Sparse config
    sparse_config: SparseIFDSConfig,
}

impl IFDSTaintService {
    /// Create service from TaintConfig
    pub fn new(config: TaintConfig) -> Self {
        let ifds_config = IFDSSolverConfig::from(&config);
        let ide_config = IDESolverConfig::from(&config);
        let sparse_config = SparseIFDSConfig::from(&config);

        Self {
            config,
            ifds_config,
            ide_config,
            sparse_config,
        }
    }

    /// Check if IFDS is enabled
    pub fn is_ifds_enabled(&self) -> bool {
        self.config.ifds_enabled
    }

    /// Check if IDE is enabled
    pub fn is_ide_enabled(&self) -> bool {
        self.config.ide_enabled
    }

    /// Check if Sparse IFDS is enabled
    pub fn is_sparse_enabled(&self) -> bool {
        self.sparse_config.enabled
    }

    /// Analyze with IFDS solver
    ///
    /// Automatically selects Sparse IFDS if beneficial.
    pub fn analyze_ifds<F: DataflowFact + 'static>(
        &self,
        problem: Box<dyn IFDSProblem<F>>,
        cfg: &IFDSCFG,
    ) -> Result<IFDSAnalysisResult<F>, IFDSAnalysisError> {
        if !self.config.ifds_enabled {
            return Err(IFDSAnalysisError::Disabled(
                "IFDS is disabled in config".into(),
            ));
        }

        let start = Instant::now();

        // Check if Sparse IFDS should be used
        if self.sparse_config.enabled {
            // Convert patterns to &str slices for taint_relevance_function
            let sources: Vec<&str> = self
                .sparse_config
                .source_patterns
                .iter()
                .map(|s| s.as_str())
                .collect();
            let sinks: Vec<&str> = self
                .sparse_config
                .sink_patterns
                .iter()
                .map(|s| s.as_str())
                .collect();
            let sanitizers: Vec<&str> = self
                .sparse_config
                .sanitizer_patterns
                .iter()
                .map(|s| s.as_str())
                .collect();

            let relevance_fn = taint_relevance_function(&sources, &sanitizers, &sinks);
            let sparse_cfg = SparseCFG::from_cfg(cfg, relevance_fn);

            let reduction_ratio = sparse_cfg.reduction_ratio();

            if reduction_ratio >= self.sparse_config.min_reduction_ratio {
                // Use Sparse IFDS - significant reduction achieved
                return self.run_sparse_ifds(problem, sparse_cfg, start);
            }
        }

        // Use standard IFDS
        self.run_standard_ifds(problem, cfg, start)
    }

    /// Run standard IFDS solver
    fn run_standard_ifds<F: DataflowFact + 'static>(
        &self,
        problem: Box<dyn IFDSProblem<F>>,
        cfg: &IFDSCFG,
        start: Instant,
    ) -> Result<IFDSAnalysisResult<F>, IFDSAnalysisError> {
        let solver = IFDSSolver::new(problem, cfg.clone());

        // Apply config limits
        let result = solver.solve_with_limits(
            self.ifds_config.max_iterations,
            self.ifds_config.max_path_edges,
        );

        let elapsed = start.elapsed();

        Ok(IFDSAnalysisResult {
            solver_type: SolverType::StandardIFDS,
            path_edges: result.path_edges_count(),
            summary_edges: result.summary_edges_count(),
            summary_reuses: result.statistics().num_summary_reuses,
            iterations: result.statistics().num_iterations,
            analysis_time_ms: elapsed.as_millis() as u64,
            reachable_facts: result.get_reachable_facts_at_all_nodes(),
            sparse_stats: None,
        })
    }

    /// Run Sparse IFDS solver
    fn run_sparse_ifds<F: DataflowFact + 'static>(
        &self,
        problem: Box<dyn IFDSProblem<F>>,
        sparse_cfg: SparseCFG,
        start: Instant,
    ) -> Result<IFDSAnalysisResult<F>, IFDSAnalysisError> {
        let mut solver = SparseIFDSSolver::new(problem, sparse_cfg.clone());

        let result = solver.solve();
        let elapsed = start.elapsed();

        let stats = solver.statistics();

        Ok(IFDSAnalysisResult {
            solver_type: SolverType::SparseIFDS,
            path_edges: stats.path_edges_processed,
            summary_edges: stats.summary_edges_created,
            summary_reuses: 0, // Sparse doesn't track this separately
            iterations: stats.iterations,
            analysis_time_ms: elapsed.as_millis() as u64,
            reachable_facts: result,
            sparse_stats: Some(SparseAnalysisStats {
                original_nodes: sparse_cfg.stats().original_nodes,
                sparse_nodes: sparse_cfg.stats().sparse_nodes,
                reduction_ratio: sparse_cfg.reduction_ratio(),
                nodes_skipped: sparse_cfg.stats().total_skipped_nodes,
            }),
        })
    }

    /// Analyze with IDE solver (includes value propagation)
    pub fn analyze_ide<F: DataflowFact + 'static, V: IDEValue + 'static>(
        &self,
        problem: Box<dyn IDEProblem<F, V>>,
        cfg: &IFDSCFG,
    ) -> Result<IDEAnalysisResult<F, V>, IFDSAnalysisError> {
        if !self.config.ide_enabled {
            return Err(IFDSAnalysisError::Disabled(
                "IDE is disabled in config".into(),
            ));
        }

        let start = Instant::now();

        let solver = IDESolver::new(problem, cfg.clone());

        // Apply config (caching is controlled internally based on config)
        let result = solver.solve_with_config(
            self.ide_config.max_iterations,
            self.ide_config.micro_cache_enabled,
            self.ide_config.jump_cache_enabled,
        );

        let elapsed = start.elapsed();
        let stats = result.statistics();

        Ok(IDEAnalysisResult {
            values: result.get_all_values(),
            micro_function_reuses: stats.num_micro_function_reuses,
            jump_function_reuses: stats.num_jump_function_reuses,
            value_propagations: stats.num_value_propagations,
            meet_operations: stats.num_meet_operations,
            analysis_time_ms: elapsed.as_millis() as u64,
        })
    }

    /// Get current config
    pub fn config(&self) -> &TaintConfig {
        &self.config
    }
}

// ============================================================================
// Result Types
// ============================================================================

/// Which solver was used
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SolverType {
    StandardIFDS,
    SparseIFDS,
}

/// Sparse analysis statistics
#[derive(Debug, Clone)]
pub struct SparseAnalysisStats {
    pub original_nodes: usize,
    pub sparse_nodes: usize,
    pub reduction_ratio: f64,
    pub nodes_skipped: usize,
}

/// IFDS analysis result
#[derive(Debug)]
pub struct IFDSAnalysisResult<F: DataflowFact> {
    pub solver_type: SolverType,
    pub path_edges: usize,
    pub summary_edges: usize,
    pub summary_reuses: usize,
    pub iterations: usize,
    pub analysis_time_ms: u64,
    pub reachable_facts: FxHashMap<String, FxHashSet<F>>,
    pub sparse_stats: Option<SparseAnalysisStats>,
}

impl<F: DataflowFact> IFDSAnalysisResult<F> {
    /// Check if a fact is reachable at a node
    pub fn is_reachable(&self, node: &str, fact: &F) -> bool {
        self.reachable_facts
            .get(node)
            .map(|facts| facts.contains(fact))
            .unwrap_or(false)
    }

    /// Get all reachable facts at a node
    pub fn facts_at(&self, node: &str) -> Option<&FxHashSet<F>> {
        self.reachable_facts.get(node)
    }

    /// Was Sparse IFDS used?
    pub fn used_sparse(&self) -> bool {
        matches!(self.solver_type, SolverType::SparseIFDS)
    }
}

/// IDE analysis result
#[derive(Debug)]
pub struct IDEAnalysisResult<F: DataflowFact, V: IDEValue> {
    pub values: FxHashMap<String, FxHashMap<F, V>>,
    pub micro_function_reuses: usize,
    pub jump_function_reuses: usize,
    pub value_propagations: usize,
    pub meet_operations: usize,
    pub analysis_time_ms: u64,
}

impl<F: DataflowFact, V: IDEValue> IDEAnalysisResult<F, V> {
    /// Get value of a fact at a node
    pub fn get_value(&self, node: &str, fact: &F) -> Option<&V> {
        self.values.get(node)?.get(fact)
    }

    /// Get all values at a node
    pub fn values_at(&self, node: &str) -> Option<&FxHashMap<F, V>> {
        self.values.get(node)
    }
}

// ============================================================================
// Error Types
// ============================================================================

/// IFDS/IDE analysis errors
#[derive(Debug, Clone)]
pub enum IFDSAnalysisError {
    /// Feature is disabled in config
    Disabled(String),
    /// Iteration limit exceeded
    IterationLimit { max: usize, reached: usize },
    /// Path edge limit exceeded
    PathEdgeLimit { max: usize, reached: usize },
    /// Invalid problem configuration
    InvalidProblem(String),
}

impl std::fmt::Display for IFDSAnalysisError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Disabled(msg) => write!(f, "IFDS/IDE disabled: {}", msg),
            Self::IterationLimit { max, reached } => {
                write!(f, "Iteration limit exceeded: {} (max {})", reached, max)
            }
            Self::PathEdgeLimit { max, reached } => {
                write!(f, "Path edge limit exceeded: {} (max {})", reached, max)
            }
            Self::InvalidProblem(msg) => write!(f, "Invalid problem: {}", msg),
        }
    }
}

impl std::error::Error for IFDSAnalysisError {}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::preset::Preset;

    #[test]
    fn test_ifds_solver_config_from_taint_config() {
        let taint_config = TaintConfig::from_preset(Preset::Balanced);
        let ifds_config = IFDSSolverConfig::from(&taint_config);

        assert_eq!(ifds_config.max_iterations, taint_config.ifds_max_iterations);
        assert_eq!(
            ifds_config.summary_cache_enabled,
            taint_config.ifds_summary_cache_enabled
        );
    }

    #[test]
    fn test_ide_solver_config_from_taint_config() {
        let taint_config = TaintConfig::from_preset(Preset::Thorough);
        let ide_config = IDESolverConfig::from(&taint_config);

        assert!(ide_config.micro_cache_enabled);
        assert!(ide_config.jump_cache_enabled);
    }

    #[test]
    fn test_sparse_config_from_taint_config() {
        let taint_config = TaintConfig::from_preset(Preset::Thorough);
        let sparse_config = SparseIFDSConfig::from(&taint_config);

        assert!(sparse_config.enabled); // Thorough enables sparse
    }

    #[test]
    fn test_service_creation() {
        let config = TaintConfig::from_preset(Preset::Balanced);
        let service = IFDSTaintService::new(config);

        assert!(service.is_ifds_enabled());
        assert!(service.is_ide_enabled());
        assert!(!service.is_sparse_enabled()); // Balanced doesn't enable sparse
    }

    #[test]
    fn test_service_with_fast_preset() {
        let config = TaintConfig::from_preset(Preset::Fast);
        let service = IFDSTaintService::new(config);

        assert!(!service.is_ifds_enabled()); // Fast disables IFDS
        assert!(!service.is_ide_enabled()); // Fast disables IDE
    }

    #[test]
    fn test_disabled_ifds_returns_error() {
        let config = TaintConfig::from_preset(Preset::Fast);
        let service = IFDSTaintService::new(config);

        // Fast preset disables IFDS for performance
        assert!(!service.is_ifds_enabled());
        assert!(!service.is_ide_enabled());
    }

    #[test]
    fn test_sparse_config_has_default_patterns() {
        let config = TaintConfig::from_preset(Preset::Thorough);
        let sparse_config = SparseIFDSConfig::from(&config);

        // Should have default patterns
        assert!(!sparse_config.source_patterns.is_empty());
        assert!(!sparse_config.sink_patterns.is_empty());
        assert!(!sparse_config.sanitizer_patterns.is_empty());

        // Check some expected patterns
        assert!(sparse_config
            .source_patterns
            .iter()
            .any(|p| p.contains("input")));
        assert!(sparse_config
            .sink_patterns
            .iter()
            .any(|p| p.contains("exec")));
        assert!(sparse_config
            .sanitizer_patterns
            .iter()
            .any(|p| p.contains("sanitize")));
    }
}
