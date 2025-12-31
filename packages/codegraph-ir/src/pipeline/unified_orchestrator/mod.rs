//! Unified Pipeline & Index Orchestrator
//!
//! Single orchestrator combining:
//! - DAG-based pipeline execution (L1-L37)
//! - MVCC transaction management
//! - Multi-layer index orchestration
//! - Arc-based zero-copy memory sharing
//!
//! See RFC-UNIFIED-ORCHESTRATOR-001 for full architecture.

pub mod core;
pub mod executors;
pub mod memory;
pub mod pipeline_state;

pub use core::{UnifiedOrchestrator, UnifiedOrchestratorConfig};
pub use executors::StageExecutor;
pub use memory::{GraphContext, ContextHandle};
pub use pipeline_state::{PipelineState, IndexingStats};
