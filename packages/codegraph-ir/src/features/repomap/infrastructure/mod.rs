//! Infrastructure - External implementation details
//!
//! Contains concrete implementations of RepoMap features:
//! - Tree Builder: Parallel construction of RepoMap tree from chunks
//! - PageRank Engine: Importance scoring algorithms (PageRank, HITS, PPR)
//! - Context Provider: Multi-source context aggregation for PPR
//!
//! Note: Git history analysis is in `features::git_history` module

pub mod context_provider;
pub mod pagerank;
pub mod tree_builder;

pub use context_provider::{ContextProviderRegistry, StaticContextProvider};
pub use pagerank::{
    GraphDocument, GraphEdge, GraphNode, ImportanceScore, PageRankEngine, PageRankSettings,
};
pub use tree_builder::RepoMapTreeBuilder;

// Git history: Use crate::features::git_history instead
// Incremental builder: Deferred to v3.0 (Merkle-based updates)
