/*
 * Differential Analysis Error Handling
 *
 * Provides comprehensive error types for differential taint analysis.
 */

use crate::errors::CodegraphError;
use thiserror::Error;

/// Differential analysis specific errors
#[derive(Debug, Error)]
pub enum DifferentialError {
    /// Analysis failed for base version
    #[error("Base version analysis failed: {0}")]
    BaseAnalysisFailed(String),

    /// Analysis failed for modified version
    #[error("Modified version analysis failed: {0}")]
    ModifiedAnalysisFailed(String),

    /// Version comparison failed
    #[error("Version comparison failed: {0}")]
    ComparisonFailed(String),

    /// Git operation failed
    #[error("Git operation failed: {0}")]
    GitError(String),

    /// Invalid version specification
    #[error("Invalid version: {0}")]
    InvalidVersion(String),

    /// Cache operation failed
    #[error("Cache error: {0}")]
    CacheError(String),

    /// Performance budget exceeded
    #[error("Analysis exceeded time budget: {expected}s, actual: {actual}s")]
    TimeoutExceeded { expected: u64, actual: u64 },

    /// Codegraph error wrapper
    #[error("Codegraph error: {0}")]
    Codegraph(#[from] CodegraphError),
}

impl From<DifferentialError> for CodegraphError {
    fn from(err: DifferentialError) -> Self {
        CodegraphError::Analysis(err.to_string())
    }
}

/// Result type for differential analysis
pub type DifferentialResult<T> = std::result::Result<T, DifferentialError>;

/// Error helpers
impl DifferentialError {
    /// Create base analysis error
    pub fn base_error(msg: impl Into<String>) -> Self {
        Self::BaseAnalysisFailed(msg.into())
    }

    /// Create modified analysis error
    pub fn modified_error(msg: impl Into<String>) -> Self {
        Self::ModifiedAnalysisFailed(msg.into())
    }

    /// Create comparison error
    pub fn comparison_error(msg: impl Into<String>) -> Self {
        Self::ComparisonFailed(msg.into())
    }

    /// Create git error
    pub fn git_error(msg: impl Into<String>) -> Self {
        Self::GitError(msg.into())
    }

    /// Create cache error
    pub fn cache_error(msg: impl Into<String>) -> Self {
        Self::CacheError(msg.into())
    }

    /// Create timeout error
    pub fn timeout(expected: u64, actual: u64) -> Self {
        Self::TimeoutExceeded { expected, actual }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_creation() {
        let err = DifferentialError::base_error("test");
        assert!(err.to_string().contains("Base version"));

        let err = DifferentialError::timeout(60, 120);
        assert!(err.to_string().contains("60s"));
        assert!(err.to_string().contains("120s"));
    }

    #[test]
    fn test_error_conversion() {
        let diff_err = DifferentialError::base_error("test");
        let cg_err: CodegraphError = diff_err.into();
        assert!(matches!(cg_err, CodegraphError::Analysis(_)));
    }
}
