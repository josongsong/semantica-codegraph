// Infrastructure: Multi-layer index implementation

pub mod change_analyzer;
pub mod orchestrator;
pub mod virtual_layer;
pub mod wal; // P1-5: WAL infrastructure

pub use change_analyzer::{ChangeAnalyzer, FourLevelHash, ImpactGraph};
pub use orchestrator::{
    ConsistencyLevel, IndexOrchestratorConfig, IndexUpdateResult, IndexUpdateResults,
    MultiLayerIndexOrchestrator, OrchestratorHealth, Query, QueryResult, SearchResult,
};
pub use virtual_layer::VirtualLayer;
pub use wal::{DurableWAL, IndexOperation, IndexWAL, IndexWalEntry, TransactionWAL, TxnWalEntry};
