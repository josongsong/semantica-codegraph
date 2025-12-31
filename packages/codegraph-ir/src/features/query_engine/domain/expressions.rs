// Domain: FlowExpr and PathQuery
// Maps to Python: src/contexts/code_foundation/domain/query/expressions.py

use super::{EdgeSelector, NodeSelector};
use serde::{Deserialize, Serialize};

/// Traversal direction
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TraversalDirection {
    Forward,
    Backward,
}

/// Flow expression (immutable structure)
/// Matches Python: FlowExpr dataclass
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FlowExpr {
    pub source: NodeSelector,
    pub target: NodeSelector,
    pub direction: TraversalDirection,
    pub edge_type: Option<EdgeSelector>,
    pub depth_range: (usize, usize),
}

impl FlowExpr {
    pub fn new(source: NodeSelector, target: NodeSelector, direction: TraversalDirection) -> Self {
        Self {
            source,
            target,
            direction,
            edge_type: None,
            depth_range: (1, 10),
        }
    }

    /// Add edge constraint (immutable)
    pub fn via(mut self, edge: EdgeSelector) -> Self {
        self.edge_type = Some(edge);
        self
    }

    /// Set depth range (immutable)
    pub fn depth(mut self, max: usize, min: usize) -> Self {
        self.depth_range = (min, max);
        self
    }

    /// Promote to PathQuery with constraint
    pub fn where_path<F>(self, predicate: F) -> PathQuery
    where
        F: Fn(&PathResult) -> bool + 'static,
    {
        PathQuery::from_flow_expr(self).where_path(predicate)
    }

    /// Promote to PathQuery for execution
    pub fn any_path(self) -> PathQuery {
        PathQuery::from_flow_expr(self)
    }

    /// Promote to PathQuery for verification
    pub fn all_paths(self) -> PathQuery {
        PathQuery::from_flow_expr(self)
    }
}

/// Path constraint predicate (type-safe)
pub type PathPredicate = Box<dyn Fn(&PathResult) -> bool>;

/// Path query with constraints (executable)
/// Matches Python: PathQuery dataclass
/// Note: Cannot derive Clone due to PathPredicate (Box<dyn Fn>)
pub struct PathQuery {
    pub flow: FlowExpr,
    pub path_constraints: Vec<PathPredicate>,
    pub excluding_nodes: Vec<NodeSelector>,
    pub within_scope: Option<NodeSelector>,
    pub max_paths: usize,
    pub timeout_ms: u64,
}

impl PathQuery {
    pub fn from_flow_expr(flow: FlowExpr) -> Self {
        Self {
            flow,
            path_constraints: Vec::new(),
            excluding_nodes: Vec::new(),
            within_scope: None,
            max_paths: 100,
            timeout_ms: 30000,
        }
    }

    pub fn where_path<F>(mut self, predicate: F) -> Self
    where
        F: Fn(&PathResult) -> bool + 'static,
    {
        self.path_constraints.push(Box::new(predicate));
        self
    }

    pub fn excluding(mut self, nodes: NodeSelector) -> Self {
        self.excluding_nodes.push(nodes);
        self
    }

    pub fn within(mut self, scope: NodeSelector) -> Self {
        self.within_scope = Some(scope);
        self
    }

    pub fn limit_paths(mut self, max: usize) -> Self {
        self.max_paths = max;
        self
    }

    pub fn timeout(mut self, ms: u64) -> Self {
        self.timeout_ms = ms;
        self
    }
}

/// Path result (placeholder - will be implemented in infrastructure)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathResult {
    pub node_ids: Vec<String>,
    pub edge_ids: Vec<String>,
}

impl PathResult {
    pub fn len(&self) -> usize {
        self.node_ids.len()
    }

    pub fn is_empty(&self) -> bool {
        self.node_ids.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::query_engine::domain::{NodeSelector, NodeSelectorType, SelectorValue};

    #[test]
    fn test_flow_expr_creation() {
        let source = NodeSelector::new(NodeSelectorType::Var)
            .with_attr("name", SelectorValue::String("user".to_string()));
        let target = NodeSelector::new(NodeSelectorType::Call)
            .with_attr("name", SelectorValue::String("execute".to_string()));

        let expr = FlowExpr::new(source, target, TraversalDirection::Forward);

        assert_eq!(expr.direction, TraversalDirection::Forward);
        assert_eq!(expr.depth_range, (1, 10));
        assert!(expr.edge_type.is_none());
    }

    #[test]
    fn test_flow_expr_via() {
        let source = NodeSelector::new(NodeSelectorType::Var);
        let target = NodeSelector::new(NodeSelectorType::Call);
        let edge = EdgeSelector::new(crate::features::query_engine::domain::EdgeType::DFG);

        let expr = FlowExpr::new(source, target, TraversalDirection::Forward).via(edge);

        assert!(expr.edge_type.is_some());
        assert_eq!(
            expr.edge_type.unwrap().edge_type,
            crate::features::query_engine::domain::EdgeType::DFG
        );
    }

    #[test]
    fn test_path_query_constraints() {
        let source = NodeSelector::new(NodeSelectorType::Source);
        let target = NodeSelector::new(NodeSelectorType::Sink);

        let query = FlowExpr::new(source, target, TraversalDirection::Forward)
            .any_path()
            .where_path(|p| p.len() > 3)
            .limit_paths(20)
            .timeout(5000);

        assert_eq!(query.max_paths, 20);
        assert_eq!(query.timeout_ms, 5000);
        assert_eq!(query.path_constraints.len(), 1);
    }
}
