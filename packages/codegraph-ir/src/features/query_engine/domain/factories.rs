// Domain: Q and E factories - Fluent API entry points
// Maps to Python: src/contexts/code_foundation/domain/query/factories.py

use super::{EdgeSelector, EdgeType, NodeSelector, NodeSelectorType, SelectorValue};

/// Q factory - Node selector builder
/// Provides Python-like API: Q::var("user"), Q::call("execute")
pub struct Q;

impl Q {
    /// Variable selector: Q::var("input")
    pub fn var(name: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Var)
            .with_attr("name", SelectorValue::String(name.into()))
    }

    /// Variable with optional attributes
    pub fn var_with_type(name: impl Into<String>, type_name: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Var)
            .with_attr("name", SelectorValue::String(name.into()))
            .with_attr("type", SelectorValue::String(type_name.into()))
    }

    /// Function selector: Q::func("process")
    pub fn func(name: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Func)
            .with_attr("name", SelectorValue::String(name.into()))
    }

    /// Call selector: Q::call("execute")
    pub fn call(name: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Call)
            .with_attr("name", SelectorValue::String(name.into()))
    }

    /// Block selector: Q::block_kind("Condition")
    pub fn block_kind(kind: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Block)
            .with_attr("kind", SelectorValue::String(kind.into()))
    }

    /// Block selector (all blocks)
    pub fn block() -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Block)
    }

    /// Expression selector: Q::expr_kind("BinOp")
    pub fn expr_kind(kind: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Expr)
            .with_attr("kind", SelectorValue::String(kind.into()))
    }

    /// Expression selector (all expressions)
    pub fn expr() -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Expr)
    }

    /// Class selector: Q::class("User")
    pub fn class(name: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Class)
            .with_attr("name", SelectorValue::String(name.into()))
    }

    /// Module selector: Q::module("core.*")
    pub fn module(pattern: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Module)
            .with_attr("pattern", SelectorValue::String(pattern.into()))
    }

    /// Field selector: Q::field("user", "id")
    pub fn field(obj: impl Into<String>, field: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Field)
            .with_attr("obj", SelectorValue::String(obj.into()))
            .with_attr("field", SelectorValue::String(field.into()))
    }

    /// Source selector: Q::source("request")
    pub fn source(category: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Source)
            .with_attr("category", SelectorValue::String(category.into()))
    }

    /// Sink selector: Q::sink("execute")
    pub fn sink(category: impl Into<String>) -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Sink)
            .with_attr("category", SelectorValue::String(category.into()))
    }

    /// Wildcard selector: Q::any()
    pub fn any() -> NodeSelector {
        NodeSelector::new(NodeSelectorType::Any)
    }
}

/// E factory - Edge selector builder
/// Provides Python-like API: E::DFG, E::CFG
pub struct E;

impl E {
    /// Data flow graph: E::dfg()
    pub fn dfg() -> EdgeSelector {
        EdgeSelector::new(EdgeType::DFG)
    }

    /// Control flow graph: E::cfg()
    pub fn cfg() -> EdgeSelector {
        EdgeSelector::new(EdgeType::CFG)
    }

    /// Call graph: E::call()
    pub fn call() -> EdgeSelector {
        EdgeSelector::new(EdgeType::Call)
    }

    /// All edges: E::all()
    pub fn all() -> EdgeSelector {
        EdgeSelector::new(EdgeType::All)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_q_var() {
        let selector = Q::var("user");
        assert_eq!(selector.selector_type, NodeSelectorType::Var);
        assert_eq!(selector.get_string("name"), Some("user"));
    }

    #[test]
    fn test_q_var_with_type() {
        let selector = Q::var_with_type("x", "str");
        assert_eq!(selector.get_string("name"), Some("x"));
        assert_eq!(selector.get_string("type"), Some("str"));
    }

    #[test]
    fn test_q_call() {
        let selector = Q::call("execute");
        assert_eq!(selector.selector_type, NodeSelectorType::Call);
        assert_eq!(selector.get_string("name"), Some("execute"));
    }

    #[test]
    fn test_q_block_kind() {
        let selector = Q::block_kind("Condition");
        assert_eq!(selector.selector_type, NodeSelectorType::Block);
        assert_eq!(selector.get_string("kind"), Some("Condition"));
    }

    #[test]
    fn test_q_expr_kind() {
        let selector = Q::expr_kind("BinOp");
        assert_eq!(selector.selector_type, NodeSelectorType::Expr);
        assert_eq!(selector.get_string("kind"), Some("BinOp"));
    }

    #[test]
    fn test_q_source_sink() {
        let source = Q::source("request");
        let sink = Q::sink("execute");

        assert_eq!(source.selector_type, NodeSelectorType::Source);
        assert_eq!(sink.selector_type, NodeSelectorType::Sink);
        assert_eq!(source.get_string("category"), Some("request"));
        assert_eq!(sink.get_string("category"), Some("execute"));
    }

    #[test]
    fn test_q_field() {
        let selector = Q::field("user", "id");
        assert_eq!(selector.selector_type, NodeSelectorType::Field);
        assert_eq!(selector.get_string("obj"), Some("user"));
        assert_eq!(selector.get_string("field"), Some("id"));
    }

    #[test]
    fn test_e_factories() {
        let dfg = E::dfg();
        let cfg = E::cfg();
        let call = E::call();
        let all = E::all();

        assert_eq!(dfg.edge_type, EdgeType::DFG);
        assert_eq!(cfg.edge_type, EdgeType::CFG);
        assert_eq!(call.edge_type, EdgeType::Call);
        assert_eq!(all.edge_type, EdgeType::All);
    }

    #[test]
    fn test_edge_modifiers() {
        let edge = E::dfg().backward().depth(5, 1);
        assert!(edge.backward);
        assert_eq!(edge.max_depth, 5);
        assert_eq!(edge.min_depth, 1);
    }
}
