/*
 * Points-to Constraint Extraction from IR
 *
 * Automatically extracts points-to constraints from IR nodes and edges.
 * This bridges the gap between static IR and dynamic points-to analysis.
 *
 * Algorithm:
 * ```
 * for node in ir_nodes:
 *     if node.kind == Variable:
 *         create_variable(node.id)
 *     elif node.kind == Function:
 *         # Function object allocation
 *         add_alloc(node.id, "fn:" + node.fqn)
 *
 * for edge in ir_edges:
 *     if edge.kind == Defines:
 *         # x = alloc()
 *         add_alloc(edge.source, edge.target)
 *     elif edge.kind == Reads:
 *         # y = *x (load)
 *         add_load(edge.target, edge.source)
 *     elif edge.kind == Writes:
 *         # *x = y (store)
 *         add_store(edge.source, edge.target)
 *     elif edge.kind == Calls:
 *         # Indirect call through pointer
 *         add_indirect_call(edge.source, edge.target)
 * ```
 *
 * References:
 * - Andersen (1994): "Program Analysis and Specialization for the C Programming Language"
 * - SHARP (OOPSLA 2022): Incremental context-sensitive pointer analysis
 */

use crate::features::points_to::PointsToAnalyzer;
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind};
use rustc_hash::FxHashSet;

/// Points-to constraint extractor from IR
///
/// Converts IR nodes/edges into points-to constraints for alias analysis.
pub struct PTAIRExtractor {
    /// Variables seen
    variables: FxHashSet<String>,

    /// Allocations seen
    allocations: FxHashSet<String>,
}

impl PTAIRExtractor {
    pub fn new() -> Self {
        Self {
            variables: FxHashSet::default(),
            allocations: FxHashSet::default(),
        }
    }

    /// Extract points-to constraints from IR and add to analyzer
    ///
    /// # Arguments
    /// - `nodes`: IR nodes (variables, functions, classes, etc.)
    /// - `edges`: IR edges (calls, reads, writes, defines)
    /// - `analyzer`: Points-to analyzer to populate
    ///
    /// # Returns
    /// Number of constraints added
    pub fn extract_constraints(
        &mut self,
        nodes: &[Node],
        edges: &[Edge],
        analyzer: &mut PointsToAnalyzer,
    ) -> usize {
        let mut count = 0;

        // Phase 1: Process nodes (create variables and allocations)
        for node in nodes {
            match node.kind {
                NodeKind::Variable | NodeKind::Parameter => {
                    // Create variable
                    if self.variables.insert(node.id.clone()) {
                        count += 1;
                        // Variables are implicitly created when used in constraints
                    }
                }
                NodeKind::Function | NodeKind::Method => {
                    // Function object allocation
                    let alloc_site = format!("fn:{}", node.fqn);
                    if self.allocations.insert(alloc_site.clone()) {
                        analyzer.add_alloc(&node.id, &alloc_site);
                        count += 1;
                    }
                }
                NodeKind::Class | NodeKind::Struct => {
                    // Class/Struct type allocation
                    let alloc_site = format!("type:{}", node.fqn);
                    if self.allocations.insert(alloc_site.clone()) {
                        analyzer.add_alloc(&node.id, &alloc_site);
                        count += 1;
                    }
                }
                _ => {
                    // Other nodes don't contribute to points-to constraints
                }
            }
        }

        // Phase 2: Process edges (create constraints)
        for edge in edges {
            match edge.kind {
                EdgeKind::Defines => {
                    // source defines target → target = alloc(source)
                    // This is simplified; in reality need to distinguish allocation sites
                    let alloc_site = format!("def:{}:{}", edge.source_id, edge.target_id);
                    if self.allocations.insert(alloc_site.clone()) {
                        analyzer.add_alloc(&edge.target_id, &alloc_site);
                        count += 1;
                    }
                }
                EdgeKind::Reads => {
                    // source reads target → source = *target (load)
                    analyzer.add_load(&edge.source_id, &edge.target_id);
                    count += 1;
                }
                EdgeKind::Writes => {
                    // source writes target → *source = target (store)
                    analyzer.add_store(&edge.source_id, &edge.target_id);
                    count += 1;
                }
                EdgeKind::Calls => {
                    // Function call: source calls target
                    // For interprocedural analysis, track call relationships
                    // This is a simplified version - full implementation would handle
                    // return values and parameters

                    // Model as: source = target (copy constraint for function pointer)
                    analyzer.add_copy(&edge.source_id, &edge.target_id);
                    count += 1;
                }
                EdgeKind::References => {
                    // source references target → source = &target (address-of)
                    // Model as simple copy for now
                    analyzer.add_copy(&edge.source_id, &edge.target_id);
                    count += 1;
                }
                _ => {
                    // Other edges don't contribute to points-to constraints
                }
            }
        }

        #[cfg(feature = "trace")]
        eprintln!(
            "[PTA IR Extractor] Added {} constraints from {} nodes, {} edges",
            count,
            nodes.len(),
            edges.len()
        );

        count
    }

    /// Get statistics
    pub fn stats(&self) -> PTAExtractionStats {
        PTAExtractionStats {
            variables_count: self.variables.len(),
            allocations_count: self.allocations.len(),
        }
    }

    /// Reset state
    pub fn reset(&mut self) {
        self.variables.clear();
        self.allocations.clear();
    }
}

impl Default for PTAIRExtractor {
    fn default() -> Self {
        Self::new()
    }
}

/// PTA extraction statistics
#[derive(Debug, Clone)]
pub struct PTAExtractionStats {
    pub variables_count: usize,
    pub allocations_count: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::points_to::{AnalysisConfig, AnalysisMode};
    use crate::shared::models::Span;

    fn create_var_node(id: &str) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Variable,
            format!("test::{}", id),
            "test.py".to_string(),
            Span::zero(),
        )
        .with_name(id)
    }

    fn create_func_node(id: &str) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Function,
            format!("test::{}", id),
            "test.py".to_string(),
            Span::zero(),
        )
        .with_name(id)
    }

    fn create_edge(source: &str, target: &str, kind: EdgeKind) -> Edge {
        Edge {
            source_id: source.to_string(),
            target_id: target.to_string(),
            kind,
            span: None,
            metadata: None,
            attrs: None,
        }
    }

    #[test]
    fn test_basic_extraction() {
        let nodes = vec![create_var_node("x"), create_var_node("y")];
        let edges = vec![
            create_edge("y", "x", EdgeKind::Defines), // y = alloc x
        ];

        let mut extractor = PTAIRExtractor::new();
        let config = AnalysisConfig {
            mode: AnalysisMode::Fast,
            ..Default::default()
        };
        let mut analyzer = PointsToAnalyzer::new(config);

        let count = extractor.extract_constraints(&nodes, &edges, &mut analyzer);
        assert!(count > 0);

        let stats = extractor.stats();
        assert_eq!(stats.variables_count, 2);
        assert_eq!(stats.allocations_count, 1);
    }

    #[test]
    fn test_function_allocation() {
        let nodes = vec![create_func_node("foo"), create_var_node("func_ptr")];
        let edges = vec![create_edge("func_ptr", "foo", EdgeKind::References)];

        let mut extractor = PTAIRExtractor::new();
        let config = AnalysisConfig::default();
        let mut analyzer = PointsToAnalyzer::new(config);

        let count = extractor.extract_constraints(&nodes, &edges, &mut analyzer);
        assert!(count >= 2); // 1 alloc for function + 1 copy

        let stats = extractor.stats();
        assert_eq!(stats.allocations_count, 1); // fn:test::foo
    }

    #[test]
    fn test_load_store() {
        let nodes = vec![create_var_node("ptr"), create_var_node("val")];
        let edges = vec![
            create_edge("val", "ptr", EdgeKind::Reads),  // val = *ptr
            create_edge("ptr", "val", EdgeKind::Writes), // *ptr = val
        ];

        let mut extractor = PTAIRExtractor::new();
        let config = AnalysisConfig::default();
        let mut analyzer = PointsToAnalyzer::new(config);

        let count = extractor.extract_constraints(&nodes, &edges, &mut analyzer);
        assert!(
            count >= 2,
            "Should extract at least 2 constraints (1 load + 1 store), got {}",
            count
        );
    }

    #[test]
    fn test_call_constraint() {
        let nodes = vec![create_func_node("main"), create_func_node("foo")];
        let edges = vec![create_edge("main", "foo", EdgeKind::Calls)];

        let mut extractor = PTAIRExtractor::new();
        let config = AnalysisConfig::default();
        let mut analyzer = PointsToAnalyzer::new(config);

        let count = extractor.extract_constraints(&nodes, &edges, &mut analyzer);
        assert!(count >= 3); // 2 allocs (functions) + 1 call
    }
}
