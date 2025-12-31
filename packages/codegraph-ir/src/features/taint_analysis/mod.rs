// Taint analysis for security vulnerability detection
//
// Hexagonal Architecture:
// - domain: Core business logic (TaintLevel, FunctionSummary)
// - infrastructure: Technical implementations (analyzers, CFG, etc.)
// - ports: Interface boundaries (Service traits, DTOs)
// - application: Use cases and orchestration

pub mod application;
pub mod domain;
pub mod infrastructure;
pub mod ports;

// Re-export application layer (primary interface)
pub use application::{
    AnalyzeTaintUseCase, DefaultTaintAnalysisService, InMemoryCodeRepository,
    InMemoryResultRepository,
};

// Re-export domain types
pub use domain::{FunctionSummaryCache, FunctionTaintSummary};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::*;
pub use ports::{
    default_config, default_sanitizer_patterns, default_sink_patterns, default_source_patterns,
    fast_config, thorough_config, AnalysisMode, AnalysisStats, BackwardTaintPathDTO,
    CodeRepository, DifferentialResult, DifferentialTaintService, ImplicitFlowDTO,
    TaintAnalysisConfig, TaintAnalysisError, TaintAnalysisRequest, TaintAnalysisResponse,
    TaintAnalysisService, TaintErrorKind, TaintPathDTO, TaintResultRepository,
};
