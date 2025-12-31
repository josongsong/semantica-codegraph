use thiserror::Error;

pub type Result<T> = std::result::Result<T, OrchestratorError>;

#[derive(Error, Debug)]
pub enum OrchestratorError {
    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("Invalid state transition: {from} -> {to}")]
    InvalidStateTransition { from: String, to: String },

    #[error("Job not found: {0}")]
    JobNotFound(String),

    #[error("Stage not found: {0}")]
    StageNotFound(String),

    #[error("Checkpoint not found: {0}")]
    CheckpointNotFound(String),

    #[error("DAG cycle detected")]
    DagCycleDetected,

    #[error("Missing dependency: {0}")]
    MissingDependency(String),

    #[error("Stage execution failed: {0}")]
    StageExecutionFailed(String),

    #[error("Timeout: {0}")]
    Timeout(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Bincode error: {0}")]
    Bincode(#[from] Box<bincode::ErrorKind>),

    #[error("Parse error: {0}")]
    Parse(String),

    #[error("Configuration error: {0}")]
    Config(String),

    #[error(transparent)]
    Other(#[from] anyhow::Error),
}

impl OrchestratorError {
    pub fn serialization<E: std::fmt::Display>(e: E) -> Self {
        Self::Serialization(e.to_string())
    }

    pub fn parse<E: std::fmt::Display>(e: E) -> Self {
        Self::Parse(e.to_string())
    }

    pub fn config<E: std::fmt::Display>(e: E) -> Self {
        Self::Config(e.to_string())
    }
}

/// Error category for retry logic (from semantica-task-engine)
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum ErrorCategory {
    /// Transient error - retry automatically (e.g., timeout, connection)
    Transient,
    /// Permanent error - don't retry (e.g., invalid input, parse error)
    Permanent,
    /// Infrastructure error - alert ops (e.g., OOM, disk full)
    Infrastructure,
}

impl ErrorCategory {
    pub fn as_str(&self) -> &'static str {
        match self {
            ErrorCategory::Transient => "transient",
            ErrorCategory::Permanent => "permanent",
            ErrorCategory::Infrastructure => "infrastructure",
        }
    }

    pub fn from_str(s: &str) -> Result<Self> {
        match s {
            "transient" => Ok(ErrorCategory::Transient),
            "permanent" => Ok(ErrorCategory::Permanent),
            "infrastructure" => Ok(ErrorCategory::Infrastructure),
            _ => Err(OrchestratorError::parse(format!(
                "Invalid error category: {}",
                s
            ))),
        }
    }
}

impl std::fmt::Display for ErrorCategory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_category_roundtrip() {
        for category in &[
            ErrorCategory::Transient,
            ErrorCategory::Permanent,
            ErrorCategory::Infrastructure,
        ] {
            let s = category.as_str();
            let parsed = ErrorCategory::from_str(s).unwrap();
            assert_eq!(*category, parsed);
        }
    }

    #[test]
    fn test_error_category_invalid() {
        assert!(ErrorCategory::from_str("invalid").is_err());
    }
}
