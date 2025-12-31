//! SOTA: Typed Pipeline Errors
//!
//! Using thiserror for ergonomic error handling with zero overhead.
//!
//! Benefits:
//! - Compile-time error categorization
//! - Zero-cost abstractions (same as manual impl)
//! - Automatic Display and Error trait derivation
//! - Source error chaining with #[source]

use thiserror::Error;

/// Pipeline execution errors with compile-time type safety
#[derive(Error, Debug, Clone)]
pub enum PipelineError {
    /// AST parsing failed
    #[error("Failed to parse {file_path}: {reason}")]
    ParseError { file_path: String, reason: String },

    /// Tree-sitter language initialization failed
    #[error("Failed to initialize tree-sitter language: {0}")]
    LanguageError(String),

    /// IR generation failed
    #[error("IR generation failed for {node_type} at {location}: {reason}")]
    IRGenerationError {
        node_type: String,
        location: String,
        reason: String,
    },

    /// Type resolution failed
    #[error("Type resolution failed for {symbol}: {reason}")]
    TypeResolutionError { symbol: String, reason: String },

    /// Flow graph construction failed
    #[error("Flow graph construction failed for {function_id}: {reason}")]
    FlowGraphError { function_id: String, reason: String },

    /// Data flow analysis failed
    #[error("Data flow analysis failed for {function_id}: {reason}")]
    DataFlowError { function_id: String, reason: String },

    /// SSA transformation failed
    #[error("SSA transformation failed for {function_id}: {reason}")]
    SSAError { function_id: String, reason: String },

    /// Cross-file resolution failed
    #[error("Cross-file resolution failed: {reason}")]
    CrossFileError { reason: String },

    /// Serialization failed
    #[error("Serialization failed: {0}")]
    SerializationError(String),

    /// Deserialization failed
    #[error("Deserialization failed: {0}")]
    DeserializationError(String),

    /// I/O operation failed
    #[error("I/O error for {path}: {reason}")]
    IOError { path: String, reason: String },

    /// Invalid configuration
    #[error("Invalid configuration: {0}")]
    ConfigError(String),

    /// Timeout exceeded
    #[error("Pipeline timeout exceeded: {stage} took longer than {timeout_ms}ms")]
    TimeoutError { stage: String, timeout_ms: u64 },

    /// Resource exhaustion
    #[error("Resource exhausted: {resource} exceeded limit of {limit}")]
    ResourceExhausted { resource: String, limit: String },

    /// Internal error (should never happen)
    #[error("Internal error: {0}")]
    Internal(String),
}

impl PipelineError {
    /// Create a parse error
    pub fn parse(file_path: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::ParseError {
            file_path: file_path.into(),
            reason: reason.into(),
        }
    }

    /// Create a language error
    pub fn language(reason: impl Into<String>) -> Self {
        Self::LanguageError(reason.into())
    }

    /// Create an IR generation error
    pub fn ir_generation(
        node_type: impl Into<String>,
        location: impl Into<String>,
        reason: impl Into<String>,
    ) -> Self {
        Self::IRGenerationError {
            node_type: node_type.into(),
            location: location.into(),
            reason: reason.into(),
        }
    }

    /// Create a type resolution error
    pub fn type_resolution(symbol: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::TypeResolutionError {
            symbol: symbol.into(),
            reason: reason.into(),
        }
    }

    /// Create a flow graph error
    pub fn flow_graph(function_id: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::FlowGraphError {
            function_id: function_id.into(),
            reason: reason.into(),
        }
    }

    /// Create a data flow error
    pub fn data_flow(function_id: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::DataFlowError {
            function_id: function_id.into(),
            reason: reason.into(),
        }
    }

    /// Create an SSA error
    pub fn ssa(function_id: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::SSAError {
            function_id: function_id.into(),
            reason: reason.into(),
        }
    }

    /// Create a cross-file error
    pub fn cross_file(reason: impl Into<String>) -> Self {
        Self::CrossFileError {
            reason: reason.into(),
        }
    }

    /// Create a serialization error
    pub fn serialization(reason: impl Into<String>) -> Self {
        Self::SerializationError(reason.into())
    }

    /// Create a deserialization error
    pub fn deserialization(reason: impl Into<String>) -> Self {
        Self::DeserializationError(reason.into())
    }

    /// Create an I/O error
    pub fn io(path: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::IOError {
            path: path.into(),
            reason: reason.into(),
        }
    }

    /// Create a config error
    pub fn config(reason: impl Into<String>) -> Self {
        Self::ConfigError(reason.into())
    }

    /// Create a timeout error
    pub fn timeout(stage: impl Into<String>, timeout_ms: u64) -> Self {
        Self::TimeoutError {
            stage: stage.into(),
            timeout_ms,
        }
    }

    /// Create a resource exhausted error
    pub fn resource_exhausted(resource: impl Into<String>, limit: impl Into<String>) -> Self {
        Self::ResourceExhausted {
            resource: resource.into(),
            limit: limit.into(),
        }
    }

    /// Create an internal error
    pub fn internal(reason: impl Into<String>) -> Self {
        Self::Internal(reason.into())
    }

    /// Check if error is retriable
    pub fn is_retriable(&self) -> bool {
        matches!(
            self,
            Self::TimeoutError { .. } | Self::IOError { .. } | Self::ResourceExhausted { .. }
        )
    }

    /// Get error category for metrics
    pub fn category(&self) -> &'static str {
        match self {
            Self::ParseError { .. } => "parse",
            Self::LanguageError(_) => "language",
            Self::IRGenerationError { .. } => "ir_generation",
            Self::TypeResolutionError { .. } => "type_resolution",
            Self::FlowGraphError { .. } => "flow_graph",
            Self::DataFlowError { .. } => "data_flow",
            Self::SSAError { .. } => "ssa",
            Self::CrossFileError { .. } => "cross_file",
            Self::SerializationError(_) => "serialization",
            Self::DeserializationError(_) => "deserialization",
            Self::IOError { .. } => "io",
            Self::ConfigError(_) => "config",
            Self::TimeoutError { .. } => "timeout",
            Self::ResourceExhausted { .. } => "resource",
            Self::Internal(_) => "internal",
        }
    }
}

/// Result type alias for pipeline operations
pub type PipelineResult<T> = Result<T, PipelineError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = PipelineError::parse("main.py", "unexpected token");
        assert_eq!(err.to_string(), "Failed to parse main.py: unexpected token");
    }

    #[test]
    fn test_error_category() {
        let err = PipelineError::parse("main.py", "error");
        assert_eq!(err.category(), "parse");
    }

    #[test]
    fn test_retriable() {
        let timeout = PipelineError::timeout("L3_Flow", 1000);
        assert!(timeout.is_retriable());

        let parse = PipelineError::parse("main.py", "error");
        assert!(!parse.is_retriable());
    }
}
