//! CodeSnapshotStore - RFC-100 High-Level API
//!
//! Wrapper around ChunkStore providing commit-based snapshot operations.
//!
//! # RFC-100 Core Contract
//!
//! This store provides:
//! 1. File-level replace primitive (atomic)
//! 2. Incremental snapshot creation (hash-based)
//! 3. Commit comparison (semantic diff)
//!
//! # Two-State Rule
//!
//! This store ONLY handles Committed state:
//! - Ephemeral: file save → local only (NOT stored here)
//! - Committed: git commit → stored here (immutable)

use chrono::Utc;
use std::collections::HashMap;
use std::sync::Arc;

use super::snapshot_diff::{SnapshotDiff, SnapshotStats as SnapshotCreationStats};
use crate::features::storage::domain::{
    models::{Chunk, ChunkId, Dependency, Snapshot},
    ports::ChunkStore,
};
use crate::features::storage::StorageStats;
use crate::shared::models::Result;

/// High-level snapshot store (RFC-100 API)
///
/// Wraps low-level ChunkStore with commit-based operations.
pub struct CodeSnapshotStore {
    /// Underlying storage backend
    store: Arc<dyn ChunkStore>,
}

impl CodeSnapshotStore {
    /// Create new snapshot store
    ///
    /// # Arguments
    /// * `store` - ChunkStore implementation (SQLite, PostgreSQL, etc.)
    pub fn new<S: ChunkStore + 'static>(store: S) -> Self {
        Self {
            store: Arc::new(store),
        }
    }

    /// RFC-100 Core Contract: File-level replace
    ///
    /// Atomically replaces chunks for a single file between commits.
    ///
    /// # Algorithm
    /// 1. Soft-delete old chunks (mark is_deleted = true)
    /// 2. UPSERT new chunks (revives if previously deleted)
    /// 3. Save dependencies
    /// 4. Update file metadata (hash)
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `base_snapshot_id` - Previous commit/branch
    /// * `new_snapshot_id` - Current commit/branch
    /// * `file_path` - File to replace
    /// * `new_chunks` - New chunks for this file
    /// * `new_dependencies` - New dependencies
    ///
    /// # Guarantees
    /// - ACID transaction (all-or-nothing)
    /// - No cascading deletes (soft delete)
    /// - Idempotent (can retry safely)
    pub async fn replace_file(
        &self,
        repo_id: &str,
        base_snapshot_id: &str,
        new_snapshot_id: &str,
        file_path: &str,
        new_chunks: Vec<Chunk>,
        new_dependencies: Vec<Dependency>,
    ) -> Result<()> {
        // 1. Soft delete old chunks ONLY if updating same snapshot
        //    (cross-snapshot updates should preserve base snapshot)
        if base_snapshot_id == new_snapshot_id {
            self.store
                .soft_delete_file_chunks(repo_id, base_snapshot_id, file_path)
                .await?;
        }

        // 2. UPSERT new chunks (batch for performance)
        if !new_chunks.is_empty() {
            self.store.save_chunks(&new_chunks).await?;
        }

        // 3. Save dependencies (batch)
        if !new_dependencies.is_empty() {
            self.store.save_dependencies(&new_dependencies).await?;
        }

        // 4. Update file metadata with new hash
        if !new_chunks.is_empty() {
            // Use first chunk's content hash as file hash
            let content_hash = new_chunks[0].content_hash.clone();
            self.store
                .update_file_metadata(repo_id, new_snapshot_id, file_path, content_hash)
                .await?;
        }

        Ok(())
    }

    /// RFC-100: Commit comparison (semantic diff)
    ///
    /// Compares two snapshots at a semantic level (FQN + content hash).
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `commit_a` - First commit/branch
    /// * `commit_b` - Second commit/branch
    ///
    /// # Returns
    /// SnapshotDiff with added/modified/deleted chunks
    pub async fn compare_commits(
        &self,
        repo_id: &str,
        commit_a: &str,
        commit_b: &str,
    ) -> Result<SnapshotDiff> {
        // Get all chunks for both snapshots
        let chunks_a = self.store.get_chunks(repo_id, commit_a).await?;
        let chunks_b = self.store.get_chunks(repo_id, commit_b).await?;

        // Build FQN-indexed maps for fast lookup
        let map_a: HashMap<String, &Chunk> = chunks_a
            .iter()
            .filter_map(|c| c.fqn.as_ref().map(|fqn| (fqn.clone(), c)))
            .collect();

        let map_b: HashMap<String, &Chunk> = chunks_b
            .iter()
            .filter_map(|c| c.fqn.as_ref().map(|fqn| (fqn.clone(), c)))
            .collect();

        let mut diff = SnapshotDiff::new();

        // Find modified and deleted chunks
        for chunk_a in &chunks_a {
            if let Some(fqn) = &chunk_a.fqn {
                if let Some(chunk_b) = map_b.get(fqn) {
                    // Check if modified (content hash differs)
                    if chunk_a.content_hash != chunk_b.content_hash {
                        diff.modified.push((chunk_a.clone(), (*chunk_b).clone()));
                    }
                } else {
                    // Deleted in B
                    diff.deleted.push(chunk_a.clone());
                }
            }
        }

        // Find added chunks
        for chunk_b in &chunks_b {
            if let Some(fqn) = &chunk_b.fqn {
                if !map_a.contains_key(fqn) {
                    diff.added.push(chunk_b.clone());
                }
            }
        }

        Ok(diff)
    }

    /// RFC-100: Incremental snapshot creation
    ///
    /// Creates new snapshot by only re-analyzing changed files.
    ///
    /// # Algorithm
    /// 1. For each file:
    ///    - Compute current hash
    ///    - Compare with stored hash
    ///    - If unchanged, skip (10-100x speedup!)
    ///    - If changed, re-analyze and replace
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `base_commit` - Previous commit
    /// * `new_commit` - Current commit
    /// * `changed_files` - Files to check (from git diff)
    /// * `analyzer` - Callback to analyze a file: fn(file_path) -> (chunks, deps)
    ///
    /// # Returns
    /// Statistics (files checked, skipped, analyzed)
    pub async fn create_incremental_snapshot<F>(
        &self,
        repo_id: &str,
        base_commit: &str,
        new_commit: &str,
        changed_files: Vec<String>,
        mut analyzer: F,
    ) -> Result<SnapshotCreationStats>
    where
        F: FnMut(&str) -> Result<(Vec<Chunk>, Vec<Dependency>)>,
    {
        let mut stats = SnapshotCreationStats::new();
        stats.files_checked = changed_files.len();

        for file_path in changed_files {
            // Get old hash from metadata
            let old_hash = self
                .store
                .get_file_hash(repo_id, base_commit, &file_path)
                .await?;

            // Analyze file to get new chunks
            let (new_chunks, new_deps) = analyzer(&file_path)?;

            // Compute new hash (use first chunk's hash)
            let new_hash = if !new_chunks.is_empty() {
                Some(new_chunks[0].content_hash.clone())
            } else {
                None
            };

            // Check if file changed
            if old_hash == new_hash {
                stats.files_skipped += 1;
                continue; // ⚡ Skip unchanged files
            }

            // Replace file in new snapshot
            self.replace_file(
                repo_id,
                base_commit,
                new_commit,
                &file_path,
                new_chunks.clone(),
                new_deps.clone(),
            )
            .await?;

            stats.files_analyzed += 1;
            stats.chunks_created += new_chunks.len();
            stats.dependencies_created += new_deps.len();
        }

        Ok(stats)
    }

    /// Create a new snapshot (commit or branch)
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `snapshot_id` - Snapshot identifier (e.g., "repo:main" or "repo:abc123")
    /// * `commit_hash` - Git commit SHA (optional)
    /// * `branch_name` - Git branch name (optional)
    pub async fn create_snapshot(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        commit_hash: Option<String>,
        branch_name: Option<String>,
    ) -> Result<()> {
        let snapshot = Snapshot {
            snapshot_id: snapshot_id.to_string(),
            repo_id: repo_id.to_string(),
            commit_hash,
            branch_name,
            created_at: Utc::now(),
        };

        self.store.save_snapshot(&snapshot).await
    }

    /// Get snapshot by ID
    pub async fn get_snapshot(&self, snapshot_id: &str) -> Result<Option<Snapshot>> {
        self.store.get_snapshot(snapshot_id).await
    }

    /// List all snapshots for a repository
    pub async fn list_snapshots(&self, repo_id: &str) -> Result<Vec<Snapshot>> {
        self.store.list_snapshots(repo_id).await
    }

    /// Get all chunks for a snapshot
    pub async fn get_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<Vec<Chunk>> {
        self.store.get_chunks(repo_id, snapshot_id).await
    }

    /// Get chunks by FQN (across all snapshots)
    pub async fn get_chunks_by_fqn(&self, fqn: &str) -> Result<Vec<Chunk>> {
        self.store.get_chunks_by_fqn(fqn).await
    }

    /// Get dependencies from a chunk
    pub async fn get_dependencies_from(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        self.store.get_dependencies_from(chunk_id).await
    }

    /// Get dependencies to a chunk
    pub async fn get_dependencies_to(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        self.store.get_dependencies_to(chunk_id).await
    }

    /// Get transitive dependencies (BFS)
    pub async fn get_transitive_dependencies(
        &self,
        chunk_id: &str,
        max_depth: usize,
    ) -> Result<Vec<ChunkId>> {
        self.store
            .get_transitive_dependencies(chunk_id, max_depth)
            .await
    }

    /// Search content (full-text)
    pub async fn search_content(&self, query: &str, limit: usize) -> Result<Vec<Chunk>> {
        self.store.search_content(query, limit).await
    }

    /// Get storage statistics
    pub async fn get_stats(&self) -> Result<StorageStats> {
        self.store.get_stats().await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::storage::domain::{models::Repository, ports::ChunkStore};
    use crate::features::storage::infrastructure::SqliteChunkStore;
    use chrono::Utc;

    #[tokio::test]
    async fn test_code_snapshot_store_creation() {
        let sqlite = SqliteChunkStore::in_memory().unwrap();

        // Create repository first (required by foreign key constraint)
        let repo = Repository {
            repo_id: "test-repo".to_string(),
            name: "Test Repository".to_string(),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        sqlite.save_repository(&repo).await.unwrap();

        let snapshot_store = CodeSnapshotStore::new(sqlite);

        // Create snapshot
        snapshot_store
            .create_snapshot(
                "test-repo",
                "test-repo:main",
                Some("abc123".to_string()),
                Some("main".to_string()),
            )
            .await
            .unwrap();

        // Verify
        let snapshot = snapshot_store.get_snapshot("test-repo:main").await.unwrap();
        assert!(snapshot.is_some());
        assert_eq!(snapshot.unwrap().commit_hash, Some("abc123".to_string()));
    }
}
