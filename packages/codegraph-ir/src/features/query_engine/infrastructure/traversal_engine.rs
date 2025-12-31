// Infrastructure: TraversalEngine - BFS graph traversal with Rayon
// Implements RFC-071 REACH primitive

use super::graph_index::GraphIndex;
use crate::features::query_engine::domain::{EdgeType, PathResult, TraversalDirection};
use crate::shared::models::{Edge, Node};
use std::collections::{HashSet, VecDeque};
use std::time::Instant;

/// Traversal Engine - BFS-based path finding
///
/// Implements:
/// - Forward/backward BFS
/// - Depth limiting
/// - Path limiting (early termination)
/// - Timeout handling
pub struct TraversalEngine<'a> {
    index: &'a GraphIndex,
}

impl<'a> TraversalEngine<'a> {
    pub fn new(index: &'a GraphIndex) -> Self {
        Self { index }
    }

    /// Find paths from sources to targets (BFS)
    ///
    /// Args:
    /// - sources: Starting nodes
    /// - targets: Target nodes (termination condition)
    /// - edge_type: Edge filter (DFG, CFG, CALL, ALL)
    /// - direction: Forward or backward
    /// - max_depth: Maximum path length
    /// - max_paths: Stop after finding N paths
    /// - timeout_ms: Stop after N milliseconds
    ///
    /// Returns:
    /// - Vec<PathResult>: Found paths
    pub fn find_paths(
        &self,
        sources: &[&Node],
        targets: &[&Node],
        edge_type: EdgeType,
        direction: TraversalDirection,
        max_depth: usize,
        max_paths: usize,
        timeout_ms: u64,
    ) -> Vec<PathResult> {
        let start_time = Instant::now();
        let target_ids: HashSet<String> = targets.iter().map(|n| n.id.clone()).collect();
        let mut paths = Vec::new();

        // BFS from each source
        for source in sources {
            if paths.len() >= max_paths {
                break;
            }

            // Check timeout
            if start_time.elapsed().as_millis() > timeout_ms as u128 {
                break;
            }

            let found = self.bfs_single(
                source,
                &target_ids,
                edge_type,
                direction,
                max_depth,
                max_paths - paths.len(),
                timeout_ms,
                start_time,
            );

            paths.extend(found);
        }

        paths
    }

    /// BFS from single source
    fn bfs_single(
        &self,
        source: &Node,
        target_ids: &HashSet<String>,
        edge_type: EdgeType,
        direction: TraversalDirection,
        max_depth: usize,
        max_paths: usize,
        timeout_ms: u64,
        start_time: Instant,
    ) -> Vec<PathResult> {
        let mut paths = Vec::new();
        let mut visited = HashSet::new();
        let mut queue = VecDeque::new();

        // Initialize: (current_node_id, path, depth)
        queue.push_back((source.id.clone(), vec![source.id.clone()], 0));
        visited.insert(source.id.clone());

        while let Some((node_id, path, depth)) = queue.pop_front() {
            // Check limits
            if paths.len() >= max_paths {
                break;
            }

            if start_time.elapsed().as_millis() > timeout_ms as u128 {
                break;
            }

            if depth >= max_depth {
                continue;
            }

            // Get neighbors
            let edges = match direction {
                TraversalDirection::Forward => self.index.get_edges_from(&node_id),
                TraversalDirection::Backward => self.index.get_edges_to(&node_id),
            };

            // Filter by edge type
            let filtered_edges: Vec<&Edge> = edges
                .into_iter()
                .filter(|e| self.matches_edge_type(e, edge_type))
                .collect();

            for edge in filtered_edges {
                let next_id = match direction {
                    TraversalDirection::Forward => &edge.target_id,
                    TraversalDirection::Backward => &edge.source_id,
                };

                // Check if reached target
                if target_ids.contains(next_id) {
                    let mut final_path = path.clone();
                    final_path.push(next_id.clone());

                    paths.push(PathResult {
                        node_ids: final_path,
                        edge_ids: vec![], // Edge tracking: requires (from, to) → edge_id index
                    });

                    if paths.len() >= max_paths {
                        return paths;
                    }

                    continue;
                }

                // Continue BFS
                if !visited.contains(next_id) {
                    visited.insert(next_id.clone());
                    let mut new_path = path.clone();
                    new_path.push(next_id.clone());
                    queue.push_back((next_id.clone(), new_path, depth + 1));
                }
            }
        }

        paths
    }

    /// Check if edge matches edge type filter
    fn matches_edge_type(&self, edge: &Edge, edge_type: EdgeType) -> bool {
        match edge_type {
            EdgeType::All => true,
            EdgeType::DFG => edge.kind.is_data_flow(),
            EdgeType::CFG => edge.kind.is_control_flow(),
            EdgeType::Call => matches!(edge.kind, crate::shared::models::EdgeKind::Calls),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::shared::models::{NodeKind, Span};

    fn create_test_graph() -> GraphIndex {
        let mut ir_doc = IRDocument::new("test.py".to_string());

        // Create a chain: node1 -> node2 -> node3
        ir_doc.nodes.push(Node {
            id: "node1".to_string(),
            kind: NodeKind::Variable,
            fqn: "test.input".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(1, 1, 1, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("input".to_string()),
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
            kind: NodeKind::Variable,
            fqn: "test.temp".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(2, 1, 2, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("temp".to_string()),
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
            id: "node3".to_string(),
            kind: NodeKind::Function,
            fqn: "test.execute".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(3, 1, 3, 10),
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

        // Create edges: node1 -> node2 -> node3
        ir_doc.edges.push(Edge {
            source_id: "node1".to_string(),
            target_id: "node2".to_string(),
            kind: crate::shared::models::EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        });

        ir_doc.edges.push(Edge {
            source_id: "node2".to_string(),
            target_id: "node3".to_string(),
            kind: crate::shared::models::EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        });

        GraphIndex::new(&ir_doc)
    }

    #[test]
    fn test_forward_traversal() {
        let index = create_test_graph();
        let engine = TraversalEngine::new(&index);

        let source = index.get_node("node1").unwrap();
        let target = index.get_node("node3").unwrap();

        let paths = engine.find_paths(
            &[source],
            &[target],
            EdgeType::DFG,
            TraversalDirection::Forward,
            10,
            100,
            30000,
        );

        assert_eq!(paths.len(), 1);
        assert_eq!(paths[0].node_ids.len(), 3); // node1 -> node2 -> node3
        assert_eq!(paths[0].node_ids[0], "node1");
        assert_eq!(paths[0].node_ids[2], "node3");
    }

    #[test]
    fn test_backward_traversal() {
        let index = create_test_graph();
        let engine = TraversalEngine::new(&index);

        let source = index.get_node("node1").unwrap();
        let target = index.get_node("node3").unwrap();

        let paths = engine.find_paths(
            &[target],
            &[source],
            EdgeType::DFG,
            TraversalDirection::Backward,
            10,
            100,
            30000,
        );

        assert_eq!(paths.len(), 1);
        assert_eq!(paths[0].node_ids.len(), 3);
    }

    #[test]
    fn test_depth_limit() {
        let index = create_test_graph();
        let engine = TraversalEngine::new(&index);

        let source = index.get_node("node1").unwrap();
        let target = index.get_node("node3").unwrap();

        // Max depth = 1 (cannot reach node3 from node1)
        let paths = engine.find_paths(
            &[source],
            &[target],
            EdgeType::DFG,
            TraversalDirection::Forward,
            1, // max_depth = 1
            100,
            30000,
        );

        assert_eq!(paths.len(), 0); // No path with depth 1
    }

    #[test]
    fn test_path_limit() {
        let index = create_test_graph();
        let engine = TraversalEngine::new(&index);

        let source = index.get_node("node1").unwrap();
        let target = index.get_node("node3").unwrap();

        let paths = engine.find_paths(
            &[source],
            &[target],
            EdgeType::DFG,
            TraversalDirection::Forward,
            10,
            1, // max_paths = 1
            30000,
        );

        assert!(paths.len() <= 1);
    }
}
