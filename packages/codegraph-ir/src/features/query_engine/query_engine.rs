// QueryEngine - Main facade for query execution
// Maps to Python: QueryEngine

use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::features::query_engine::domain::{PathQuery, PathResult};
use crate::features::query_engine::infrastructure::{GraphIndex, NodeMatcher, TraversalEngine};

/// Query Engine - Main entry point for query execution
///
/// Facade pattern over:
/// - GraphIndex: O(1) node/edge lookups
/// - NodeMatcher: Selector to node matching
/// - TraversalEngine: BFS graph traversal
///
/// Example:
/// ```no_run
/// use codegraph_ir::features::query_engine::{QueryEngine, Q, E};
/// use codegraph_ir::features::ir_generation::domain::ir_document::IRDocument;
///
/// let ir_doc = IRDocument::new("test.py".to_string());
/// let engine = QueryEngine::new(&ir_doc);
///
/// // Find: user -> execute
/// let query = (Q::var("user") >> Q::call("execute"))
///     .via(E::dfg())
///     .any_path()
///     .limit_paths(20);
///
/// let paths = engine.execute(query);
/// println!("Found {} paths", paths.len());
/// ```
pub struct QueryEngine<'a> {
    index: GraphIndex,
    _ir_doc: &'a IRDocument,
}

impl<'a> QueryEngine<'a> {
    /// Create new QueryEngine from IRDocument
    pub fn new(ir_doc: &'a IRDocument) -> Self {
        let index = GraphIndex::new(ir_doc);

        Self {
            index,
            _ir_doc: ir_doc,
        }
    }

    /// Execute query and find paths
    ///
    /// This is the main execution method that:
    /// 1. Matches source/target selectors to nodes
    /// 2. Runs BFS traversal
    /// 3. Applies path constraints
    /// 4. Returns results
    pub fn execute(&self, query: PathQuery) -> Vec<PathResult> {
        // Step 1: Match source nodes
        let matcher = NodeMatcher::new(&self.index);
        let source_nodes = matcher.match_nodes(&query.flow.source);

        if source_nodes.is_empty() {
            return Vec::new();
        }

        // Step 2: Match target nodes
        let target_nodes = matcher.match_nodes(&query.flow.target);

        if target_nodes.is_empty() {
            return Vec::new();
        }

        // Step 3: Extract edge type and direction
        let edge_type = query
            .flow
            .edge_type
            .as_ref()
            .map(|e| e.edge_type)
            .unwrap_or(crate::features::query_engine::domain::EdgeType::All);

        let direction = query.flow.direction;

        // Step 4: Extract constraints
        let (min_depth, max_depth) = query.flow.depth_range;
        let max_paths = query.max_paths;
        let timeout_ms = query.timeout_ms;

        // Step 5: Run BFS traversal
        let engine = TraversalEngine::new(&self.index);
        let mut paths = engine.find_paths(
            &source_nodes,
            &target_nodes,
            edge_type,
            direction,
            max_depth,
            max_paths,
            timeout_ms,
        );

        // Step 6: Apply path constraints
        paths.retain(|path| {
            // Min depth filter
            if path.node_ids.len() < min_depth {
                return false;
            }

            // Custom predicates
            for predicate in &query.path_constraints {
                if !predicate(path) {
                    return false;
                }
            }

            true
        });

        paths
    }

    /// Get graph statistics
    pub fn stats(&self) -> QueryEngineStats {
        QueryEngineStats {
            node_count: self.index.node_count(),
            edge_count: self.index.edge_count(),
        }
    }
}

/// Query engine statistics
#[derive(Debug, Clone)]
pub struct QueryEngineStats {
    pub node_count: usize,
    pub edge_count: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::query_engine::domain::{E, Q};
    use crate::shared::models::{Edge, Node, NodeKind, Span};

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

    fn create_test_ir() -> IRDocument {
        let mut ir_doc = IRDocument::new("test.py".to_string());

        // Create test graph: user -> temp -> execute
        ir_doc.nodes.push(create_test_node(
            "var_user".to_string(),
            "user".to_string(),
            NodeKind::Variable,
            1,
        ));

        ir_doc.nodes.push(create_test_node(
            "var_temp".to_string(),
            "temp".to_string(),
            NodeKind::Variable,
            2,
        ));

        ir_doc.nodes.push(create_test_node(
            "call_execute".to_string(),
            "execute".to_string(),
            NodeKind::Function,
            3,
        ));

        // Create edges
        ir_doc.edges.push(Edge {
            source_id: "var_user".to_string(),
            target_id: "var_temp".to_string(),
            kind: crate::shared::models::EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        });

        ir_doc.edges.push(Edge {
            source_id: "var_temp".to_string(),
            target_id: "call_execute".to_string(),
            kind: crate::shared::models::EdgeKind::DataFlow,
            span: None,
            metadata: None,
            attrs: None,
        });

        ir_doc
    }

    #[test]
    fn test_query_engine_creation() {
        let ir_doc = create_test_ir();
        let engine = QueryEngine::new(&ir_doc);

        let stats = engine.stats();
        assert_eq!(stats.node_count, 3);
        assert_eq!(stats.edge_count, 2);
    }

    #[test]
    fn test_basic_query_execution() {
        let ir_doc = create_test_ir();
        let engine = QueryEngine::new(&ir_doc);

        // Query: user >> execute
        let query = (Q::var("user") >> Q::call("execute"))
            .via(E::dfg())
            .any_path();

        let paths = engine.execute(query);

        assert_eq!(paths.len(), 1);
        assert_eq!(paths[0].node_ids.len(), 3); // user -> temp -> execute
        assert_eq!(paths[0].node_ids[0], "var_user");
        assert_eq!(paths[0].node_ids[2], "call_execute");
    }

    #[test]
    fn test_query_with_path_constraint() {
        let ir_doc = create_test_ir();
        let engine = QueryEngine::new(&ir_doc);

        // Query with constraint: path length > 5
        let query = (Q::var("user") >> Q::call("execute"))
            .via(E::dfg())
            .any_path()
            .where_path(|p| p.len() > 5);

        let paths = engine.execute(query);

        assert_eq!(paths.len(), 0); // No path with length > 5
    }

    #[test]
    #[ignore]
    fn test_query_with_depth_limit() {
        let ir_doc = create_test_ir();
        let engine = QueryEngine::new(&ir_doc);

        // Query with max_depth = 1 (cannot reach execute)
        let query = (Q::var("user") >> Q::call("execute"))
            .via(E::dfg().depth(1, 1))
            .any_path();

        let paths = engine.execute(query);

        assert_eq!(paths.len(), 0);
    }

    #[test]
    fn test_query_with_path_limit() {
        let ir_doc = create_test_ir();
        let engine = QueryEngine::new(&ir_doc);

        let query = (Q::var("user") >> Q::call("execute"))
            .via(E::dfg())
            .any_path()
            .limit_paths(1);

        let paths = engine.execute(query);

        assert!(paths.len() <= 1);
    }
}
