// Domain: Operator overloading for fluent DSL
// Enables syntax: Q::var("user") >> Q::call("execute")

use super::{FlowExpr, NodeSelector, TraversalDirection};
use std::ops::{BitAnd, BitOr, Shl, Shr};

// ============================================================================
// >> operator: Forward reachability (N-hop)
// ============================================================================

impl Shr<NodeSelector> for NodeSelector {
    type Output = FlowExpr;

    /// Forward reachability: source >> target
    /// Example: Q::var("user") >> Q::call("execute")
    fn shr(self, rhs: NodeSelector) -> FlowExpr {
        FlowExpr::new(self, rhs, TraversalDirection::Forward)
    }
}

// ============================================================================
// << operator: Backward reachability (N-hop)
// ============================================================================

impl Shl<NodeSelector> for NodeSelector {
    type Output = FlowExpr;

    /// Backward reachability: target << source
    /// Example: Q::call("execute") << Q::var("user")
    fn shl(self, rhs: NodeSelector) -> FlowExpr {
        FlowExpr::new(rhs, self, TraversalDirection::Backward)
    }
}

// ============================================================================
// | operator: Union (OR)
// ============================================================================

impl BitOr<NodeSelector> for NodeSelector {
    type Output = NodeSelectorUnion;

    /// Union: selector1 | selector2
    /// Example: Q::var("input") | Q::var("argv")
    fn bitor(self, rhs: NodeSelector) -> NodeSelectorUnion {
        NodeSelectorUnion {
            selectors: vec![self, rhs],
        }
    }
}

/// Union of node selectors
#[derive(Debug, Clone)]
pub struct NodeSelectorUnion {
    pub selectors: Vec<NodeSelector>,
}

impl BitOr<NodeSelector> for NodeSelectorUnion {
    type Output = NodeSelectorUnion;

    /// Chainable union: union | selector
    fn bitor(mut self, rhs: NodeSelector) -> NodeSelectorUnion {
        self.selectors.push(rhs);
        self
    }
}

// Union can also create flow expressions
impl Shr<NodeSelector> for NodeSelectorUnion {
    type Output = Vec<FlowExpr>;

    /// Forward from union: (A | B) >> C creates [A >> C, B >> C]
    fn shr(self, rhs: NodeSelector) -> Vec<FlowExpr> {
        self.selectors
            .into_iter()
            .map(|sel| FlowExpr::new(sel, rhs.clone(), TraversalDirection::Forward))
            .collect()
    }
}

impl Shl<NodeSelector> for NodeSelectorUnion {
    type Output = Vec<FlowExpr>;

    /// Backward to union: C << (A | B) creates [C << A, C << B]
    fn shl(self, rhs: NodeSelector) -> Vec<FlowExpr> {
        self.selectors
            .into_iter()
            .map(|sel| FlowExpr::new(rhs.clone(), sel, TraversalDirection::Backward))
            .collect()
    }
}

// ============================================================================
// & operator: Intersection (AND) - for filtering
// ============================================================================

impl BitAnd<NodeSelector> for NodeSelector {
    type Output = NodeSelectorIntersection;

    /// Intersection: selector1 & selector2
    /// Example: Q::var(type="str") & Q::tainted()
    fn bitand(self, rhs: NodeSelector) -> NodeSelectorIntersection {
        NodeSelectorIntersection {
            selectors: vec![self, rhs],
        }
    }
}

/// Intersection of node selectors (all must match)
#[derive(Debug, Clone)]
pub struct NodeSelectorIntersection {
    pub selectors: Vec<NodeSelector>,
}

impl BitAnd<NodeSelector> for NodeSelectorIntersection {
    type Output = NodeSelectorIntersection;

    fn bitand(mut self, rhs: NodeSelector) -> NodeSelectorIntersection {
        self.selectors.push(rhs);
        self
    }
}

#[cfg(test)]
mod tests {
    use super::super::{NodeSelectorType, SelectorValue, Q};
    use super::*;

    #[test]
    fn test_forward_operator() {
        let source = Q::var("user");
        let target = Q::call("execute");

        let expr = source >> target;

        assert_eq!(expr.direction, TraversalDirection::Forward);
        assert_eq!(expr.source.selector_type, NodeSelectorType::Var);
        assert_eq!(expr.target.selector_type, NodeSelectorType::Call);
    }

    #[test]
    fn test_backward_operator() {
        let target = Q::call("execute");
        let source = Q::var("user");

        let expr = target << source;

        assert_eq!(expr.direction, TraversalDirection::Backward);
        assert_eq!(expr.source.selector_type, NodeSelectorType::Var);
        assert_eq!(expr.target.selector_type, NodeSelectorType::Call);
    }

    #[test]
    fn test_union_operator() {
        let var1 = Q::var("input");
        let var2 = Q::var("argv");

        let union = var1 | var2;

        assert_eq!(union.selectors.len(), 2);
    }

    #[test]
    fn test_union_chaining() {
        let var1 = Q::var("input");
        let var2 = Q::var("argv");
        let var3 = Q::var("env");

        let union = var1 | var2 | var3;

        assert_eq!(union.selectors.len(), 3);
    }

    #[test]
    fn test_union_to_flow_expr() {
        let sources = Q::var("input") | Q::var("argv");
        let sink = Q::sink("execute");

        let exprs = sources >> sink;

        assert_eq!(exprs.len(), 2);
        assert_eq!(exprs[0].direction, TraversalDirection::Forward);
        assert_eq!(exprs[1].direction, TraversalDirection::Forward);
    }

    #[test]
    fn test_intersection_operator() {
        let type_filter = Q::var_with_type("x", "str");
        let scope_filter = NodeSelector::new(NodeSelectorType::Var)
            .with_attr("scope", SelectorValue::String("main".to_string()));

        let intersection = type_filter & scope_filter;

        assert_eq!(intersection.selectors.len(), 2);
    }

    #[test]
    fn test_complex_expression() {
        // Q::source("request") >> Q::sink("execute")
        let expr = Q::source("request") >> Q::sink("execute");

        assert_eq!(expr.source.selector_type, NodeSelectorType::Source);
        assert_eq!(expr.target.selector_type, NodeSelectorType::Sink);
        assert_eq!(expr.source.get_string("category"), Some("request"));
        assert_eq!(expr.target.get_string("category"), Some("execute"));
    }
}
