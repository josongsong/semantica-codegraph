///! In-Memory Chunk Store (for testing)
///!
///! Simple HashMap-based implementation for unit tests.
///! NOT for production use.
use async_trait::async_trait;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use crate::features::storage::domain::models::{Chunk, Dependency, Repository, Snapshot};
use crate::features::storage::domain::ports::ChunkStore;
use crate::shared::models::Result;

#[derive(Clone)]
pub struct InMemoryChunkStore {
    repos: Arc<RwLock<HashMap<String, Repository>>>,
    snapshots: Arc<RwLock<HashMap<String, Snapshot>>>,
    chunks: Arc<RwLock<HashMap<String, Chunk>>>,
    dependencies: Arc<RwLock<Vec<Dependency>>>,
}

impl InMemoryChunkStore {
    pub fn new() -> Self {
        Self {
            repos: Arc::new(RwLock::new(HashMap::new())),
            snapshots: Arc::new(RwLock::new(HashMap::new())),
            chunks: Arc::new(RwLock::new(HashMap::new())),
            dependencies: Arc::new(RwLock::new(Vec::new())),
        }
    }

    /// Create new in-memory store (alias for new, for compatibility)
    pub fn in_memory() -> Result<Self> {
        Ok(Self::new())
    }
}

impl Default for InMemoryChunkStore {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl ChunkStore for InMemoryChunkStore {
    async fn save_repository(&self, repo: &Repository) -> Result<()> {
        self.repos
            .write()
            .unwrap()
            .insert(repo.repo_id.clone(), repo.clone());
        Ok(())
    }

    async fn get_repository(&self, repo_id: &str) -> Result<Option<Repository>> {
        Ok(self.repos.read().unwrap().get(repo_id).cloned())
    }

    async fn list_repositories(&self) -> Result<Vec<Repository>> {
        Ok(self.repos.read().unwrap().values().cloned().collect())
    }

    async fn save_snapshot(&self, snapshot: &Snapshot) -> Result<()> {
        self.snapshots
            .write()
            .unwrap()
            .insert(snapshot.snapshot_id.clone(), snapshot.clone());
        Ok(())
    }

    async fn get_snapshot(&self, snapshot_id: &str) -> Result<Option<Snapshot>> {
        Ok(self.snapshots.read().unwrap().get(snapshot_id).cloned())
    }

    async fn list_snapshots(&self, repo_id: &str) -> Result<Vec<Snapshot>> {
        Ok(self
            .snapshots
            .read()
            .unwrap()
            .values()
            .filter(|s| s.repo_id == repo_id)
            .cloned()
            .collect())
    }

    async fn save_chunk(&self, chunk: &Chunk) -> Result<()> {
        self.chunks
            .write()
            .unwrap()
            .insert(chunk.chunk_id.clone(), chunk.clone());
        Ok(())
    }

    async fn save_chunks(&self, chunks: &[Chunk]) -> Result<()> {
        let mut store = self.chunks.write().unwrap();
        for chunk in chunks {
            store.insert(chunk.chunk_id.clone(), chunk.clone());
        }
        Ok(())
    }

    async fn get_chunk(&self, chunk_id: &str) -> Result<Option<Chunk>> {
        Ok(self.chunks.read().unwrap().get(chunk_id).cloned())
    }

    async fn get_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<Vec<Chunk>> {
        Ok(self
            .chunks
            .read()
            .unwrap()
            .values()
            .filter(|c| c.repo_id == repo_id && c.snapshot_id == snapshot_id && !c.is_deleted)
            .cloned()
            .collect())
    }

    async fn get_chunks_by_file(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<Vec<Chunk>> {
        Ok(self
            .chunks
            .read()
            .unwrap()
            .values()
            .filter(|c| {
                c.repo_id == repo_id
                    && c.snapshot_id == snapshot_id
                    && c.file_path == file_path
                    && !c.is_deleted
            })
            .cloned()
            .collect())
    }

    async fn get_chunks_by_fqn(&self, fqn: &str) -> Result<Vec<Chunk>> {
        Ok(self
            .chunks
            .read()
            .unwrap()
            .values()
            .filter(|c| c.fqn.as_deref() == Some(fqn) && !c.is_deleted)
            .cloned()
            .collect())
    }

    async fn soft_delete_file_chunks(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
    ) -> Result<()> {
        let mut store = self.chunks.write().unwrap();
        for chunk in store.values_mut() {
            if chunk.repo_id == repo_id
                && chunk.snapshot_id == snapshot_id
                && chunk.file_path == file_path
            {
                chunk.is_deleted = true;
            }
        }
        Ok(())
    }

    async fn save_dependency(&self, dep: &Dependency) -> Result<()> {
        self.dependencies.write().unwrap().push(dep.clone());
        Ok(())
    }

    async fn save_dependencies(&self, deps: &[Dependency]) -> Result<()> {
        self.dependencies.write().unwrap().extend_from_slice(deps);
        Ok(())
    }

    async fn get_dependencies_from(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        Ok(self
            .dependencies
            .read()
            .unwrap()
            .iter()
            .filter(|d| d.from_chunk_id == chunk_id)
            .cloned()
            .collect())
    }

    async fn get_dependencies_to(&self, chunk_id: &str) -> Result<Vec<Dependency>> {
        Ok(self
            .dependencies
            .read()
            .unwrap()
            .iter()
            .filter(|d| d.to_chunk_id == chunk_id)
            .cloned()
            .collect())
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

            let deps = self.dependencies.read().unwrap();
            for dep in deps.iter() {
                if dep.from_chunk_id == current_id && !visited.contains(&dep.to_chunk_id) {
                    visited.insert(dep.to_chunk_id.clone());
                    result.push(dep.to_chunk_id.clone());
                    queue.push_back((dep.to_chunk_id.clone(), depth + 1));
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
        // In-memory implementation doesn't persist file hashes
        // Return None (file never indexed)
        Ok(None)
    }

    async fn update_file_metadata(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        file_path: &str,
        content_hash: String,
    ) -> Result<()> {
        // In-memory implementation doesn't persist metadata
        Ok(())
    }

    async fn search_content(&self, query: &str, limit: usize) -> Result<Vec<Chunk>> {
        // Simple substring search in content
        let chunks = self.chunks.read().unwrap();
        let results: Vec<Chunk> = chunks
            .values()
            .filter(|c| !c.is_deleted && c.content.contains(query))
            .take(limit)
            .cloned()
            .collect();
        Ok(results)
    }

    async fn get_chunks_by_kind(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        kind: &str,
    ) -> Result<Vec<Chunk>> {
        let chunks = self.chunks.read().unwrap();
        Ok(chunks
            .values()
            .filter(|c| {
                c.repo_id == repo_id
                    && c.snapshot_id == snapshot_id
                    && c.kind == kind
                    && !c.is_deleted
            })
            .cloned()
            .collect())
    }

    async fn count_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<usize> {
        let chunks = self.chunks.read().unwrap();
        Ok(chunks
            .values()
            .filter(|c| c.repo_id == repo_id && c.snapshot_id == snapshot_id && !c.is_deleted)
            .count())
    }

    async fn get_stats(&self) -> Result<crate::features::storage::domain::ports::StorageStats> {
        let repos = self.repos.read().unwrap();
        let snapshots = self.snapshots.read().unwrap();
        let chunks = self.chunks.read().unwrap();
        let deps = self.dependencies.read().unwrap();

        Ok(crate::features::storage::domain::ports::StorageStats {
            total_repos: repos.len(),
            total_snapshots: snapshots.len(),
            total_chunks: chunks.values().filter(|c| !c.is_deleted).count(),
            total_dependencies: deps.len(),
            storage_size_bytes: 0, // In-memory has no persistent size
        })
    }
}
