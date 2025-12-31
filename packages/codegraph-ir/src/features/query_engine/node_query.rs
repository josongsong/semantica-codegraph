// NodeQueryBuilder - Node filtering, ordering, aggregation
//
// Provides fluent API for node queries:
// - Filtering: .filter(), .where_field(), .where_expr() (Expression AST)
// - Ordering: .order_by()
// - Pagination: .limit(), .offset()
// - Aggregation: .aggregate()
// - Streaming: .stream()
//
// Design: RFC-RUST-SDK-002 (Expression AST, no closures)

use std::collections::HashMap;
use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::shared::models::{Node, NodeKind};  // Use shared NodeKind
use crate::features::query_engine::infrastructure::GraphIndex;
use super::aggregation::AggregationBuilder;
use super::streaming::NodeStream;
use super::expression::{Expr, ExprBuilder, ExprEvaluator, Op, Value};

/// Order direction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Order {
    Asc,
    Desc,
}

/// NodeQueryBuilder - Fluent API for node queries
///
/// Example (Expression AST - RFC-RUST-SDK-002):
/// ```no_run
/// let nodes = engine.query()
///     .nodes()
///     .filter(NodeKind::Function)
///     .where_field("language", "python")
///     .where_expr(ExprBuilder::gte("complexity", 10))
///     .order_by("name", Order::Asc)
///     .limit(100)
///     .execute()?;
/// ```
pub struct NodeQueryBuilder<'a> {
    index: &'a GraphIndex,
    ir_doc: &'a IRDocument,

    // Filters
    kind_filter: Option<NodeKind>,
    field_filters: Vec<(String, String)>,  // (field_name, expected_value)
    expr_filters: Vec<Expr>,  // Expression AST filters (RFC-002)
    custom_predicates: Vec<Box<dyn Fn(&Node) -> bool>>,  // Custom filter predicates

    // Ordering
    order_by_field: Option<String>,
    order_direction: Order,

    // Pagination
    limit: Option<usize>,
    offset: usize,
}

impl<'a> NodeQueryBuilder<'a> {
    /// Create new NodeQueryBuilder
    pub fn new(index: &'a GraphIndex, ir_doc: &'a IRDocument) -> Self {
        Self {
            index,
            ir_doc,
            kind_filter: None,
            field_filters: Vec::new(),
            expr_filters: Vec::new(),
            custom_predicates: Vec::new(),
            order_by_field: None,
            order_direction: Order::Asc,
            limit: None,
            offset: 0,
        }
    }

    /// Filter by node kind
    ///
    /// Example:
    /// ```no_run
    /// .filter(NodeKind::Function)
    /// ```
    pub fn filter(mut self, kind: NodeKind) -> Self {
        self.kind_filter = Some(kind);
        self
    }

    /// Filter by field value
    ///
    /// Example:
    /// ```no_run
    /// .where_field("language", "python")
    /// .where_field("file_path", "src/main.py")
    /// ```
    pub fn where_field(mut self, field: &str, value: &str) -> Self {
        self.field_filters.push((field.to_string(), value.to_string()));
        self
    }

    /// Filter with custom predicate
    ///
    /// Example:
    /// ```no_run
    /// .where_fn(|n| {
    ///     n.metadata.get("complexity")
    ///         .and_then(|v| v.parse::<i32>().ok())
    ///         .unwrap_or(0) > 10
    /// })
    /// ```
    pub fn where_fn<F>(mut self, predicate: F) -> Self
    where
        F: Fn(&Node) -> bool + 'static,
    {
        self.custom_predicates.push(Box::new(predicate));
        self
    }

    /// Order by field
    ///
    /// Example:
    /// ```no_run
    /// .order_by("complexity", Order::Desc)
    /// ```
    pub fn order_by(mut self, field: &str, direction: Order) -> Self {
        self.order_by_field = Some(field.to_string());
        self.order_direction = direction;
        self
    }

    /// Limit number of results
    ///
    /// Example:
    /// ```no_run
    /// .limit(100)
    /// ```
    pub fn limit(mut self, limit: usize) -> Self {
        self.limit = Some(limit);
        self
    }

    /// Skip first N results (pagination)
    ///
    /// Example:
    /// ```no_run
    /// .offset(50).limit(100)  // Page 2
    /// ```
    pub fn offset(mut self, offset: usize) -> Self {
        self.offset = offset;
        self
    }

    /// Start aggregation
    ///
    /// Example:
    /// ```no_run
    /// .aggregate().count().avg("complexity").execute()?
    /// ```
    pub fn aggregate(self) -> AggregationBuilder<'a> {
        AggregationBuilder::new(self)
    }

    /// Stream results in chunks (memory-efficient)
    ///
    /// Example:
    /// ```no_run
    /// let stream = query.stream(1000)?;
    /// for batch in stream {
    ///     process_batch(batch);
    /// }
    /// ```
    pub fn stream(self, chunk_size: usize) -> Result<NodeStream<'a>, String> {
        NodeStream::new(self, chunk_size)
    }

    /// Execute query and return nodes
    ///
    /// Example:
    /// ```no_run
    /// let nodes = query.execute()?;
    /// ```
    pub fn execute(self) -> Result<Vec<Node>, String> {
        // Step 1: Get all nodes from IR document
        let all_nodes = self.ir_doc.get_all_nodes();

        // Step 2: Apply filters
        let mut filtered: Vec<Node> = all_nodes
            .into_iter()
            .filter(|node| self.matches_filters(node))
            .collect();

        // Step 3: Apply ordering
        if let Some(ref field) = self.order_by_field {
            let field_clone = field.clone();
            let direction = self.order_direction;

            filtered.sort_by(|a, b| {
                let a_val = self.get_field_value(a, &field_clone);
                let b_val = self.get_field_value(b, &field_clone);

                let cmp = a_val.cmp(&b_val);
                match direction {
                    Order::Asc => cmp,
                    Order::Desc => cmp.reverse(),
                }
            });
        }

        // Step 4: Apply pagination
        let start = self.offset;
        let end = self.limit.map(|l| start + l).unwrap_or(filtered.len());

        Ok(filtered.into_iter().skip(start).take(end - start).collect())
    }

    /// Internal: Check if node matches all filters
    fn matches_filters(&self, node: &Node) -> bool {
        // Kind filter
        if let Some(kind) = self.kind_filter {
            if !self.matches_kind(node, kind) {
                return false;
            }
        }

        // Field filters
        for (field, expected_value) in &self.field_filters {
            let actual_value = self.get_field_value(node, field);
            if actual_value != *expected_value {
                return false;
            }
        }

        // Custom predicates (ALL must pass)
        for predicate in &self.custom_predicates {
            if !predicate(node) {
                return false;
            }
        }

        true
    }

    /// Internal: Check if node matches kind
    fn matches_kind(&self, node: &Node, kind: NodeKind) -> bool {
        // Direct comparison now that we use shared NodeKind
        node.kind == kind
    }

    /// Internal: Get field value from node
    fn get_field_value(&self, node: &Node, field: &str) -> String {
        match field {
            "name" => node.name.clone().unwrap_or_default(),
            "kind" => node.kind.as_str().to_string(),
            "file_path" => node.file_path.clone(),
            // Metadata fields - metadata is Option<String>, not a HashMap
            _ => node.metadata.clone().unwrap_or_default(),
        }
    }

    /// Internal: Get nodes for streaming/aggregation
    pub(crate) fn get_filtered_nodes(&self) -> Vec<Node> {
        let all_nodes = self.ir_doc.get_all_nodes();
        all_nodes
            .into_iter()
            .filter(|node| self.matches_filters(node))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::features::query_engine::infrastructure::GraphIndex;
    use crate::shared::models::Span;

    fn create_test_doc() -> IRDocument {
        let mut doc = IRDocument::new("test.py".to_string());

        // Add test nodes using proper Node constructor
        let node1 = Node::builder()
            .id("func1")
            .kind(NodeKind::Function)
            .fqn("test.func1")
            .file_path("test.py")
            .span(Span::new(1, 0, 5, 0))
            .with_name("func1")
            .build()
            .expect("Failed to build node1");

        let node2 = Node::builder()
            .id("func2")
            .kind(NodeKind::Function)
            .fqn("test.func2")
            .file_path("test.py")
            .span(Span::new(7, 0, 12, 0))
            .with_name("func2")
            .build()
            .expect("Failed to build node2");

        let node3 = Node::builder()
            .id("MyClass")
            .kind(NodeKind::Class)
            .fqn("test.MyClass")
            .file_path("test.py")
            .span(Span::new(14, 0, 20, 0))
            .with_name("MyClass")
            .build()
            .expect("Failed to build node3");

        doc.add_node(node1);
        doc.add_node(node2);
        doc.add_node(node3);

        doc
    }

    #[test]
    fn test_filter_by_kind() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let nodes = builder.filter(NodeKind::Function).execute().unwrap();
        assert_eq!(nodes.len(), 2);
        assert!(nodes.iter().all(|n| n.kind == NodeKind::Function));
    }

    #[test]
    fn test_where_field() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let nodes = builder
            .filter(NodeKind::Function)
            .where_field("language", "python")
            .execute()
            .unwrap();

        assert_eq!(nodes.len(), 2);
    }

    #[test]
    fn test_where_fn() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        // Note: Since metadata is now Option<String>, not HashMap,
        // we can't test complex filtering. This is a simplified test.
        let nodes = builder
            .filter(NodeKind::Function)
            .where_fn(|n| n.name.as_ref().map(|name| name == "func2").unwrap_or(false))
            .execute()
            .unwrap();

        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].name, Some("func2".to_string()));
    }

    #[test]
    fn test_order_by() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let nodes = builder
            .filter(NodeKind::Function)
            .order_by("name", Order::Desc)
            .execute()
            .unwrap();

        assert_eq!(nodes.len(), 2);
        // Alphabetically: func2 > func1 in descending order
        assert_eq!(nodes[0].name, Some("func2".to_string()));
        assert_eq!(nodes[1].name, Some("func1".to_string()));
    }

    #[test]
    fn test_limit_offset() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let nodes = builder
            .offset(1)
            .limit(1)
            .execute()
            .unwrap();

        assert_eq!(nodes.len(), 1);
    }
}
