// Multi-Layer Incremental Indexing (RFC-072)
//
// # Non-Negotiable Design Principles
// This module implements RFC-072 with 6 immutable contracts:
//
// 1. TxnWatermark Consistency: applied_up_to() for consistency, health() for observation
// 2. Embed Unit: Function signature + docstring (NOT body)
// 3. Propagation Rules: Signature changes only, MAX_IMPACT_DEPTH = 2
// 4. Virtual Layer: Overlay + merge-on-read (NO snapshot clone)
// 5. WAL Responsibility: Txn WAL authoritative, Index WAL auxiliary
// 6. UpdateStrategy Semantics: Sync blocks, Async/Full background, Lazy query-time

pub mod application;
pub mod config;
pub mod domain;
pub mod infrastructure;
pub mod ports;

pub use ports::{
    ChangeScope, DeltaAnalysis, ExpandedScope, HashComparison, IndexError, IndexHealth,
    IndexImpact, IndexPlugin, IndexStats, IndexType, QueryType, Region, UpdateStrategy,
};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{
    ChangeAnalyzer, IndexOrchestratorConfig, MultiLayerIndexOrchestrator, OrchestratorHealth,
    VirtualLayer,
};
