//! Error types for the codegraph-ir crate
//!
//! SOTA: Unified error handling across all features with PyO3 integration.
//!
//! Features:
//! - Categorized error kinds matching L1-L6 pipeline stages
//! - Optional file path and line context
//! - Source error chaining
//! - PyO3 automatic conversion to Python exceptions

use std::fmt;

/// Error kind categorization
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    /// Parsing errors (L1)
    Parse,
    /// IR generation errors (L2)
    IRGeneration,
    /// Flow analysis errors (L3)
    FlowAnalysis,
    /// Type resolution errors (L3)
    TypeResolution,
    /// Data flow errors (L4)
    DataFlow,
    /// SSA construction errors (L5)
    SSA,
    /// PDG construction errors
    PDG,
    /// Taint analysis errors
    TaintAnalysis,
    /// Slicing errors
    Slicing,
    /// Configuration errors
    Config,
    /// IO errors
    IO,
    /// Storage errors (database, serialization)
    Storage,
    /// Internal errors (bugs)
    Internal,
}

impl ErrorKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            ErrorKind::Parse => "parse",
            ErrorKind::IRGeneration => "ir_generation",
            ErrorKind::FlowAnalysis => "flow_analysis",
            ErrorKind::TypeResolution => "type_resolution",
            ErrorKind::DataFlow => "data_flow",
            ErrorKind::SSA => "ssa",
            ErrorKind::PDG => "pdg",
            ErrorKind::TaintAnalysis => "taint_analysis",
            ErrorKind::Slicing => "slicing",
            ErrorKind::Config => "config",
            ErrorKind::IO => "io",
            ErrorKind::Storage => "storage",
            ErrorKind::Internal => "internal",
        }
    }
}

/// Unified error type
#[derive(Debug)]
pub struct CodegraphError {
    pub kind: ErrorKind,
    pub message: String,
    pub file_path: Option<String>,
    pub line: Option<u32>,
    pub source: Option<Box<dyn std::error::Error + Send + Sync>>,
}

impl CodegraphError {
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
            file_path: None,
            line: None,
            source: None,
        }
    }

    pub fn with_file(mut self, file_path: impl Into<String>) -> Self {
        self.file_path = Some(file_path.into());
        self
    }

    pub fn with_line(mut self, line: u32) -> Self {
        self.line = Some(line);
        self
    }

    pub fn with_source(mut self, source: impl std::error::Error + Send + Sync + 'static) -> Self {
        self.source = Some(Box::new(source));
        self
    }

    // Convenience constructors
    pub fn parse(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Parse, message)
    }

    pub fn ir_generation(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::IRGeneration, message)
    }

    pub fn flow_analysis(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::FlowAnalysis, message)
    }

    pub fn type_resolution(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::TypeResolution, message)
    }

    pub fn data_flow(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::DataFlow, message)
    }

    pub fn ssa(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::SSA, message)
    }

    pub fn storage(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Storage, message)
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Internal, message)
    }
}

impl fmt::Display for CodegraphError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}] {}", self.kind.as_str(), self.message)?;
        if let Some(ref file) = self.file_path {
            write!(f, " in {}", file)?;
            if let Some(line) = self.line {
                write!(f, ":{}", line)?;
            }
        }
        Ok(())
    }
}

impl std::error::Error for CodegraphError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        self.source
            .as_ref()
            .map(|e| e.as_ref() as &(dyn std::error::Error + 'static))
    }
}

/// Result type alias
pub type Result<T> = std::result::Result<T, CodegraphError>;

// PyO3 integration (only when python feature is enabled)
#[cfg(feature = "python")]
impl From<pyo3::PyErr> for CodegraphError {
    fn from(err: pyo3::PyErr) -> Self {
        CodegraphError::parse(format!("Python error: {}", err))
    }
}

// Storage Backend Error Conversions (PostgreSQL)
impl From<sqlx::Error> for CodegraphError {
    fn from(err: sqlx::Error) -> Self {
        CodegraphError::storage(format!("Database error: {}", err)).with_source(err)
    }
}

impl From<serde_json::Error> for CodegraphError {
    fn from(err: serde_json::Error) -> Self {
        CodegraphError::storage(format!("JSON serialization error: {}", err)).with_source(err)
    }
}

// SQLite Error Conversion
#[cfg(feature = "sqlite")]
impl From<rusqlite::Error> for CodegraphError {
    fn from(err: rusqlite::Error) -> Self {
        CodegraphError::storage(format!("SQLite error: {}", err)).with_source(err)
    }
}

// Mutex Poison Error (for Arc<Mutex<Connection>>)
#[cfg(feature = "sqlite")]
impl<T> From<std::sync::PoisonError<T>> for CodegraphError {
    fn from(_err: std::sync::PoisonError<T>) -> Self {
        CodegraphError::internal("Mutex poisoned")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = CodegraphError::parse("unexpected token")
            .with_file("test.py")
            .with_line(42);

        let msg = format!("{}", err);
        assert!(msg.contains("parse"));
        assert!(msg.contains("unexpected token"));
        assert!(msg.contains("test.py"));
        assert!(msg.contains("42"));
    }
}
