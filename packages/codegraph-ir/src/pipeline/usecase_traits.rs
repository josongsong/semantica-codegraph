//! UseCase Traits for Dependency Inversion
//!
//! **SOLID Principle D**: Depend on abstractions, not concretions.
//!
//! These traits define the contracts for UseCases used by the orchestrator,
//! enabling:
//! - Easy mocking for unit tests
//! - Swappable implementations
//! - Clear dependency boundaries
//!
//! # Example
//! ```rust,ignore
//! // Production
//! let orchestrator = IRIndexingOrchestrator::new(config);
//!
//! // Testing with mocks
//! let orchestrator = IRIndexingOrchestrator::builder(config)
//!     .with_effect_usecase(MockEffectUseCase::new())
//!     .build();
//! ```

use crate::config::stage_configs::{TaintConfig, PTAConfig, CloneConfig, ChunkingConfig};
use crate::config::preset::Preset;
use crate::features::chunking::domain::Chunk;
use crate::features::cross_file::IRDocument;
use crate::features::effect_analysis::EffectSet;
use crate::features::concurrency_analysis::RaceCondition;
use crate::pipeline::stages::TaintSummary;
use crate::shared::models::{Node, Edge};
use std::collections::HashMap;
use std::sync::Arc;

// ============================================================================
// Effect Analysis UseCase Trait
// ============================================================================

/// Trait for effect analysis use case
///
/// Implementations analyze function purity and side effects.
pub trait EffectUseCase: Send + Sync {
    /// Analyze all functions in IR document for effects
    fn analyze_all_effects(&self, ir_doc: &IRDocument) -> HashMap<String, EffectSet>;
}

// ============================================================================
// Concurrency Analysis UseCase Trait
// ============================================================================

/// Trait for concurrency analysis use case
///
/// Implementations detect race conditions and deadlocks.
pub trait ConcurrencyUseCase: Send + Sync {
    /// Analyze all async functions for race conditions
    fn analyze_all(&self, ir_doc: &IRDocument) -> Result<Vec<RaceCondition>, crate::features::concurrency_analysis::ConcurrencyError>;
}

// ============================================================================
// Chunking UseCase Trait
// ============================================================================

/// Input for chunking analysis
pub struct ChunkingInput<'a> {
    pub file_path: &'a str,
    pub content: &'a str,
    pub nodes: &'a [crate::shared::models::Node],
    pub edges: &'a [crate::shared::models::Edge],
}

/// Trait for chunking use case
///
/// Implementations create searchable chunks from IR.
pub trait ChunkingUseCase: Send + Sync {
    /// Build chunks from input
    fn build_chunks(&self, input: ChunkingInput<'_>) -> Vec<Chunk>;
}

// ============================================================================
// Default Implementations (connect to existing UseCases)
// ============================================================================

use crate::features::effect_analysis::application::EffectAnalysisUseCase;
use crate::features::concurrency_analysis::application::ConcurrencyAnalysisUseCase;
use crate::features::chunking::application::ChunkingUseCaseImpl;

impl EffectUseCase for EffectAnalysisUseCase {
    fn analyze_all_effects(&self, ir_doc: &IRDocument) -> HashMap<String, EffectSet> {
        self.analyze_all_effects(ir_doc)
    }
}

impl ConcurrencyUseCase for ConcurrencyAnalysisUseCase {
    fn analyze_all(&self, ir_doc: &IRDocument) -> Result<Vec<RaceCondition>, crate::features::concurrency_analysis::ConcurrencyError> {
        self.analyze_all(ir_doc)
    }
}

// Note: ChunkingUseCase implementation is more complex due to different API
// Will be implemented separately if needed

// ============================================================================
// Taint Analysis UseCase Trait
// ============================================================================

/// Input for taint analysis
pub struct TaintAnalysisInput {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
}

/// Trait for taint analysis use case
///
/// Implementations perform interprocedural taint tracking.
pub trait TaintUseCase: Send + Sync {
    /// Analyze taint flows across the codebase
    fn analyze_taint(&self, input: TaintAnalysisInput) -> Vec<TaintSummary>;
}

/// Default implementation using TaintAnalyzer (infrastructure)
///
/// **RFC-001 Config Integration**: Accepts TaintConfig for IFDS/IDE settings
pub struct TaintAnalysisUseCaseImpl {
    config: TaintConfig,
}

impl TaintAnalysisUseCaseImpl {
    /// Create with specific TaintConfig
    pub fn new(config: TaintConfig) -> Self {
        Self { config }
    }

    /// Create with preset (convenience)
    pub fn from_preset(preset: Preset) -> Self {
        Self::new(TaintConfig::from_preset(preset))
    }

    /// Get current config (for debugging/logging)
    pub fn config(&self) -> &TaintConfig {
        &self.config
    }
}

impl Default for TaintAnalysisUseCaseImpl {
    fn default() -> Self {
        Self::new(TaintConfig::from_preset(Preset::Balanced))
    }
}

impl TaintUseCase for TaintAnalysisUseCaseImpl {
    fn analyze_taint(&self, input: TaintAnalysisInput) -> Vec<TaintSummary> {
        use crate::features::taint_analysis::infrastructure::taint::{TaintAnalyzer, CallGraphNode, TaintPath, TaintSeverity};

        // Log config settings
        eprintln!(
            "[TaintUseCase] Config: max_depth={}, max_paths={}, ifds={}, sanitizers={}",
            self.config.max_depth,
            self.config.max_paths,
            self.config.ifds_enabled,
            self.config.detect_sanitizers
        );

        // Build call graph
        let mut call_graph: HashMap<String, Vec<String>> = HashMap::new();
        for edge in &input.edges {
            if matches!(edge.kind, crate::shared::models::EdgeKind::Calls) {
                call_graph
                    .entry(edge.source_id.clone())
                    .or_insert_with(Vec::new)
                    .push(edge.target_id.clone());
            }
        }

        // Convert to CallGraphNode format
        let mut cg_nodes: HashMap<String, CallGraphNode> = HashMap::new();

        for node in &input.nodes {
            let callees = call_graph.get(&node.id).cloned().unwrap_or_default();
            cg_nodes.insert(
                node.id.clone(),
                CallGraphNode {
                    id: node.id.clone(),
                    name: node.fqn.clone(),
                    callees,
                },
            );
        }

        // Add external call targets
        for edge in &input.edges {
            if matches!(edge.kind, crate::shared::models::EdgeKind::Calls)
                && !cg_nodes.contains_key(&edge.target_id)
            {
                cg_nodes.insert(
                    edge.target_id.clone(),
                    CallGraphNode {
                        id: edge.target_id.clone(),
                        name: edge.target_id.clone(),
                        callees: Vec::new(),
                    },
                );
            }
        }

        // Run taint analysis
        let analyzer = TaintAnalyzer::new();
        let mut taint_paths = analyzer.analyze(&cg_nodes);

        // Apply config: filter sanitized paths if detect_sanitizers is enabled
        if self.config.detect_sanitizers {
            taint_paths.retain(|p| !p.is_sanitized);
        }

        // Apply config: limit max paths
        if taint_paths.len() > self.config.max_paths {
            taint_paths.truncate(self.config.max_paths);
        }

        // Add intra-procedural taint detection
        for (func_id, func_node) in &cg_nodes {
            if func_node.name.starts_with("builtins.") || func_node.name.starts_with("os.") {
                continue;
            }

            if analyzer.get_sources().iter().any(|s| s.matches(&func_node.name))
                || analyzer.get_sinks().iter().any(|s| s.matches(&func_node.name))
            {
                continue;
            }

            // Find callees that are sources
            let source_callees: Vec<String> = func_node
                .callees
                .iter()
                .filter(|callee_id| {
                    cg_nodes
                        .get(*callee_id)
                        .map(|node| analyzer.get_sources().iter().any(|s| s.matches(&node.name)))
                        .unwrap_or(false)
                })
                .cloned()
                .collect();

            // Find callees that are sinks
            let sink_callees: Vec<String> = func_node
                .callees
                .iter()
                .filter(|callee_id| {
                    cg_nodes
                        .get(*callee_id)
                        .map(|node| analyzer.get_sinks().iter().any(|s| s.matches(&node.name)))
                        .unwrap_or(false)
                })
                .cloned()
                .collect();

            // If function calls both source AND sink - potential intra-procedural flow
            if !source_callees.is_empty() && !sink_callees.is_empty() {
                for source in &source_callees {
                    for sink in &sink_callees {
                        taint_paths.push(TaintPath {
                            source: source.clone(),
                            sink: sink.clone(),
                            path: vec![source.clone(), func_id.clone(), sink.clone()],
                            is_sanitized: false,
                            severity: TaintSeverity::High,
                        });
                    }
                }
            }
        }

        // Group by function and convert to stages::TaintSummary format
        let mut function_summaries: HashMap<String, TaintSummary> = HashMap::new();

        for path in &taint_paths {
            if let Some(first_func) = path.path.first() {
                let summary = function_summaries
                    .entry(first_func.clone())
                    .or_insert_with(|| TaintSummary {
                        function_id: first_func.clone(),
                        sources_found: 0,
                        sinks_found: 0,
                        taint_flows: 0,
                    });

                summary.sources_found += 1;
                summary.sinks_found += 1;
                summary.taint_flows += 1;
            }
        }

        function_summaries.into_values().collect()
    }
}

// ============================================================================
// PTA (Points-To Analysis) UseCase Trait
// ============================================================================

use crate::pipeline::processor::PointsToSummary;

/// Input for points-to analysis
pub struct PTAInput {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
}

/// Trait for points-to analysis use case
///
/// Implementations perform pointer/reference analysis for precision.
pub trait PTAUseCase: Send + Sync {
    /// Run points-to analysis
    fn analyze_pta(&self, input: PTAInput) -> PointsToSummary;
}

/// Default PTA implementation with Config support
pub struct PTAUseCaseImpl {
    config: PTAConfig,
}

impl PTAUseCaseImpl {
    pub fn new(config: PTAConfig) -> Self {
        Self { config }
    }

    pub fn from_preset(preset: Preset) -> Self {
        Self::new(PTAConfig::from_preset(preset))
    }

    pub fn config(&self) -> &PTAConfig {
        &self.config
    }
}

impl Default for PTAUseCaseImpl {
    fn default() -> Self {
        Self::new(PTAConfig::from_preset(Preset::Balanced))
    }
}

impl PTAUseCase for PTAUseCaseImpl {
    fn analyze_pta(&self, input: PTAInput) -> PointsToSummary {
        eprintln!(
            "[PTAUseCase] Config: mode={:?}, field_sensitive={}, parallel={}",
            self.config.mode,
            self.config.field_sensitive,
            self.config.enable_parallel
        );

        // Note: Actual PTA logic is called in execute_l6_points_to
        // This trait allows for DI and mocking in tests
        PointsToSummary {
            variables_count: input.nodes.len(),
            allocations_count: 0,
            constraints_count: input.edges.len(),
            alias_pairs: 0,
            mode_used: format!("{:?}", self.config.mode),
            duration_ms: 0.0,
        }
    }
}

// ============================================================================
// Clone Detection UseCase Trait
// ============================================================================

use crate::pipeline::end_to_end_result::ClonePairSummary;

/// Input for clone detection
pub struct CloneInput<'a> {
    pub nodes: &'a [Node],
    pub file_contents: &'a HashMap<String, String>,
}

/// Trait for clone detection use case
pub trait CloneUseCase: Send + Sync {
    /// Detect code clones
    fn detect_clones(&self, input: CloneInput<'_>) -> Vec<ClonePairSummary>;
}

/// Default Clone implementation with Config support
pub struct CloneUseCaseImpl {
    config: CloneConfig,
}

impl CloneUseCaseImpl {
    pub fn new(config: CloneConfig) -> Self {
        Self { config }
    }

    pub fn from_preset(preset: Preset) -> Self {
        Self::new(CloneConfig::from_preset(preset))
    }

    pub fn config(&self) -> &CloneConfig {
        &self.config
    }
}

impl Default for CloneUseCaseImpl {
    fn default() -> Self {
        Self::new(CloneConfig::from_preset(Preset::Balanced))
    }
}

impl CloneUseCase for CloneUseCaseImpl {
    fn detect_clones(&self, input: CloneInput<'_>) -> Vec<ClonePairSummary> {
        eprintln!(
            "[CloneUseCase] Config: types_enabled={:?}",
            self.config.types_enabled
        );

        // Note: Actual clone detection logic is called in execute_l10_clone_detection
        // This trait allows for DI and mocking in tests
        Vec::new()
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // Mock implementations for testing
    struct MockEffectUseCase;

    impl EffectUseCase for MockEffectUseCase {
        fn analyze_all_effects(&self, _ir_doc: &IRDocument) -> HashMap<String, EffectSet> {
            // Return mock data
            let mut result = HashMap::new();
            result.insert("mock_function".to_string(), EffectSet::pure("mock_function".to_string()));
            result
        }
    }

    struct MockConcurrencyUseCase;

    impl ConcurrencyUseCase for MockConcurrencyUseCase {
        fn analyze_all(&self, _ir_doc: &IRDocument) -> Result<Vec<RaceCondition>, crate::features::concurrency_analysis::ConcurrencyError> {
            // Return empty - no races in mock
            Ok(vec![])
        }
    }

    #[test]
    fn test_effect_usecase_trait() {
        let mock = MockEffectUseCase;
        let ir_doc = IRDocument::new("test.py".to_string(), vec![], vec![]);

        let result = mock.analyze_all_effects(&ir_doc);
        assert!(result.contains_key("mock_function"));
    }

    #[test]
    fn test_concurrency_usecase_trait() {
        let mock = MockConcurrencyUseCase;
        let ir_doc = IRDocument::new("test.py".to_string(), vec![], vec![]);

        let result = mock.analyze_all(&ir_doc).unwrap();
        assert!(result.is_empty());
    }

    #[test]
    fn test_default_impl_effect_usecase() {
        // Test that EffectAnalysisUseCase implements EffectUseCase trait
        let usecase = EffectAnalysisUseCase::new();
        let ir_doc = IRDocument::new("test.py".to_string(), vec![], vec![]);

        // Should compile and run
        let _result: HashMap<String, EffectSet> = <EffectAnalysisUseCase as EffectUseCase>::analyze_all_effects(&usecase, &ir_doc);
    }

    #[test]
    fn test_default_impl_concurrency_usecase() {
        // Test that ConcurrencyAnalysisUseCase implements ConcurrencyUseCase trait
        let usecase = ConcurrencyAnalysisUseCase::new();
        let ir_doc = IRDocument::new("test.py".to_string(), vec![], vec![]);

        // Should compile and run
        let _result = <ConcurrencyAnalysisUseCase as ConcurrencyUseCase>::analyze_all(&usecase, &ir_doc);
    }

    #[test]
    fn test_trait_object_boxing() {
        // Test that traits can be used as trait objects
        let effect: Box<dyn EffectUseCase> = Box::new(MockEffectUseCase);
        let concurrency: Box<dyn ConcurrencyUseCase> = Box::new(MockConcurrencyUseCase);

        let ir_doc = IRDocument::new("test.py".to_string(), vec![], vec![]);

        // Both should work as trait objects
        let _ = effect.analyze_all_effects(&ir_doc);
        let _ = concurrency.analyze_all(&ir_doc);
    }
}
