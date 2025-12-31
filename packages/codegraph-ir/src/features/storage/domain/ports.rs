//! Storage Port (Trait Interface)
//!
//! Port/Adapter pattern for backend flexibility:
//! - Development: SQLite (zero-config)
//! - Production: PostgreSQL (scale + concurrency)
//! - Testing: InMemory (fast unit tests)

use async_trait::async_trait;
use chrono::{DateTime, Utc};

use super::models::{Chunk, ChunkId, Dependency, RepoId, Repository, Snapshot, SnapshotId};
use crate::shared::models::Result;

/// Chunk Store Port (Primary Interface)
///
/// All storage backends must implement this trait
#[async_trait]
pub trait ChunkStore: Send + Sync {
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Repository Management
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Save or update a repository
    async fn save_repository(&self, repo: &Repository) -> Result<()>;

    /// Get repository by ID
    async fn get_repository(&self, repo_id: &str) -> Result<Option<Repository>>;

    /// List all repositories
    async fn list_repositories(&self) -> Result<Vec<Repository>>;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Snapshot Management
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Save or update a snapshot
    async fn save_snapshot(&self, snapshot: &Snapshot) -> Result<()>;

    /// Get snapshot by ID
    async fn get_snapshot(&self, snapshot_id: &str) -> Result<Option<Snapshot>>;

    /// List snapshots for a repository
    async fn list_snapshots(&self, repo_id: &str) -> Result<Vec<Snapshot>>;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Chunk CRUD (Core Operations)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Save a single chunk (UPSERT: insert or update)
    ///
    /// - If chunk exists: UPDATE (revive if deleted)
    /// - If chunk doesn't exist: INSERT
    async fn save_chunk(&self, chunk: &Chunk) -> Result<()>;

    /// Save multiple chunks in a transaction
    async fn save_chunks(&self, chunks: &[Chunk]) -> Result<()>;

    /// Get chunk by ID
    async fn get_chunk(&self, chunk_id: &str) -> Result<Option<Chunk>>;

    /// Get all active chunks for a repo + snapshot
    ///
    /// Filters out soft-deleted chunks (is_deleted = TRUE)
    async fn get_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<Vec<Chunk>>;

    /// Get chunks by file path
    async fn get_chunks_by_file(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<Vec<Chunk>>;

    /// Get chunks by FQN (Fully Qualified Name)
    async fn get_chunks_by_fqn(&self, fqn: &str) -> Result<Vec<Chunk>>;

    /// Soft-delete chunks for a file (mark as deleted)
    ///
    /// Used during incremental updates before re-analyzing
    async fn soft_delete_file_chunks(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<()>;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Dependency Graph
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Save a dependency relationship
    async fn save_dependency(&self, dep: &Dependency) -> Result<()>;

    /// Save multiple dependencies in a transaction
    async fn save_dependencies(&self, deps: &[Dependency]) -> Result<()>;

    /// Get dependencies from a chunk (outgoing edges)
    async fn get_dependencies_from(&self, chunk_id: &str) -> Result<Vec<Dependency>>;

    /// Get dependencies to a chunk (incoming edges)
    async fn get_dependencies_to(&self, chunk_id: &str) -> Result<Vec<Dependency>>;

    /// Get transitive dependencies (BFS traversal up to max_depth)
    async fn get_transitive_dependencies(
        &self,
        chunk_id: &str,
        max_depth: usize,
    ) -> Result<Vec<ChunkId>>;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Incremental Updates (Content-Addressable)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Get file content hash from metadata
    ///
    /// Returns None if file never indexed
    async fn get_file_hash(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<Option<String>>;

    /// Update file metadata (content hash + timestamp)
    async fn update_file_metadata(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
        content_hash: String,
    ) -> Result<()>;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Search & Query
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Full-text search in chunk content (if backend supports)
    async fn search_content(&self, query: &str, limit: usize) -> Result<Vec<Chunk>>;

    /// Get chunks by kind (e.g., "function", "class")
    async fn get_chunks_by_kind(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        kind: &str,
    ) -> Result<Vec<Chunk>>;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Statistics
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Get total chunk count for a repo + snapshot
    async fn count_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<usize>;

    /// Get storage statistics
    async fn get_stats(&self) -> Result<StorageStats>;
}

/// Storage Statistics
#[derive(Debug, Clone)]
pub struct StorageStats {
    /// Total number of repositories
    pub total_repos: usize,

    /// Total number of snapshots
    pub total_snapshots: usize,

    /// Total number of chunks (active only)
    pub total_chunks: usize,

    /// Total number of dependencies
    pub total_dependencies: usize,

    /// Total storage size (bytes)
    pub storage_size_bytes: u64,
}

/// Query Filter (for advanced queries)
#[derive(Debug, Clone)]
pub struct ChunkFilter {
    /// Repository ID
    pub repo_id: Option<String>,

    /// Snapshot ID
    pub snapshot_id: Option<String>,

    /// File path pattern (glob)
    pub file_path_pattern: Option<String>,

    /// Chunk kind
    pub kind: Option<String>,

    /// Symbol visibility
    pub visibility: Option<String>,

    /// Minimum importance score
    pub min_importance: Option<f32>,

    /// Include deleted chunks
    pub include_deleted: bool,

    /// Limit
    pub limit: Option<usize>,
}

impl Default for ChunkFilter {
    fn default() -> Self {
        Self {
            repo_id: None,
            snapshot_id: None,
            file_path_pattern: None,
            kind: None,
            visibility: None,
            min_importance: None,
            include_deleted: false,
            limit: Some(1000),
        }
    }
}

/// Incremental Update Result
#[derive(Debug, Clone)]
pub struct IncrementalUpdateResult {
    /// Number of files checked
    pub files_checked: usize,

    /// Number of files skipped (unchanged)
    pub files_skipped: usize,

    /// Number of files re-analyzed
    pub files_analyzed: usize,

    /// Number of chunks updated
    pub chunks_updated: usize,

    /// Number of chunks inserted
    pub chunks_inserted: usize,

    /// Number of chunks soft-deleted
    pub chunks_deleted: usize,
}
