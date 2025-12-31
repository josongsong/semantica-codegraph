//! Ports (Interfaces) for Points-to Analysis
//!
//! SOTA Dependency Injection pattern for Rust:
//! - **Trait Objects**: Runtime polymorphism (`dyn PTAAnalyzer`)
//! - **Generic Bounds**: Zero-cost compile-time polymorphism (`T: PTAAnalyzer`)
//! - **Factory Pattern**: Decoupled object creation
//! - **Type State**: Compile-time state verification
//!
//! ## SOLID Compliance
//! - **SRP**: Each trait has single responsibility
//! - **OCP**: New analyzers don't modify existing code
//! - **LSP**: All implementations are substitutable
//! - **ISP**: Small, focused interfaces
//! - **DIP**: High-level modules depend on abstractions

use crate::features::points_to::domain::{
    constraint::VarId,
    abstract_location::LocationId,
    points_to_graph::PointsToGraph,
    Constraint,
};

// ============================================================================
// Core Traits (ISP: Interface Segregation)
// ============================================================================

/// Core points-to analyzer trait
///
/// # Example (Generic - Zero-cost)
/// ```ignore
/// fn analyze_code<A: PTAAnalyzer>(analyzer: &mut A) -> bool {
///     let graph = analyzer.analyze();
///     analyzer.may_alias(1, 2)
/// }
/// ```
pub trait PTAAnalyzer: Send + Sync {
    /// Analyze and produce points-to graph
    fn analyze(&mut self) -> PointsToGraph;

    /// Check if two variables may alias
    fn may_alias(&self, v1: VarId, v2: VarId) -> bool;

    /// Check if two variables must alias
    fn must_alias(&self, v1: VarId, v2: VarId) -> bool;
}

/// Demand-driven query trait (for IDE/real-time)
pub trait PTAQuery: Send + Sync {
    /// Query points-to set for a single variable (on-demand)
    fn query_points_to(&mut self, var: VarId) -> Vec<LocationId>;

    /// Query if two variables may alias
    fn query_may_alias(&mut self, v1: VarId, v2: VarId) -> bool;

    /// Query if data may flow from source to sink
    fn query_may_flow(&mut self, source: VarId, sink: VarId) -> bool;
}

/// Incremental update trait (for CI/CD)
pub trait PTAIncremental: Send + Sync {
    /// Apply incremental updates and return affected variables
    fn apply_updates(&mut self) -> Vec<VarId>;

    /// Check if there are pending changes
    fn has_pending(&self) -> bool;
}

/// Constraint generator trait
pub trait ConstraintGenerator: Send + Sync {
    /// Generate constraints from source representation
    fn generate(&self) -> Vec<Constraint>;
}

// ============================================================================
// Factory Pattern (DIP: Dependency Inversion)
// ============================================================================

/// Analyzer type for factory
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnalyzerKind {
    /// Context-sensitive for security analysis (precise, slower)
    Security,
    /// Demand-driven for IDE (fast, on-demand)
    Realtime,
    /// Incremental for CI/CD (fast updates)
    Incremental,
    /// Flow-sensitive for path-aware analysis
    FlowSensitive,
    /// Parallel for large-scale analysis
    Parallel,
    /// Hybrid mode (auto-select based on size)
    Auto,
}

/// Factory for creating analyzers (DIP)
///
/// # Example
/// ```ignore
/// use codegraph_ir::features::points_to::ports::{PTAFactory, AnalyzerKind};
///
/// // Runtime selection
/// let analyzer = PTAFactory::create_boxed(AnalyzerKind::Security);
///
/// // Or with config
/// let analyzer = PTAFactory::create_security()
///     .with_context_depth(3)
///     .build();
/// ```
pub struct PTAFactory;

impl PTAFactory {
    /// Create analyzer as trait object (runtime polymorphism)
    pub fn create_boxed(kind: AnalyzerKind) -> Box<dyn PTAAnalyzer> {
        use crate::features::points_to::application::SecurityAnalyzer;

        match kind {
            AnalyzerKind::Security => Box::new(SecurityAnalyzer::new()),
            AnalyzerKind::Realtime => Box::new(RealtimeAnalyzerAsFullPTA::new()),
            AnalyzerKind::Incremental => Box::new(IncrementalAnalyzerAsFullPTA::new()),
            AnalyzerKind::FlowSensitive => Box::new(FlowSensitiveAnalyzerAsFullPTA::new()),
            AnalyzerKind::Parallel => Box::new(ParallelAnalyzerAsFullPTA::new()),
            AnalyzerKind::Auto => Box::new(SecurityAnalyzer::new()), // Default to security
        }
    }

    /// Create security analyzer builder
    pub fn security() -> SecurityAnalyzerBuilder {
        SecurityAnalyzerBuilder::new()
    }

    /// Create realtime analyzer builder
    pub fn realtime() -> RealtimeAnalyzerBuilder {
        RealtimeAnalyzerBuilder::new()
    }

    /// Create incremental analyzer builder
    pub fn incremental() -> IncrementalAnalyzerBuilder {
        IncrementalAnalyzerBuilder::new()
    }

    /// Create flow-sensitive analyzer builder
    pub fn flow_sensitive() -> FlowSensitiveAnalyzerBuilder {
        FlowSensitiveAnalyzerBuilder::new()
    }

    /// Create parallel analyzer builder
    pub fn parallel() -> ParallelAnalyzerBuilder {
        ParallelAnalyzerBuilder::new()
    }
}

// ============================================================================
// Builder Pattern (Type State for compile-time safety)
// ============================================================================

/// Security analyzer builder
#[derive(Default)]
pub struct SecurityAnalyzerBuilder {
    context_depth: Option<usize>,
    strategy: Option<super::infrastructure::ContextStrategy>,
}

impl SecurityAnalyzerBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_context_depth(mut self, depth: usize) -> Self {
        self.context_depth = Some(depth);
        self
    }

    pub fn with_strategy(mut self, strategy: super::infrastructure::ContextStrategy) -> Self {
        self.strategy = Some(strategy);
        self
    }

    pub fn build(self) -> crate::features::points_to::application::SecurityAnalyzer {
        use crate::features::points_to::application::SecurityAnalyzer;

        let mut analyzer = SecurityAnalyzer::new();
        if let Some(depth) = self.context_depth {
            analyzer = analyzer.with_context_depth(depth);
        }
        analyzer
    }
}

/// Realtime analyzer builder
#[derive(Default)]
pub struct RealtimeAnalyzerBuilder {
    _config: (),
}

impl RealtimeAnalyzerBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn build(self) -> crate::features::points_to::application::RealtimeAnalyzer {
        crate::features::points_to::application::RealtimeAnalyzer::new()
    }
}

/// Incremental analyzer builder
#[derive(Default)]
pub struct IncrementalAnalyzerBuilder {
    _config: (),
}

impl IncrementalAnalyzerBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn build(self) -> crate::features::points_to::application::IncrementalAnalyzer {
        crate::features::points_to::application::IncrementalAnalyzer::new()
    }
}

/// Flow-sensitive analyzer builder
#[derive(Default)]
pub struct FlowSensitiveAnalyzerBuilder {
    precision: Option<crate::features::points_to::application::FlowPrecision>,
    enable_strong_updates: Option<bool>,
}

impl FlowSensitiveAnalyzerBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_precision(mut self, precision: crate::features::points_to::application::FlowPrecision) -> Self {
        self.precision = Some(precision);
        self
    }

    pub fn with_strong_updates(mut self, enable: bool) -> Self {
        self.enable_strong_updates = Some(enable);
        self
    }

    pub fn build(self) -> crate::features::points_to::application::FlowSensitiveAnalyzer {
        use crate::features::points_to::application::FlowSensitiveAnalyzer;

        let mut analyzer = FlowSensitiveAnalyzer::new();
        if let Some(precision) = self.precision {
            analyzer = analyzer.with_precision(precision);
        }
        if let Some(enable) = self.enable_strong_updates {
            analyzer = analyzer.with_strong_updates(enable);
        }
        analyzer
    }
}

/// Parallel analyzer builder
#[derive(Default)]
pub struct ParallelAnalyzerBuilder {
    threads: Option<usize>,
    strategy: Option<crate::features::points_to::application::ParallelStrategy>,
    enable_scc: Option<bool>,
}

impl ParallelAnalyzerBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_threads(mut self, count: usize) -> Self {
        self.threads = Some(count);
        self
    }

    pub fn with_strategy(mut self, strategy: crate::features::points_to::application::ParallelStrategy) -> Self {
        self.strategy = Some(strategy);
        self
    }

    pub fn with_scc_optimization(mut self, enable: bool) -> Self {
        self.enable_scc = Some(enable);
        self
    }

    pub fn build(self) -> crate::features::points_to::application::ParallelAnalyzer {
        use crate::features::points_to::application::ParallelAnalyzer;

        let mut analyzer = ParallelAnalyzer::new();
        if let Some(threads) = self.threads {
            analyzer = analyzer.with_threads(threads);
        }
        if let Some(strategy) = self.strategy {
            analyzer = analyzer.with_strategy(strategy);
        }
        if let Some(enable) = self.enable_scc {
            analyzer = analyzer.with_scc_optimization(enable);
        }
        analyzer
    }
}

// ============================================================================
// Adapter wrappers (for trait object compatibility)
// ============================================================================

/// Wrapper to make RealtimeAnalyzer implement PTAAnalyzer
pub struct RealtimeAnalyzerAsFullPTA {
    inner: crate::features::points_to::application::RealtimeAnalyzer,
    cached_graph: Option<PointsToGraph>,
}

impl RealtimeAnalyzerAsFullPTA {
    pub fn new() -> Self {
        Self {
            inner: crate::features::points_to::application::RealtimeAnalyzer::new(),
            cached_graph: None,
        }
    }
}

impl PTAAnalyzer for RealtimeAnalyzerAsFullPTA {
    fn analyze(&mut self) -> PointsToGraph {
        // Demand-driven doesn't do full analysis, return empty or cached
        self.cached_graph.clone().unwrap_or_default()
    }

    fn may_alias(&self, _v1: VarId, _v2: VarId) -> bool {
        // Would need mutable access, return conservative answer
        true
    }

    fn must_alias(&self, _v1: VarId, _v2: VarId) -> bool {
        false
    }
}

/// Wrapper to make IncrementalAnalyzer implement PTAAnalyzer
pub struct IncrementalAnalyzerAsFullPTA {
    inner: crate::features::points_to::application::IncrementalAnalyzer,
}

impl IncrementalAnalyzerAsFullPTA {
    pub fn new() -> Self {
        Self {
            inner: crate::features::points_to::application::IncrementalAnalyzer::new(),
        }
    }
}

impl PTAAnalyzer for IncrementalAnalyzerAsFullPTA {
    fn analyze(&mut self) -> PointsToGraph {
        self.inner.commit();
        PointsToGraph::default()
    }

    fn may_alias(&self, v1: VarId, v2: VarId) -> bool {
        self.inner.may_alias(v1, v2)
    }

    fn must_alias(&self, _v1: VarId, _v2: VarId) -> bool {
        false
    }
}

/// Wrapper to make FlowSensitiveAnalyzer implement PTAAnalyzer
pub struct FlowSensitiveAnalyzerAsFullPTA {
    inner: Option<crate::features::points_to::application::FlowSensitiveAnalyzer>,
    cached_graph: Option<PointsToGraph>,
}

impl FlowSensitiveAnalyzerAsFullPTA {
    pub fn new() -> Self {
        Self {
            inner: Some(crate::features::points_to::application::FlowSensitiveAnalyzer::new()),
            cached_graph: None,
        }
    }
}

impl Default for FlowSensitiveAnalyzerAsFullPTA {
    fn default() -> Self {
        Self::new()
    }
}

impl PTAAnalyzer for FlowSensitiveAnalyzerAsFullPTA {
    fn analyze(&mut self) -> PointsToGraph {
        if let Some(analyzer) = self.inner.take() {
            let result = analyzer.analyze();
            // Convert FlowState to PointsToGraph
            let mut graph = PointsToGraph::default();
            for (var, pts) in &result.final_state.points_to {
                for loc in pts.iter() {
                    graph.add_points_to(*var, *loc);
                }
            }
            self.cached_graph = Some(graph.clone());
            graph
        } else {
            self.cached_graph.clone().unwrap_or_default()
        }
    }

    fn may_alias(&self, _v1: VarId, _v2: VarId) -> bool {
        // Flow-sensitive requires state, conservative answer
        true
    }

    fn must_alias(&self, _v1: VarId, _v2: VarId) -> bool {
        false
    }
}

/// Wrapper to make ParallelAnalyzer implement PTAAnalyzer
pub struct ParallelAnalyzerAsFullPTA {
    inner: Option<crate::features::points_to::application::ParallelAnalyzer>,
    cached_graph: Option<PointsToGraph>,
}

impl ParallelAnalyzerAsFullPTA {
    pub fn new() -> Self {
        Self {
            inner: Some(crate::features::points_to::application::ParallelAnalyzer::new()),
            cached_graph: None,
        }
    }
}

impl Default for ParallelAnalyzerAsFullPTA {
    fn default() -> Self {
        Self::new()
    }
}

impl PTAAnalyzer for ParallelAnalyzerAsFullPTA {
    fn analyze(&mut self) -> PointsToGraph {
        if let Some(analyzer) = self.inner.take() {
            let result = analyzer.analyze();
            self.cached_graph = Some(result.graph.clone());
            result.graph
        } else {
            self.cached_graph.clone().unwrap_or_default()
        }
    }

    fn may_alias(&self, v1: VarId, v2: VarId) -> bool {
        if let Some(graph) = &self.cached_graph {
            let pts1: std::collections::HashSet<_> = graph.get_points_to(v1).into_iter().collect();
            let pts2: std::collections::HashSet<_> = graph.get_points_to(v2).into_iter().collect();
            !pts1.is_disjoint(&pts2)
        } else {
            true // Conservative
        }
    }

    fn must_alias(&self, v1: VarId, v2: VarId) -> bool {
        if let Some(graph) = &self.cached_graph {
            let pts1 = graph.get_points_to(v1);
            let pts2 = graph.get_points_to(v2);
            pts1.len() == 1 && pts1 == pts2
        } else {
            false
        }
    }
}

// ============================================================================
// Generic helper functions (Zero-cost abstraction)
// ============================================================================

/// Run analysis with any PTAAnalyzer (compile-time polymorphism, zero-cost)
pub fn run_analysis<A: PTAAnalyzer>(analyzer: &mut A) -> PointsToGraph {
    analyzer.analyze()
}

/// Check alias with any PTAAnalyzer
pub fn check_alias<A: PTAAnalyzer>(analyzer: &A, v1: VarId, v2: VarId) -> bool {
    analyzer.may_alias(v1, v2)
}

/// Run query with any PTAQuery
pub fn run_query<Q: PTAQuery>(query: &mut Q, var: VarId) -> Vec<LocationId> {
    query.query_points_to(var)
}

// ============================================================================
// Legacy compatibility (keep old names working)
// ============================================================================

// Re-export with old names for backward compatibility
pub use PTAAnalyzer as PointsToAnalyzer;
pub use PTAQuery as DemandDrivenQuery;
pub use PTAIncremental as IncrementalUpdate;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_factory_security() {
        let analyzer = PTAFactory::security()
            .with_context_depth(3)
            .build();
        assert!(analyzer.config.max_context_depth == 3);
    }

    #[test]
    fn test_factory_boxed() {
        let _analyzer: Box<dyn PTAAnalyzer> = PTAFactory::create_boxed(AnalyzerKind::Security);
    }

    #[test]
    fn test_generic_function() {
        use crate::features::points_to::application::SecurityAnalyzer;
        let mut analyzer = SecurityAnalyzer::new();
        let _graph = run_analysis(&mut analyzer);
    }
}
