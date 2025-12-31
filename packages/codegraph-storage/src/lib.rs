//! CodeSnapshotStore - RFC-100: Commit-based Persistent Storage
//!
//! > "commit 단위의 코드 스냅샷을 한 번 만들고, 여러 번 안정적으로 활용한다."
//!
//! ## Core Principles
//!
//! 1. **Two-State Rule**: Only Committed state (git commit), NOT Ephemeral (IDE save)
//! 2. **Snapshot Identity**: `snapshot_id = commit_hash` (immutable)
//! 3. **Core Contract**: File-level replace (chunk UPSERT is internal implementation)
//!
//! ## Status
//!
//! - ✅ RFC-100: Core principles defined, storage separated from codegraph-ir
//! - ⏳ RFC-101: API design (replace_file, transaction model)
//! - ⏳ RFC-102: SQLite adapter implementation
//! - ⏳ RFC-103: PostgreSQL adapter
//! - ⏳ RFC-104: Snapshot diff & PR analysis
//! - ⏳ RFC-105: Retention & history policy
//!
//! ## Usage
//!
//! ```rust,ignore
//! use codegraph_storage::{CodeSnapshotStore, Snapshot, Chunk};
//!
//! // 1. Create immutable snapshot (commit-based)
//! let snapshot = Snapshot::new("abc123def", "my-repo");
//! store.save_snapshot(&snapshot).await?;
//!
//! // 2. Save chunks (immutable)
//! for chunk in chunks {
//!     store.save_chunk(&snapshot.id, &chunk).await?;
//! }
//!
//! // 3. Query (Index Once, Query Many)
//! let results = store.get_chunks(&snapshot.id, "auth.py").await?;
//!
//! // 4. Replace file (creates new snapshot)
//! store.replace_file(
//!     "my-repo",
//!     "abc123def",  // old commit
//!     "def456abc",  // new commit
//!     "auth.py",
//!     new_chunks,
//!     new_deps
//! ).await?;
//! ```

// Placeholder for RFC-101+ implementation
// This module structure will be filled in RFC-101~105 sessions

pub mod domain;
pub mod error;

#[cfg(feature = "sqlite")]
pub mod infrastructure;

pub use error::{Result, StorageError};

// Domain re-exports (RFC-101)
pub use domain::{Chunk, CodeSnapshotStore, Dependency, Repository, Snapshot};
