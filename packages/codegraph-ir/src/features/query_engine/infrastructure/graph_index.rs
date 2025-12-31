// Infrastructure: GraphIndex - O(1) node/edge lookups
// Maps to Python: UnifiedGraphIndex
//
// DEPRECATED: This is a simplified version of GraphIndex
// MIGRATION(v2): Migrate to features/graph_builder/domain::GraphIndex (SOTA version)
// - 50% memory reduction (string interning)
// - 2-3x faster (AHashMap)
// - EdgeKind-specific indexes
// - Framework awareness (routes, services)
//
// This version is kept temporarily for PyGraphIndex compatibility
// until graph_builder is completed.

use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::shared::models::{Edge, Node};
use std::collections::HashMap;

/// Unified Graph Index - Fast lookups for query execution
///
/// Provides O(1) access to:
/// - Nodes by ID
/// - Edges by source/target
/// - Nodes by name (semantic search)
///
/// DEPRECATED: Use features/graph_builder/domain::GraphIndex instead
#[derive(Debug)]
#[deprecated(
    since = "0.1.0",
    note = "Use features/graph_builder/domain::GraphIndex for better performance"
)]
pub struct GraphIndex {
    /// All nodes indexed by ID
    nodes_by_id: HashMap<String, Node>,

    /// Forward edges: source_id -> Vec<Edge>
    edges_from: HashMap<String, Vec<Edge>>,

    /// Backward edges: target_id -> Vec<Edge>
    edges_to: HashMap<String, Vec<Edge>>,

    /// Semantic index: name -> Vec<Node>
    nodes_by_name: HashMap<String, Vec<Node>>,

    /// Stats
    node_count: usize,
    edge_count: usize,
}

impl GraphIndex {
    /// Build index from IRDocument
    pub fn new(ir_doc: &IRDocument) -> Self {
        let mut index = Self {
            nodes_by_id: HashMap::new(),
            edges_from: HashMap::new(),
            edges_to: HashMap::new(),
            nodes_by_name: HashMap::new(),
            node_count: 0,
            edge_count: 0,
        };

        index.build(ir_doc);
        index
    }

    /// Build all indexes from IR document
    fn build(&mut self, ir_doc: &IRDocument) {
        // Index nodes by ID
        for node in &ir_doc.nodes {
            self.nodes_by_id.insert(node.id.clone(), node.clone());
            self.node_count += 1;

            // Index by name for semantic search
            if let Some(name) = &node.name {
                self.nodes_by_name
                    .entry(name.clone())
                    .or_insert_with(Vec::new)
                    .push(node.clone());
            }
        }

        // Index edges (forward and backward)
        for edge in &ir_doc.edges {
            self.edge_count += 1;

            // Forward: source -> target
            self.edges_from
                .entry(edge.source_id.clone())
                .or_insert_with(Vec::new)
                .push(edge.clone());

            // Backward: target <- source
            self.edges_to
                .entry(edge.target_id.clone())
                .or_insert_with(Vec::new)
                .push(edge.clone());
        }
    }

    /// Get node by ID (O(1))
    pub fn get_node(&self, node_id: &str) -> Option<&Node> {
        self.nodes_by_id.get(node_id)
    }

    /// Get all nodes (for wildcard queries)
    pub fn get_all_nodes(&self) -> Vec<&Node> {
        self.nodes_by_id.values().collect()
    }

    /// Find nodes by name (O(1) lookup + O(k) filter)
    pub fn find_nodes_by_name(&self, name: &str) -> Vec<&Node> {
        self.nodes_by_name
            .get(name)
            .map(|nodes| nodes.iter().collect())
            .unwrap_or_default()
    }

    /// Get outgoing edges from node (O(1))
    pub fn get_edges_from(&self, node_id: &str) -> Vec<&Edge> {
        self.edges_from
            .get(node_id)
            .map(|edges| edges.iter().collect())
            .unwrap_or_default()
    }

    /// Get incoming edges to node (O(1))
    pub fn get_edges_to(&self, node_id: &str) -> Vec<&Edge> {
        self.edges_to
            .get(node_id)
            .map(|edges| edges.iter().collect())
            .unwrap_or_default()
    }

    /// Get all edges (for union queries)
    pub fn get_all_edges(&self) -> Vec<&Edge> {
        self.edges_from
            .values()
            .flat_map(|edges| edges.iter())
            .collect()
    }

    /// Get stats
    pub fn node_count(&self) -> usize {
        self.node_count
    }

    pub fn edge_count(&self) -> usize {
        self.edge_count
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{NodeKind, Span};

    fn create_test_ir() -> IRDocument {
        let mut ir_doc = IRDocument::new("test.py".to_string());

        // Create test nodes
        ir_doc.nodes.push(Node {
            id: "node1".to_string(),
            kind: NodeKind::Variable,
            fqn: "test.user".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(1, 1, 1, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("user".to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        });

        ir_doc.nodes.push(Node {
            id: "node2".to_string(),
            kind: NodeKind::Function,
            fqn: "test.execute".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(2, 1, 2, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("execute".to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        });

        // Create test edge
        ir_doc.edges.push(Edge {
            source_id: "node1".to_string(),
            target_id: "node2".to_string(),
            kind: crate::shared::models::EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        });

        ir_doc
    }

    #[test]
    fn test_graph_index_creation() {
        let ir_doc = create_test_ir();
        let index = GraphIndex::new(&ir_doc);

        assert_eq!(index.node_count(), 2);
        assert_eq!(index.edge_count(), 1);
    }

    #[test]
    fn test_get_node_by_id() {
        let ir_doc = create_test_ir();
        let index = GraphIndex::new(&ir_doc);

        let node = index.get_node("node1");
        assert!(node.is_some());
        assert_eq!(node.unwrap().name, Some("user".to_string()));
    }

    #[test]
    fn test_find_nodes_by_name() {
        let ir_doc = create_test_ir();
        let index = GraphIndex::new(&ir_doc);

        let nodes = index.find_nodes_by_name("user");
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].id, "node1");
    }

    #[test]
    fn test_get_edges_from() {
        let ir_doc = create_test_ir();
        let index = GraphIndex::new(&ir_doc);

        let edges = index.get_edges_from("node1");
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].target_id, "node2");
    }

    #[test]
    fn test_get_edges_to() {
        let ir_doc = create_test_ir();
        let index = GraphIndex::new(&ir_doc);

        let edges = index.get_edges_to("node2");
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].source_id, "node1");
    }
}
