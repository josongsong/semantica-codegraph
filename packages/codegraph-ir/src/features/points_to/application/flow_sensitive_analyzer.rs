//! Flow-Sensitive Points-to Analyzer
//!
//! High-level wrapper for Flow-Sensitive PTA, providing precise per-program-point
//! alias information for path-sensitive analysis.
//!
//! # Use Cases
//! - Path-sensitive taint analysis
//! - Null dereference detection with control flow awareness
//! - Strong update optimization
//!
//! # Example (Builder Pattern)
//! ```rust,ignore
//! let mut analyzer = FlowSensitiveAnalyzer::new()
//!     .with_strong_updates(true)
//!     .with_cfg(cfg_edges);
//! ```
//!
//! # Example (Config-based - recommended for benchmarks)
//! ```rust,ignore
//! use codegraph_ir::config::PTAConfig;
//!
//! let config = PTAConfig::default()
//!     .mode(PTAMode::Precise)
//!     .field_sensitive(true);
//!
//! let analyzer = FlowSensitiveAnalyzer::from_config(&config);
//! ```

use crate::config::PTAConfig;
use crate::features::flow_graph::infrastructure::cfg::CFGEdge;
use crate::features::points_to::domain::{
    abstract_location::LocationId,
    constraint::{Constraint, VarId},
    FlowState, LocationSet, ProgramPoint,
};
use crate::features::points_to::infrastructure::{
    FlowSensitivePTA, FlowSensitiveResult, AnalysisStats,
};

/// Analysis precision level
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum FlowPrecision {
    /// Fast: fewer iterations, may miss some facts
    Fast,
    /// Standard: balanced precision/performance
    #[default]
    Standard,
    /// Precise: more iterations, better precision
    Precise,
}

/// Flow-sensitive analysis result
#[derive(Debug, Clone)]
pub struct FlowAnalysisResult {
    /// Points-to state at each program point
    pub states: rustc_hash::FxHashMap<ProgramPoint, FlowState>,
    /// Final merged state
    pub final_state: FlowState,
    /// Analysis statistics
    pub stats: FlowAnalysisStats,
}

/// Analysis statistics
#[derive(Debug, Clone, Default)]
pub struct FlowAnalysisStats {
    pub program_points: usize,
    pub iterations: usize,
    pub total_facts: usize,
    pub strong_updates: usize,
    pub weak_updates: usize,
    pub analysis_time_ms: u64,
}

impl From<AnalysisStats> for FlowAnalysisStats {
    fn from(s: AnalysisStats) -> Self {
        Self {
            program_points: s.program_points,
            iterations: s.iterations,
            total_facts: s.total_facts,
            strong_updates: 0,  // Not tracked in base implementation
            weak_updates: 0,
            analysis_time_ms: s.time_ms,
        }
    }
}

impl FlowAnalysisResult {
    /// Get points-to set at a specific program point
    pub fn points_to_at(&self, pp: &ProgramPoint, var: VarId) -> &LocationSet {
        self.states
            .get(pp)
            .map(|s| s.get_points_to(var))
            .unwrap_or_else(|| self.final_state.get_points_to(var))
    }

    /// Check if two variables may alias at a program point
    pub fn may_alias_at(&self, pp: &ProgramPoint, var1: VarId, var2: VarId) -> bool {
        if let Some(state) = self.states.get(pp) {
            state.may_alias(var1, var2)
        } else {
            self.final_state.may_alias(var1, var2)
        }
    }

    /// Check if two variables must alias at a program point
    pub fn must_alias_at(&self, pp: &ProgramPoint, var1: VarId, var2: VarId) -> bool {
        if let Some(state) = self.states.get(pp) {
            state.must_alias(var1, var2)
        } else {
            self.final_state.must_alias(var1, var2)
        }
    }

    /// Get the final (merged) points-to set
    pub fn points_to(&self, var: VarId) -> &LocationSet {
        self.final_state.get_points_to(var)
    }
}

/// High-level flow-sensitive analyzer
#[derive(Debug)]
pub struct FlowSensitiveAnalyzer {
    solver: FlowSensitivePTA,
    precision: FlowPrecision,
    enable_strong_updates: bool,
    cfg_edges: Vec<CFGEdge>,
}

impl Default for FlowSensitiveAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

impl FlowSensitiveAnalyzer {
    /// Create a new analyzer with default settings
    pub fn new() -> Self {
        Self {
            solver: FlowSensitivePTA::new(),
            precision: FlowPrecision::Standard,
            enable_strong_updates: true,
            cfg_edges: Vec::new(),
        }
    }

    /// Create from config (recommended for benchmarks/pipelines)
    ///
    /// # Example
    /// ```rust,ignore
    /// let config = PTAConfig::default().field_sensitive(true);
    /// let analyzer = FlowSensitiveAnalyzer::from_config(&config);
    /// ```
    pub fn from_config(config: &PTAConfig) -> Self {
        use crate::config::PTAMode;

        let precision = match config.mode {
            PTAMode::Fast => FlowPrecision::Fast,
            PTAMode::Precise => FlowPrecision::Precise,
            PTAMode::Hybrid | PTAMode::Auto => FlowPrecision::Standard,
        };

        Self {
            solver: FlowSensitivePTA::new(),
            precision,
            enable_strong_updates: config.field_sensitive,
            cfg_edges: Vec::new(),
        }
    }

    /// Set analysis precision
    pub fn with_precision(mut self, precision: FlowPrecision) -> Self {
        self.precision = precision;
        self
    }

    /// Enable/disable strong updates
    pub fn with_strong_updates(mut self, enable: bool) -> Self {
        self.enable_strong_updates = enable;
        self
    }

    /// Set CFG edges for control flow analysis
    pub fn with_cfg(mut self, edges: Vec<CFGEdge>) -> Self {
        self.cfg_edges = edges.clone();
        self.solver = self.solver.with_cfg(edges);
        self
    }

    /// Add allocation constraint: var = alloc(location)
    pub fn add_alloc(&mut self, var: VarId, location: LocationId) {
        self.solver.add_alloc(var, location);
    }

    /// Add copy constraint: lhs = rhs
    pub fn add_copy(&mut self, lhs: VarId, rhs: VarId) {
        self.solver.add_copy(lhs, rhs);
    }

    /// Add load constraint: lhs = *rhs
    pub fn add_load(&mut self, lhs: VarId, rhs: VarId) {
        self.solver.add_load(lhs, rhs);
    }

    /// Add store constraint: *lhs = rhs
    pub fn add_store(&mut self, lhs: VarId, rhs: VarId) {
        self.solver.add_store(lhs, rhs);
    }

    /// Add a generic constraint
    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.solver.add_constraint(constraint);
    }

    /// Run the analysis
    pub fn analyze(self) -> FlowAnalysisResult {
        let result = self.solver.solve();

        FlowAnalysisResult {
            states: result.states,
            final_state: result.final_state,
            stats: result.stats.into(),
        }
    }

    /// Query points-to at a specific program point (before full analysis)
    pub fn query_at(&self, pp: &ProgramPoint, var: VarId) -> Option<&LocationSet> {
        self.solver.states.get(pp).map(|s| s.get_points_to(var))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_flow_sensitive() {
        let mut analyzer = FlowSensitiveAnalyzer::new();

        // x = alloc()
        analyzer.add_alloc(0, 100);
        // y = x
        analyzer.add_copy(1, 0);

        let result = analyzer.analyze();

        assert!(result.points_to(0).contains(&100));
        assert!(result.points_to(1).contains(&100));
    }

    #[test]
    fn test_with_precision() {
        let analyzer = FlowSensitiveAnalyzer::new()
            .with_precision(FlowPrecision::Precise)
            .with_strong_updates(true);

        assert_eq!(analyzer.precision, FlowPrecision::Precise);
        assert!(analyzer.enable_strong_updates);
    }

    #[test]
    fn test_builder_pattern() {
        let analyzer = FlowSensitiveAnalyzer::new()
            .with_precision(FlowPrecision::Fast)
            .with_cfg(vec![]);

        assert_eq!(analyzer.precision, FlowPrecision::Fast);
    }

    #[test]
    fn test_from_config() {
        use crate::config::PTAMode;

        let config = PTAConfig::default().mode(PTAMode::Precise);
        let analyzer = FlowSensitiveAnalyzer::from_config(&config);

        assert_eq!(analyzer.precision, FlowPrecision::Precise);
    }

    #[test]
    fn test_from_config_field_sensitive() {
        let config = PTAConfig::default().field_sensitive(true);
        let analyzer = FlowSensitiveAnalyzer::from_config(&config);

        assert!(analyzer.enable_strong_updates);
    }
}
