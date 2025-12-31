//! Stub Executors for L4-L37
//!
//! These are placeholder implementations that will be completed later.
//! They validate dependencies and pass through successfully.

use super::base::{StageExecutor, StageResult};
use super::context::PipelineContext;
use crate::pipeline::dag::StageId;
use crate::shared::models::CodegraphError;
use std::time::Instant;

/// Macro to generate stub executors
macro_rules! stub_executor {
    ($name:ident, $stage:expr, $deps:expr) => {
        pub struct $name;

        impl $name {
            pub fn new() -> Self {
                Self
            }
        }

        impl StageExecutor for $name {
            fn stage_id(&self) -> StageId {
                $stage
            }

            fn execute(
                &self,
                context: &mut PipelineContext,
            ) -> Result<StageResult, CodegraphError> {
                let start = Instant::now();
                eprintln!("[{}] Stub execution", self.name());

                // Validate dependencies
                for dep in self.dependencies() {
                    if !context.is_completed(dep) {
                        return Err(CodegraphError::internal(format!(
                            "Dependency {:?} not completed",
                            dep
                        )));
                    }
                }

                let duration = start.elapsed();
                Ok(StageResult::success($stage, duration, 0))
            }

            fn dependencies(&self) -> Vec<StageId> {
                $deps
            }
        }
    };
}

// L4-L5: Basic stages
stub_executor!(
    OccurrencesExecutor,
    StageId::L4Occurrences,
    vec![StageId::L1IrBuild]
);

stub_executor!(
    SymbolsExecutor,
    StageId::L5Symbols,
    vec![StageId::L1IrBuild]
);

// L6-L9: Advanced analysis
stub_executor!(
    PointsToExecutor,
    StageId::L6PointsTo,
    vec![StageId::L1IrBuild, StageId::L3CrossFile]
);

// L10: Clone Detection
stub_executor!(
    CloneDetectionExecutor,
    StageId::L10CloneDetection,
    vec![StageId::L1IrBuild, StageId::L2Chunking]
);

// L13: Effect Analysis
stub_executor!(
    EffectAnalysisExecutor,
    StageId::L13EffectAnalysis,
    vec![StageId::L1IrBuild]
);

// L14: Taint Analysis (IMPORTANT!)
stub_executor!(
    TaintAnalysisExecutor,
    StageId::L14TaintAnalysis,
    vec![StageId::L1IrBuild, StageId::L3CrossFile]
);

// L15: Cost Analysis
stub_executor!(
    CostAnalysisExecutor,
    StageId::L15CostAnalysis,
    vec![StageId::L1IrBuild]
);

// L16: RepoMap
stub_executor!(
    RepoMapExecutor,
    StageId::L16RepoMap,
    vec![StageId::L1IrBuild, StageId::L2Chunking]
);

// L18: Concurrency Analysis
stub_executor!(
    ConcurrencyAnalysisExecutor,
    StageId::L18ConcurrencyAnalysis,
    vec![StageId::L1IrBuild]
);

// L21: SMT Verification
stub_executor!(
    SmtVerificationExecutor,
    StageId::L21SmtVerification,
    vec![StageId::L1IrBuild]
);

// L2.5: Lexical Index
stub_executor!(
    LexicalExecutor,
    StageId::L2_5Lexical,
    vec![StageId::L1IrBuild, StageId::L2Chunking]
);

// L33: Git History
stub_executor!(
    GitHistoryExecutor,
    StageId::L33GitHistory,
    vec![StageId::L1IrBuild]
);

// L37: Query Engine
stub_executor!(
    QueryEngineExecutor,
    StageId::L37QueryEngine,
    vec![StageId::L1IrBuild, StageId::L2Chunking]
);
