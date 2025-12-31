//! RepoMap - Repository Structure Mapping
//!
//! Builds a hierarchical map of repository structure with importance scoring.
//!
//! # Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────┐
//! │                    RepoMap Feature                      │
//! ├─────────────────────────────────────────────────────────┤
//! │  Domain:                                                │
//! │    - RepoMapNode (tree structure)                       │
//! │    - Metrics (LOC, complexity, importance)              │
//! │    - RepoMapSnapshot (versioned state)                  │
//! ├─────────────────────────────────────────────────────────┤
//! │  Infrastructure:                                        │
//! │    - TreeBuilder (Chunk → RepoMapNode, parallel)        │
//! │    - PageRankEngine (SOTA: PPR + HITS + Combined)       │
//! │    - GitHistoryAnalyzer (Change frequency, Churn)       │
//! │    - IncrementalBuilder (Merkle Hash, O(delta))         │
//! │    - Storage (JSON, InMemory, PostgreSQL)               │
//! └─────────────────────────────────────────────────────────┘
//! ```
//!
//! # Features
//!
//! - **Parallel Tree Building**: Rayon work-stealing, DashMap lock-free
//! - **SOTA PageRank**: Personalized PageRank + HITS + Combined scoring
//! - **Incremental Updates**: Merkle Hash based O(delta) complexity
//! - **Git Integration**: Change frequency, Code Churn, Hot Spot detection
//! - **Multi-storage**: JSON (dev), InMemory (test), PostgreSQL (prod)

pub mod application; // UseCase layer
pub mod domain;
pub mod infrastructure;
pub mod ports;

// Re-export application layer (primary interface)
pub use application::{RepoMapInput, RepoMapOutput, RepoMapUseCase, RepoMapUseCaseImpl};

// Re-export domain types
pub use domain::{
    ContextItem, ContextProvider, ContextSet, ContextType, ImportanceWeights, NodeKind,
    RepoMapMetrics, RepoMapNode, RepoMapSnapshot,
};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{
    ContextProviderRegistry, GraphDocument, GraphEdge, GraphNode, ImportanceScore, PageRankEngine,
    PageRankSettings, RepoMapTreeBuilder,
};
pub use ports::RepoMapStorage;
