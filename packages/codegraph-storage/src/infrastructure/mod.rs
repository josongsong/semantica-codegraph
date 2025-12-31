//! Infrastructure layer - Storage adapters
//!
//! RFC-102: SQLite adapter
//! RFC-103: PostgreSQL adapter (future)

#[cfg(feature = "sqlite")]
pub mod sqlite;

#[cfg(feature = "sqlite")]
pub use sqlite::SqliteSnapshotStore;
