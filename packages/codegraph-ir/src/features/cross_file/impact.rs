//! Impact Analysis (SOTA - Priority 3)
//!
//! Compute the impact of changing a symbol on the codebase.
//!
//! Academic SOTA:
//! - Change Impact Analysis (IEEE): Transitive dependency closure
//! - Program Slicing (Weiser 1981): Backward slicing for affected code
//! - Dependency-based Test Selection: Only run affected tests
//!
//! Industry SOTA:
//! - JetBrains Safe Refactoring: Pre-refactoring impact preview
//! - Visual Studio Code Navigation: "Find All References"
//! - Bazel/Buck: Minimal rebuild based on dependency graph
//!
//! Key features:
//! - Direct and transitive dependent analysis
//! - Risk scoring (0.0-1.0) based on usage frequency
//! - Affected file computation for incremental updates
//! - Test impact analysis (which tests need to run?)

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

use super::symbol_graph::{SymbolDependencyGraph, SymbolEdgeKind};

/// Impact analysis result
///
/// Computes what breaks if a symbol is changed/removed
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImpactAnalysis {
    /// Symbol being analyzed
    pub target_fqn: String,

    /// Symbols that directly depend on target
    pub direct_dependents: Vec<String>,

    /// Symbols that transitively depend on target
    pub transitive_dependents: Vec<String>,

    /// Files affected by the change
    pub affected_files: Vec<String>,

    /// Risk score (0.0-1.0)
    ///
    /// Higher = more impact (more dependents)
    /// - 0.0-0.3: Low risk (few dependents)
    /// - 0.3-0.7: Medium risk
    /// - 0.7-1.0: High risk (many dependents, core infrastructure)
    pub risk_score: f64,

    /// Call chain depth (for functions)
    ///
    /// Maximum depth of call chains starting from this symbol
    pub max_call_depth: usize,

    /// Impact by edge type
    pub impact_by_kind: HashMap<SymbolEdgeKind, usize>,
}

impl ImpactAnalysis {
    /// Compute impact of changing a symbol
    ///
    /// SOTA: Multi-dimensional impact analysis
    pub fn compute(
        graph: &SymbolDependencyGraph,
        target_fqn: &str,
        total_symbols: usize,
    ) -> Option<Self> {
        // Verify symbol exists
        let _target_symbol = graph.get_symbol(target_fqn)?;

        // Get direct dependents
        let direct_dependents = graph.get_dependents(target_fqn, None);

        // Get transitive dependents
        let transitive_dependents = graph.get_transitive_dependents(target_fqn);

        // Compute affected files
        let affected_files = Self::compute_affected_files(graph, &transitive_dependents);

        // Compute risk score
        let risk_score = Self::compute_risk_score(
            direct_dependents.len(),
            transitive_dependents.len(),
            total_symbols,
        );

        // Compute max call depth (if function)
        let max_call_depth = if let Some(call_graph) = graph.call_graph() {
            Self::compute_max_call_depth(call_graph, target_fqn)
        } else {
            0
        };

        // Impact by edge kind
        let mut impact_by_kind = HashMap::new();
        for kind in [
            SymbolEdgeKind::Calls,
            SymbolEdgeKind::Inherits,
            SymbolEdgeKind::Reads,
            SymbolEdgeKind::Writes,
            SymbolEdgeKind::Imports,
        ] {
            let count = graph.get_dependents(target_fqn, Some(kind)).len();
            if count > 0 {
                impact_by_kind.insert(kind, count);
            }
        }

        Some(ImpactAnalysis {
            target_fqn: target_fqn.to_string(),
            direct_dependents,
            transitive_dependents,
            affected_files,
            risk_score,
            max_call_depth,
            impact_by_kind,
        })
    }

    /// Compute affected files from dependent symbols
    fn compute_affected_files(
        graph: &SymbolDependencyGraph,
        dependent_fqns: &[String],
    ) -> Vec<String> {
        let mut files = HashSet::new();

        for fqn in dependent_fqns {
            if let Some(symbol) = graph.get_symbol(fqn) {
                files.insert(symbol.file_path.clone());
            }
        }

        files.into_iter().collect()
    }

    /// Compute risk score based on dependent count
    ///
    /// Formula: min(1.0, (transitive_count / total_symbols) * 10.0)
    ///
    /// Logic:
    /// - If 10% of codebase depends on this: High risk (1.0)
    /// - If 5% of codebase depends on this: Medium-high risk (0.5)
    /// - If 1% of codebase depends on this: Low-medium risk (0.1)
    fn compute_risk_score(
        direct_count: usize,
        transitive_count: usize,
        total_symbols: usize,
    ) -> f64 {
        if total_symbols == 0 {
            return 0.0;
        }

        // Base score from transitive impact
        let transitive_ratio = transitive_count as f64 / total_symbols as f64;
        let base_score = (transitive_ratio * 10.0).min(1.0);

        // Boost score if high direct impact (sign of core infrastructure)
        let direct_ratio = direct_count as f64 / total_symbols as f64;
        let direct_boost = (direct_ratio * 5.0).min(0.3);

        (base_score + direct_boost).min(1.0)
    }

    /// Compute maximum call depth from this function
    fn compute_max_call_depth(call_graph: &super::symbol_graph::CallGraph, fqn: &str) -> usize {
        let mut max_depth = 0;
        let mut visited = HashSet::new();
        Self::dfs_call_depth(call_graph, fqn, 0, &mut visited, &mut max_depth);
        max_depth
    }

    fn dfs_call_depth(
        call_graph: &super::symbol_graph::CallGraph,
        fqn: &str,
        current_depth: usize,
        visited: &mut HashSet<String>,
        max_depth: &mut usize,
    ) {
        if !visited.insert(fqn.to_string()) {
            return; // Cycle detected
        }

        *max_depth = (*max_depth).max(current_depth);

        for callee in call_graph.get_callees(fqn) {
            Self::dfs_call_depth(call_graph, &callee, current_depth + 1, visited, max_depth);
        }

        visited.remove(fqn);
    }

    /// Get risk level as enum
    pub fn risk_level(&self) -> RiskLevel {
        if self.risk_score >= 0.7 {
            RiskLevel::High
        } else if self.risk_score >= 0.3 {
            RiskLevel::Medium
        } else {
            RiskLevel::Low
        }
    }

    /// Is this a breaking change? (high risk)
    pub fn is_breaking(&self) -> bool {
        self.risk_score >= 0.7
    }
}

/// Risk level classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RiskLevel {
    Low,    // 0.0-0.3
    Medium, // 0.3-0.7
    High,   // 0.7-1.0
}

/// Batch impact analysis for multiple symbols
///
/// Useful for analyzing impact of refactoring multiple symbols at once
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchImpactAnalysis {
    pub impacts: Vec<ImpactAnalysis>,
    pub total_affected_files: Vec<String>,
    pub max_risk_score: f64,
    pub summary: ImpactSummary,
}

impl BatchImpactAnalysis {
    /// Compute impact for multiple symbols
    pub fn compute(graph: &SymbolDependencyGraph, target_fqns: &[String]) -> Self {
        let total_symbols = graph.stats().total_symbols;

        let impacts: Vec<ImpactAnalysis> = target_fqns
            .iter()
            .filter_map(|fqn| ImpactAnalysis::compute(graph, fqn, total_symbols))
            .collect();

        // Aggregate affected files
        let mut all_files = HashSet::new();
        for impact in &impacts {
            for file in &impact.affected_files {
                all_files.insert(file.clone());
            }
        }

        let total_affected_files: Vec<String> = all_files.into_iter().collect();

        // Find max risk
        let max_risk_score = impacts.iter().map(|i| i.risk_score).fold(0.0, f64::max);

        // Compute summary
        let summary = ImpactSummary {
            total_symbols_changed: target_fqns.len(),
            total_dependents: impacts.iter().map(|i| i.transitive_dependents.len()).sum(),
            total_affected_files: total_affected_files.len(),
            high_risk_count: impacts
                .iter()
                .filter(|i| i.risk_level() == RiskLevel::High)
                .count(),
            medium_risk_count: impacts
                .iter()
                .filter(|i| i.risk_level() == RiskLevel::Medium)
                .count(),
            low_risk_count: impacts
                .iter()
                .filter(|i| i.risk_level() == RiskLevel::Low)
                .count(),
        };

        BatchImpactAnalysis {
            impacts,
            total_affected_files,
            max_risk_score,
            summary,
        }
    }
}

/// Impact summary statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImpactSummary {
    pub total_symbols_changed: usize,
    pub total_dependents: usize,
    pub total_affected_files: usize,
    pub high_risk_count: usize,
    pub medium_risk_count: usize,
    pub low_risk_count: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::cross_file::IRDocument;
    use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};

    fn make_test_node(id: &str, kind: NodeKind, fqn: &str, file_path: &str) -> Node {
        Node::new(
            id.to_string(),
            kind,
            fqn.to_string(),
            file_path.to_string(),
            Span::new(1, 0, 10, 0),
        )
        .with_name(fqn.split('.').last().unwrap_or(fqn).to_string())
    }

    fn make_call_edge(source_id: &str, target_id: &str) -> Edge {
        Edge::new(
            source_id.to_string(),
            target_id.to_string(),
            EdgeKind::Calls,
        )
    }

    #[test]
    fn test_impact_analysis_simple() {
        // a calls b, c calls b
        let ir = IRDocument {
            file_path: "src/test.py".to_string(),
            nodes: vec![
                make_test_node("a", NodeKind::Function, "test.a", "src/test.py"),
                make_test_node("b", NodeKind::Function, "test.b", "src/test.py"),
                make_test_node("c", NodeKind::Function, "test.c", "src/test.py"),
            ],
            edges: vec![make_call_edge("a", "b"), make_call_edge("c", "b")],
            repo_id: None,
        };

        let graph = SymbolDependencyGraph::build_from_irs(&[ir]);
        let total_symbols = graph.stats().total_symbols;

        // Analyze impact of changing 'b'
        let impact = ImpactAnalysis::compute(&graph, "test.b", total_symbols)
            .expect("Impact analysis failed");

        assert_eq!(impact.target_fqn, "test.b");
        assert_eq!(impact.direct_dependents.len(), 2); // a and c
        assert!(impact.direct_dependents.contains(&"test.a".to_string()));
        assert!(impact.direct_dependents.contains(&"test.c".to_string()));
    }

    #[test]
    #[ignore]
    fn test_risk_scoring() {
        // a → b → c → d (chain)
        let ir = IRDocument {
            file_path: "src/test.py".to_string(),
            nodes: vec![
                make_test_node("a", NodeKind::Function, "test.a", "src/test.py"),
                make_test_node("b", NodeKind::Function, "test.b", "src/test.py"),
                make_test_node("c", NodeKind::Function, "test.c", "src/test.py"),
                make_test_node("d", NodeKind::Function, "test.d", "src/test.py"),
            ],
            edges: vec![
                make_call_edge("a", "b"),
                make_call_edge("b", "c"),
                make_call_edge("c", "d"),
            ],
            repo_id: None,
        };

        let graph = SymbolDependencyGraph::build_from_irs(&[ir]);
        let total_symbols = graph.stats().total_symbols;

        // Analyze impact of 'd' (leaf node - low risk)
        let impact_d = ImpactAnalysis::compute(&graph, "test.d", total_symbols).unwrap();
        assert_eq!(impact_d.risk_level(), RiskLevel::High); // 3/4 = 75% dependency

        // Analyze impact of 'a' (root node - no dependents)
        let impact_a = ImpactAnalysis::compute(&graph, "test.a", total_symbols).unwrap();
        assert_eq!(impact_a.direct_dependents.len(), 0);
        assert_eq!(impact_a.risk_level(), RiskLevel::Low);
    }

    #[test]
    fn test_batch_impact_analysis() {
        let ir = IRDocument {
            file_path: "src/test.py".to_string(),
            nodes: vec![
                make_test_node("a", NodeKind::Function, "test.a", "src/test.py"),
                make_test_node("b", NodeKind::Function, "test.b", "src/test.py"),
                make_test_node("c", NodeKind::Function, "test.c", "src/test.py"),
            ],
            edges: vec![make_call_edge("a", "b"), make_call_edge("b", "c")],
            repo_id: None,
        };

        let graph = SymbolDependencyGraph::build_from_irs(&[ir]);

        let batch =
            BatchImpactAnalysis::compute(&graph, &["test.b".to_string(), "test.c".to_string()]);

        assert_eq!(batch.impacts.len(), 2);
        assert_eq!(batch.summary.total_symbols_changed, 2);
        assert!(batch
            .total_affected_files
            .contains(&"src/test.py".to_string()));
    }

    #[test]
    fn test_call_depth_calculation() {
        // a → b → c → d (depth 3)
        let ir = IRDocument {
            file_path: "src/test.py".to_string(),
            nodes: vec![
                make_test_node("a", NodeKind::Function, "test.a", "src/test.py"),
                make_test_node("b", NodeKind::Function, "test.b", "src/test.py"),
                make_test_node("c", NodeKind::Function, "test.c", "src/test.py"),
                make_test_node("d", NodeKind::Function, "test.d", "src/test.py"),
            ],
            edges: vec![
                make_call_edge("a", "b"),
                make_call_edge("b", "c"),
                make_call_edge("c", "d"),
            ],
            repo_id: None,
        };

        let graph = SymbolDependencyGraph::build_from_irs(&[ir]);
        let total_symbols = graph.stats().total_symbols;

        let impact_a = ImpactAnalysis::compute(&graph, "test.a", total_symbols).unwrap();
        assert_eq!(impact_a.max_call_depth, 3); // a → b → c → d

        let impact_b = ImpactAnalysis::compute(&graph, "test.b", total_symbols).unwrap();
        assert_eq!(impact_b.max_call_depth, 2); // b → c → d
    }
}
