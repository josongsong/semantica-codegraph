// PostgreSQL Storage Adapter
//!
//! SOTA Production Design:
//! - Multi-user concurrency: MVCC transactions
//! - Connection pooling: PgPool for efficient resource management
//! - Schema migrations: sqlx migrate for version control
//! - Full-text search: Native PostgreSQL GIN indexes
//! - ACID guarantees with better scalability

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use serde_json::Value as JsonValue;
use sqlx::postgres::{PgPool, PgPoolOptions, PgRow};
use sqlx::{Executor, Postgres, Row, Transaction};
use std::collections::HashMap;
use std::time::Duration;

use crate::features::storage::domain::{
    Chunk, ChunkFilter, ChunkId, ChunkStore, Dependency, DependencyType, IncrementalUpdateResult,
    Repository, RepoId, Snapshot, SnapshotId, StorageStats,
};
use crate::shared::models::{CodegraphError, Result};

/// PostgreSQL Chunk Store (Production/Server)
///
/// Optimized for:
/// - Multi-user concurrent access
/// - Large-scale data (millions of chunks)
/// - High availability deployments
/// - MVCC transaction isolation
pub struct PostgresChunkStore {
    /// Connection pool for concurrent requests
    pool: PgPool,
}

impl PostgresChunkStore {
    /// Create a new PostgreSQL store with connection pooling
    ///
    /// # Arguments
    /// * `database_url` - PostgreSQL connection string (e.g., "postgres://user:pass@localhost/codegraph")
    ///
    /// # Example
    /// ```no_run
    /// use codegraph_ir::features::storage::infrastructure::PostgresChunkStore;
    ///
    /// #[tokio::main]
    /// async fn main() {
    ///     let store = PostgresChunkStore::new("postgres://localhost/codegraph")
    ///         .await
    ///         .unwrap();
    /// }
    /// ```
    pub async fn new(database_url: &str) -> Result<Self> {
        // SOTA connection pool settings
        let pool = PgPoolOptions::new()
            .max_connections(20) // Production: adjust based on load
            .min_connections(2) // Keep warm connections
            .acquire_timeout(Duration::from_secs(5))
            .idle_timeout(Duration::from_secs(600)) // 10 minutes
            .max_lifetime(Duration::from_secs(1800)) // 30 minutes
            .connect(database_url)
            .await
            .map_err(|e| CodegraphError::storage(format!("Failed to connect to PostgreSQL: {}", e)))?;

        let store = Self { pool };

        // Note: Migrations must be run manually using `sqlx migrate run`
        // This avoids dependency conflicts with rusqlite
        // See README.md for migration instructions

        Ok(store)
    }

    /// Get connection pool reference (for advanced usage)
    pub fn pool(&self) -> &PgPool {
        &self.pool
    }

    /// Close connection pool gracefully
    pub async fn close(self) {
        self.pool.close().await;
    }

    /// Helper: Convert PgRow to Chunk
    fn row_to_chunk(row: &PgRow) -> Result<Chunk> {
        // Parse attrs from JSONB
        let attrs_json: serde_json::Value = row.try_get("attrs")
            .map_err(|e| CodegraphError::storage(format!("Failed to parse attrs: {}", e)))?;
        let attrs: HashMap<String, JsonValue> = serde_json::from_value(attrs_json)
            .unwrap_or_default();

        Ok(Chunk {
            chunk_id: row.try_get("chunk_id")
                .map_err(|e| CodegraphError::storage(format!("Missing chunk_id: {}", e)))?,
            repo_id: row.try_get("repo_id")
                .map_err(|e| CodegraphError::storage(format!("Missing repo_id: {}", e)))?,
            snapshot_id: row.try_get("snapshot_id")
                .map_err(|e| CodegraphError::storage(format!("Missing snapshot_id: {}", e)))?,
            file_path: row.try_get("file_path")
                .map_err(|e| CodegraphError::storage(format!("Missing file_path: {}", e)))?,
            start_line: row.try_get::<i32, _>("start_line")
                .map_err(|e| CodegraphError::storage(format!("Missing start_line: {}", e)))? as u32,
            end_line: row.try_get::<i32, _>("end_line")
                .map_err(|e| CodegraphError::storage(format!("Missing end_line: {}", e)))? as u32,
            kind: row.try_get("kind")
                .map_err(|e| CodegraphError::storage(format!("Missing kind: {}", e)))?,
            fqn: row.try_get("fqn").ok(),
            language: row.try_get("language")
                .map_err(|e| CodegraphError::storage(format!("Missing language: {}", e)))?,
            symbol_visibility: row.try_get("symbol_visibility").ok(),
            content: row.try_get("content")
                .map_err(|e| CodegraphError::storage(format!("Missing content: {}", e)))?,
            content_hash: row.try_get("content_hash")
                .map_err(|e| CodegraphError::storage(format!("Missing content_hash: {}", e)))?,
            summary: row.try_get("summary").ok(),
            importance: row.try_get("importance")
                .map_err(|e| CodegraphError::storage(format!("Missing importance: {}", e)))?,
            is_deleted: row.try_get("is_deleted")
                .map_err(|e| CodegraphError::storage(format!("Missing is_deleted: {}", e)))?,
            attrs,
            created_at: row.try_get("created_at")
                .map_err(|e| CodegraphError::storage(format!("Missing created_at: {}", e)))?,
            updated_at: row.try_get("updated_at")
                .map_err(|e| CodegraphError::storage(format!("Missing updated_at: {}", e)))?,
        })
    }

    /// Helper: Convert PgRow to Dependency
    fn row_to_dependency(row: &PgRow) -> Result<Dependency> {
        let relationship_str: String = row.try_get("relationship")
            .map_err(|e| CodegraphError::storage(format!("Missing relationship: {}", e)))?;
        let relationship = DependencyType::from_str(&relationship_str);

        Ok(Dependency {
            id: row.try_get("id")
                .map_err(|e| CodegraphError::storage(format!("Missing id: {}", e)))?,
            from_chunk_id: row.try_get("from_chunk_id")
                .map_err(|e| CodegraphError::storage(format!("Missing from_chunk_id: {}", e)))?,
            to_chunk_id: row.try_get("to_chunk_id")
                .map_err(|e| CodegraphError::storage(format!("Missing to_chunk_id: {}", e)))?,
            relationship,
            confidence: row.try_get("confidence")
                .map_err(|e| CodegraphError::storage(format!("Missing confidence: {}", e)))?,
            created_at: row.try_get("created_at")
                .map_err(|e| CodegraphError::storage(format!("Missing created_at: {}", e)))?,
        })
    }

    /// Helper: Convert PgRow to Snapshot
    fn row_to_snapshot(row: &PgRow) -> Result<Snapshot> {
        Ok(Snapshot {
            snapshot_id: row.try_get("snapshot_id")
                .map_err(|e| CodegraphError::storage(format!("Missing snapshot_id: {}", e)))?,
            repo_id: row.try_get("repo_id")
                .map_err(|e| CodegraphError::storage(format!("Missing repo_id: {}", e)))?,
            commit_hash: row.try_get("commit_hash").ok(),
            branch_name: row.try_get("branch_name").ok(),
            created_at: row.try_get("created_at")
                .map_err(|e| CodegraphError::storage(format!("Missing created_at: {}", e)))?,
        })
    }

    /// Helper: Convert PgRow to Repository
    fn row_to_repository(row: &PgRow) -> Result<Repository> {
        Ok(Repository {
            repo_id: row.try_get("repo_id")
                .map_err(|e| CodegraphError::storage(format!("Missing repo_id: {}", e)))?,
            name: row.try_get("name")
                .map_err(|e| CodegraphError::storage(format!("Missing name: {}", e)))?,
            remote_url: row.try_get("remote_url").ok(),
            local_path: row.try_get("local_path").ok(),
            default_branch: row.try_get("default_branch")
                .map_err(|e| CodegraphError::storage(format!("Missing default_branch: {}", e)))?,
            created_at: row.try_get("created_at")
                .map_err(|e| CodegraphError::storage(format!("Missing created_at: {}", e)))?,
            updated_at: row.try_get("updated_at")
                .map_err(|e| CodegraphError::storage(format!("Missing updated_at: {}", e)))?,
        })
    }
}

#[async_trait]
impl ChunkStore for PostgresChunkStore {
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Repository Operations
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async fn save_repository(&self, repo: &Repository) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO repositories (repo_id, name, remote_url, local_path, default_branch, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (repo_id) DO UPDATE SET
                name = EXCLUDED.name,
                remote_url = EXCLUDED.remote_url,
                local_path = EXCLUDED.local_path,
                default_branch = EXCLUDED.default_branch,
                updated_at = EXCLUDED.updated_at
            "#,
            repo.repo_id,
            repo.name,
            repo.remote_url,
            repo.local_path,
            repo.default_branch,
            repo.created_at,
            repo.updated_at
        )
        .execute(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to save repository: {}", e)))?;

        Ok(())
    }

    async fn get_repository(&self, repo_id: &str) -> Result<Option<Repository>> {
        let row = sqlx::query!(
            "SELECT * FROM repositories WHERE repo_id = $1",
            repo_id
        )
        .fetch_optional(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get repository: {}", e)))?;

        match row {
            Some(r) => Ok(Some(Repository {
                repo_id: r.repo_id,
                name: r.name,
                remote_url: r.remote_url,
                local_path: r.local_path,
                default_branch: r.default_branch,
                created_at: r.created_at,
                updated_at: r.updated_at,
            })),
            None => Ok(None),
        }
    }

    async fn list_repositories(&self) -> Result<Vec<Repository>> {
        let rows = sqlx::query!("SELECT * FROM repositories ORDER BY name")
            .fetch_all(&self.pool)
            .await
            .map_err(|e| CodegraphError::storage(format!("Failed to list repositories: {}", e)))?;

        let repos = rows
            .into_iter()
            .map(|r| Repository {
                repo_id: r.repo_id,
                name: r.name,
                remote_url: r.remote_url,
                local_path: r.local_path,
                default_branch: r.default_branch,
                created_at: r.created_at,
                updated_at: r.updated_at,
            })
            .collect();

        Ok(repos)
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Snapshot Operations
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async fn save_snapshot(&self, snapshot: &Snapshot) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO snapshots (snapshot_id, repo_id, commit_hash, branch_name, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (snapshot_id) DO UPDATE SET
                commit_hash = EXCLUDED.commit_hash,
                branch_name = EXCLUDED.branch_name
            "#,
            snapshot.snapshot_id,
            snapshot.repo_id,
            snapshot.commit_hash,
            snapshot.branch_name,
            snapshot.created_at
        )
        .execute(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to save snapshot: {}", e)))?;

        Ok(())
    }

    async fn get_snapshot(&self, snapshot_id: &str) -> Result<Option<Snapshot>> {
        let row = sqlx::query!(
            "SELECT * FROM snapshots WHERE snapshot_id = $1",
            snapshot_id
        )
        .fetch_optional(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get snapshot: {}", e)))?;

        match row {
            Some(r) => Ok(Some(Snapshot {
                snapshot_id: r.snapshot_id,
                repo_id: r.repo_id,
                commit_hash: r.commit_hash,
                branch_name: r.branch_name,
                created_at: r.created_at,
            })),
            None => Ok(None),
        }
    }

    async fn list_snapshots(&self, repo_id: &str) -> Result<Vec<Snapshot>> {
        let rows = sqlx::query!(
            "SELECT * FROM snapshots WHERE repo_id = $1 ORDER BY created_at DESC",
            repo_id
        )
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to list snapshots: {}", e)))?;

        let snapshots = rows
            .into_iter()
            .map(|r| Snapshot {
                snapshot_id: r.snapshot_id,
                repo_id: r.repo_id,
                commit_hash: r.commit_hash,
                branch_name: r.branch_name,
                created_at: r.created_at,
            })
            .collect();

        Ok(snapshots)
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Chunk Operations (CRUD)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async fn save_chunk(&self, chunk: &Chunk) -> Result<()> {
        let attrs_json = serde_json::to_value(&chunk.attrs)
            .map_err(|e| CodegraphError::storage(format!("Failed to serialize attrs: {}", e)))?;

        sqlx::query!(
            r#"
            INSERT INTO chunks (
                chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                kind, fqn, language, symbol_visibility, content, content_hash,
                summary, importance, is_deleted, attrs, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            ON CONFLICT (chunk_id) DO UPDATE SET
                snapshot_id = EXCLUDED.snapshot_id,
                file_path = EXCLUDED.file_path,
                start_line = EXCLUDED.start_line,
                end_line = EXCLUDED.end_line,
                content = EXCLUDED.content,
                content_hash = EXCLUDED.content_hash,
                summary = EXCLUDED.summary,
                importance = EXCLUDED.importance,
                is_deleted = FALSE,
                attrs = EXCLUDED.attrs,
                updated_at = CURRENT_TIMESTAMP
            "#,
            chunk.chunk_id,
            chunk.repo_id,
            chunk.snapshot_id,
            chunk.file_path,
            chunk.start_line as i32,
            chunk.end_line as i32,
            chunk.kind,
            chunk.fqn,
            chunk.language,
            chunk.symbol_visibility,
            chunk.content,
            chunk.content_hash,
            chunk.summary,
            chunk.importance,
            chunk.is_deleted,
            attrs_json,
            chunk.created_at,
            chunk.updated_at
        )
        .execute(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to save chunk: {}", e)))?;

        Ok(())
    }

    async fn save_chunks(&self, chunks: &[Chunk]) -> Result<()> {
        if chunks.is_empty() {
            return Ok(());
        }

        // Use transaction for batch insert (SOTA atomicity)
        let mut tx = self.pool.begin().await
            .map_err(|e| CodegraphError::storage(format!("Failed to begin transaction: {}", e)))?;

        for chunk in chunks {
            let attrs_json = serde_json::to_value(&chunk.attrs)
                .map_err(|e| CodegraphError::storage(format!("Failed to serialize attrs: {}", e)))?;

            sqlx::query!(
                r#"
                INSERT INTO chunks (
                    chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                    kind, fqn, language, symbol_visibility, content, content_hash,
                    summary, importance, is_deleted, attrs, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    snapshot_id = EXCLUDED.snapshot_id,
                    file_path = EXCLUDED.file_path,
                    start_line = EXCLUDED.start_line,
                    end_line = EXCLUDED.end_line,
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    summary = EXCLUDED.summary,
                    importance = EXCLUDED.importance,
                    is_deleted = FALSE,
                    attrs = EXCLUDED.attrs,
                    updated_at = CURRENT_TIMESTAMP
                "#,
                chunk.chunk_id,
                chunk.repo_id,
                chunk.snapshot_id,
                chunk.file_path,
                chunk.start_line as i32,
                chunk.end_line as i32,
                chunk.kind,
                chunk.fqn,
                chunk.language,
                chunk.symbol_visibility,
                chunk.content,
                chunk.content_hash,
                chunk.summary,
                chunk.importance,
                chunk.is_deleted,
                attrs_json,
                chunk.created_at,
                chunk.updated_at
            )
            .execute(&mut *tx)
            .await
            .map_err(|e| CodegraphError::storage(format!("Failed to save chunk in batch: {}", e)))?;
        }

        tx.commit().await
            .map_err(|e| CodegraphError::storage(format!("Failed to commit transaction: {}", e)))?;

        Ok(())
    }

    async fn get_chunk(&self, chunk_id: &str) -> Result<Option<Chunk>> {
        let row = sqlx::query(
            "SELECT * FROM chunks WHERE chunk_id = $1 AND is_deleted = FALSE"
        )
        .bind(chunk_id)
        .fetch_optional(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get chunk: {}", e)))?;

        match row {
            Some(r) => Ok(Some(Self::row_to_chunk(&r)?)),
            None => Ok(None),
        }
    }

    async fn get_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<Vec<Chunk>> {
        let rows = sqlx::query(
            "SELECT * FROM chunks WHERE repo_id = $1 AND snapshot_id = $2 AND is_deleted = FALSE ORDER BY file_path, start_line"
        )
        .bind(repo_id)
        .bind(snapshot_id)
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get chunks: {}", e)))?;

        rows.iter().map(|r| Self::row_to_chunk(r)).collect()
    }

    async fn get_chunks_by_fqn(&self, fqn: &str) -> Result<Vec<Chunk>> {
        let rows = sqlx::query(
            "SELECT * FROM chunks WHERE fqn = $1 AND is_deleted = FALSE"
        )
        .bind(fqn)
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get chunks by FQN: {}", e)))?;

        rows.iter().map(|r| Self::row_to_chunk(&r)).collect()
    }

    async fn get_chunks_by_file(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<Vec<Chunk>> {
        let rows = sqlx::query(
            "SELECT * FROM chunks WHERE repo_id = $1 AND snapshot_id = $2 AND file_path = $3 AND is_deleted = FALSE ORDER BY start_line"
        )
        .bind(repo_id)
        .bind(snapshot_id)
        .bind(file_path)
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get chunks by file: {}", e)))?;

        rows.iter().map(|r| Self::row_to_chunk(&r)).collect()
    }

    async fn get_chunks_by_kind(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        kind: &str,
    ) -> Result<Vec<Chunk>> {
        let rows = sqlx::query(
            "SELECT * FROM chunks WHERE repo_id = $1 AND snapshot_id = $2 AND kind = $3 AND is_deleted = FALSE"
        )
        .bind(repo_id)
        .bind(snapshot_id)
        .bind(kind)
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get chunks by kind: {}", e)))?;

        rows.iter().map(|r| Self::row_to_chunk(&r)).collect()
    }

    async fn soft_delete_file_chunks(&self, repo_id: &str, snapshot_id: &str, file_path: &str) -> Result<()> {
        sqlx::query!(
            "UPDATE chunks SET is_deleted = TRUE, updated_at = CURRENT_TIMESTAMP WHERE repo_id = $1 AND snapshot_id = $2 AND file_path = $3",
            repo_id,
            snapshot_id,
            file_path
        )
        .execute(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to soft delete file chunks: {}", e)))?;

        Ok(())
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Dependency Operations
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async fn save_dependency(&self, dep: &Dependency) -> Result<()> {
        let relationship_str = dep.relationship.to_string();

        sqlx::query!(
            r#"
            INSERT INTO dependencies (id, from_chunk_id, to_chunk_id, relationship, confidence, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (from_chunk_id, to_chunk_id, relationship) DO UPDATE SET
                confidence = EXCLUDED.confidence
            "#,
            dep.id,
            dep.from_chunk_id,
            dep.to_chunk_id,
            relationship_str,
            dep.confidence,
            dep.created_at
        )
        .execute(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to save dependency: {}", e)))?;

        Ok(())
    }

    async fn save_dependencies(&self, deps: &[Dependency]) -> Result<()> {
        if deps.is_empty() {
            return Ok(());
        }

        let mut tx = self.pool.begin().await
            .map_err(|e| CodegraphError::storage(format!("Failed to begin transaction: {}", e)))?;

        for dep in deps {
            let relationship_str = dep.relationship.to_string();

            sqlx::query!(
                r#"
                INSERT INTO dependencies (id, from_chunk_id, to_chunk_id, relationship, confidence, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (from_chunk_id, to_chunk_id, relationship) DO UPDATE SET
                    confidence = EXCLUDED.confidence
                "#,
                dep.id,
                dep.from_chunk_id,
                dep.to_chunk_id,
                relationship_str,
                dep.confidence,
                dep.created_at
            )
            .execute(&mut *tx)
            .await
            .map_err(|e| CodegraphError::storage(format!("Failed to save dependency in batch: {}", e)))?;
        }

        tx.commit().await
            .map_err(|e| CodegraphError::storage(format!("Failed to commit transaction: {}", e)))?;

        Ok(())
    }

    async fn get_dependencies_from(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        let rows = sqlx::query(
            "SELECT * FROM dependencies WHERE from_chunk_id = $1"
        )
        .bind(chunk_id)
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get dependencies from: {}", e)))?;

        rows.iter().map(|r| Self::row_to_dependency(r)).collect()
    }

    async fn get_dependencies_to(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        let rows = sqlx::query(
            "SELECT * FROM dependencies WHERE to_chunk_id = $1"
        )
        .bind(chunk_id)
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get dependencies to: {}", e)))?;

        rows.iter().map(|r| Self::row_to_dependency(r)).collect()
    }

    async fn get_transitive_dependencies(&self, chunk_id: &str, max_depth: usize) -> Result<Vec<ChunkId>> {
        // BFS traversal (SOTA algorithm)
        let mut visited = std::collections::HashSet::new();
        let mut queue = std::collections::VecDeque::new();
        let mut result = Vec::new();

        queue.push_back((chunk_id.to_string(), 0));
        visited.insert(chunk_id.to_string());

        while let Some((current_id, depth)) = queue.pop_front() {
            if depth >= max_depth {
                continue;
            }

            result.push(current_id.clone());

            // Get outgoing dependencies
            let deps = self.get_dependencies_from(&current_id).await?;

            for dep in deps {
                if !visited.contains(&dep.to_chunk_id) {
                    visited.insert(dep.to_chunk_id.clone());
                    queue.push_back((dep.to_chunk_id, depth + 1));
                }
            }
        }

        Ok(result)
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // File Metadata & Incremental Updates
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async fn update_file_metadata(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
        content_hash: String,
    ) -> Result<()> {
        let id = format!("{}:{}:{}", repo_id, snapshot_id, file_path);

        sqlx::query!(
            r#"
            INSERT INTO file_metadata (id, repo_id, snapshot_id, file_path, content_hash, last_analyzed)
            VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)
            ON CONFLICT (repo_id, snapshot_id, file_path) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                last_analyzed = CURRENT_TIMESTAMP
            "#,
            id,
            repo_id,
            snapshot_id,
            file_path,
            content_hash
        )
        .execute(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to update file metadata: {}", e)))?;

        Ok(())
    }

    async fn get_file_hash(&self, repo_id: &str, snapshot_id: &str, file_path: &str) -> Result<Option<String>> {
        let row = sqlx::query!(
            "SELECT content_hash FROM file_metadata WHERE repo_id = $1 AND snapshot_id = $2 AND file_path = $3",
            repo_id,
            snapshot_id,
            file_path
        )
        .fetch_optional(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get file hash: {}", e)))?;

        Ok(row.map(|r| r.content_hash))
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Search & Statistics
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async fn search_content(&self, query: &str, limit: usize) -> Result<Vec<Chunk>> {
        // PostgreSQL full-text search (SOTA native GIN index)
        let rows = sqlx::query(
            r#"
            SELECT * FROM chunks
            WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
            AND is_deleted = FALSE
            ORDER BY ts_rank(to_tsvector('english', content), plainto_tsquery('english', $1)) DESC
            LIMIT $2
            "#
        )
        .bind(query)
        .bind(limit as i64)
        .fetch_all(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to search content: {}", e)))?;

        rows.iter().map(|r| Self::row_to_chunk(r)).collect()
    }

    async fn count_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<usize> {
        let row = sqlx::query!(
            "SELECT COUNT(*) as count FROM chunks WHERE repo_id = $1 AND snapshot_id = $2 AND is_deleted = FALSE",
            repo_id,
            snapshot_id
        )
        .fetch_one(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to count chunks: {}", e)))?;

        Ok(row.count.unwrap_or(0) as usize)
    }

    async fn get_stats(&self) -> Result<StorageStats> {
        let chunk_row = sqlx::query!(
            "SELECT COUNT(*) as count FROM chunks WHERE is_deleted = FALSE"
        )
        .fetch_one(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get chunk count: {}", e)))?;

        let dep_row = sqlx::query!(
            "SELECT COUNT(*) as count FROM dependencies"
        )
        .fetch_one(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get dependency count: {}", e)))?;

        let snapshot_row = sqlx::query!(
            "SELECT COUNT(*) as count FROM snapshots"
        )
        .fetch_one(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get snapshot count: {}", e)))?;

        let repo_row = sqlx::query!(
            "SELECT COUNT(*) as count FROM repositories"
        )
        .fetch_one(&self.pool)
        .await
        .map_err(|e| CodegraphError::storage(format!("Failed to get repository count: {}", e)))?;

        Ok(StorageStats {
            total_repos: repo_row.count.unwrap_or(0) as usize,
            total_chunks: chunk_row.count.unwrap_or(0) as usize,
            total_dependencies: dep_row.count.unwrap_or(0) as usize,
            total_snapshots: snapshot_row.count.unwrap_or(0) as usize,
            storage_size_bytes: 0,  // Requires: SELECT pg_database_size(current_database())
        })
    }
}

// DependencyType string conversion
impl DependencyType {
    fn from_str(s: &str) -> Self {
        match s {
            "Calls" => DependencyType::Calls,
            "Imports" => DependencyType::Imports,
            "Extends" => DependencyType::Extends,
            "Implements" => DependencyType::Implements,
            "Flows" => DependencyType::Flows,
            "TypedBy" => DependencyType::TypedBy,
            _ => DependencyType::Calls,  // Default to Calls
        }
    }

    fn to_string(&self) -> String {
        match self {
            DependencyType::Calls => "Calls".to_string(),
            DependencyType::Imports => "Imports".to_string(),
            DependencyType::Extends => "Extends".to_string(),
            DependencyType::Implements => "Implements".to_string(),
            DependencyType::Flows => "Flows".to_string(),
            DependencyType::TypedBy => "TypedBy".to_string(),
        }
    }
}
