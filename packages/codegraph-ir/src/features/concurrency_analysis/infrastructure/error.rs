/// Concurrency analysis errors
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ConcurrencyError {
    #[error("Function not found: {0}")]
    FunctionNotFound(String),

    #[error("Function is not async: {0}")]
    NotAsyncFunction(String),

    #[error("Invalid IR document: {0}")]
    InvalidIR(String),

    #[error("Analysis failed: {0}")]
    AnalysisFailed(String),
}

pub type Result<T> = std::result::Result<T, ConcurrencyError>;
