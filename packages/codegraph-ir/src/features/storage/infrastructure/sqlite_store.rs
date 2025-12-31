///! SQLite Chunk Store
///!
///! File-based persistent storage using SQLite.
///! Suitable for local development and testing.
use async_trait::async_trait;
use rusqlite::{params, Connection, OptionalExtension};
use std::path::Path;
use std::sync::{Arc, Mutex};

use crate::features::storage::domain::models::{Chunk, Dependency, Repository, Snapshot};
use crate::features::storage::domain::ports::{ChunkStore, StorageStats};
use crate::shared::models::Result;

/// SQLite-based ChunkStore implementation
#[derive(Clone)]
pub struct SqliteChunkStore {
    conn: Arc<Mutex<Connection>>,
}

impl SqliteChunkStore {
    /// Create a new SQLite store at the given path
    pub fn new(db_path: impl AsRef<Path>) -> Result<Self> {
        let conn = Connection::open(db_path)?;
        let store = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        store.init_schema()?;
        Ok(store)
    }

    /// Create an in-memory SQLite store (for testing)
    pub fn in_memory() -> Result<Self> {
        let conn = Connection::open_in_memory()?;
        let store = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        store.init_schema()?;
        Ok(store)
    }

    /// Initialize database schema
    fn init_schema(&self) -> Result<()> {
        let conn = self.conn.lock().unwrap();

        // Repositories table
        conn.execute(
            "CREATE TABLE IF NOT EXISTS repositories (
                repo_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                remote_url TEXT,
                local_path TEXT,
                default_branch TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )",
            [],
        )?;

        // Snapshots table
        conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                commit_hash TEXT,
                branch_name TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (repo_id) REFERENCES repositories(repo_id)
            )",
            [],
        )?;

        // Chunks table
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                kind TEXT NOT NULL,
                fqn TEXT,
                language TEXT NOT NULL,
                symbol_visibility TEXT,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                summary TEXT,
                importance REAL NOT NULL DEFAULT 0.5,
                is_deleted BOOLEAN NOT NULL DEFAULT 0,
                attrs TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (repo_id) REFERENCES repositories(repo_id),
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
            )",
            [],
        )?;

        // Create indexes for fast lookups
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_repo_snapshot
             ON chunks(repo_id, snapshot_id, is_deleted)",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_file
             ON chunks(repo_id, snapshot_id, file_path, is_deleted)",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_fqn
             ON chunks(fqn, is_deleted)",
            [],
        )?;

        // Dependencies table
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dependencies (
                id TEXT PRIMARY KEY,
                from_chunk_id TEXT NOT NULL,
                to_chunk_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (from_chunk_id) REFERENCES chunks(chunk_id),
                FOREIGN KEY (to_chunk_id) REFERENCES chunks(chunk_id)
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_deps_from
             ON dependencies(from_chunk_id)",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_deps_to
             ON dependencies(to_chunk_id)",
            [],
        )?;

        // File metadata table (for incremental indexing)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS file_metadata (
                repo_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (repo_id, snapshot_id, file_path),
                FOREIGN KEY (repo_id) REFERENCES repositories(repo_id),
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_metadata_hash
             ON file_metadata(content_hash)",
            [],
        )?;

        Ok(())
    }
}

#[async_trait]
impl ChunkStore for SqliteChunkStore {
    async fn save_repository(&self, repo: &Repository) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO repositories (repo_id, name, remote_url, local_path, default_branch, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                &repo.repo_id,
                &repo.name,
                &repo.remote_url,
                &repo.local_path,
                &repo.default_branch,
                repo.created_at.timestamp(),
                repo.updated_at.timestamp()
            ],
        )?;
        Ok(())
    }

    async fn get_repository(&self, repo_id: &str) -> Result<Option<Repository>> {
        let conn = self.conn.lock().unwrap();
        let result = conn
            .query_row(
                "SELECT repo_id, name, remote_url, local_path, default_branch, created_at, updated_at FROM repositories WHERE repo_id = ?1",
                params![repo_id],
                |row| {
                    Ok(Repository {
                        repo_id: row.get(0)?,
                        name: row.get(1)?,
                        remote_url: row.get(2)?,
                        local_path: row.get(3)?,
                        default_branch: row.get(4)?,
                        created_at: chrono::DateTime::from_timestamp(row.get(5)?, 0)
                            .unwrap_or_default(),
                        updated_at: chrono::DateTime::from_timestamp(row.get(6)?, 0)
                            .unwrap_or_default(),
                    })
                },
            )
            .optional()?;
        Ok(result)
    }

    async fn list_repositories(&self) -> Result<Vec<Repository>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT repo_id, name, remote_url, local_path, default_branch, created_at, updated_at FROM repositories")?;
        let repos = stmt
            .query_map([], |row| {
                Ok(Repository {
                    repo_id: row.get(0)?,
                    name: row.get(1)?,
                    remote_url: row.get(2)?,
                    local_path: row.get(3)?,
                    default_branch: row.get(4)?,
                    created_at: chrono::DateTime::from_timestamp(row.get(5)?, 0)
                        .unwrap_or_default(),
                    updated_at: chrono::DateTime::from_timestamp(row.get(6)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(repos)
    }

    async fn save_snapshot(&self, snapshot: &Snapshot) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO snapshots (snapshot_id, repo_id, commit_hash, branch_name, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                &snapshot.snapshot_id,
                &snapshot.repo_id,
                &snapshot.commit_hash,
                &snapshot.branch_name,
                snapshot.created_at.timestamp()
            ],
        )?;
        Ok(())
    }

    async fn get_snapshot(&self, snapshot_id: &str) -> Result<Option<Snapshot>> {
        let conn = self.conn.lock().unwrap();
        let result = conn
            .query_row(
                "SELECT snapshot_id, repo_id, commit_hash, branch_name, created_at
                 FROM snapshots WHERE snapshot_id = ?1",
                params![snapshot_id],
                |row| {
                    Ok(Snapshot {
                        snapshot_id: row.get(0)?,
                        repo_id: row.get(1)?,
                        commit_hash: row.get(2)?,
                        branch_name: row.get(3)?,
                        created_at: chrono::DateTime::from_timestamp(row.get(4)?, 0)
                            .unwrap_or_default(),
                    })
                },
            )
            .optional()?;
        Ok(result)
    }

    async fn list_snapshots(&self, repo_id: &str) -> Result<Vec<Snapshot>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT snapshot_id, repo_id, commit_hash, branch_name, created_at
             FROM snapshots WHERE repo_id = ?1",
        )?;
        let snapshots = stmt
            .query_map(params![repo_id], |row| {
                Ok(Snapshot {
                    snapshot_id: row.get(0)?,
                    repo_id: row.get(1)?,
                    commit_hash: row.get(2)?,
                    branch_name: row.get(3)?,
                    created_at: chrono::DateTime::from_timestamp(row.get(4)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(snapshots)
    }

    async fn save_chunk(&self, chunk: &Chunk) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO chunks
             (chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
              kind, fqn, language, symbol_visibility, content, content_hash, summary,
              importance, is_deleted, attrs, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)",
            params![
                &chunk.chunk_id,
                &chunk.repo_id,
                &chunk.snapshot_id,
                &chunk.file_path,
                chunk.start_line,
                chunk.end_line,
                &chunk.kind,
                &chunk.fqn,
                &chunk.language,
                &chunk.symbol_visibility,
                &chunk.content,
                &chunk.content_hash,
                &chunk.summary,
                chunk.importance,
                chunk.is_deleted,
                serde_json::to_string(&chunk.attrs).ok(),
                chunk.created_at.timestamp(),
                chunk.updated_at.timestamp(),
            ],
        )?;
        Ok(())
    }

    async fn save_chunks(&self, chunks: &[Chunk]) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let tx = conn.unchecked_transaction()?;

        for chunk in chunks {
            tx.execute(
                "INSERT OR REPLACE INTO chunks
                 (chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                  kind, fqn, language, symbol_visibility, content, content_hash, summary,
                  importance, is_deleted, attrs, created_at, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)",
                params![
                    &chunk.chunk_id,
                    &chunk.repo_id,
                    &chunk.snapshot_id,
                    &chunk.file_path,
                    chunk.start_line,
                    chunk.end_line,
                    &chunk.kind,
                    &chunk.fqn,
                    &chunk.language,
                    &chunk.symbol_visibility,
                    &chunk.content,
                    &chunk.content_hash,
                    &chunk.summary,
                    chunk.importance,
                    chunk.is_deleted,
                    serde_json::to_string(&chunk.attrs).ok(),
                    chunk.created_at.timestamp(),
                    chunk.updated_at.timestamp(),
                ],
            )?;
        }

        tx.commit()?;
        Ok(())
    }

    async fn get_chunk(&self, chunk_id: &str) -> Result<Option<Chunk>> {
        let conn = self.conn.lock().unwrap();
        let result = conn
            .query_row(
                "SELECT chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                        kind, fqn, language, symbol_visibility, content, content_hash, summary,
                        importance, is_deleted, attrs, created_at, updated_at
                 FROM chunks WHERE chunk_id = ?1",
                params![chunk_id],
                |row| {
                    let attrs_str: Option<String> = row.get(15)?;
                    let attrs = attrs_str
                        .and_then(|s| serde_json::from_str(&s).ok())
                        .unwrap_or_else(|| std::collections::HashMap::new());

                    Ok(Chunk {
                        chunk_id: row.get(0)?,
                        repo_id: row.get(1)?,
                        snapshot_id: row.get(2)?,
                        file_path: row.get(3)?,
                        start_line: row.get(4)?,
                        end_line: row.get(5)?,
                        kind: row.get(6)?,
                        fqn: row.get(7)?,
                        language: row.get(8)?,
                        symbol_visibility: row.get(9)?,
                        content: row.get(10)?,
                        content_hash: row.get(11)?,
                        summary: row.get(12)?,
                        importance: row.get(13)?,
                        is_deleted: row.get(14)?,
                        attrs,
                        created_at: chrono::DateTime::from_timestamp(row.get(16)?, 0)
                            .unwrap_or_default(),
                        updated_at: chrono::DateTime::from_timestamp(row.get(17)?, 0)
                            .unwrap_or_default(),
                    })
                },
            )
            .optional()?;
        Ok(result)
    }

    async fn get_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<Vec<Chunk>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                    kind, fqn, language, symbol_visibility, content, content_hash, summary,
                    importance, is_deleted, attrs, created_at, updated_at
             FROM chunks WHERE repo_id = ?1 AND snapshot_id = ?2 AND is_deleted = 0",
        )?;

        let chunks = stmt
            .query_map(params![repo_id, snapshot_id], |row| {
                let attrs_str: Option<String> = row.get(15)?;
                let attrs = attrs_str
                    .and_then(|s| serde_json::from_str(&s).ok())
                    .unwrap_or_else(|| std::collections::HashMap::new());

                Ok(Chunk {
                    chunk_id: row.get(0)?,
                    repo_id: row.get(1)?,
                    snapshot_id: row.get(2)?,
                    file_path: row.get(3)?,
                    start_line: row.get(4)?,
                    end_line: row.get(5)?,
                    kind: row.get(6)?,
                    fqn: row.get(7)?,
                    language: row.get(8)?,
                    symbol_visibility: row.get(9)?,
                    content: row.get(10)?,
                    content_hash: row.get(11)?,
                    summary: row.get(12)?,
                    importance: row.get(13)?,
                    is_deleted: row.get(14)?,
                    attrs,
                    created_at: chrono::DateTime::from_timestamp(row.get(16)?, 0)
                        .unwrap_or_default(),
                    updated_at: chrono::DateTime::from_timestamp(row.get(17)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        Ok(chunks)
    }

    async fn get_chunks_by_file(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<Vec<Chunk>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                    kind, fqn, language, symbol_visibility, content, content_hash, summary,
                    importance, is_deleted, attrs, created_at, updated_at
             FROM chunks WHERE repo_id = ?1 AND snapshot_id = ?2 AND file_path = ?3 AND is_deleted = 0",
        )?;

        let chunks = stmt
            .query_map(params![repo_id, snapshot_id, file_path], |row| {
                let attrs_str: Option<String> = row.get(15)?;
                let attrs = attrs_str
                    .and_then(|s| serde_json::from_str(&s).ok())
                    .unwrap_or_else(|| std::collections::HashMap::new());

                Ok(Chunk {
                    chunk_id: row.get(0)?,
                    repo_id: row.get(1)?,
                    snapshot_id: row.get(2)?,
                    file_path: row.get(3)?,
                    start_line: row.get(4)?,
                    end_line: row.get(5)?,
                    kind: row.get(6)?,
                    fqn: row.get(7)?,
                    language: row.get(8)?,
                    symbol_visibility: row.get(9)?,
                    content: row.get(10)?,
                    content_hash: row.get(11)?,
                    summary: row.get(12)?,
                    importance: row.get(13)?,
                    is_deleted: row.get(14)?,
                    attrs,
                    created_at: chrono::DateTime::from_timestamp(row.get(16)?, 0)
                        .unwrap_or_default(),
                    updated_at: chrono::DateTime::from_timestamp(row.get(17)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        Ok(chunks)
    }

    async fn get_chunks_by_fqn(&self, fqn: &str) -> Result<Vec<Chunk>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                    kind, fqn, language, symbol_visibility, content, content_hash, summary,
                    importance, is_deleted, attrs, created_at, updated_at
             FROM chunks WHERE fqn = ?1 AND is_deleted = 0",
        )?;

        let chunks = stmt
            .query_map(params![fqn], |row| {
                let attrs_str: Option<String> = row.get(15)?;
                let attrs = attrs_str
                    .and_then(|s| serde_json::from_str(&s).ok())
                    .unwrap_or_else(|| std::collections::HashMap::new());

                Ok(Chunk {
                    chunk_id: row.get(0)?,
                    repo_id: row.get(1)?,
                    snapshot_id: row.get(2)?,
                    file_path: row.get(3)?,
                    start_line: row.get(4)?,
                    end_line: row.get(5)?,
                    kind: row.get(6)?,
                    fqn: row.get(7)?,
                    language: row.get(8)?,
                    symbol_visibility: row.get(9)?,
                    content: row.get(10)?,
                    content_hash: row.get(11)?,
                    summary: row.get(12)?,
                    importance: row.get(13)?,
                    is_deleted: row.get(14)?,
                    attrs,
                    created_at: chrono::DateTime::from_timestamp(row.get(16)?, 0)
                        .unwrap_or_default(),
                    updated_at: chrono::DateTime::from_timestamp(row.get(17)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        Ok(chunks)
    }

    async fn soft_delete_file_chunks(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE chunks SET is_deleted = 1
             WHERE repo_id = ?1 AND snapshot_id = ?2 AND file_path = ?3",
            params![repo_id, snapshot_id, file_path],
        )?;
        Ok(())
    }

    async fn save_dependency(&self, dep: &Dependency) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO dependencies (id, from_chunk_id, to_chunk_id, relationship, confidence, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                &dep.id,
                &dep.from_chunk_id,
                &dep.to_chunk_id,
                serde_json::to_string(&dep.relationship).unwrap_or_default(),
                dep.confidence,
                dep.created_at.timestamp()
            ],
        )?;
        Ok(())
    }

    async fn save_dependencies(&self, deps: &[Dependency]) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let tx = conn.unchecked_transaction()?;

        for dep in deps {
            tx.execute(
                "INSERT OR REPLACE INTO dependencies (id, from_chunk_id, to_chunk_id, relationship, confidence, created_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    &dep.id,
                    &dep.from_chunk_id,
                    &dep.to_chunk_id,
                    serde_json::to_string(&dep.relationship).unwrap_or_default(),
                    dep.confidence,
                    dep.created_at.timestamp()
                ],
            )?;
        }

        tx.commit()?;
        Ok(())
    }

    async fn get_dependencies_from(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, from_chunk_id, to_chunk_id, relationship, confidence, created_at
             FROM dependencies WHERE from_chunk_id = ?1",
        )?;

        let deps = stmt
            .query_map(params![chunk_id], |row| {
                let relationship_str: String = row.get(3)?;
                let relationship = serde_json::from_str(&relationship_str)
                    .unwrap_or(crate::features::storage::domain::models::DependencyType::Calls);

                Ok(Dependency {
                    id: row.get(0)?,
                    from_chunk_id: row.get(1)?,
                    to_chunk_id: row.get(2)?,
                    relationship,
                    confidence: row.get(4)?,
                    created_at: chrono::DateTime::from_timestamp(row.get(5)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        Ok(deps)
    }

    async fn get_dependencies_to(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, from_chunk_id, to_chunk_id, relationship, confidence, created_at
             FROM dependencies WHERE to_chunk_id = ?1",
        )?;

        let deps = stmt
            .query_map(params![chunk_id], |row| {
                let relationship_str: String = row.get(3)?;
                let relationship = serde_json::from_str(&relationship_str)
                    .unwrap_or(crate::features::storage::domain::models::DependencyType::Calls);

                Ok(Dependency {
                    id: row.get(0)?,
                    from_chunk_id: row.get(1)?,
                    to_chunk_id: row.get(2)?,
                    relationship,
                    confidence: row.get(4)?,
                    created_at: chrono::DateTime::from_timestamp(row.get(5)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        Ok(deps)
    }

    async fn get_transitive_dependencies(
        &self,
        chunk_id: &str,
        max_depth: usize,
    ) -> Result<Vec<String>> {
        use std::collections::{HashSet, VecDeque};

        let mut visited = HashSet::new();
        let mut queue = VecDeque::new();
        let mut result = Vec::new();

        queue.push_back((chunk_id.to_string(), 0));
        visited.insert(chunk_id.to_string());

        while let Some((current_id, depth)) = queue.pop_front() {
            if depth >= max_depth {
                continue;
            }

            let deps = self.get_dependencies_from(&current_id).await?;
            for dep in deps {
                if !visited.contains(&dep.to_chunk_id) {
                    visited.insert(dep.to_chunk_id.clone());
                    result.push(dep.to_chunk_id.clone());
                    queue.push_back((dep.to_chunk_id, depth + 1));
                }
            }
        }

        Ok(result)
    }

    async fn get_file_hash(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<Option<String>> {
        let conn = self.conn.lock().unwrap();

        let hash = conn
            .query_row(
                "SELECT content_hash FROM file_metadata
                 WHERE repo_id = ?1 AND snapshot_id = ?2 AND file_path = ?3",
                params![repo_id, snapshot_id, file_path],
                |row| row.get(0),
            )
            .optional()?;

        Ok(hash)
    }

    async fn update_file_metadata(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
        content_hash: String,
    ) -> Result<()> {
        let conn = self.conn.lock().unwrap();

        conn.execute(
            "INSERT OR REPLACE INTO file_metadata (repo_id, snapshot_id, file_path, content_hash, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                repo_id,
                snapshot_id,
                file_path,
                content_hash,
                chrono::Utc::now().timestamp()
            ],
        )?;

        Ok(())
    }

    async fn search_content(&self, query: &str, limit: usize) -> Result<Vec<Chunk>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                    kind, fqn, language, symbol_visibility, content, content_hash, summary,
                    importance, is_deleted, attrs, created_at, updated_at
             FROM chunks WHERE content LIKE ?1 AND is_deleted = 0 LIMIT ?2",
        )?;

        let search_pattern = format!("%{}%", query);
        let chunks = stmt
            .query_map(params![search_pattern, limit as i64], |row| {
                let attrs_str: Option<String> = row.get(15)?;
                let attrs = attrs_str
                    .and_then(|s| serde_json::from_str(&s).ok())
                    .unwrap_or_else(|| std::collections::HashMap::new());

                Ok(Chunk {
                    chunk_id: row.get(0)?,
                    repo_id: row.get(1)?,
                    snapshot_id: row.get(2)?,
                    file_path: row.get(3)?,
                    start_line: row.get(4)?,
                    end_line: row.get(5)?,
                    kind: row.get(6)?,
                    fqn: row.get(7)?,
                    language: row.get(8)?,
                    symbol_visibility: row.get(9)?,
                    content: row.get(10)?,
                    content_hash: row.get(11)?,
                    summary: row.get(12)?,
                    importance: row.get(13)?,
                    is_deleted: row.get(14)?,
                    attrs,
                    created_at: chrono::DateTime::from_timestamp(row.get(16)?, 0)
                        .unwrap_or_default(),
                    updated_at: chrono::DateTime::from_timestamp(row.get(17)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        Ok(chunks)
    }

    async fn get_chunks_by_kind(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        kind: &str,
    ) -> Result<Vec<Chunk>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT chunk_id, repo_id, snapshot_id, file_path, start_line, end_line,
                    kind, fqn, language, symbol_visibility, content, content_hash, summary,
                    importance, is_deleted, attrs, created_at, updated_at
             FROM chunks WHERE repo_id = ?1 AND snapshot_id = ?2 AND kind = ?3 AND is_deleted = 0",
        )?;

        let chunks = stmt
            .query_map(params![repo_id, snapshot_id, kind], |row| {
                let attrs_str: Option<String> = row.get(15)?;
                let attrs = attrs_str
                    .and_then(|s| serde_json::from_str(&s).ok())
                    .unwrap_or_else(|| std::collections::HashMap::new());

                Ok(Chunk {
                    chunk_id: row.get(0)?,
                    repo_id: row.get(1)?,
                    snapshot_id: row.get(2)?,
                    file_path: row.get(3)?,
                    start_line: row.get(4)?,
                    end_line: row.get(5)?,
                    kind: row.get(6)?,
                    fqn: row.get(7)?,
                    language: row.get(8)?,
                    symbol_visibility: row.get(9)?,
                    content: row.get(10)?,
                    content_hash: row.get(11)?,
                    summary: row.get(12)?,
                    importance: row.get(13)?,
                    is_deleted: row.get(14)?,
                    attrs,
                    created_at: chrono::DateTime::from_timestamp(row.get(16)?, 0)
                        .unwrap_or_default(),
                    updated_at: chrono::DateTime::from_timestamp(row.get(17)?, 0)
                        .unwrap_or_default(),
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        Ok(chunks)
    }

    async fn count_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<usize> {
        let conn = self.conn.lock().unwrap();
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM chunks WHERE repo_id = ?1 AND snapshot_id = ?2 AND is_deleted = 0",
            params![repo_id, snapshot_id],
            |row| row.get(0),
        )?;
        Ok(count as usize)
    }

    async fn get_stats(&self) -> Result<StorageStats> {
        let conn = self.conn.lock().unwrap();

        let total_repos: i64 =
            conn.query_row("SELECT COUNT(*) FROM repositories", [], |row| row.get(0))?;

        let total_snapshots: i64 =
            conn.query_row("SELECT COUNT(*) FROM snapshots", [], |row| row.get(0))?;

        let total_chunks: i64 = conn.query_row(
            "SELECT COUNT(*) FROM chunks WHERE is_deleted = 0",
            [],
            |row| row.get(0),
        )?;

        let total_dependencies: i64 =
            conn.query_row("SELECT COUNT(*) FROM dependencies", [], |row| row.get(0))?;

        // Get database file size (approximate)
        let storage_size_bytes: u64 = conn
            .query_row(
                "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()",
                [],
                |row| {
                    let pages: i64 = row.get(0)?;
                    let page_size: i64 = row.get(1)?;
                    Ok((pages * page_size) as u64)
                },
            )
            .unwrap_or(0);

        Ok(StorageStats {
            total_repos: total_repos as usize,
            total_snapshots: total_snapshots as usize,
            total_chunks: total_chunks as usize,
            total_dependencies: total_dependencies as usize,
            storage_size_bytes,
        })
    }
}
