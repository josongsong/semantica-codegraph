// Domain: QueryEngine DSL - Pure domain logic
// Maps to: packages/codegraph-engine/.../code_foundation/domain/query/

pub mod edge_selector;
pub mod expressions;
pub mod factories;
pub mod node_selector;
pub mod operators;

// Re-export for public API
pub use edge_selector::{EdgeSelector, EdgeType, EdgeTypeSet};
pub use expressions::{FlowExpr, PathPredicate, PathQuery, PathResult, TraversalDirection};
pub use factories::{E, Q};
pub use node_selector::{NodeSelector, NodeSelectorType, SelectorValue};
pub use operators::{NodeSelectorIntersection, NodeSelectorUnion};
