/*
 * Call Graph Builder for IR Integration
 *
 * Builds call graph from IR nodes and edges for interprocedural taint analysis.
 *
 * Integration with Rust IR Pipeline:
 * - Extracts function calls from IR
 * - Implements CallGraphProvider trait
 * - Enables interprocedural analysis on IR
 */

use super::interprocedural_taint::CallGraphProvider;
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind};
use std::collections::{HashMap, HashSet};

/// Call graph built from IR
///
/// Extracts call relationships from IR nodes and edges.
pub struct IRCallGraph {
    /// Function -> Callees mapping
    calls: HashMap<String, Vec<String>>,

    /// All functions in the graph
    functions: HashSet<String>,
}

impl IRCallGraph {
    /// Create new empty call graph
    pub fn new() -> Self {
        Self {
            calls: HashMap::new(),
            functions: HashSet::new(),
        }
    }

    /// Build call graph from IR nodes and edges
    ///
    /// # Arguments
    /// * `nodes` - IR nodes
    /// * `edges` - IR edges
    ///
    /// # Returns
    /// Call graph ready for analysis
    pub fn build_from_ir(nodes: &[Node], edges: &[Edge]) -> Self {
        let mut graph = Self::new();

        // Extract function nodes
        for node in nodes {
            if matches!(node.kind, NodeKind::Function | NodeKind::Method) {
                graph.functions.insert(node.id.clone());
            }
        }

        // Extract call edges
        for edge in edges {
            if edge.kind == EdgeKind::Calls {
                // Add function if not already present
                graph.functions.insert(edge.source_id.clone());
                graph.functions.insert(edge.target_id.clone());

                // Add call relationship
                graph
                    .calls
                    .entry(edge.source_id.clone())
                    .or_insert_with(Vec::new)
                    .push(edge.target_id.clone());
            }
        }

        #[cfg(feature = "trace")]
        eprintln!(
            "[Call Graph] Built from IR: {} functions, {} call edges",
            graph.functions.len(),
            graph.calls.values().map(|v| v.len()).sum::<usize>()
        );

        graph
    }

    /// Get number of functions
    pub fn function_count(&self) -> usize {
        self.functions.len()
    }

    /// Get number of call edges
    pub fn edge_count(&self) -> usize {
        self.calls.values().map(|v| v.len()).sum()
    }

    /// Get functions with no callees (leaf functions)
    pub fn leaf_functions(&self) -> Vec<String> {
        self.functions
            .iter()
            .filter(|f| !self.calls.contains_key(*f))
            .cloned()
            .collect()
    }

    /// Get functions with no callers (entry points)
    pub fn entry_points(&self) -> Vec<String> {
        let all_callees: HashSet<String> = self
            .calls
            .values()
            .flat_map(|v| v.iter())
            .cloned()
            .collect();

        self.functions
            .iter()
            .filter(|f| !all_callees.contains(*f))
            .cloned()
            .collect()
    }
}

impl Default for IRCallGraph {
    fn default() -> Self {
        Self::new()
    }
}

impl CallGraphProvider for IRCallGraph {
    fn get_callees(&self, func_name: &str) -> Vec<String> {
        self.calls.get(func_name).cloned().unwrap_or_default()
    }

    fn get_functions(&self) -> Vec<String> {
        self.functions.iter().cloned().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    fn create_test_node(id: &str, kind: NodeKind) -> Node {
        Node::new(
            id.to_string(),
            kind,
            format!("test::{}", id), // fqn
            "test.py".to_string(),   // file_path
            Span::zero(),
        )
        .with_name(id)
    }

    fn create_call_edge(source: &str, target: &str) -> Edge {
        Edge {
            source_id: source.to_string(),
            target_id: target.to_string(),
            kind: EdgeKind::Calls,
            span: None,
            metadata: None,
            attrs: None,
        }
    }

    #[test]
    fn test_empty_call_graph() {
        let graph = IRCallGraph::new();
        assert_eq!(graph.function_count(), 0);
        assert_eq!(graph.edge_count(), 0);
    }

    #[test]
    fn test_build_from_ir_simple() {
        let nodes = vec![
            create_test_node("main", NodeKind::Function),
            create_test_node("foo", NodeKind::Function),
        ];
        let edges = vec![create_call_edge("main", "foo")];

        let graph = IRCallGraph::build_from_ir(&nodes, &edges);

        assert_eq!(graph.function_count(), 2);
        assert_eq!(graph.edge_count(), 1);
        assert_eq!(graph.get_callees("main"), vec!["foo"]);
        assert_eq!(graph.get_callees("foo"), Vec::<String>::new());
    }

    #[test]
    fn test_build_from_ir_multi_hop() {
        let nodes = vec![
            create_test_node("main", NodeKind::Function),
            create_test_node("process", NodeKind::Function),
            create_test_node("execute", NodeKind::Function),
        ];
        let edges = vec![
            create_call_edge("main", "process"),
            create_call_edge("process", "execute"),
        ];

        let graph = IRCallGraph::build_from_ir(&nodes, &edges);

        assert_eq!(graph.function_count(), 3);
        assert_eq!(graph.edge_count(), 2);

        let callees = graph.get_callees("main");
        assert_eq!(callees, vec!["process"]);

        let callees = graph.get_callees("process");
        assert_eq!(callees, vec!["execute"]);
    }

    #[test]
    fn test_leaf_functions() {
        let nodes = vec![
            create_test_node("main", NodeKind::Function),
            create_test_node("foo", NodeKind::Function),
            create_test_node("bar", NodeKind::Function),
        ];
        let edges = vec![
            create_call_edge("main", "foo"),
            create_call_edge("main", "bar"),
        ];

        let graph = IRCallGraph::build_from_ir(&nodes, &edges);
        let leaves = graph.leaf_functions();

        assert_eq!(leaves.len(), 2);
        assert!(leaves.contains(&"foo".to_string()));
        assert!(leaves.contains(&"bar".to_string()));
    }

    #[test]
    fn test_entry_points() {
        let nodes = vec![
            create_test_node("main", NodeKind::Function),
            create_test_node("foo", NodeKind::Function),
            create_test_node("bar", NodeKind::Function),
        ];
        let edges = vec![
            create_call_edge("main", "foo"),
            create_call_edge("main", "bar"),
        ];

        let graph = IRCallGraph::build_from_ir(&nodes, &edges);
        let entries = graph.entry_points();

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0], "main");
    }

    #[test]
    fn test_circular_calls() {
        let nodes = vec![
            create_test_node("a", NodeKind::Function),
            create_test_node("b", NodeKind::Function),
        ];
        let edges = vec![create_call_edge("a", "b"), create_call_edge("b", "a")];

        let graph = IRCallGraph::build_from_ir(&nodes, &edges);

        assert_eq!(graph.function_count(), 2);
        assert_eq!(graph.edge_count(), 2);
        assert_eq!(graph.get_callees("a"), vec!["b"]);
        assert_eq!(graph.get_callees("b"), vec!["a"]);
    }

    #[test]
    fn test_call_graph_provider_trait() {
        let nodes = vec![
            create_test_node("main", NodeKind::Function),
            create_test_node("foo", NodeKind::Function),
        ];
        let edges = vec![create_call_edge("main", "foo")];

        let graph = IRCallGraph::build_from_ir(&nodes, &edges);

        // Test CallGraphProvider trait
        let callees = graph.get_callees("main");
        assert_eq!(callees, vec!["foo"]);

        let functions = graph.get_functions();
        assert_eq!(functions.len(), 2);
    }
}
