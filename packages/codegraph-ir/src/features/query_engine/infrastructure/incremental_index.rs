// Infrastructure: IncrementalGraphIndex - Mutable graph with differential updates
// Supports add/remove operations for incremental updates

use crate::shared::models::{Edge, Node};
use std::collections::HashMap;

/// Incremental Graph Index - Supports differential updates
///
/// Key features:
/// - Add/remove nodes and edges
/// - Track changes for differential updates
/// - Invalidate affected caches
/// - Maintain index consistency
#[derive(Debug)]
pub struct IncrementalGraphIndex {
    /// All nodes indexed by ID
    nodes_by_id: HashMap<String, Node>,

    /// Forward edges: source_id -> Vec<Edge>
    edges_from: HashMap<String, Vec<Edge>>,

    /// Backward edges: target_id -> Vec<Edge>
    edges_to: HashMap<String, Vec<Edge>>,

    /// Semantic index: name -> Vec<Node>
    nodes_by_name: HashMap<String, Vec<Node>>,

    /// Change tracking
    added_nodes: Vec<String>,
    removed_nodes: Vec<String>,
    added_edges: Vec<(String, String)>, // (source_id, target_id)
    removed_edges: Vec<(String, String)>,

    /// Stats
    node_count: usize,
    edge_count: usize,
}

impl IncrementalGraphIndex {
    /// Create new empty index
    pub fn new() -> Self {
        Self {
            nodes_by_id: HashMap::new(),
            edges_from: HashMap::new(),
            edges_to: HashMap::new(),
            nodes_by_name: HashMap::new(),
            added_nodes: Vec::new(),
            removed_nodes: Vec::new(),
            added_edges: Vec::new(),
            removed_edges: Vec::new(),
            node_count: 0,
            edge_count: 0,
        }
    }

    /// Add a single node (incremental)
    pub fn add_node(&mut self, node: Node) {
        // Check if already exists
        if self.nodes_by_id.contains_key(&node.id) {
            return;
        }

        // Track change
        self.added_nodes.push(node.id.clone());

        // Add to by_id index
        self.nodes_by_id.insert(node.id.clone(), node.clone());
        self.node_count += 1;

        // Add to by_name index
        if let Some(name) = &node.name {
            self.nodes_by_name
                .entry(name.clone())
                .or_insert_with(Vec::new)
                .push(node);
        }
    }

    /// Remove a single node (incremental)
    pub fn remove_node(&mut self, node_id: &str) -> Option<Node> {
        // Remove from by_id index
        let removed = self.nodes_by_id.remove(node_id)?;

        // Track change
        self.removed_nodes.push(node_id.to_string());
        self.node_count = self.node_count.saturating_sub(1);

        // Remove from by_name index
        if let Some(name) = &removed.name {
            if let Some(nodes) = self.nodes_by_name.get_mut(name) {
                nodes.retain(|n| n.id != node_id);
                if nodes.is_empty() {
                    self.nodes_by_name.remove(name);
                }
            }
        }

        // Remove all edges connected to this node
        self.remove_edges_for_node(node_id);

        Some(removed)
    }

    /// Add a single edge (incremental)
    pub fn add_edge(&mut self, edge: Edge) {
        // Track change
        self.added_edges
            .push((edge.source_id.clone(), edge.target_id.clone()));

        // Add to forward index
        self.edges_from
            .entry(edge.source_id.clone())
            .or_insert_with(Vec::new)
            .push(edge.clone());

        // Add to backward index
        self.edges_to
            .entry(edge.target_id.clone())
            .or_insert_with(Vec::new)
            .push(edge);

        self.edge_count += 1;
    }

    /// Remove edges between source and target
    pub fn remove_edge(&mut self, source_id: &str, target_id: &str) -> usize {
        let mut removed_count = 0;

        // Track change
        self.removed_edges
            .push((source_id.to_string(), target_id.to_string()));

        // Remove from forward index
        if let Some(edges) = self.edges_from.get_mut(source_id) {
            let before = edges.len();
            edges.retain(|e| e.target_id != target_id);
            removed_count += before - edges.len();

            if edges.is_empty() {
                self.edges_from.remove(source_id);
            }
        }

        // Remove from backward index
        if let Some(edges) = self.edges_to.get_mut(target_id) {
            edges.retain(|e| e.source_id != source_id);

            if edges.is_empty() {
                self.edges_to.remove(target_id);
            }
        }

        self.edge_count = self.edge_count.saturating_sub(removed_count);
        removed_count
    }

    /// Remove all edges connected to a node
    fn remove_edges_for_node(&mut self, node_id: &str) {
        // Remove outgoing edges
        if let Some(edges) = self.edges_from.remove(node_id) {
            for edge in edges {
                self.removed_edges
                    .push((edge.source_id.clone(), edge.target_id.clone()));
                self.edge_count = self.edge_count.saturating_sub(1);

                // Also remove from backward index
                if let Some(backward) = self.edges_to.get_mut(&edge.target_id) {
                    backward.retain(|e| e.source_id != node_id);
                }
            }
        }

        // Remove incoming edges
        if let Some(edges) = self.edges_to.remove(node_id) {
            for edge in edges {
                self.removed_edges
                    .push((edge.source_id.clone(), edge.target_id.clone()));
                self.edge_count = self.edge_count.saturating_sub(1);

                // Also remove from forward index
                if let Some(forward) = self.edges_from.get_mut(&edge.source_id) {
                    forward.retain(|e| e.target_id != node_id);
                }
            }
        }
    }

    /// Get node by ID (O(1))
    pub fn get_node(&self, node_id: &str) -> Option<&Node> {
        self.nodes_by_id.get(node_id)
    }

    /// Find nodes by name (O(1) lookup)
    pub fn find_nodes_by_name(&self, name: &str) -> Vec<&Node> {
        self.nodes_by_name
            .get(name)
            .map(|nodes| nodes.iter().collect())
            .unwrap_or_default()
    }

    /// Get outgoing edges (O(1))
    pub fn get_edges_from(&self, node_id: &str) -> Vec<&Edge> {
        self.edges_from
            .get(node_id)
            .map(|edges| edges.iter().collect())
            .unwrap_or_default()
    }

    /// Get incoming edges (O(1))
    pub fn get_edges_to(&self, node_id: &str) -> Vec<&Edge> {
        self.edges_to
            .get(node_id)
            .map(|edges| edges.iter().collect())
            .unwrap_or_default()
    }

    /// Get all nodes
    pub fn get_all_nodes(&self) -> Vec<&Node> {
        self.nodes_by_id.values().collect()
    }

    /// Get change summary (for differential updates)
    pub fn get_changes(&self) -> ChangeSet {
        ChangeSet {
            added_nodes: self.added_nodes.clone(),
            removed_nodes: self.removed_nodes.clone(),
            added_edges: self.added_edges.clone(),
            removed_edges: self.removed_edges.clone(),
        }
    }

    /// Clear change tracking (after processing)
    pub fn clear_changes(&mut self) {
        self.added_nodes.clear();
        self.removed_nodes.clear();
        self.added_edges.clear();
        self.removed_edges.clear();
    }

    /// Get stats
    pub fn node_count(&self) -> usize {
        self.node_count
    }

    pub fn edge_count(&self) -> usize {
        self.edge_count
    }
}

impl Default for IncrementalGraphIndex {
    fn default() -> Self {
        Self::new()
    }
}

/// Change set for differential updates
#[derive(Debug, Clone)]
pub struct ChangeSet {
    pub added_nodes: Vec<String>,
    pub removed_nodes: Vec<String>,
    pub added_edges: Vec<(String, String)>,
    pub removed_edges: Vec<(String, String)>,
}

impl ChangeSet {
    pub fn is_empty(&self) -> bool {
        self.added_nodes.is_empty()
            && self.removed_nodes.is_empty()
            && self.added_edges.is_empty()
            && self.removed_edges.is_empty()
    }

    pub fn total_changes(&self) -> usize {
        self.added_nodes.len()
            + self.removed_nodes.len()
            + self.added_edges.len()
            + self.removed_edges.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{EdgeKind, NodeKind, Span};

    fn create_test_node(id: String, name: String, kind: NodeKind, line: u32) -> Node {
        Node {
            id,
            kind,
            fqn: format!("test.{}", name),
            file_path: "test.py".to_string(),
            span: Span::new(line, 1, line, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some(name),
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
        }
    }

    #[test]
    fn test_incremental_add_node() {
        let mut index = IncrementalGraphIndex::new();

        let node = create_test_node(
            "node1".to_string(),
            "var".to_string(),
            NodeKind::Variable,
            1,
        );

        index.add_node(node);

        assert_eq!(index.node_count(), 1);
        assert!(index.get_node("node1").is_some());
        assert_eq!(index.find_nodes_by_name("var").len(), 1);
    }

    #[test]
    fn test_incremental_remove_node() {
        let mut index = IncrementalGraphIndex::new();

        let node = create_test_node(
            "node1".to_string(),
            "var".to_string(),
            NodeKind::Variable,
            1,
        );

        index.add_node(node);
        assert_eq!(index.node_count(), 1);

        let removed = index.remove_node("node1");
        assert!(removed.is_some());
        assert_eq!(index.node_count(), 0);
        assert!(index.get_node("node1").is_none());
    }

    #[test]
    fn test_incremental_add_edge() {
        let mut index = IncrementalGraphIndex::new();

        let edge = Edge {
            source_id: "node1".to_string(),
            target_id: "node2".to_string(),
            kind: EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        };

        index.add_edge(edge);

        assert_eq!(index.edge_count(), 1);
        assert_eq!(index.get_edges_from("node1").len(), 1);
        assert_eq!(index.get_edges_to("node2").len(), 1);
    }

    #[test]
    fn test_incremental_remove_edge() {
        let mut index = IncrementalGraphIndex::new();

        let edge = Edge {
            source_id: "node1".to_string(),
            target_id: "node2".to_string(),
            kind: EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        };

        index.add_edge(edge);
        assert_eq!(index.edge_count(), 1);

        let removed = index.remove_edge("node1", "node2");
        assert_eq!(removed, 1);
        assert_eq!(index.edge_count(), 0);
    }

    #[test]
    fn test_change_tracking() {
        let mut index = IncrementalGraphIndex::new();

        let node = create_test_node(
            "node1".to_string(),
            "var".to_string(),
            NodeKind::Variable,
            1,
        );

        index.add_node(node);

        let changes = index.get_changes();
        assert_eq!(changes.added_nodes.len(), 1);
        assert_eq!(changes.added_nodes[0], "node1");

        index.clear_changes();
        let changes = index.get_changes();
        assert!(changes.is_empty());
    }

    #[test]
    fn test_remove_node_removes_edges() {
        let mut index = IncrementalGraphIndex::new();

        // Add nodes
        let node1 = create_test_node(
            "node1".to_string(),
            "var1".to_string(),
            NodeKind::Variable,
            1,
        );
        let node2 = create_test_node(
            "node2".to_string(),
            "var2".to_string(),
            NodeKind::Variable,
            2,
        );

        index.add_node(node1);
        index.add_node(node2);

        // Add edge
        let edge = Edge {
            source_id: "node1".to_string(),
            target_id: "node2".to_string(),
            kind: EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        };

        index.add_edge(edge);
        assert_eq!(index.edge_count(), 1);

        // Remove node1 should also remove the edge
        index.remove_node("node1");
        assert_eq!(index.edge_count(), 0);
        assert_eq!(index.get_edges_to("node2").len(), 0);
    }
}
