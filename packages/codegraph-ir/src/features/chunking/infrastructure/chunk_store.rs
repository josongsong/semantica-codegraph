//! Chunk Store for P0-2: Partial Chunk Regeneration
//!
//! Enables O(n_affected) chunk updates instead of O(n_files) full rebuild.
//!
//! ## Design
//!
//! ```text
//! ChunkStore
//! ├── file_index: HashMap<FileId, Vec<ChunkId>>  // O(1) lookup of chunks by file
//! └── chunks: Arc<HashMap<ChunkId, Chunk>>       // Persistent storage with structural sharing
//! ```
//!
//! ## Performance
//!
//! - **Before**: Full rebuild = O(n_files) = 1000 files × 0.2ms = 200ms
//! - **After**: Partial rebuild = O(n_affected) = 30 files × 0.2ms = 6ms
//! - **Speedup**: 33x for typical incremental update
//!
//! ## Usage
//!
//! ```ignore
//! // Initial build
//! let mut store = ChunkStore::new();
//! store.insert_all(initial_chunks);
//!
//! // Incremental update
//! for affected_file in &affected_files {
//!     store.remove_chunks_for_file(affected_file);
//!     let new_chunks = build_chunks(affected_file);
//!     store.insert_all(new_chunks);
//! }
//! ```

use std::collections::HashMap;
use std::sync::Arc;

use super::super::domain::{Chunk, ChunkId};

/// File ID for chunk indexing
pub type FileId = String;

/// Persistent chunk storage with O(1) file-based lookup
///
/// P0-2: Enables incremental chunk updates by tracking which chunks belong to which files.
/// Uses Arc for structural sharing (cheap clones for MVCC-style updates).
#[derive(Debug, Clone)]
pub struct ChunkStore {
    /// File → Chunk IDs mapping
    /// Enables O(1) lookup of "which chunks belong to this file?"
    file_index: HashMap<FileId, Vec<ChunkId>>,

    /// Chunk ID → Chunk mapping
    /// Arc enables cheap clones for persistent data structure pattern
    /// (multiple versions can share unchanged chunks)
    chunks: Arc<HashMap<ChunkId, Chunk>>,
}

impl ChunkStore {
    /// Create empty chunk store
    pub fn new() -> Self {
        Self {
            file_index: HashMap::new(),
            chunks: Arc::new(HashMap::new()),
        }
    }

    /// Create chunk store from initial chunks
    ///
    /// Builds file_index automatically by scanning chunk file_paths.
    pub fn from_chunks(chunks: Vec<Chunk>) -> Self {
        let mut store = Self::new();
        store.insert_all(chunks);
        store
    }

    /// Insert a single chunk
    ///
    /// Updates both chunks map and file_index.
    pub fn insert(&mut self, chunk: Chunk) {
        let chunk_id = chunk.chunk_id.clone();
        let file_id = chunk.file_path.clone().unwrap_or_default();

        // Update file index
        if !file_id.is_empty() {
            self.file_index
                .entry(file_id)
                .or_insert_with(Vec::new)
                .push(chunk_id.clone());
        }

        // Update chunks map (requires Arc::make_mut for COW)
        Arc::make_mut(&mut self.chunks).insert(chunk_id, chunk);
    }

    /// Insert multiple chunks efficiently
    ///
    /// Batches updates to minimize Arc::make_mut calls.
    pub fn insert_all(&mut self, chunks: Vec<Chunk>) {
        if chunks.is_empty() {
            return;
        }

        // Get mutable reference once (COW happens here if needed)
        let chunks_map = Arc::make_mut(&mut self.chunks);

        for chunk in chunks {
            let chunk_id = chunk.chunk_id.clone();
            let file_id = chunk.file_path.clone().unwrap_or_default();

            // Update file index
            if !file_id.is_empty() {
                self.file_index
                    .entry(file_id)
                    .or_insert_with(Vec::new)
                    .push(chunk_id.clone());
            }

            // Insert chunk
            chunks_map.insert(chunk_id, chunk);
        }
    }

    /// Remove all chunks for a file
    ///
    /// P0-2 core operation: Remove old chunks before inserting new ones.
    /// Returns the removed chunk IDs for tracking.
    pub fn remove_chunks_for_file(&mut self, file_id: &FileId) -> Vec<ChunkId> {
        // Get chunk IDs for this file
        let chunk_ids = match self.file_index.remove(file_id) {
            Some(ids) => ids,
            None => return Vec::new(), // File has no chunks
        };

        // Remove chunks from map
        let chunks_map = Arc::make_mut(&mut self.chunks);
        for chunk_id in &chunk_ids {
            chunks_map.remove(chunk_id);
        }

        chunk_ids
    }

    /// Get chunk by ID
    pub fn get(&self, chunk_id: &ChunkId) -> Option<&Chunk> {
        self.chunks.get(chunk_id)
    }

    /// Get all chunk IDs for a file
    pub fn get_chunk_ids_for_file(&self, file_id: &FileId) -> Option<&Vec<ChunkId>> {
        self.file_index.get(file_id)
    }

    /// Get all chunks for a file
    pub fn get_chunks_for_file(&self, file_id: &FileId) -> Vec<Chunk> {
        match self.file_index.get(file_id) {
            Some(chunk_ids) => chunk_ids
                .iter()
                .filter_map(|id| self.chunks.get(id).cloned())
                .collect(),
            None => Vec::new(),
        }
    }

    /// Get all chunks (for export)
    pub fn get_all_chunks(&self) -> Vec<Chunk> {
        self.chunks.values().cloned().collect()
    }

    /// Get total chunk count
    pub fn len(&self) -> usize {
        self.chunks.len()
    }

    /// Check if store is empty
    pub fn is_empty(&self) -> bool {
        self.chunks.is_empty()
    }

    /// Get number of files tracked
    pub fn file_count(&self) -> usize {
        self.file_index.len()
    }

    /// Clear all chunks
    pub fn clear(&mut self) {
        self.file_index.clear();
        self.chunks = Arc::new(HashMap::new());
    }

    /// Clone with structural sharing
    ///
    /// Cheap operation due to Arc - only the file_index HashMap is cloned,
    /// the chunks Arc is just reference-counted.
    pub fn clone_shared(&self) -> Self {
        Self {
            file_index: self.file_index.clone(),
            chunks: Arc::clone(&self.chunks),
        }
    }

    /// Get memory usage estimate (bytes)
    pub fn memory_usage(&self) -> usize {
        // Approximate: file_index + chunks map overhead
        let file_index_size = self.file_index.len() * 64; // Rough HashMap entry size
        let chunks_size = self.chunks.len() * 512; // Rough Chunk size estimate
        file_index_size + chunks_size
    }
}

impl Default for ChunkStore {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::chunking::domain::{Chunk, ChunkKind};

    fn make_test_chunk(chunk_id: &str, file_path: &str, fqn: &str) -> Chunk {
        Chunk {
            chunk_id: chunk_id.to_string(),
            repo_id: "test-repo".to_string(),
            snapshot_id: "snap-1".to_string(),
            project_id: None,
            module_path: None,
            file_path: Some(file_path.to_string()),
            kind: ChunkKind::Function,
            fqn: fqn.to_string(),
            start_line: Some(1),
            end_line: Some(10),
            original_start_line: Some(1),
            original_end_line: Some(10),
            content_hash: Some("abc123".to_string()),
            parent_id: None,
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: Default::default(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            base_chunk_id: None,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
        }
    }

    #[test]
    fn test_chunk_store_new() {
        let store = ChunkStore::new();
        assert_eq!(store.len(), 0);
        assert_eq!(store.file_count(), 0);
        assert!(store.is_empty());
    }

    #[test]
    fn test_chunk_store_insert() {
        let mut store = ChunkStore::new();
        let chunk = make_test_chunk("chunk1", "src/main.py", "main.foo");

        store.insert(chunk);

        assert_eq!(store.len(), 1);
        assert_eq!(store.file_count(), 1);
        assert!(store.get(&"chunk1".to_string()).is_some());
    }

    #[test]
    fn test_chunk_store_insert_all() {
        let mut store = ChunkStore::new();
        let chunks = vec![
            make_test_chunk("chunk1", "src/main.py", "main.foo"),
            make_test_chunk("chunk2", "src/main.py", "main.bar"),
            make_test_chunk("chunk3", "src/utils.py", "utils.helper"),
        ];

        store.insert_all(chunks);

        assert_eq!(store.len(), 3);
        assert_eq!(store.file_count(), 2); // 2 files
    }

    #[test]
    fn test_chunk_store_get_chunks_for_file() {
        let mut store = ChunkStore::new();
        store.insert_all(vec![
            make_test_chunk("chunk1", "src/main.py", "main.foo"),
            make_test_chunk("chunk2", "src/main.py", "main.bar"),
            make_test_chunk("chunk3", "src/utils.py", "utils.helper"),
        ]);

        let main_chunks = store.get_chunks_for_file(&"src/main.py".to_string());
        assert_eq!(main_chunks.len(), 2);

        let utils_chunks = store.get_chunks_for_file(&"src/utils.py".to_string());
        assert_eq!(utils_chunks.len(), 1);
    }

    #[test]
    fn test_chunk_store_remove_chunks_for_file() {
        let mut store = ChunkStore::new();
        store.insert_all(vec![
            make_test_chunk("chunk1", "src/main.py", "main.foo"),
            make_test_chunk("chunk2", "src/main.py", "main.bar"),
            make_test_chunk("chunk3", "src/utils.py", "utils.helper"),
        ]);

        // Remove main.py chunks
        let removed = store.remove_chunks_for_file(&"src/main.py".to_string());
        assert_eq!(removed.len(), 2);
        assert_eq!(store.len(), 1); // Only utils.py chunk remains
        assert_eq!(store.file_count(), 1);

        // Verify main.py chunks are gone
        let main_chunks = store.get_chunks_for_file(&"src/main.py".to_string());
        assert_eq!(main_chunks.len(), 0);

        // Verify utils.py chunk still exists
        let utils_chunks = store.get_chunks_for_file(&"src/utils.py".to_string());
        assert_eq!(utils_chunks.len(), 1);
    }

    #[test]
    fn test_chunk_store_incremental_update() {
        let mut store = ChunkStore::new();

        // Initial build
        store.insert_all(vec![
            make_test_chunk("chunk1", "src/main.py", "main.foo"),
            make_test_chunk("chunk2", "src/main.py", "main.bar"),
            make_test_chunk("chunk3", "src/utils.py", "utils.helper"),
        ]);
        assert_eq!(store.len(), 3);

        // Incremental update: main.py changed
        store.remove_chunks_for_file(&"src/main.py".to_string());
        store.insert_all(vec![
            make_test_chunk("chunk1_v2", "src/main.py", "main.foo"), // Updated
            make_test_chunk("chunk4", "src/main.py", "main.baz"),    // New
        ]);

        // Verify results
        assert_eq!(store.len(), 3); // utils.helper + foo + baz
        assert!(store.get(&"chunk1".to_string()).is_none()); // Old version gone
        assert!(store.get(&"chunk1_v2".to_string()).is_some()); // New version present
        assert!(store.get(&"chunk4".to_string()).is_some()); // New chunk present
        assert!(store.get(&"chunk3".to_string()).is_some()); // utils.helper unchanged
    }

    #[test]
    fn test_chunk_store_clone_shared() {
        let mut store1 = ChunkStore::new();
        store1.insert(make_test_chunk("chunk1", "src/main.py", "main.foo"));

        // Clone with structural sharing
        let store2 = store1.clone_shared();

        // Both point to same chunks Arc
        assert_eq!(store1.len(), 1);
        assert_eq!(store2.len(), 1);
        assert_eq!(Arc::strong_count(&store1.chunks), 2); // Shared
    }

    #[test]
    fn test_chunk_store_from_chunks() {
        let chunks = vec![
            make_test_chunk("chunk1", "src/main.py", "main.foo"),
            make_test_chunk("chunk2", "src/utils.py", "utils.helper"),
        ];

        let store = ChunkStore::from_chunks(chunks);

        assert_eq!(store.len(), 2);
        assert_eq!(store.file_count(), 2);
    }
}
