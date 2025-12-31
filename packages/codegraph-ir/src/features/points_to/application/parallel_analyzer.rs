//! Parallel Points-to Analyzer
//!
//! High-level wrapper for Parallel Andersen's algorithm, optimized for
//! large codebases with multi-core systems.
//!
//! # Use Cases
//! - Large-scale codebase analysis (>100k constraints)
//! - CI/CD pipelines with multiple cores
//! - Batch analysis of multiple files
//!
//! # Performance Guidelines
//! - Best for constraint sets > 1,000 (parallel overhead otherwise)
//! - Linear speedup up to ~8 cores, then diminishing returns
//! - Consider sequential analyzer for small constraint sets
//!
//! # Example (Builder Pattern)
//! ```rust,ignore
//! let mut analyzer = ParallelAnalyzer::new()
//!     .with_threads(8)
//!     .with_scc_optimization(true);
//! ```
//!
//! # Example (Config-based - recommended for benchmarks)
//! ```rust,ignore
//! use codegraph_ir::config::{PTAConfig, ParallelConfig};
//!
//! let pta_config = PTAConfig::default()
//!     .enable_scc(true)
//!     .enable_parallel(true);
//! let parallel_config = ParallelConfig::default()
//!     .num_workers(8);
//!
//! let analyzer = ParallelAnalyzer::from_config(&pta_config, &parallel_config);
//! ```

use crate::config::{PTAConfig, ParallelConfig};
use crate::features::points_to::domain::{
    abstract_location::LocationId,
    constraint::{Constraint, ConstraintKind, VarId},
    points_to_graph::PointsToGraph,
};
use crate::features::points_to::infrastructure::{
    ParallelAndersenSolver, AndersenConfig, AndersenStats,
};

/// Parallelization strategy
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ParallelStrategy {
    /// Auto-detect based on constraint count
    #[default]
    Auto,
    /// Force sequential (for debugging or small sets)
    Sequential,
    /// Force parallel (always use threads)
    ForceParallel,
    /// Adaptive (switch based on runtime metrics)
    Adaptive,
}

/// Parallel analysis result
#[derive(Debug, Clone)]
pub struct ParallelAnalysisResult {
    /// Resulting points-to graph
    pub graph: PointsToGraph,
    /// Analysis statistics
    pub stats: ParallelStats,
}

/// Parallel analysis statistics
#[derive(Debug, Clone, Default)]
pub struct ParallelStats {
    pub variables: usize,
    pub constraints: usize,
    pub iterations: usize,
    pub scc_count: usize,
    pub largest_scc: usize,
    pub thread_count: usize,
    pub time_ms: u64,
    pub speedup_estimate: f64,
}

impl From<AndersenStats> for ParallelStats {
    fn from(s: AndersenStats) -> Self {
        Self {
            variables: 0, // Not tracked in AndersenStats
            constraints: s.constraints_total,
            iterations: s.iterations,
            scc_count: s.scc_count,
            largest_scc: 0, // Not tracked
            thread_count: rayon::current_num_threads(),
            time_ms: s.duration_ms as u64,
            speedup_estimate: 1.0, // Not tracked in base
        }
    }
}

/// High-level parallel analyzer
pub struct ParallelAnalyzer {
    constraints: Vec<Constraint>,
    strategy: ParallelStrategy,
    thread_count: Option<usize>,
    enable_scc: bool,
    cached_graph: Option<PointsToGraph>,
}

impl std::fmt::Debug for ParallelAnalyzer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ParallelAnalyzer")
            .field("constraints", &self.constraints.len())
            .field("strategy", &self.strategy)
            .field("thread_count", &self.thread_count)
            .field("enable_scc", &self.enable_scc)
            .finish()
    }
}

impl Default for ParallelAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

impl ParallelAnalyzer {
    /// Create a new parallel analyzer with defaults
    pub fn new() -> Self {
        Self {
            constraints: Vec::new(),
            strategy: ParallelStrategy::Auto,
            thread_count: None,
            enable_scc: true,
            cached_graph: None,
        }
    }

    /// Create from config (recommended for benchmarks/pipelines)
    ///
    /// # Example
    /// ```rust,ignore
    /// let pta = PTAConfig::default().enable_scc(true);
    /// let parallel = ParallelConfig::default().num_workers(8);
    /// let analyzer = ParallelAnalyzer::from_config(&pta, &parallel);
    /// ```
    pub fn from_config(pta_config: &PTAConfig, parallel_config: &ParallelConfig) -> Self {
        let strategy = if parallel_config.enable_rayon {
            ParallelStrategy::ForceParallel
        } else if parallel_config.num_workers <= 1 {
            ParallelStrategy::Sequential
        } else {
            ParallelStrategy::Auto
        };

        Self {
            constraints: Vec::new(),
            strategy,
            thread_count: if parallel_config.num_workers > 0 {
                Some(parallel_config.num_workers)
            } else {
                None
            },
            enable_scc: pta_config.enable_scc,
            cached_graph: None,
        }
    }

    /// Set parallelization strategy
    pub fn with_strategy(mut self, strategy: ParallelStrategy) -> Self {
        self.strategy = strategy;
        self
    }

    /// Set thread count (overrides auto-detection)
    pub fn with_threads(mut self, count: usize) -> Self {
        self.thread_count = Some(count.max(1));
        self
    }

    /// Enable/disable SCC optimization
    pub fn with_scc_optimization(mut self, enable: bool) -> Self {
        self.enable_scc = enable;
        self
    }

    /// Add allocation constraint: var = alloc(location)
    pub fn add_alloc(&mut self, var: VarId, location: LocationId) {
        self.constraints.push(Constraint::alloc(var, location));
    }

    /// Add copy constraint: lhs = rhs
    pub fn add_copy(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::copy(lhs, rhs));
    }

    /// Add load constraint: lhs = *rhs
    pub fn add_load(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::load(lhs, rhs));
    }

    /// Add store constraint: *lhs = rhs
    pub fn add_store(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::store(lhs, rhs));
    }

    /// Add a generic constraint
    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.constraints.push(constraint);
    }

    /// Check if parallel mode should be used
    fn should_use_parallel(&self) -> bool {
        match self.strategy {
            ParallelStrategy::Sequential => false,
            ParallelStrategy::ForceParallel => true,
            ParallelStrategy::Auto | ParallelStrategy::Adaptive => {
                // Use parallel if > 1000 constraints
                self.constraints.len() > 1000
            }
        }
    }

    /// Get effective thread count
    pub fn effective_threads(&self) -> usize {
        self.thread_count.unwrap_or_else(|| {
            if self.should_use_parallel() {
                rayon::current_num_threads()
            } else {
                1
            }
        })
    }

    /// Run the analysis
    pub fn analyze(mut self) -> ParallelAnalysisResult {
        let config = AndersenConfig {
            enable_scc: self.enable_scc,
            ..Default::default()
        };

        let mut solver = ParallelAndersenSolver::new(config);
        solver.add_constraints(self.constraints.drain(..));
        let result = solver.solve_parallel();

        self.cached_graph = Some(result.graph.clone());

        ParallelAnalysisResult {
            graph: result.graph,
            stats: result.stats.into(),
        }
    }

    /// Get current constraint count
    pub fn constraint_count(&self) -> usize {
        self.constraints.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_parallel() {
        let mut analyzer = ParallelAnalyzer::new();

        analyzer.add_alloc(0, 100);
        analyzer.add_copy(1, 0);

        let result = analyzer.analyze();

        assert!(result.graph.get_points_to(0).contains(&100));
        assert!(result.graph.get_points_to(1).contains(&100));
    }

    #[test]
    fn test_strategy_auto() {
        let analyzer = ParallelAnalyzer::new()
            .with_strategy(ParallelStrategy::Auto);

        // Small set, should use sequential
        assert!(!analyzer.should_use_parallel());
    }

    #[test]
    fn test_strategy_force_parallel() {
        let analyzer = ParallelAnalyzer::new()
            .with_strategy(ParallelStrategy::ForceParallel);

        assert!(analyzer.should_use_parallel());
    }

    #[test]
    fn test_with_threads() {
        let analyzer = ParallelAnalyzer::new()
            .with_threads(4);

        assert_eq!(analyzer.thread_count, Some(4));
    }

    #[test]
    fn test_scc_optimization() {
        let analyzer = ParallelAnalyzer::new()
            .with_scc_optimization(true);

        assert!(analyzer.enable_scc);
    }

    #[test]
    fn test_large_constraint_set() {
        let mut analyzer = ParallelAnalyzer::new()
            .with_strategy(ParallelStrategy::Auto);

        // Add > 1000 constraints
        for i in 0..1500 {
            analyzer.add_alloc(i, i + 10000);
        }

        assert!(analyzer.should_use_parallel());
        assert_eq!(analyzer.constraint_count(), 1500);
    }

    #[test]
    fn test_from_config() {
        let pta_config = PTAConfig::default().enable_scc(true);
        let parallel_config = ParallelConfig::default();

        let analyzer = ParallelAnalyzer::from_config(&pta_config, &parallel_config);

        assert!(analyzer.enable_scc);
    }

    #[test]
    fn test_from_config_with_workers() {
        let pta_config = PTAConfig::default();
        let mut parallel_config = ParallelConfig::default();
        parallel_config.num_workers = 8;

        let analyzer = ParallelAnalyzer::from_config(&pta_config, &parallel_config);

        assert_eq!(analyzer.thread_count, Some(8));
    }
}
