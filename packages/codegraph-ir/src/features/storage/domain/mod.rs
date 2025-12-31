//! Storage Domain Layer
//!
//! Port/Adapter pattern for storage backend abstraction

pub mod models;
pub mod ports;

pub use models::{
    Chunk, ChunkId, ChunkKind, Dependency, DependencyType, RepoId, Repository, Snapshot,
    SnapshotId, SymbolVisibility,
};
pub use ports::{ChunkFilter, ChunkStore, IncrementalUpdateResult, StorageStats};
