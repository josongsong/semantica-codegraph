//! Security-focused Points-to Analyzer
//!
//! High-level wrapper for Context-Sensitive PTA, optimized for security analysis.
//! Provides precise alias information to reduce false positives in taint analysis.
//!
//! # Use Cases
//! - SQL Injection detection with call-site sensitivity
//! - XSS detection with object sensitivity
//! - Privilege escalation analysis
//!
//! # Example (Config-based - recommended for benchmarks)
//! ```rust,ignore
//! use codegraph_ir::config::PTAConfig;
//!
//! let config = PTAConfig::default()
//!     .mode(PTAMode::Precise)
//!     .field_sensitive(true);
//!
//! let analyzer = SecurityAnalyzer::from_config(&config);
//! ```

use crate::config::PTAConfig;
use crate::features::points_to::domain::{
    Constraint,
    constraint::VarId,
    abstract_location::LocationId,
    PointsToGraph,
};
use crate::features::points_to::infrastructure::{
    ContextSensitiveSolver, ContextSensitiveConfig, ContextSensitiveResult,
    ContextStrategy,
};

/// Security analysis strategy presets
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum SecurityStrategy {
    /// Call-string sensitivity (k-CFA style)
    CallString,
    /// 1-object sensitivity
    ObjectSensitive,
    /// 2-object sensitivity (recommended)
    #[default]
    TwoObjectSensitive,
    /// Type-based sensitivity
    TypeSensitive,
    /// Selective sensitivity (adaptive)
    Selective,
}

impl From<SecurityStrategy> for ContextStrategy {
    fn from(s: SecurityStrategy) -> Self {
        match s {
            SecurityStrategy::CallString => ContextStrategy::CallString(2),
            SecurityStrategy::ObjectSensitive => ContextStrategy::ObjectSensitive,
            SecurityStrategy::TwoObjectSensitive => ContextStrategy::TwoObjectSensitive,
            SecurityStrategy::TypeSensitive => ContextStrategy::TypeSensitive,
            SecurityStrategy::Selective => ContextStrategy::Selective,
        }
    }
}

/// Security analysis result
#[derive(Debug, Clone)]
pub struct SecurityAnalysisResult {
    pub graph: PointsToGraph,
    pub contexts_analyzed: usize,
    pub heap_clones: usize,
    pub fp_reduction_estimate: f64,
    pub analysis_time_ms: u64,
}

/// High-level security analyzer wrapping Context-Sensitive PTA
#[derive(Debug)]
pub struct SecurityAnalyzer {
    /// Configuration (public for factory/builder access)
    pub config: ContextSensitiveConfig,
    constraints: Vec<Constraint>,
}

impl SecurityAnalyzer {
    pub fn new() -> Self {
        Self {
            config: ContextSensitiveConfig {
                strategy: ContextStrategy::TwoObjectSensitive,
                max_context_depth: 3,
                ..Default::default()
            },
            constraints: Vec::new(),
        }
    }

    /// Create from config (recommended for benchmarks/pipelines)
    ///
    /// # Example
    /// ```rust,ignore
    /// let config = PTAConfig::default().field_sensitive(true);
    /// let analyzer = SecurityAnalyzer::from_config(&config);
    /// ```
    pub fn from_config(config: &PTAConfig) -> Self {
        use crate::config::PTAMode;

        let strategy = match config.mode {
            PTAMode::Fast => ContextStrategy::ObjectSensitive,
            PTAMode::Precise => ContextStrategy::TwoObjectSensitive,
            PTAMode::Hybrid | PTAMode::Auto => ContextStrategy::Selective,
        };

        Self {
            config: ContextSensitiveConfig {
                strategy,
                max_context_depth: config.max_iterations.unwrap_or(3).min(10),
                ..Default::default()
            },
            constraints: Vec::new(),
        }
    }

    pub fn with_strategy(mut self, strategy: SecurityStrategy) -> Self {
        self.config.strategy = strategy.into();
        self
    }

    pub fn with_context_depth(mut self, depth: usize) -> Self {
        self.config.max_context_depth = depth;
        self
    }

    pub fn add_alloc(&mut self, var: VarId, location: LocationId) {
        self.constraints.push(Constraint::alloc(var, location));
    }

    pub fn add_copy(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::copy(lhs, rhs));
    }

    pub fn add_load(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::load(lhs, rhs));
    }

    pub fn add_store(&mut self, lhs: VarId, rhs: VarId) {
        self.constraints.push(Constraint::store(lhs, rhs));
    }

    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.constraints.push(constraint);
    }

    pub fn analyze(&mut self) -> SecurityAnalysisResult {
        let start = std::time::Instant::now();
        let mut solver = ContextSensitiveSolver::new(self.config.clone());

        for c in &self.constraints {
            solver.add_constraint(c.clone());
        }

        let result: ContextSensitiveResult = solver.solve();
        let elapsed = start.elapsed();

        // OCP: Strategy knows its own characteristics
        let fp_reduction = self.config.strategy.fp_reduction_estimate();

        SecurityAnalysisResult {
            graph: result.graph,
            contexts_analyzed: result.stats.contexts_created,
            heap_clones: result.stats.heap_clones,
            fp_reduction_estimate: fp_reduction,
            analysis_time_ms: elapsed.as_millis() as u64,
        }
    }

    pub fn may_alias(&mut self, v1: VarId, v2: VarId) -> bool {
        let result = self.analyze();
        result.graph.may_alias(v1, v2)
    }
}

impl Default for SecurityAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

// LSP: Implement core trait for substitutability
impl crate::features::points_to::ports::PTAAnalyzer for SecurityAnalyzer {
    fn analyze(&mut self) -> PointsToGraph {
        self.analyze().graph
    }

    fn may_alias(&self, v1: VarId, v2: VarId) -> bool {
        // Note: requires mutable self in actual impl, so we clone
        let mut clone = Self {
            config: self.config.clone(),
            constraints: self.constraints.clone(),
        };
        clone.analyze().graph.may_alias(v1, v2)
    }

    fn must_alias(&self, _v1: VarId, _v2: VarId) -> bool {
        // Context-sensitive analysis doesn't provide must-alias
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_security_analysis() {
        let mut analyzer = SecurityAnalyzer::new()
            .with_strategy(SecurityStrategy::TwoObjectSensitive);
        analyzer.add_alloc(1, 100);
        analyzer.add_copy(2, 1);
        let result = analyzer.analyze();
        assert!(result.fp_reduction_estimate > 0.5);
    }

    #[test]
    fn test_builder_pattern() {
        let analyzer = SecurityAnalyzer::new()
            .with_strategy(SecurityStrategy::ObjectSensitive)
            .with_context_depth(5);
        assert_eq!(analyzer.config.max_context_depth, 5);
    }
}
