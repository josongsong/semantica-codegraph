// Domain: NodeSelector - Type-safe node matching
// Maps to Python: src/contexts/code_foundation/domain/query/selectors.py

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Node selector types (matches Python NodeSelectorType)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NodeSelectorType {
    Var,
    Func,
    Call,
    Block,
    Expr,
    Class,
    Module,
    Field,
    Source,
    Sink,
    Any,
}

/// Node selector with attributes
/// Matches Python: NodeSelector dataclass
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NodeSelector {
    pub selector_type: NodeSelectorType,
    pub attributes: HashMap<String, SelectorValue>,
}

/// Selector attribute value types
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum SelectorValue {
    String(String),
    Int(i64),
    Bool(bool),
    None,
}

impl NodeSelector {
    pub fn new(selector_type: NodeSelectorType) -> Self {
        Self {
            selector_type,
            attributes: HashMap::new(),
        }
    }

    pub fn with_attr(mut self, key: impl Into<String>, value: SelectorValue) -> Self {
        self.attributes.insert(key.into(), value);
        self
    }

    pub fn get_attr(&self, key: &str) -> Option<&SelectorValue> {
        self.attributes.get(key)
    }

    pub fn get_string(&self, key: &str) -> Option<&str> {
        match self.get_attr(key) {
            Some(SelectorValue::String(s)) => Some(s.as_str()),
            _ => None,
        }
    }

    pub fn get_int(&self, key: &str) -> Option<i64> {
        match self.get_attr(key) {
            Some(SelectorValue::Int(i)) => Some(*i),
            _ => None,
        }
    }

    pub fn get_bool(&self, key: &str) -> Option<bool> {
        match self.get_attr(key) {
            Some(SelectorValue::Bool(b)) => Some(*b),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_node_selector_creation() {
        let selector = NodeSelector::new(NodeSelectorType::Var)
            .with_attr("name", SelectorValue::String("user".to_string()));

        assert_eq!(selector.selector_type, NodeSelectorType::Var);
        assert_eq!(selector.get_string("name"), Some("user"));
    }

    #[test]
    fn test_selector_value_types() {
        let selector = NodeSelector::new(NodeSelectorType::Block)
            .with_attr("kind", SelectorValue::String("Condition".to_string()))
            .with_attr("depth", SelectorValue::Int(5))
            .with_attr("enabled", SelectorValue::Bool(true));

        assert_eq!(selector.get_string("kind"), Some("Condition"));
        assert_eq!(selector.get_int("depth"), Some(5));
        assert_eq!(selector.get_bool("enabled"), Some(true));
    }
}
