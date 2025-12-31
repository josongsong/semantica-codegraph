//! Chunk Repository Port - Dependency Inversion Principle (DIP)
//!
//! This trait defines the abstraction for chunk storage, allowing:
//! - Swappable implementations (PostgreSQL, SQLite, In-Memory)
//! - Easy testing with mock repositories
//! - No infrastructure dependencies in domain layer
//!
//! # Architecture
//! ```text
//! ┌────────────────┐
//! │ Domain Layer   │
//! │  (ChunkService)│
//! └───────┬────────┘
//!         │ depends on
//!         ▼
//! ┌────────────────────┐
//! │ Port (this trait)  │ ◄── Abstraction (no concrete deps)
//! └────────┬───────────┘
//!          │ implemented by
//!          ▼
//! ┌────────────────────┐
//! │ Infrastructure     │
//! │  - PostgresRepo    │
//! │  - SQLiteRepo      │
//! │  - InMemoryRepo    │
//! └────────────────────┘
//! ```

use crate::shared::models::Result;

/// Chunk identifier
pub type ChunkId = String;

/// Minimal chunk model for repository operations
///
/// This is a lightweight DTO (Data Transfer Object) for the repository layer.
/// Full `Chunk` domain model is in `domain/chunk.rs`.
#[derive(Debug, Clone)]
pub struct ChunkDto {
    pub id: ChunkId,
    pub file_path: String,
    pub content: String,
    pub start_line: usize,
    pub end_line: usize,
    pub language: String,
    pub embedding: Option<Vec<f32>>,
}

/// Chunk repository abstraction (Port in Hexagonal Architecture)
///
/// This trait must be implemented by all chunk storage backends.
/// It defines **what** operations are needed, not **how** they are implemented.
pub trait ChunkRepository: Send + Sync {
    /// Save a chunk to the repository
    ///
    /// # Arguments
    /// * `chunk` - Chunk to save
    ///
    /// # Returns
    /// * `Ok(chunk_id)` - Successfully saved, returns assigned ID
    /// * `Err(...)` - Storage error
    fn save(&self, chunk: ChunkDto) -> Result<ChunkId>;

    /// Save multiple chunks in a batch (optimized for bulk insert)
    ///
    /// # Arguments
    /// * `chunks` - Vector of chunks to save
    ///
    /// # Returns
    /// * `Ok(count)` - Number of chunks successfully saved
    /// * `Err(...)` - Storage error
    fn save_batch(&self, chunks: Vec<ChunkDto>) -> Result<usize> {
        // Default implementation: sequential saves
        // Implementations can override for optimized batch insert
        let mut count = 0;
        for chunk in chunks {
            self.save(chunk)?;
            count += 1;
        }
        Ok(count)
    }

    /// Find chunk by ID
    ///
    /// # Returns
    /// * `Ok(Some(chunk))` - Chunk found
    /// * `Ok(None)` - Chunk not found
    /// * `Err(...)` - Storage error
    fn find_by_id(&self, id: &ChunkId) -> Result<Option<ChunkDto>>;

    /// Find all chunks for a file
    ///
    /// # Arguments
    /// * `file_path` - Relative path to file
    ///
    /// # Returns
    /// * `Ok(chunks)` - All chunks for the file (may be empty)
    /// * `Err(...)` - Storage error
    fn find_by_file(&self, file_path: &str) -> Result<Vec<ChunkDto>>;

    /// Find chunks by line range
    ///
    /// Useful for finding chunks that overlap with a specific line range.
    ///
    /// # Arguments
    /// * `file_path` - File path
    /// * `start_line` - Start line (inclusive)
    /// * `end_line` - End line (inclusive)
    ///
    /// # Returns
    /// * `Ok(chunks)` - Chunks overlapping the range
    /// * `Err(...)` - Storage error
    fn find_by_line_range(
        &self,
        file_path: &str,
        start_line: usize,
        end_line: usize,
    ) -> Result<Vec<ChunkDto>>;

    /// Delete chunk by ID
    ///
    /// # Returns
    /// * `Ok(true)` - Chunk was deleted
    /// * `Ok(false)` - Chunk did not exist
    /// * `Err(...)` - Storage error
    fn delete(&self, id: &ChunkId) -> Result<bool>;

    /// Delete all chunks for a file
    ///
    /// # Returns
    /// * `Ok(count)` - Number of chunks deleted
    /// * `Err(...)` - Storage error
    fn delete_by_file(&self, file_path: &str) -> Result<usize>;

    /// Update chunk embedding
    ///
    /// Specialized method for updating embeddings without rewriting full chunk.
    ///
    /// # Returns
    /// * `Ok(true)` - Embedding updated
    /// * `Ok(false)` - Chunk not found
    /// * `Err(...)` - Storage error
    fn update_embedding(&self, id: &ChunkId, embedding: Vec<f32>) -> Result<bool>;

    /// Count total chunks in repository
    fn count(&self) -> Result<usize>;

    /// Count chunks for a specific file
    fn count_by_file(&self, file_path: &str) -> Result<usize>;
}

/// Mock chunk repository for testing
///
/// Use this in tests to avoid database dependencies.
///
/// # Example
/// ```
/// use codegraph_ir::features::chunking::ports::{ChunkRepository, MockChunkRepository};
///
/// let repo = MockChunkRepository::new();
/// let chunk = ChunkDto { ... };
/// repo.save(chunk)?;
/// ```
#[cfg(test)]
pub struct MockChunkRepository {
    chunks: std::sync::Mutex<std::collections::HashMap<ChunkId, ChunkDto>>,
}

#[cfg(test)]
impl MockChunkRepository {
    pub fn new() -> Self {
        Self {
            chunks: std::sync::Mutex::new(std::collections::HashMap::new()),
        }
    }
}

#[cfg(test)]
impl ChunkRepository for MockChunkRepository {
    fn save(&self, chunk: ChunkDto) -> Result<ChunkId> {
        let id = chunk.id.clone();
        self.chunks.lock().unwrap().insert(id.clone(), chunk);
        Ok(id)
    }

    fn find_by_id(&self, id: &ChunkId) -> Result<Option<ChunkDto>> {
        Ok(self.chunks.lock().unwrap().get(id).cloned())
    }

    fn find_by_file(&self, file_path: &str) -> Result<Vec<ChunkDto>> {
        Ok(self
            .chunks
            .lock()
            .unwrap()
            .values()
            .filter(|c| c.file_path == file_path)
            .cloned()
            .collect())
    }

    fn find_by_line_range(
        &self,
        file_path: &str,
        start_line: usize,
        end_line: usize,
    ) -> Result<Vec<ChunkDto>> {
        Ok(self
            .chunks
            .lock()
            .unwrap()
            .values()
            .filter(|c| {
                c.file_path == file_path && c.start_line <= end_line && c.end_line >= start_line
            })
            .cloned()
            .collect())
    }

    fn delete(&self, id: &ChunkId) -> Result<bool> {
        Ok(self.chunks.lock().unwrap().remove(id).is_some())
    }

    fn delete_by_file(&self, file_path: &str) -> Result<usize> {
        let mut chunks = self.chunks.lock().unwrap();
        let before = chunks.len();
        chunks.retain(|_, c| c.file_path != file_path);
        Ok(before - chunks.len())
    }

    fn update_embedding(&self, id: &ChunkId, embedding: Vec<f32>) -> Result<bool> {
        let mut chunks = self.chunks.lock().unwrap();
        if let Some(chunk) = chunks.get_mut(id) {
            chunk.embedding = Some(embedding);
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn count(&self) -> Result<usize> {
        Ok(self.chunks.lock().unwrap().len())
    }

    fn count_by_file(&self, file_path: &str) -> Result<usize> {
        Ok(self
            .chunks
            .lock()
            .unwrap()
            .values()
            .filter(|c| c.file_path == file_path)
            .count())
    }
}
