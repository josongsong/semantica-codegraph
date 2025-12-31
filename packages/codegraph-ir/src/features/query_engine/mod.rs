//! Query Engine Feature - Rust QueryDSL implementation
//!
//! Provides Python-like fluent API with operator overloading.
//!
//! # Hexagonal Architecture
//! ```text
//! External (Pipeline/Adapters)
//!           ↓
//! application/ (UseCase - entry point)
//!           ↓
//! domain/ (entities, expressions)
//!           ↓
//! infrastructure/ (graph index, traversal)
//! ```
//!
//! # Usage
//! ```ignore
//! use crate::features::query_engine::application::{QueryUseCase, QueryUseCaseImpl};
//!
//! let usecase = QueryUseCaseImpl::new();
//! let output = usecase.execute_query(&ir_doc, query);
//! ```

pub mod application; // UseCase layer (entry point)
pub mod domain;
pub mod infrastructure;
pub mod query_engine;

// Re-export application layer (primary interface)
pub use application::{QueryInput, QueryOutput, QueryUseCase, QueryUseCaseImpl};

// Re-export domain types
pub use domain::{
    EdgeSelector, EdgeType, FlowExpr, NodeSelector, NodeSelectorType, PathQuery, PathResult,
    TraversalDirection, E, Q,
};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use query_engine::{QueryEngine, QueryEngineStats};
