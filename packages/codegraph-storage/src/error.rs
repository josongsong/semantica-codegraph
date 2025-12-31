//! Error types for codegraph-storage

use std::fmt;
use thiserror::Error;

/// Storage error kinds
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    /// Database errors (SQLite, PostgreSQL)
    Database,
    /// Serialization/deserialization errors
    Serialization,
    /// Snapshot not found
    SnapshotNotFound,
    /// Repository not found
    RepositoryNotFound,
    /// Chunk not found
    ChunkNotFound,
    /// Transaction errors
    Transaction,
    /// Configuration errors
    Config,
    /// I/O errors
    IO,
}

impl ErrorKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            ErrorKind::Database => "database",
            ErrorKind::Serialization => "serialization",
            ErrorKind::SnapshotNotFound => "snapshot_not_found",
            ErrorKind::RepositoryNotFound => "repository_not_found",
            ErrorKind::ChunkNotFound => "chunk_not_found",
            ErrorKind::Transaction => "transaction",
            ErrorKind::Config => "config",
            ErrorKind::IO => "io",
        }
    }
}

impl fmt::Display for ErrorKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Storage error type
#[derive(Debug, Error)]
#[error("[{kind}] {message}")]
pub struct StorageError {
    #[source]
    pub source: Option<Box<dyn std::error::Error + Send + Sync>>,
    pub kind: ErrorKind,
    pub message: String,
}

impl StorageError {
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
            source: None,
        }
    }

    pub fn with_source(mut self, source: impl std::error::Error + Send + Sync + 'static) -> Self {
        self.source = Some(Box::new(source));
        self
    }

    // Convenience constructors
    pub fn database(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Database, message)
    }

    pub fn serialization(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Serialization, message)
    }

    pub fn snapshot_not_found(snapshot_id: impl Into<String>) -> Self {
        Self::new(
            ErrorKind::SnapshotNotFound,
            format!("Snapshot not found: {}", snapshot_id.into()),
        )
    }

    pub fn repository_not_found(repo_id: impl Into<String>) -> Self {
        Self::new(
            ErrorKind::RepositoryNotFound,
            format!("Repository not found: {}", repo_id.into()),
        )
    }

    pub fn transaction(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Transaction, message)
    }
}

// SQLite error conversions
#[cfg(feature = "sqlite")]
impl From<rusqlite::Error> for StorageError {
    fn from(err: rusqlite::Error) -> Self {
        StorageError::database(format!("SQLite error: {}", err)).with_source(err)
    }
}

// JSON error conversions
impl From<serde_json::Error> for StorageError {
    fn from(err: serde_json::Error) -> Self {
        StorageError::serialization(format!("JSON error: {}", err)).with_source(err)
    }
}

/// Result type alias
pub type Result<T> = std::result::Result<T, StorageError>;

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    // ═══════════════════════════════════════════════════════════════════════
    // Error Construction Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_error_display() {
        let err = StorageError::snapshot_not_found("abc123def");
        let msg = format!("{}", err);
        assert!(msg.contains("snapshot_not_found"));
        assert!(msg.contains("abc123def"));
    }

    #[test]
    fn test_database_error() {
        let err = StorageError::database("Connection failed");
        assert_eq!(err.kind, ErrorKind::Database);
        assert_eq!(err.message, "Connection failed");
        assert!(err.source.is_none());

        let msg = format!("{}", err);
        assert_eq!(msg, "[database] Connection failed");
    }

    #[test]
    fn test_serialization_error() {
        let err = StorageError::serialization("Invalid JSON");
        assert_eq!(err.kind, ErrorKind::Serialization);
        assert_eq!(err.message, "Invalid JSON");

        let msg = format!("{}", err);
        assert_eq!(msg, "[serialization] Invalid JSON");
    }

    #[test]
    fn test_snapshot_not_found() {
        let err = StorageError::snapshot_not_found("abc123def");
        assert_eq!(err.kind, ErrorKind::SnapshotNotFound);
        assert!(err.message.contains("abc123def"));

        let msg = format!("{}", err);
        assert!(msg.contains("[snapshot_not_found]"));
        assert!(msg.contains("abc123def"));
    }

    #[test]
    fn test_repository_not_found() {
        let err = StorageError::repository_not_found("my-repo");
        assert_eq!(err.kind, ErrorKind::RepositoryNotFound);
        assert!(err.message.contains("my-repo"));

        let msg = format!("{}", err);
        assert!(msg.contains("[repository_not_found]"));
        assert!(msg.contains("my-repo"));
    }

    #[test]
    fn test_transaction_error() {
        let err = StorageError::transaction("ROLLBACK failed");
        assert_eq!(err.kind, ErrorKind::Transaction);
        assert_eq!(err.message, "ROLLBACK failed");

        let msg = format!("{}", err);
        assert_eq!(msg, "[transaction] ROLLBACK failed");
    }

    #[test]
    fn test_with_source() {
        use std::io;

        let io_err = io::Error::new(io::ErrorKind::NotFound, "file not found");
        let err = StorageError::database("DB file missing").with_source(io_err);

        assert_eq!(err.kind, ErrorKind::Database);
        assert!(err.source.is_some());

        // Test error source chain
        let source = err.source().unwrap();
        assert!(source.to_string().contains("file not found"));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ErrorKind Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_error_kind_as_str() {
        assert_eq!(ErrorKind::Database.as_str(), "database");
        assert_eq!(ErrorKind::Serialization.as_str(), "serialization");
        assert_eq!(ErrorKind::SnapshotNotFound.as_str(), "snapshot_not_found");
        assert_eq!(
            ErrorKind::RepositoryNotFound.as_str(),
            "repository_not_found"
        );
        assert_eq!(ErrorKind::ChunkNotFound.as_str(), "chunk_not_found");
        assert_eq!(ErrorKind::Transaction.as_str(), "transaction");
        assert_eq!(ErrorKind::Config.as_str(), "config");
        assert_eq!(ErrorKind::IO.as_str(), "io");
    }

    #[test]
    fn test_error_kind_equality() {
        assert_eq!(ErrorKind::Database, ErrorKind::Database);
        assert_ne!(ErrorKind::Database, ErrorKind::Serialization);
    }

    #[test]
    fn test_error_kind_clone() {
        let kind = ErrorKind::Database;
        let cloned = kind;
        assert_eq!(kind, cloned);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Conversion Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[cfg(feature = "sqlite")]
    #[test]
    fn test_from_rusqlite_error() {
        use rusqlite::Error as SqliteError;

        let sqlite_err = SqliteError::QueryReturnedNoRows;
        let err: StorageError = sqlite_err.into();

        assert_eq!(err.kind, ErrorKind::Database);
        assert!(err.message.contains("SQLite error"));
        assert!(err.source.is_some());
    }

    #[test]
    fn test_from_serde_json_error() {
        use serde_json;

        // Create invalid JSON parse error
        let json_err = serde_json::from_str::<serde_json::Value>("invalid json")
            .err()
            .unwrap();
        let err: StorageError = json_err.into();

        assert_eq!(err.kind, ErrorKind::Serialization);
        assert!(err.message.contains("JSON error"));
        assert!(err.source.is_some());
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Result Type Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_result_ok() {
        let result: Result<i32> = Ok(42);
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), 42);
    }

    #[test]
    fn test_result_err() {
        let result: Result<i32> = Err(StorageError::database("test"));
        assert!(result.is_err());

        let err = result.unwrap_err();
        assert_eq!(err.kind, ErrorKind::Database);
    }

    #[test]
    fn test_result_propagation() {
        fn inner() -> Result<()> {
            Err(StorageError::snapshot_not_found("test"))
        }

        fn outer() -> Result<()> {
            inner()?;
            Ok(())
        }

        let result = outer();
        assert!(result.is_err());

        let err = result.unwrap_err();
        assert_eq!(err.kind, ErrorKind::SnapshotNotFound);
    }
}
