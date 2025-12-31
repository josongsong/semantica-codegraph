//! Error types for cache system

use thiserror::Error;

#[derive(Error, Debug)]
pub enum CacheError {
    #[error("Cache corrupted: {0}")]
    Corrupted(String),

    #[error("Cache version mismatch: found {found}, expected {expected}")]
    VersionMismatch { found: String, expected: String },

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("Deserialization error: {0}")]
    Deserialization(String),

    #[error("Disk full")]
    DiskFull,

    #[error("Permission denied: {0}")]
    PermissionDenied(String),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Invalid fingerprint: {0}")]
    InvalidFingerprint(String),

    #[error("Dependency cycle detected")]
    DependencyCycle,

    #[error("Cache not found")]
    NotFound,

    #[error("Internal error: {0}")]
    Internal(String),

    #[error("Other error: {0}")]
    Other(String),
}

pub type CacheResult<T> = Result<T, CacheError>;
