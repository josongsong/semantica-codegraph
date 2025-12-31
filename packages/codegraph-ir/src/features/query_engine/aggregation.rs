// AggregationBuilder - Statistical aggregations over nodes
//
// Provides fluent API for aggregations:
// - count(), avg(), sum(), min(), max()
// - Multiple aggregations in single query
// - Result type with all requested metrics

use std::collections::HashMap;
use crate::shared::models::Node;
use super::node_query::NodeQueryBuilder;

/// Aggregation result
#[derive(Debug, Clone, PartialEq)]
pub struct AggregationResult {
    pub count: Option<usize>,
    pub avg: HashMap<String, f64>,
    pub sum: HashMap<String, f64>,
    pub min: HashMap<String, f64>,
    pub max: HashMap<String, f64>,
}

impl AggregationResult {
    pub fn new() -> Self {
        Self {
            count: None,
            avg: HashMap::new(),
            sum: HashMap::new(),
            min: HashMap::new(),
            max: HashMap::new(),
        }
    }
}

/// AggregationBuilder - Fluent API for aggregations
///
/// Example:
/// ```no_run
/// let stats = engine.query()
///     .nodes()
///     .filter(NodeKind::Function)
///     .where_field("language", "python")
///     .aggregate()
///     .count()
///     .avg("complexity")
///     .max("complexity")
///     .execute()?;
///
/// println!("Total functions: {}", stats.count.unwrap());
/// println!("Avg complexity: {}", stats.avg.get("complexity").unwrap());
/// ```
pub struct AggregationBuilder<'a> {
    node_query: NodeQueryBuilder<'a>,

    // Requested aggregations
    do_count: bool,
    avg_fields: Vec<String>,
    sum_fields: Vec<String>,
    min_fields: Vec<String>,
    max_fields: Vec<String>,
}

impl<'a> AggregationBuilder<'a> {
    /// Create new AggregationBuilder from NodeQueryBuilder
    pub fn new(node_query: NodeQueryBuilder<'a>) -> Self {
        Self {
            node_query,
            do_count: false,
            avg_fields: Vec::new(),
            sum_fields: Vec::new(),
            min_fields: Vec::new(),
            max_fields: Vec::new(),
        }
    }

    /// Count nodes
    ///
    /// Example:
    /// ```no_run
    /// .aggregate().count().execute()?
    /// ```
    pub fn count(mut self) -> Self {
        self.do_count = true;
        self
    }

    /// Average of field
    ///
    /// Example:
    /// ```no_run
    /// .aggregate().avg("complexity").execute()?
    /// ```
    pub fn avg(mut self, field: &str) -> Self {
        self.avg_fields.push(field.to_string());
        self
    }

    /// Sum of field
    ///
    /// Example:
    /// ```no_run
    /// .aggregate().sum("lines_of_code").execute()?
    /// ```
    pub fn sum(mut self, field: &str) -> Self {
        self.sum_fields.push(field.to_string());
        self
    }

    /// Min of field
    ///
    /// Example:
    /// ```no_run
    /// .aggregate().min("complexity").execute()?
    /// ```
    pub fn min(mut self, field: &str) -> Self {
        self.min_fields.push(field.to_string());
        self
    }

    /// Max of field
    ///
    /// Example:
    /// ```no_run
    /// .aggregate().max("complexity").execute()?
    /// ```
    pub fn max(mut self, field: &str) -> Self {
        self.max_fields.push(field.to_string());
        self
    }

    /// Execute aggregation and return result
    pub fn execute(self) -> Result<AggregationResult, String> {
        // Get filtered nodes from node query
        let nodes = self.node_query.get_filtered_nodes();

        let mut result = AggregationResult::new();

        // Count
        if self.do_count {
            result.count = Some(nodes.len());
        }

        // Average
        for field in &self.avg_fields {
            if let Some(avg_val) = self.compute_avg(&nodes, field) {
                result.avg.insert(field.clone(), avg_val);
            }
        }

        // Sum
        for field in &self.sum_fields {
            if let Some(sum_val) = self.compute_sum(&nodes, field) {
                result.sum.insert(field.clone(), sum_val);
            }
        }

        // Min
        for field in &self.min_fields {
            if let Some(min_val) = self.compute_min(&nodes, field) {
                result.min.insert(field.clone(), min_val);
            }
        }

        // Max
        for field in &self.max_fields {
            if let Some(max_val) = self.compute_max(&nodes, field) {
                result.max.insert(field.clone(), max_val);
            }
        }

        Ok(result)
    }

    /// Internal: Compute average
    fn compute_avg(&self, nodes: &[Node], field: &str) -> Option<f64> {
        let values: Vec<f64> = nodes
            .iter()
            .filter_map(|n| self.get_numeric_field(n, field))
            .collect();

        if values.is_empty() {
            return None;
        }

        let sum: f64 = values.iter().sum();
        Some(sum / values.len() as f64)
    }

    /// Internal: Compute sum
    fn compute_sum(&self, nodes: &[Node], field: &str) -> Option<f64> {
        let values: Vec<f64> = nodes
            .iter()
            .filter_map(|n| self.get_numeric_field(n, field))
            .collect();

        if values.is_empty() {
            return None;
        }

        Some(values.iter().sum())
    }

    /// Internal: Compute min
    fn compute_min(&self, nodes: &[Node], field: &str) -> Option<f64> {
        nodes
            .iter()
            .filter_map(|n| self.get_numeric_field(n, field))
            .min_by(|a, b| a.partial_cmp(b).unwrap())
    }

    /// Internal: Compute max
    fn compute_max(&self, nodes: &[Node], field: &str) -> Option<f64> {
        nodes
            .iter()
            .filter_map(|n| self.get_numeric_field(n, field))
            .max_by(|a, b| a.partial_cmp(b).unwrap())
    }

    /// Internal: Get numeric field value
    fn get_numeric_field(&self, node: &Node, field: &str) -> Option<f64> {
        // metadata is Option<String>, not a HashMap
        let value = node.metadata.as_ref()?;
        value.parse::<f64>().ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::shared::models::{Node, NodeKind};
    use crate::features::query_engine::infrastructure::GraphIndex;
    use crate::features::query_engine::node_query::NodeQueryBuilder;

    fn create_test_doc() -> IRDocument {
        let mut doc = IRDocument::new("test.py".to_string());

        // Add test nodes with complexity
        for i in 1..=5 {
            let mut node = Node::new(
                format!("func{}", i),
                "function".to_string(),
            );
            node.metadata.insert("complexity".to_string(), (i * 5).to_string());
            node.metadata.insert("lines".to_string(), (i * 10).to_string());
            doc.add_node(node);
        }

        doc
    }

    #[test]
    fn test_count() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let result = builder
            .filter(NodeKind::Function)
            .aggregate()
            .count()
            .execute()
            .unwrap();

        assert_eq!(result.count, Some(5));
    }

    #[test]
    fn test_avg() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let result = builder
            .filter(NodeKind::Function)
            .aggregate()
            .avg("complexity")
            .execute()
            .unwrap();

        // (5 + 10 + 15 + 20 + 25) / 5 = 15.0
        assert_eq!(result.avg.get("complexity"), Some(&15.0));
    }

    #[test]
    fn test_sum() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let result = builder
            .filter(NodeKind::Function)
            .aggregate()
            .sum("complexity")
            .execute()
            .unwrap();

        // 5 + 10 + 15 + 20 + 25 = 75
        assert_eq!(result.sum.get("complexity"), Some(&75.0));
    }

    #[test]
    fn test_min_max() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let result = builder
            .filter(NodeKind::Function)
            .aggregate()
            .min("complexity")
            .max("complexity")
            .execute()
            .unwrap();

        assert_eq!(result.min.get("complexity"), Some(&5.0));
        assert_eq!(result.max.get("complexity"), Some(&25.0));
    }

    #[test]
    fn test_multiple_aggregations() {
        let doc = create_test_doc();
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let result = builder
            .filter(NodeKind::Function)
            .aggregate()
            .count()
            .avg("complexity")
            .sum("lines")
            .min("complexity")
            .max("complexity")
            .execute()
            .unwrap();

        assert_eq!(result.count, Some(5));
        assert_eq!(result.avg.get("complexity"), Some(&15.0));
        assert_eq!(result.sum.get("lines"), Some(&150.0)); // 10+20+30+40+50
        assert_eq!(result.min.get("complexity"), Some(&5.0));
        assert_eq!(result.max.get("complexity"), Some(&25.0));
    }
}
