// EdgeQueryBuilder - Edge filtering and querying
//
// Provides fluent API for edge queries:
// - Filtering: .filter(), .where_field()
// - Callers/Callees: Specialized queries for call graph
// - Pagination: .limit(), .offset()

use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::shared::models::Edge;
use crate::features::query_engine::infrastructure::GraphIndex;

/// Edge kind filter (P0: TYPE-SAFE selector support)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum EdgeKind {
    Calls,      // Function call edge
    Dataflow,   // Data flow edge (DFG)
    ControlFlow, // Control flow edge (CFG)
    References, // Reference edge
    Contains,   // Containment edge (class contains method)
    All,        // Any edge type
}

/// EdgeQueryBuilder - Fluent API for edge queries
///
/// Example:
/// ```no_run
/// // Get all callers of a function
/// let callers = engine.query()
///     .edges()
///     .filter(EdgeKind::Calls)
///     .where_field("target_id", symbol_id)
///     .execute()?;
/// ```
pub struct EdgeQueryBuilder<'a> {
    index: &'a GraphIndex,
    ir_doc: &'a IRDocument,

    // Filters
    kind_filter: Option<EdgeKind>,
    field_filters: Vec<(String, String)>,  // (field_name, expected_value)

    // Pagination
    limit: Option<usize>,
    offset: usize,
}

impl<'a> EdgeQueryBuilder<'a> {
    /// Create new EdgeQueryBuilder
    pub fn new(index: &'a GraphIndex, ir_doc: &'a IRDocument) -> Self {
        Self {
            index,
            ir_doc,
            kind_filter: None,
            field_filters: Vec::new(),
            limit: None,
            offset: 0,
        }
    }

    /// Filter by edge kind
    ///
    /// Example:
    /// ```no_run
    /// .filter(EdgeKind::Calls)
    /// ```
    pub fn filter(mut self, kind: EdgeKind) -> Self {
        self.kind_filter = Some(kind);
        self
    }

    /// Filter by field value
    ///
    /// Example:
    /// ```no_run
    /// .where_field("source_id", node_id)
    /// .where_field("target_id", other_id)
    /// ```
    pub fn where_field(mut self, field: &str, value: &str) -> Self {
        self.field_filters.push((field.to_string(), value.to_string()));
        self
    }

    /// Limit number of results
    pub fn limit(mut self, limit: usize) -> Self {
        self.limit = Some(limit);
        self
    }

    /// Skip first N results (pagination)
    pub fn offset(mut self, offset: usize) -> Self {
        self.offset = offset;
        self
    }

    /// Execute query and return edges
    pub fn execute(self) -> Result<Vec<Edge>, String> {
        // Step 1: Get all edges from IR document
        let all_edges = self.ir_doc.get_all_edges();

        // Step 2: Apply filters
        let filtered: Vec<Edge> = all_edges
            .into_iter()
            .filter(|edge| self.matches_filters(edge))
            .collect();

        // Step 3: Apply pagination
        let start = self.offset;
        let end = self.limit.map(|l| start + l).unwrap_or(filtered.len());

        Ok(filtered.into_iter().skip(start).take(end - start).collect())
    }

    /// Internal: Check if edge matches all filters
    fn matches_filters(&self, edge: &Edge) -> bool {
        // Kind filter
        if let Some(kind) = self.kind_filter {
            if !self.matches_kind(edge, kind) {
                return false;
            }
        }

        // Field filters
        for (field, expected_value) in &self.field_filters {
            let actual_value = self.get_field_value(edge, field);
            if actual_value != *expected_value {
                return false;
            }
        }

        true
    }

    /// Internal: Check if edge matches kind
    fn matches_kind(&self, edge: &Edge, kind: EdgeKind) -> bool {
        use crate::shared::models::EdgeKind as EK;
        match kind {
            EdgeKind::All => true,
            EdgeKind::Calls => edge.kind == EK::Calls || edge.kind == EK::Invokes,
            EdgeKind::Dataflow => edge.kind == EK::DataFlow,
            EdgeKind::ControlFlow => edge.kind == EK::ControlFlow,
            EdgeKind::References => edge.kind == EK::References,
            EdgeKind::Contains => edge.kind == EK::Contains,
        }
    }

    /// Internal: Get field value from edge
    fn get_field_value(&self, edge: &Edge, field: &str) -> String {
        match field {
            "source_id" => edge.source_id.clone(),
            "target_id" => edge.target_id.clone(),
            "kind" => edge.kind.as_str().to_string(),
            // Metadata fields - metadata is Option<EdgeMetadata>, not HashMap
            _ => String::new(),
        }
    }
}

/// Helper functions for common edge queries

impl<'a> EdgeQueryBuilder<'a> {
    /// Get all callers of a node (incoming call edges)
    ///
    /// Example:
    /// ```no_run
    /// let callers = engine.query()
    ///     .edges()
    ///     .callers_of("func_123")
    ///     .execute()?;
    /// ```
    pub fn callers_of(self, target_id: &str) -> Self {
        self.filter(EdgeKind::Calls)
            .where_field("target_id", target_id)
    }

    /// Get all callees of a node (outgoing call edges)
    ///
    /// Example:
    /// ```no_run
    /// let callees = engine.query()
    ///     .edges()
    ///     .callees_of("func_123")
    ///     .execute()?;
    /// ```
    pub fn callees_of(self, source_id: &str) -> Self {
        self.filter(EdgeKind::Calls)
            .where_field("source_id", source_id)
    }

    /// Get all references to a node
    ///
    /// Example:
    /// ```no_run
    /// let refs = engine.query()
    ///     .edges()
    ///     .references_to("var_456")
    ///     .execute()?;
    /// ```
    pub fn references_to(self, target_id: &str) -> Self {
        self.filter(EdgeKind::References)
            .where_field("target_id", target_id)
    }

    /// Get dataflow edges from a node
    ///
    /// Example:
    /// ```no_run
    /// let flows = engine.query()
    ///     .edges()
    ///     .dataflow_from("user_input")
    ///     .execute()?;
    /// ```
    pub fn dataflow_from(self, source_id: &str) -> Self {
        self.filter(EdgeKind::Dataflow)
            .where_field("source_id", source_id)
    }

    /// Get dataflow edges to a node
    pub fn dataflow_to(self, target_id: &str) -> Self {
        self.filter(EdgeKind::Dataflow)
            .where_field("target_id", target_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::shared::models::Edge;
    use crate::features::query_engine::infrastructure::GraphIndex;

    fn create_test_doc() -> IRDocument {
        let mut doc = IRDocument::new("test.py".to_string());

        // Add test edges
        let edge1 = Edge::new("func1".to_string(), "func2".to_string(), "call".to_string());
        let edge2 = Edge::new("func2".to_string(), "func3".to_string(), "call".to_string());
        let edge3 = Edge::new("var1".to_string(), "var2".to_string(), "dataflow".to_string());

        doc.add_edge(edge1);
        doc.add_edge(edge2);
        doc.add_edge(edge3);

        doc
    }

    #[test]
    fn test_filter_by_kind() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = EdgeQueryBuilder::new(&index, &doc);

        let edges = builder.filter(EdgeKind::Calls).execute().unwrap();
        assert_eq!(edges.len(), 2);
        assert!(edges.iter().all(|e| e.edge_type == "call"));
    }

    #[test]
    fn test_where_field() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = EdgeQueryBuilder::new(&index, &doc);

        let edges = builder
            .filter(EdgeKind::Calls)
            .where_field("source_id", "func1")
            .execute()
            .unwrap();

        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].target_id, "func2");
    }

    #[test]
    fn test_callers_of() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = EdgeQueryBuilder::new(&index, &doc);

        let edges = builder.callers_of("func2").execute().unwrap();

        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].source_id, "func1");
    }

    #[test]
    fn test_callees_of() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = EdgeQueryBuilder::new(&index, &doc);

        let edges = builder.callees_of("func2").execute().unwrap();

        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].target_id, "func3");
    }

    #[test]
    fn test_dataflow_from() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = EdgeQueryBuilder::new(&index, &doc);

        let edges = builder.dataflow_from("var1").execute().unwrap();

        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].target_id, "var2");
    }
}
