// Infrastructure: ReachabilityCache - Transitive closure for fast queries
// Pre-compute and cache reachability to avoid repeated BFS

use super::graph_index::GraphIndex;
use crate::features::query_engine::domain::EdgeType;
use crate::shared::models::Edge;
use std::collections::{HashMap, HashSet, VecDeque};

/// Reachability Cache - Pre-computed transitive closure
///
/// Strategy:
/// - Build transitive closure for frequently queried edge types
/// - Cache reachability matrix: node_id -> reachable_node_ids
/// - O(1) reachability check after O(V^2) build
///
/// Use cases:
/// - Impact analysis (what is affected by change?)
/// - Dependency queries (what does X depend on?)
/// - Security analysis (can source reach sink?)
#[derive(Debug, Clone)]
pub struct ReachabilityCache {
    /// Forward reachability: node -> all reachable nodes
    forward_reach: HashMap<String, HashSet<String>>,

    /// Backward reachability: node -> all nodes that can reach it
    backward_reach: HashMap<String, HashSet<String>>,

    /// Edge type this cache is for
    edge_type: EdgeType,

    /// Build stats
    node_count: usize,
    edge_count: usize,
    build_time_ms: u64,
}

impl ReachabilityCache {
    /// Build reachability cache for given edge type
    ///
    /// Complexity: O(V * (V + E)) where V = nodes, E = edges
    /// Memory: O(V^2) worst case (dense graph)
    pub fn build(index: &GraphIndex, edge_type: EdgeType) -> Self {
        let start = std::time::Instant::now();

        let mut forward_reach = HashMap::new();
        let mut backward_reach = HashMap::new();

        let all_nodes = index.get_all_nodes();

        // Build forward reachability for each node (BFS)
        for node in &all_nodes {
            let reachable = Self::compute_reachable_forward(index, &node.id, edge_type);
            forward_reach.insert(node.id.clone(), reachable);
        }

        // Build backward reachability for each node (reverse BFS)
        for node in &all_nodes {
            let reachable = Self::compute_reachable_backward(index, &node.id, edge_type);
            backward_reach.insert(node.id.clone(), reachable);
        }

        let build_time_ms = start.elapsed().as_millis() as u64;

        Self {
            forward_reach,
            backward_reach,
            edge_type,
            node_count: all_nodes.len(),
            edge_count: index.edge_count(),
            build_time_ms,
        }
    }

    /// Compute all nodes reachable from source (forward)
    fn compute_reachable_forward(
        index: &GraphIndex,
        source_id: &str,
        edge_type: EdgeType,
    ) -> HashSet<String> {
        let mut reachable = HashSet::new();
        let mut queue = VecDeque::new();
        let mut visited = HashSet::new();

        queue.push_back(source_id.to_string());
        visited.insert(source_id.to_string());

        while let Some(node_id) = queue.pop_front() {
            let edges = index.get_edges_from(&node_id);

            for edge in edges {
                if !Self::matches_edge_type(edge, edge_type) {
                    continue;
                }

                let target_id = &edge.target_id;

                if !visited.contains(target_id) {
                    visited.insert(target_id.clone());
                    reachable.insert(target_id.clone());
                    queue.push_back(target_id.clone());
                }
            }
        }

        reachable
    }

    /// Compute all nodes that can reach target (backward)
    fn compute_reachable_backward(
        index: &GraphIndex,
        target_id: &str,
        edge_type: EdgeType,
    ) -> HashSet<String> {
        let mut reachable = HashSet::new();
        let mut queue = VecDeque::new();
        let mut visited = HashSet::new();

        queue.push_back(target_id.to_string());
        visited.insert(target_id.to_string());

        while let Some(node_id) = queue.pop_front() {
            let edges = index.get_edges_to(&node_id);

            for edge in edges {
                if !Self::matches_edge_type(edge, edge_type) {
                    continue;
                }

                let source_id = &edge.source_id;

                if !visited.contains(source_id) {
                    visited.insert(source_id.clone());
                    reachable.insert(source_id.clone());
                    queue.push_back(source_id.clone());
                }
            }
        }

        reachable
    }

    /// Check if target is reachable from source (O(1))
    pub fn is_reachable(&self, source_id: &str, target_id: &str) -> bool {
        self.forward_reach
            .get(source_id)
            .map(|set| set.contains(target_id))
            .unwrap_or(false)
    }

    /// Get all nodes reachable from source (O(1))
    pub fn get_reachable_from(&self, source_id: &str) -> Option<&HashSet<String>> {
        self.forward_reach.get(source_id)
    }

    /// Get all nodes that can reach target (O(1))
    pub fn get_reaching_to(&self, target_id: &str) -> Option<&HashSet<String>> {
        self.backward_reach.get(target_id)
    }

    /// Get build statistics
    pub fn stats(&self) -> CacheStats {
        CacheStats {
            node_count: self.node_count,
            edge_count: self.edge_count,
            build_time_ms: self.build_time_ms,
            forward_entries: self.forward_reach.len(),
            backward_entries: self.backward_reach.len(),
            avg_reachable: self.average_reachable_count(),
        }
    }

    fn average_reachable_count(&self) -> f64 {
        if self.forward_reach.is_empty() {
            return 0.0;
        }

        let total: usize = self.forward_reach.values().map(|set| set.len()).sum();
        total as f64 / self.forward_reach.len() as f64
    }

    fn matches_edge_type(edge: &Edge, edge_type: EdgeType) -> bool {
        match edge_type {
            EdgeType::All => true,
            EdgeType::DFG => edge.kind.is_data_flow(),
            EdgeType::CFG => edge.kind.is_control_flow(),
            EdgeType::Call => matches!(edge.kind, crate::shared::models::EdgeKind::Calls),
        }
    }
}

/// Cache statistics
#[derive(Debug, Clone)]
pub struct CacheStats {
    pub node_count: usize,
    pub edge_count: usize,
    pub build_time_ms: u64,
    pub forward_entries: usize,
    pub backward_entries: usize,
    pub avg_reachable: f64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::shared::models::{EdgeKind, Node, NodeKind, Span};

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

    fn create_test_graph() -> GraphIndex {
        let mut ir_doc = IRDocument::new("test.py".to_string());

        // Create chain: A -> B -> C -> D
        for i in 0..4 {
            ir_doc.nodes.push(create_test_node(
                format!("node{}", i),
                format!("var{}", i),
                NodeKind::Variable,
                (i + 1) as u32,
            ));
        }

        // Edges: 0->1, 1->2, 2->3
        for i in 0..3 {
            ir_doc.edges.push(Edge {
                source_id: format!("node{}", i),
                target_id: format!("node{}", i + 1),
                kind: EdgeKind::DataFlow,
                span: None,
                metadata: None,
                attrs: None,
            });
        }

        GraphIndex::new(&ir_doc)
    }

    #[test]
    fn test_reachability_cache_build() {
        let index = create_test_graph();
        let cache = ReachabilityCache::build(&index, EdgeType::DFG);

        assert_eq!(cache.node_count, 4);
        assert_eq!(cache.edge_count, 3);
    }

    #[test]
    fn test_is_reachable() {
        let index = create_test_graph();
        let cache = ReachabilityCache::build(&index, EdgeType::DFG);

        // node0 can reach node1, node2, node3
        assert!(cache.is_reachable("node0", "node1"));
        assert!(cache.is_reachable("node0", "node2"));
        assert!(cache.is_reachable("node0", "node3"));

        // node3 cannot reach anyone
        assert!(!cache.is_reachable("node3", "node0"));
        assert!(!cache.is_reachable("node3", "node1"));
    }

    #[test]
    fn test_get_reachable_from() {
        let index = create_test_graph();
        let cache = ReachabilityCache::build(&index, EdgeType::DFG);

        let reachable = cache.get_reachable_from("node0").unwrap();
        assert_eq!(reachable.len(), 3); // node1, node2, node3

        let reachable = cache.get_reachable_from("node3").unwrap();
        assert_eq!(reachable.len(), 0); // No outgoing edges
    }

    #[test]
    fn test_get_reaching_to() {
        let index = create_test_graph();
        let cache = ReachabilityCache::build(&index, EdgeType::DFG);

        let reaching = cache.get_reaching_to("node3").unwrap();
        assert_eq!(reaching.len(), 3); // node0, node1, node2 can reach node3

        let reaching = cache.get_reaching_to("node0").unwrap();
        assert_eq!(reaching.len(), 0); // No incoming edges
    }

    #[test]
    fn test_cache_stats() {
        let index = create_test_graph();
        let cache = ReachabilityCache::build(&index, EdgeType::DFG);

        let stats = cache.stats();
        assert_eq!(stats.node_count, 4);
        assert_eq!(stats.forward_entries, 4);
        assert_eq!(stats.backward_entries, 4);
        assert!(stats.build_time_ms >= 0);
    }
}
