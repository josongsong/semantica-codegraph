//! Application layer for Points-to Analysis
//!
//! High-level APIs for different use cases:
//! - **PointsToAnalyzer**: Standard analysis (Hybrid/Fast/Precise modes)
//! - **SecurityAnalyzer**: Context-sensitive analysis for security scanning
//! - **RealtimeAnalyzer**: Demand-driven analysis for IDE/real-time queries
//! - **IncrementalAnalyzer**: Incremental analysis for CI/CD and watch mode
//! - **FlowSensitiveAnalyzer**: Flow-sensitive analysis for path-aware queries
//! - **ParallelAnalyzer**: Parallel analysis for large codebases
//! - **NullSafetyAnalyzer**: Null dereference detection

pub mod analyzer;
pub mod null_safety;
pub mod security_analyzer;
pub mod realtime_analyzer;
pub mod incremental_analyzer;
pub mod flow_sensitive_analyzer;
pub mod parallel_analyzer;

// Standard analyzer
pub use analyzer::{AnalysisConfig, AnalysisMode, PointsToAnalyzer};

// Null safety
pub use null_safety::{NullDereferenceError, NullSafetyAnalyzer, NULL_LOCATION};

// Security analysis (Context-Sensitive)
pub use security_analyzer::{SecurityAnalyzer, SecurityStrategy, SecurityAnalysisResult};

// Real-time analysis (Demand-Driven)
pub use realtime_analyzer::{RealtimeAnalyzer, RealtimeQueryResult};

// Incremental analysis (CI/CD)
pub use incremental_analyzer::{IncrementalAnalyzer, IncrementalResult};

// Flow-sensitive analysis (Path-aware)
pub use flow_sensitive_analyzer::{FlowSensitiveAnalyzer, FlowAnalysisResult, FlowPrecision};

// Parallel analysis (Large-scale)
pub use parallel_analyzer::{ParallelAnalyzer, ParallelAnalysisResult, ParallelStrategy};
