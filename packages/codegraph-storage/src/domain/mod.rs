//! Domain layer for CodeSnapshotStore (RFC-101)
//!
//! # Core Principles (RFC-100)
//!
//! 1. **Two-State Rule**: Only Committed state (git commit), NOT Ephemeral (IDE save)
//! 2. **Snapshot Identity**: `snapshot_id = commit_hash` (immutable)
//! 3. **Core Contract**: File-level replace (chunk UPSERT is internal implementation)
//!
//! # Domain Models
//!
//! - `Snapshot`: Immutable commit-based snapshot
//! - `Chunk`: Code chunk within a file (no soft delete)
//! - `Repository`: Repository metadata
//! - `Dependency`: Cross-chunk/cross-file dependencies
//!
//! # Port Trait
//!
//! - `CodeSnapshotStore`: Primary storage abstraction
//!
//! # Examples
//!
//! ```rust,ignore
//! use codegraph_storage::domain::{CodeSnapshotStore, Snapshot, Chunk};
//!
//! async fn example(store: impl CodeSnapshotStore) -> Result<()> {
//!     // Create snapshot
//!     let snapshot = Snapshot::new("abc123def", "my-repo");
//!     store.save_snapshot(&snapshot).await?;
//!
//!     // Save chunks
//!     let chunk = Chunk::new("chunk_001", "auth.py", 1, 50, "def login():\n...");
//!     store.save_chunk(&snapshot.id, &chunk).await?;
//!
//!     // Query chunks
//!     let chunks = store.get_chunks(&snapshot.id, "auth.py").await?;
//!
//!     // Replace file (creates new snapshot)
//!     store.replace_file(
//!         "my-repo",
//!         "abc123def",  // old commit
//!         "def456abc",  // new commit
//!         "auth.py",
//!         vec![chunk],
//!     ).await?;
//!     Ok(())
//! }
//! ```

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::Result;

// ═══════════════════════════════════════════════════════════════════════════
// Domain Models
// ═══════════════════════════════════════════════════════════════════════════

/// Immutable code snapshot (commit-based)
///
/// A snapshot represents a complete state of a repository at a specific commit.
/// Snapshots are immutable - once created, they never change.
///
/// # Identity
///
/// - `id`: commit hash (SHA-1/SHA-256)
/// - Uniquely identifies the snapshot
/// - Never reused (immutable)
///
/// # Examples
///
/// ```rust
/// use codegraph_storage::domain::Snapshot;
///
/// let snapshot = Snapshot::new("abc123def456", "my-repo");
/// assert_eq!(snapshot.id, "abc123def456");
/// assert_eq!(snapshot.repo_id, "my-repo");
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Snapshot {
    /// Snapshot ID (commit hash)
    pub id: String,
    /// Repository ID
    pub repo_id: String,
    /// Snapshot creation timestamp
    pub timestamp: DateTime<Utc>,
    /// Optional metadata (branch, author, message, etc.)
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl Snapshot {
    /// Create a new snapshot
    ///
    /// # Arguments
    ///
    /// - `id`: Commit hash (snapshot identifier)
    /// - `repo_id`: Repository identifier
    ///
    /// # Examples
    ///
    /// ```rust
    /// use codegraph_storage::domain::Snapshot;
    ///
    /// let snapshot = Snapshot::new("abc123", "my-repo");
    /// ```
    pub fn new(id: impl Into<String>, repo_id: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            repo_id: repo_id.into(),
            timestamp: Utc::now(),
            metadata: serde_json::Value::Null,
        }
    }

    /// Create a snapshot with metadata
    pub fn with_metadata(
        id: impl Into<String>,
        repo_id: impl Into<String>,
        metadata: serde_json::Value,
    ) -> Self {
        Self {
            id: id.into(),
            repo_id: repo_id.into(),
            timestamp: Utc::now(),
            metadata,
        }
    }
}

/// Code chunk within a file
///
/// A chunk represents a contiguous region of code within a file.
/// Chunks are immutable - they belong to a specific snapshot.
///
/// # No Soft Delete
///
/// When a file changes, old chunks remain (tied to old snapshot).
/// New chunks are created for the new snapshot.
///
/// # Examples
///
/// ```rust
/// use codegraph_storage::domain::Chunk;
///
/// let chunk = Chunk::new(
///     "chunk_001",
///     "src/auth.py",
///     1,
///     50,
///     "def login():\n    pass"
/// );
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Chunk {
    /// Chunk ID (unique within snapshot)
    pub id: String,
    /// File path (relative to repository root)
    pub file_path: String,
    /// Start line number (1-indexed)
    pub start_line: usize,
    /// End line number (inclusive)
    pub end_line: usize,
    /// Chunk content (source code)
    pub content: String,
    /// Optional metadata (embeddings, analysis results, etc.)
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl Chunk {
    /// Create a new chunk
    ///
    /// # Arguments
    ///
    /// - `id`: Chunk identifier (unique within snapshot)
    /// - `file_path`: File path (relative to repo root)
    /// - `start_line`: Start line (1-indexed)
    /// - `end_line`: End line (inclusive)
    /// - `content`: Source code content
    pub fn new(
        id: impl Into<String>,
        file_path: impl Into<String>,
        start_line: usize,
        end_line: usize,
        content: impl Into<String>,
    ) -> Self {
        Self {
            id: id.into(),
            file_path: file_path.into(),
            start_line,
            end_line,
            content: content.into(),
            metadata: serde_json::Value::Null,
        }
    }

    /// Create a chunk with metadata
    pub fn with_metadata(
        id: impl Into<String>,
        file_path: impl Into<String>,
        start_line: usize,
        end_line: usize,
        content: impl Into<String>,
        metadata: serde_json::Value,
    ) -> Self {
        Self {
            id: id.into(),
            file_path: file_path.into(),
            start_line,
            end_line,
            content: content.into(),
            metadata,
        }
    }

    /// Get chunk line count
    pub fn line_count(&self) -> usize {
        self.end_line.saturating_sub(self.start_line) + 1
    }
}

/// Repository metadata
///
/// Stores repository-level information.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Repository {
    /// Repository ID (unique identifier)
    pub id: String,
    /// Repository name
    pub name: String,
    /// Optional URL
    pub url: Option<String>,
    /// Creation timestamp
    pub created_at: DateTime<Utc>,
    /// Optional metadata
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl Repository {
    /// Create a new repository
    pub fn new(id: impl Into<String>, name: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            url: None,
            created_at: Utc::now(),
            metadata: serde_json::Value::Null,
        }
    }
}

/// Cross-chunk dependency
///
/// Represents a dependency relationship between chunks.
///
/// # Examples
///
/// - Function call: chunk A calls function in chunk B
/// - Import: chunk A imports module in chunk B
/// - Inheritance: chunk A inherits class in chunk B
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Dependency {
    /// Source chunk ID
    pub from_chunk_id: String,
    /// Target chunk ID
    pub to_chunk_id: String,
    /// Dependency type (call, import, inheritance, etc.)
    pub dep_type: String,
    /// Optional metadata
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl Dependency {
    /// Create a new dependency
    pub fn new(
        from_chunk_id: impl Into<String>,
        to_chunk_id: impl Into<String>,
        dep_type: impl Into<String>,
    ) -> Self {
        Self {
            from_chunk_id: from_chunk_id.into(),
            to_chunk_id: to_chunk_id.into(),
            dep_type: dep_type.into(),
            metadata: serde_json::Value::Null,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Port Trait: CodeSnapshotStore
// ═══════════════════════════════════════════════════════════════════════════

/// Code snapshot storage abstraction (RFC-101)
///
/// This trait defines the core storage operations for commit-based code snapshots.
///
/// # Core Operations
///
/// 1. **Snapshot Management**
///    - `save_snapshot`: Create a new immutable snapshot
///    - `get_snapshot`: Retrieve snapshot metadata
///    - `list_snapshots`: List all snapshots for a repository
///
/// 2. **Chunk Management**
///    - `save_chunk`: Save a chunk (immutable)
///    - `save_chunks`: Batch save chunks
///    - `get_chunks`: Query chunks by file path
///    - `get_chunk`: Get single chunk by ID
///
/// 3. **File-level Operations**
///    - `replace_file`: Replace all chunks for a file (creates new snapshot)
///
/// 4. **Dependency Management**
///    - `save_dependencies`: Save chunk dependencies
///    - `get_dependencies`: Get dependencies for a chunk
///
/// # Implementations
///
/// - `SqliteSnapshotStore` (RFC-102): SQLite adapter
/// - `PostgresSnapshotStore` (RFC-103): PostgreSQL adapter
///
/// # Examples
///
/// ```rust,ignore
/// use codegraph_storage::domain::{CodeSnapshotStore, Snapshot, Chunk};
///
/// async fn example(store: impl CodeSnapshotStore) -> Result<()> {
///     // Create snapshot
///     let snapshot = Snapshot::new("abc123", "my-repo");
///     store.save_snapshot(&snapshot).await?;
///
///     // Save chunks
///     let chunks = vec![
///         Chunk::new("chunk_1", "auth.py", 1, 50, "def login():\n..."),
///         Chunk::new("chunk_2", "auth.py", 51, 100, "def logout():\n..."),
///     ];
///     store.save_chunks(&snapshot.id, &chunks).await?;
///
///     // Query chunks
///     let results = store.get_chunks(&snapshot.id, "auth.py").await?;
///     assert_eq!(results.len(), 2);
///
///     Ok(())
/// }
/// ```
#[async_trait]
pub trait CodeSnapshotStore: Send + Sync {
    // ═══════════════════════════════════════════════════════════════════════
    // Snapshot Operations
    // ═══════════════════════════════════════════════════════════════════════

    /// Save a new snapshot (immutable)
    ///
    /// # Arguments
    ///
    /// - `snapshot`: Snapshot to save
    ///
    /// # Errors
    ///
    /// Returns `StorageError` if:
    /// - Database error occurs
    /// - Snapshot already exists (duplicate ID)
    async fn save_snapshot(&self, snapshot: &Snapshot) -> Result<()>;

    /// Get snapshot by ID
    ///
    /// # Errors
    ///
    /// Returns `StorageError::SnapshotNotFound` if snapshot doesn't exist
    async fn get_snapshot(&self, snapshot_id: &str) -> Result<Snapshot>;

    /// List all snapshots for a repository
    ///
    /// # Arguments
    ///
    /// - `repo_id`: Repository identifier
    /// - `limit`: Maximum number of snapshots to return (None = unlimited)
    ///
    /// # Returns
    ///
    /// Snapshots ordered by timestamp (newest first)
    async fn list_snapshots(&self, repo_id: &str, limit: Option<usize>) -> Result<Vec<Snapshot>>;

    // ═══════════════════════════════════════════════════════════════════════
    // Chunk Operations
    // ═══════════════════════════════════════════════════════════════════════

    /// Save a single chunk (immutable)
    ///
    /// # Arguments
    ///
    /// - `snapshot_id`: Snapshot identifier
    /// - `chunk`: Chunk to save
    async fn save_chunk(&self, snapshot_id: &str, chunk: &Chunk) -> Result<()>;

    /// Batch save chunks (more efficient than multiple save_chunk calls)
    ///
    /// # Arguments
    ///
    /// - `snapshot_id`: Snapshot identifier
    /// - `chunks`: Chunks to save
    async fn save_chunks(&self, snapshot_id: &str, chunks: &[Chunk]) -> Result<()>;

    /// Get all chunks for a file in a snapshot
    ///
    /// # Arguments
    ///
    /// - `snapshot_id`: Snapshot identifier
    /// - `file_path`: File path (relative to repo root)
    ///
    /// # Returns
    ///
    /// Chunks ordered by start_line
    async fn get_chunks(&self, snapshot_id: &str, file_path: &str) -> Result<Vec<Chunk>>;

    /// Get a single chunk by ID
    ///
    /// # Errors
    ///
    /// Returns `StorageError::ChunkNotFound` if chunk doesn't exist
    async fn get_chunk(&self, snapshot_id: &str, chunk_id: &str) -> Result<Chunk>;

    // ═══════════════════════════════════════════════════════════════════════
    // File-level Operations (RFC-100 Core Contract)
    // ═══════════════════════════════════════════════════════════════════════

    /// Replace all chunks for a file (creates new snapshot)
    ///
    /// This is the **core contract** (RFC-100):
    /// - File-level operation (not chunk-level)
    /// - Chunk UPSERT is internal implementation detail
    /// - Creates new snapshot with updated file
    ///
    /// # Arguments
    ///
    /// - `repo_id`: Repository identifier
    /// - `old_commit`: Old commit hash (source snapshot)
    /// - `new_commit`: New commit hash (target snapshot)
    /// - `file_path`: File to replace
    /// - `chunks`: New chunks for the file
    ///
    /// # Behavior
    ///
    /// 1. Copy all chunks from old_commit snapshot to new_commit snapshot
    /// 2. Replace chunks for `file_path` with new chunks
    /// 3. Old snapshot remains unchanged (immutable)
    ///
    /// # Examples
    ///
    /// ```rust,ignore
    /// store.replace_file(
    ///     "my-repo",
    ///     "abc123",  // old commit
    ///     "def456",  // new commit
    ///     "src/auth.py",
    ///     vec![
    ///         Chunk::new("chunk_1", "src/auth.py", 1, 60, "# Fixed bug\n..."),
    ///     ],
    /// ).await?;
    /// ```
    async fn replace_file(
        &self,
        repo_id: &str,
        old_commit: &str,
        new_commit: &str,
        file_path: &str,
        chunks: Vec<Chunk>,
    ) -> Result<()>;

    // ═══════════════════════════════════════════════════════════════════════
    // Dependency Operations
    // ═══════════════════════════════════════════════════════════════════════

    /// Save dependencies for chunks
    ///
    /// # Arguments
    ///
    /// - `snapshot_id`: Snapshot identifier
    /// - `dependencies`: Dependencies to save
    async fn save_dependencies(&self, snapshot_id: &str, dependencies: &[Dependency])
        -> Result<()>;

    /// Get all dependencies for a chunk
    ///
    /// # Arguments
    ///
    /// - `snapshot_id`: Snapshot identifier
    /// - `chunk_id`: Source chunk identifier
    ///
    /// # Returns
    ///
    /// Dependencies where `from_chunk_id == chunk_id`
    async fn get_dependencies(&self, snapshot_id: &str, chunk_id: &str) -> Result<Vec<Dependency>>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    // ═══════════════════════════════════════════════════════════════════════
    // Snapshot Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_snapshot_new() {
        let snapshot = Snapshot::new("abc123", "my-repo");

        assert_eq!(snapshot.id, "abc123");
        assert_eq!(snapshot.repo_id, "my-repo");
        assert_eq!(snapshot.metadata, serde_json::Value::Null);
    }

    #[test]
    fn test_snapshot_with_metadata() {
        let metadata = serde_json::json!({
            "branch": "main",
            "author": "Alice",
            "message": "Fix bug"
        });

        let snapshot = Snapshot::with_metadata("abc123", "my-repo", metadata.clone());

        assert_eq!(snapshot.id, "abc123");
        assert_eq!(snapshot.repo_id, "my-repo");
        assert_eq!(snapshot.metadata, metadata);
    }

    #[test]
    fn test_snapshot_serde() {
        let snapshot = Snapshot::new("abc123", "my-repo");

        // Serialize
        let json = serde_json::to_string(&snapshot).unwrap();
        assert!(json.contains("abc123"));
        assert!(json.contains("my-repo"));

        // Deserialize
        let deserialized: Snapshot = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.id, snapshot.id);
        assert_eq!(deserialized.repo_id, snapshot.repo_id);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Chunk Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_chunk_new() {
        let chunk = Chunk::new("chunk_1", "src/auth.py", 1, 50, "def login():\n    pass");

        assert_eq!(chunk.id, "chunk_1");
        assert_eq!(chunk.file_path, "src/auth.py");
        assert_eq!(chunk.start_line, 1);
        assert_eq!(chunk.end_line, 50);
        assert_eq!(chunk.content, "def login():\n    pass");
        assert_eq!(chunk.metadata, serde_json::Value::Null);
    }

    #[test]
    fn test_chunk_with_metadata() {
        let metadata = serde_json::json!({
            "embedding": [0.1, 0.2, 0.3],
            "language": "python"
        });

        let chunk = Chunk::with_metadata(
            "chunk_1",
            "src/auth.py",
            1,
            50,
            "def login():\n    pass",
            metadata.clone(),
        );

        assert_eq!(chunk.metadata, metadata);
    }

    #[test]
    fn test_chunk_line_count() {
        let chunk = Chunk::new("chunk_1", "auth.py", 1, 50, "content");
        assert_eq!(chunk.line_count(), 50);

        let chunk2 = Chunk::new("chunk_2", "auth.py", 10, 20, "content");
        assert_eq!(chunk2.line_count(), 11);

        let chunk3 = Chunk::new("chunk_3", "auth.py", 42, 42, "content");
        assert_eq!(chunk3.line_count(), 1);
    }

    #[test]
    fn test_chunk_serde() {
        let chunk = Chunk::new("chunk_1", "src/auth.py", 1, 50, "def login():\n    pass");

        // Serialize
        let json = serde_json::to_string(&chunk).unwrap();
        assert!(json.contains("chunk_1"));
        assert!(json.contains("src/auth.py"));

        // Deserialize
        let deserialized: Chunk = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.id, chunk.id);
        assert_eq!(deserialized.file_path, chunk.file_path);
        assert_eq!(deserialized.start_line, chunk.start_line);
        assert_eq!(deserialized.end_line, chunk.end_line);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Repository Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_repository_new() {
        let repo = Repository::new("repo_1", "my-repo");

        assert_eq!(repo.id, "repo_1");
        assert_eq!(repo.name, "my-repo");
        assert_eq!(repo.url, None);
        assert_eq!(repo.metadata, serde_json::Value::Null);
    }

    #[test]
    fn test_repository_serde() {
        let repo = Repository::new("repo_1", "my-repo");

        // Serialize
        let json = serde_json::to_string(&repo).unwrap();
        assert!(json.contains("repo_1"));
        assert!(json.contains("my-repo"));

        // Deserialize
        let deserialized: Repository = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.id, repo.id);
        assert_eq!(deserialized.name, repo.name);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Dependency Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_dependency_new() {
        let dep = Dependency::new("chunk_1", "chunk_2", "call");

        assert_eq!(dep.from_chunk_id, "chunk_1");
        assert_eq!(dep.to_chunk_id, "chunk_2");
        assert_eq!(dep.dep_type, "call");
        assert_eq!(dep.metadata, serde_json::Value::Null);
    }

    #[test]
    fn test_dependency_serde() {
        let dep = Dependency::new("chunk_1", "chunk_2", "import");

        // Serialize
        let json = serde_json::to_string(&dep).unwrap();
        assert!(json.contains("chunk_1"));
        assert!(json.contains("chunk_2"));
        assert!(json.contains("import"));

        // Deserialize
        let deserialized: Dependency = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.from_chunk_id, dep.from_chunk_id);
        assert_eq!(deserialized.to_chunk_id, dep.to_chunk_id);
        assert_eq!(deserialized.dep_type, dep.dep_type);
    }
}
