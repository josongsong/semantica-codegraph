//! SOTA Benchmark System - Rust-Only with Ground Truth Regression
//!
//! RFC-002: Comprehensive benchmarking system with:
//! - Ground Truth baseline management
//! - Automatic regression detection (±5% tolerance)
//! - Multi-repo support (small/medium/large)
//! - RFC-CONFIG integration (PipelineConfig + Preset system)
//! - Rich reporting (JSON, Markdown, Terminal, HTML)
//!
//! # Examples
//!
//! ```no_run
//! use codegraph_ir::benchmark::{BenchmarkConfig, Repository, BenchmarkRunner};
//! use codegraph_ir::config::Preset;
//! use std::path::PathBuf;
//!
//! // Simple benchmark with Fast preset
//! let config = BenchmarkConfig::with_preset(Preset::Fast);
//! let repo = Repository::from_path(PathBuf::from("tools/benchmark/repo-test/small/typer")).unwrap();
//! let runner = BenchmarkRunner::new(config, repo);
//! let report = runner.run().unwrap();
//! ```

pub mod config;
pub mod ground_truth;
pub mod report;
pub mod repository;
pub mod result;
pub mod runner;
pub mod validator;

pub use config::{BenchmarkConfig, BenchmarkOptions, Tolerance};
pub use ground_truth::{ExpectedMetrics, GroundTruth, GroundTruthStore, ValidationStatus};
pub use repository::{Language, RepoCategory, Repository};
pub use result::{BenchmarkDiff, BenchmarkResult, PTASummary, RepoMapSummary, TaintSummary};
pub use runner::{BenchmarkReport, BenchmarkRunner};
pub use validator::{GroundTruthValidator, Severity, ValidationResult, Violation};

#[derive(Debug, thiserror::Error)]
pub enum BenchmarkError {
    #[error("Invalid repository: {0}")]
    InvalidRepo(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Serialization error: {0}")]
    Serde(#[from] serde_json::Error),

    #[error("Indexing error: {0}")]
    Indexing(String),

    #[error("Ground truth not found: {0}")]
    GroundTruthNotFound(String),

    #[error("Configuration error: {0}")]
    Config(String),
}

pub type BenchmarkResult2<T> = std::result::Result<T, BenchmarkError>;
