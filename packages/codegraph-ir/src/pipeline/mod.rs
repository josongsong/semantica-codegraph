//! Pipeline orchestration

pub mod config;
pub mod core;
pub mod dag;
pub mod error;
pub mod preprocessors;
pub mod processor; // ✅ Refactored modular processor (Phase 4 complete)
pub mod result;
pub mod sota_pipeline;
pub mod unified_processor; // SOTA: Zero-dependency DAG from task-engine
pub mod unified_orchestrator; // SOTA: Arc-based unified orchestrator (RFC-001 integrated)
                              // pub mod stage_dag;  // REMOVED: Replaced by self-contained DAG
pub mod end_to_end_config;
pub mod end_to_end_orchestrator;
pub mod end_to_end_result;
pub mod orchestrator;
pub mod pagerank_mode_detector;
pub mod stages; // Auto-detect PageRank mode
pub mod usecase_traits; // SOLID D: Dependency Inversion traits
                // pub mod storage_integration;  // RFC-074/RFC-100: Storage Backend Integration (TODO: fix Node/Edge API mismatch)

pub use config::*;
pub use dag::{PipelineDAG, StageId, StageNode, StageState}; // New: Self-contained DAG
pub use end_to_end_config::*;
pub use end_to_end_orchestrator::{E2EOrchestrator, IRIndexingOrchestrator};
pub use end_to_end_result::*;
pub use unified_orchestrator::{UnifiedOrchestrator, UnifiedOrchestratorConfig};
pub use pagerank_mode_detector::{
    configure_smart_mode, detect_mode, AnalysisType, ModeDetectionContext, RecommendedMode,
};
pub use processor::*;
pub use result::ProcessResult;
pub use sota_pipeline::{IRPipelineDAG, SOTAStageControl, SOTAStageId, SOTAStageMetadata};
pub use stages::{IncrementalStages, RepositoryStages, SingleFileStages};
pub use unified_processor::{get_file_category, process_any_file, FileCategory};
// pub use storage_integration::StorageIntegratedOrchestrator;
