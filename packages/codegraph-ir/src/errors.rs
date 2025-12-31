//! Error types for codegraph-ir
//!
//! Provides unified error handling across the crate.

use thiserror::Error;

/// Main error type for codegraph-ir operations
#[derive(Debug, Error)]
pub enum CodegraphError {
    /// IO error
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    /// Parse error
    #[error("Parse error: {0}")]
    Parse(String),

    /// Analysis error
    #[error("Analysis error: {0}")]
    Analysis(String),

    /// Pipeline error
    #[error("Pipeline error: {0}")]
    Pipeline(String),

    /// Configuration error
    #[error("Configuration error: {0}")]
    Config(String),
}

impl CodegraphError {
    /// Create a parse error (lowercase)
    pub fn parse_error(msg: impl Into<String>) -> Self {
        CodegraphError::Parse(msg.into())
    }

    /// Create a parse error (Pascal case - for backward compatibility)
    #[allow(non_snake_case)]
    pub fn ParseError(msg: impl Into<String>) -> Self {
        CodegraphError::Parse(msg.into())
    }

    /// Create an internal error (alias for analysis error)
    pub fn internal(msg: impl Into<String>) -> Self {
        CodegraphError::Analysis(msg.into())
    }

    /// Create a configuration error
    pub fn config(msg: impl Into<String>) -> Self {
        CodegraphError::Config(msg.into())
    }
}

/// Result type alias for codegraph operations
pub type Result<T> = std::result::Result<T, CodegraphError>;
