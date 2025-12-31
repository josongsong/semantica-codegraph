// QueryBuilder - Entry point for extended QueryDSL
//
// Provides fluent API for:
// - Node queries: engine.query().nodes()
// - Edge queries: engine.query().edges()
// - Path queries: engine.query().path()
// - Specialized: engine.query().taint_flows(), .clone_pairs()

use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::features::query_engine::infrastructure::GraphIndex;

use super::node_query::NodeQueryBuilder;
use super::edge_query::EdgeQueryBuilder;
use super::taint_query::TaintQueryBuilder;
use super::clone_query::CloneQueryBuilder;
use super::domain::{PathQuery, NodeSelector};

/// QueryBuilder - Main entry point for extended QueryDSL
///
/// Example:
/// ```no_run
/// let engine = QueryEngine::new(&ir_doc);
/// let nodes = engine.query()
///     .nodes()
///     .filter(NodeKind::Function)
///     .where_field("language", "python")
///     .execute()?;
/// ```
pub struct QueryBuilder<'a> {
    pub(crate) index: &'a GraphIndex,
    pub(crate) ir_doc: &'a IRDocument,
}

impl<'a> QueryBuilder<'a> {
    /// Create new QueryBuilder
    pub fn new(index: &'a GraphIndex, ir_doc: &'a IRDocument) -> Self {
        Self { index, ir_doc }
    }

    /// Start node query
    ///
    /// Example:
    /// ```no_run
    /// engine.query()
    ///     .nodes()
    ///     .filter(NodeKind::Function)
    ///     .execute()?
    /// ```
    pub fn nodes(self) -> NodeQueryBuilder<'a> {
        NodeQueryBuilder::new(self.index, self.ir_doc)
    }

    /// Start edge query
    ///
    /// Example:
    /// ```no_run
    /// engine.query()
    ///     .edges()
    ///     .filter(EdgeKind::Calls)
    ///     .execute()?
    /// ```
    pub fn edges(self) -> EdgeQueryBuilder<'a> {
        EdgeQueryBuilder::new(self.index, self.ir_doc)
    }

    /// Start path query (existing PathQuery API)
    ///
    /// Example:
    /// ```no_run
    /// use codegraph_ir::features::query_engine::{Q, E};
    ///
    /// engine.query()
    ///     .path(Q::var("user") >> Q::call("exec"))
    ///     .via(E::dfg())
    ///     .execute()?
    /// ```
    pub fn path(self, query: PathQuery) -> PathQuery {
        query
    }

    /// Start path query from node selector
    ///
    /// Example:
    /// ```no_run
    /// engine.query()
    ///     .from_node(Q::var("anchor"))
    ///     .via(E::dfg())
    ///     .depth(5)
    ///     .execute()?
    /// ```
    pub fn from_node(self, node: NodeSelector) -> PathQuery {
        // Create a FlowExpr from the node selector
        use super::domain::{FlowExpr, TraversalDirection};
        let flow = FlowExpr::new(node.clone(), node, TraversalDirection::Forward);
        PathQuery::from_flow_expr(flow)
    }

    /// Start taint flow query
    ///
    /// Example:
    /// ```no_run
    /// engine.query()
    ///     .taint_flows()
    ///     .severity(Severity::Critical)
    ///     .vulnerability_type("CWE-89")
    ///     .execute()?
    /// ```
    pub fn taint_flows(self) -> TaintQueryBuilder<'a> {
        TaintQueryBuilder::new(self.index, self.ir_doc)
    }

    /// Start clone pair query
    ///
    /// Example:
    /// ```no_run
    /// engine.query()
    ///     .clone_pairs()
    ///     .min_similarity(0.85)
    ///     .clone_type(CloneType::Type3)
    ///     .execute()?
    /// ```
    pub fn clone_pairs(self) -> CloneQueryBuilder<'a> {
        CloneQueryBuilder::new(self.index, self.ir_doc)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::features::query_engine::infrastructure::GraphIndex;

    #[test]
    fn test_query_builder_nodes() {
        let ir_doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&ir_doc);
        let builder = QueryBuilder::new(&index, &ir_doc);

        // Should return NodeQueryBuilder
        let _node_query = builder.nodes();
    }

    #[test]
    fn test_query_builder_edges() {
        let ir_doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&ir_doc);
        let builder = QueryBuilder::new(&index, &ir_doc);

        // Should return EdgeQueryBuilder
        let _edge_query = builder.edges();
    }
}
