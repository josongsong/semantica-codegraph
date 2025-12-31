// Node and Edge Selectors for Path Queries - RFC-RUST-SDK-002 P0
//
// Provides FFI-safe selector types for graph traversal:
// - NodeSelector: Select start/end nodes for path queries
// - EdgeSelector: Filter edges during traversal
// - PathLimits: Safety guardrails against graph explosion
//
// Design: RFC-RUST-SDK-002 Section 9.1.3

use serde::{Deserialize, Serialize};
use crate::features::query_engine::expression::Expr;

// Re-export NodeKind from shared models and EdgeKind from edge_query
pub use crate::shared::models::NodeKind;
pub use crate::features::query_engine::edge_query::EdgeKind;

/// Node selection strategies for path queries
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum NodeSelector {
    /// Direct node ID
    ById(String),

    /// By fully qualified name
    ByName {
        name: String,
        scope: Option<String>,  // file/module scope
    },

    /// By node kind + filters (TYPE-SAFE with NodeKind enum)
    ByKind {
        kind: NodeKind,
        filters: Vec<Expr>,
    },

    /// Multiple selectors (union)
    Union(Vec<NodeSelector>),
}

/// Edge selection for path traversal
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum EdgeSelector {
    /// Any edge type
    Any,

    /// Single edge kind (TYPE-SAFE with EdgeKind enum)
    ByKind(EdgeKind),

    /// Multiple edge kinds (union, TYPE-SAFE)
    ByKinds(Vec<EdgeKind>),

    /// Edge filter expression
    ByFilter(Vec<Expr>),
}

/// Safety limits for path queries (CRITICAL - prevents graph explosion)
///
/// Default limits are conservative to prevent DoS:
/// - max_paths: 100 (enough for most analyses)
/// - max_expansions: 10,000 (BFS node visit limit)
/// - timeout_ms: 30,000 (30 seconds)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PathLimits {
    /// Max paths to return (default: 100)
    pub max_paths: usize,

    /// Max nodes to expand during search (default: 10,000)
    pub max_expansions: usize,

    /// Query timeout in milliseconds (default: 30,000)
    pub timeout_ms: u64,

    /// Max path length (overrides depth if smaller)
    pub max_path_length: Option<usize>,
}

impl Default for PathLimits {
    fn default() -> Self {
        Self {
            max_paths: 100,
            max_expansions: 10_000,
            timeout_ms: 30_000,
            max_path_length: None,
        }
    }
}

impl PathLimits {
    /// Create custom limits (validates ranges)
    pub fn new(
        max_paths: usize,
        max_expansions: usize,
        timeout_ms: u64,
    ) -> Result<Self, String> {
        if max_paths == 0 {
            return Err("max_paths must be > 0".to_string());
        }
        if max_expansions == 0 {
            return Err("max_expansions must be > 0".to_string());
        }
        if timeout_ms == 0 {
            return Err("timeout_ms must be > 0".to_string());
        }

        Ok(Self {
            max_paths,
            max_expansions,
            timeout_ms,
            max_path_length: None,
        })
    }

    /// Set max path length
    pub fn with_max_length(mut self, length: usize) -> Self {
        self.max_path_length = Some(length);
        self
    }

    /// Unlimited (DANGEROUS - only for trusted queries)
    pub fn unlimited() -> Self {
        Self {
            max_paths: usize::MAX,
            max_expansions: usize::MAX,
            timeout_ms: u64::MAX,
            max_path_length: None,
        }
    }
}

/// Builder for NodeSelector
pub struct NodeSelectorBuilder;

impl NodeSelectorBuilder {
    /// Select by node ID
    pub fn by_id(id: impl Into<String>) -> NodeSelector {
        NodeSelector::ById(id.into())
    }

    /// Select by fully qualified name
    pub fn by_name(name: impl Into<String>) -> NodeSelector {
        NodeSelector::ByName {
            name: name.into(),
            scope: None,
        }
    }

    /// Select by name with scope
    pub fn by_name_scoped(name: impl Into<String>, scope: impl Into<String>) -> NodeSelector {
        NodeSelector::ByName {
            name: name.into(),
            scope: Some(scope.into()),
        }
    }

    /// Select by kind (TYPE-SAFE)
    pub fn by_kind(kind: NodeKind) -> NodeSelector {
        NodeSelector::ByKind {
            kind,
            filters: Vec::new(),
        }
    }

    /// Select by kind with filters (TYPE-SAFE)
    pub fn by_kind_filtered(kind: NodeKind, filters: Vec<Expr>) -> NodeSelector {
        NodeSelector::ByKind {
            kind,
            filters,
        }
    }

    /// Union of multiple selectors
    pub fn union(selectors: Vec<NodeSelector>) -> NodeSelector {
        NodeSelector::Union(selectors)
    }
}

/// Builder for EdgeSelector
pub struct EdgeSelectorBuilder;

impl EdgeSelectorBuilder {
    /// Select any edge
    pub fn any() -> EdgeSelector {
        EdgeSelector::Any
    }

    /// Select by edge kind (TYPE-SAFE)
    pub fn by_kind(kind: EdgeKind) -> EdgeSelector {
        EdgeSelector::ByKind(kind)
    }

    /// Select by multiple kinds (TYPE-SAFE)
    pub fn by_kinds(kinds: Vec<EdgeKind>) -> EdgeSelector {
        EdgeSelector::ByKinds(kinds)
    }

    /// Select by filter expression
    pub fn by_filter(filters: Vec<Expr>) -> EdgeSelector {
        EdgeSelector::ByFilter(filters)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_node_selector_by_id() {
        let selector = NodeSelectorBuilder::by_id("node123");
        assert_eq!(selector, NodeSelector::ById("node123".to_string()));
    }

    #[test]
    fn test_node_selector_by_name() {
        let selector = NodeSelectorBuilder::by_name("main");
        match selector {
            NodeSelector::ByName { name, scope } => {
                assert_eq!(name, "main");
                assert_eq!(scope, None);
            }
            _ => panic!("Expected ByName"),
        }
    }

    #[test]
    fn test_node_selector_by_name_scoped() {
        let selector = NodeSelectorBuilder::by_name_scoped("main", "src/main.rs");
        match selector {
            NodeSelector::ByName { name, scope } => {
                assert_eq!(name, "main");
                assert_eq!(scope, Some("src/main.rs".to_string()));
            }
            _ => panic!("Expected ByName with scope"),
        }
    }

    #[test]
    fn test_node_selector_by_kind() {
        let selector = NodeSelectorBuilder::by_kind(NodeKind::Function);
        match selector {
            NodeSelector::ByKind { kind, filters } => {
                assert_eq!(kind, NodeKind::Function);
                assert!(filters.is_empty());
            }
            _ => panic!("Expected ByKind"),
        }
    }

    #[test]
    fn test_edge_selector_any() {
        let selector = EdgeSelectorBuilder::any();
        assert_eq!(selector, EdgeSelector::Any);
    }

    #[test]
    fn test_edge_selector_by_kind() {
        let selector = EdgeSelectorBuilder::by_kind(EdgeKind::Calls);
        assert_eq!(selector, EdgeSelector::ByKind(EdgeKind::Calls));
    }

    #[test]
    fn test_path_limits_default() {
        let limits = PathLimits::default();
        assert_eq!(limits.max_paths, 100);
        assert_eq!(limits.max_expansions, 10_000);
        assert_eq!(limits.timeout_ms, 30_000);
        assert_eq!(limits.max_path_length, None);
    }

    #[test]
    fn test_path_limits_custom() {
        let limits = PathLimits::new(1000, 50_000, 60_000).unwrap();
        assert_eq!(limits.max_paths, 1000);
        assert_eq!(limits.max_expansions, 50_000);
        assert_eq!(limits.timeout_ms, 60_000);
    }

    #[test]
    fn test_path_limits_validation() {
        assert!(PathLimits::new(0, 1000, 1000).is_err());
        assert!(PathLimits::new(100, 0, 1000).is_err());
        assert!(PathLimits::new(100, 1000, 0).is_err());
    }

    #[test]
    fn test_path_limits_with_max_length() {
        let limits = PathLimits::default().with_max_length(50);
        assert_eq!(limits.max_path_length, Some(50));
    }

    #[test]
    fn test_path_limits_unlimited() {
        let limits = PathLimits::unlimited();
        assert_eq!(limits.max_paths, usize::MAX);
        assert_eq!(limits.max_expansions, usize::MAX);
    }

    #[test]
    fn test_selector_serialization() {
        let selector = NodeSelectorBuilder::by_id("test123");
        let json = serde_json::to_string(&selector).unwrap();
        assert!(json.contains("test123"));

        let deserialized: NodeSelector = serde_json::from_str(&json).unwrap();
        assert_eq!(selector, deserialized);
    }

    #[test]
    fn test_limits_serialization() {
        let limits = PathLimits::default();
        let json = serde_json::to_string(&limits).unwrap();

        let deserialized: PathLimits = serde_json::from_str(&json).unwrap();
        assert_eq!(limits, deserialized);
    }
}
