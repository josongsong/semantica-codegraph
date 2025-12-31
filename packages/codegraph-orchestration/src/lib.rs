/*
 * Codegraph Orchestration - SOTA Job Orchestration System
 *
 * High-performance, distributed pipeline orchestration for code analysis.
 *
 * Architecture:
 * - Job State Machine (PostgreSQL)
 * - Distributed Locking (Redis)
 * - Checkpoint/Resume System
 * - Pipeline Stages (pluggable)
 * - Observability (metrics, logging)
 *
 * Performance Target: 5-10x faster than Python
 */

// Public modules
pub mod checkpoint;
pub mod dag;
pub mod dependency_graph;
pub mod error;
pub mod incremental;
pub mod job;
pub mod orchestrator;
pub mod pipeline;
pub mod stages;

// Re-exports
pub use checkpoint::{Checkpoint, CheckpointManager};
pub use dag::{CacheKeyManager, PipelineDAG, StageNode};
pub use dependency_graph::{compute_affected_files, FileId, ImportKey, ReverseDependencyIndex};
pub use error::{ErrorCategory, OrchestratorError, Result};
pub use incremental::{IncrementalOrchestrator, IncrementalResult};
pub use job::{Job, JobState, JobStateMachine, StageId};
pub use orchestrator::{PipelineOrchestrator, PipelineResult};
pub use pipeline::{
    StageConfig, StageContext, StageHandler, StageInput, StageMetrics, StageOutput,
};
pub use stages::{
    ChunkResult, ChunkStage, IRResult, IRStage, ImportInfo, LexicalStage, VectorResult, VectorStage,
};

#[cfg(test)]
mod tests {
    #[test]
    fn it_works() {
        assert_eq!(2 + 2, 4);
    }
}
