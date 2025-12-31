//! Stage Executors
//!
//! Each pipeline stage (L1-L37) implements the StageExecutor trait.

pub mod base;
pub mod context;
pub mod l1_ir_build;
pub mod l2_chunking;
pub mod l3_cross_file;
pub mod stubs;

pub use base::{StageExecutor, StageResult, MetricValue, BoxedExecutor};
pub use context::PipelineContext;

// Re-export core executors (L1-L3)
pub use l1_ir_build::IRBuildExecutor;
pub use l2_chunking::ChunkingExecutor;
pub use l3_cross_file::CrossFileExecutor;

// Re-export stub executors (L4-L37)
pub use stubs::{
    OccurrencesExecutor,
    SymbolsExecutor,
    PointsToExecutor,
    CloneDetectionExecutor,
    EffectAnalysisExecutor,
    TaintAnalysisExecutor,
    CostAnalysisExecutor,
    RepoMapExecutor,
    ConcurrencyAnalysisExecutor,
    SmtVerificationExecutor,
    LexicalExecutor,
    GitHistoryExecutor,
    QueryEngineExecutor,
};
