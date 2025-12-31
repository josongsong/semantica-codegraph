//! Storage Infrastructure Layer
//!
//! Multiple storage backends for ChunkStore trait

pub mod memory_store;
pub use memory_store::InMemoryChunkStore;

#[cfg(feature = "sqlite")]
pub mod sqlite_store;
#[cfg(feature = "sqlite")]
pub use sqlite_store::SqliteChunkStore;

// If sqlite feature disabled, use InMemory as fallback
#[cfg(not(feature = "sqlite"))]
pub type SqliteChunkStore = InMemoryChunkStore;

// Temporarily disabled to avoid sqlx compile-time DB check
// pub mod postgres_store;
// pub use postgres_store::PostgresChunkStore;
