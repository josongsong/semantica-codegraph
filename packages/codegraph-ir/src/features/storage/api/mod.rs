//! Storage API Layer - RFC-100 CodeSnapshotStore
//!
//! High-level API wrapping the low-level ChunkStore trait.
//!
//! This module provides the RFC-100 CodeSnapshotStore interface:
//! - File-level replace primitive (commit-based)
//! - Incremental snapshot creation
//! - Commit comparison (semantic diff)
//!
//! # Example
//!
//! ```rust,no_run
//! use codegraph_ir::features::storage::api::CodeSnapshotStore;
//! use codegraph_ir::features::storage::infrastructure::SqliteChunkStore;
//!
//! # async fn example() -> Result<(), Box<dyn std::error::Error>> {
//! let store = SqliteChunkStore::new("codegraph.db")?;
//! let snapshot_store = CodeSnapshotStore::new(store);
//!
//! // Replace a file in new commit
//! snapshot_store.replace_file(
//!     "my-repo",
//!     "main",           // base commit
//!     "feature/auth",   // new commit
//!     "src/auth.py",
//!     vec![],          // new chunks
//!     vec![],          // new dependencies
//! ).await?;
//! # Ok(())
//! # }
//! ```

pub mod snapshot_diff;
pub mod snapshot_store;

pub use snapshot_diff::{SnapshotDiff, SnapshotStats};
pub use snapshot_store::CodeSnapshotStore;
