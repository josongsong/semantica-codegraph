// Infrastructure: Query execution components

pub mod graph_index;
pub mod incremental_index;
pub mod node_matcher;
pub mod parallel_traversal;
pub mod reachability_cache;
pub mod shadow_fs_orchestrator;
pub mod transaction_index;
pub mod traversal_engine;

pub use graph_index::GraphIndex;
pub use incremental_index::{ChangeSet, IncrementalGraphIndex};
pub use node_matcher::NodeMatcher;
pub use parallel_traversal::ParallelTraversalEngine;
pub use reachability_cache::{CacheStats, ReachabilityCache};
pub use shadow_fs_orchestrator::{
    AgentSession, CacheStrategy, CommitResult, OrchestratorStats, ShadowFSOrchestrator,
};
pub use transaction_index::{ChangeOp, Snapshot, TransactionDelta, TransactionalGraphIndex, TxnId};
pub use traversal_engine::TraversalEngine;
