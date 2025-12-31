/*
 * Typestate Application Layer
 *
 * Analyzers and use cases for typestate protocol analysis.
 */

mod analyzer;
mod path_sensitive;
mod type_narrowing_integration;

pub use analyzer::{
    AnalysisStats, ProgramPoint, SimpleBlock, Statement, TypestateAnalyzer, TypestateConfig,
    TypestateResult,
};

pub use path_sensitive::{BranchId, MergedState, PathSensitiveTypestateAnalyzer};

pub use type_narrowing_integration::{
    CombinedAnalysisResult, CombinedStats, CombinedTypeAnalyzer, TypeNarrowingViolation,
};
