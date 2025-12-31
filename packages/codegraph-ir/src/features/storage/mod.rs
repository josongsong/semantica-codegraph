//! Storage Backend (SOTA 2025)
//!
//! RFC-074: Multi-Repository Persistent Storage
//! RFC-100: CodeSnapshotStore (Commit-based API)
//!
//! # Hexagonal Architecture
//! ```text
//! External (Pipeline/Adapters)
//!           ↓
//! application/ (UseCase)
//!           ↓
//! api/ (High-level snapshot API)
//!           ↓
//! domain/ (entities, ports)
//!           ↓
//! infrastructure/ (PostgreSQL, SQLite)
//! ```

pub mod api; // RFC-100: High-level snapshot API
pub mod application; // UseCase layer
pub mod domain; // RFC-074: Core domain models & ports
pub mod infrastructure; // RFC-074: PostgreSQL adapter

// Re-export application layer
pub use application::{StorageUseCase, StorageUseCaseImpl};

// High-level API (RFC-100)
pub use api::{CodeSnapshotStore, SnapshotDiff, SnapshotStats};

// Low-level API (RFC-074)
pub use domain::{
    Chunk, ChunkFilter, ChunkId, ChunkKind, ChunkStore, Dependency, DependencyType,
    IncrementalUpdateResult, RepoId, Repository, Snapshot, SnapshotId, StorageStats,
    SymbolVisibility,
};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{InMemoryChunkStore, SqliteChunkStore};

// PostgreSQL adapter (production) - Temporarily disabled
// #[doc(hidden)]
// pub use infrastructure::PostgresChunkStore;
