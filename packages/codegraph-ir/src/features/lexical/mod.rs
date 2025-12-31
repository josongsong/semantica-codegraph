//! Lexical Search Index (SOTA Native Tantivy Implementation)
//!
//! # Architecture Overview
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────┐
//! │                    Lexical Search Layer                     │
//! ├─────────────────────────────────────────────────────────────┤
//! │  Query Router (Unified Search API)                          │
//! │    ↓                                                        │
//! │  TantivyLexicalIndex (IndexPlugin)                          │
//! │    ↓                    ↓                                   │
//! │  Tantivy Index      ChunkStore (SQLite)                     │
//! └─────────────────────────────────────────────────────────────┘
//! ```
//!
//! # Key Features
//!
//! - **Native Tantivy**: 2x faster than Lucene, no Python FFI overhead
//! - **3-gram + CamelCase Tokenizer**: "getUserName" → ["get", "User", "Name"]
//! - **Incremental Updates**: Tree-sitter + IndexPlugin.apply_delta()
//! - **Chunk Mapping**: file:line → chunk_id via SQLite
//! - **BM25 Ranking**: Default Tantivy similarity
//!
//! # Performance Targets
//!
//! - Indexing: 500+ files/s (vs Python 40 files/s = 12x)
//! - Search: < 5ms p95 (vs Python 15ms = 3x)
//! - Incremental: < 50ms for 10 files (vs Python 30-60s = 600x)
//!
//! # Usage
//!
//! ```text
//! use codegraph_ir::features::lexical::{TantivyLexicalIndex, IndexingMode};
//! use codegraph_ir::features::multi_index::MultiLayerIndexOrchestrator;
//!
//! // 1. Create index
//! let lexical_index = TantivyLexicalIndex::new(
//!     "data/tantivy_index",
//!     chunk_store,
//!     IndexingMode::BALANCED,
//! )?;
//!
//! // 2. Register with orchestrator
//! let orchestrator = MultiLayerIndexOrchestrator::new(config);
//! orchestrator.register_index(Box::new(lexical_index));
//!
//! // 3. Full indexing
//! let files = vec![FileToIndex { repo_id, file_path, content }];
//! lexical_index.index_files_batch(&files)?;
//!
//! // 4. Search
//! let hits = lexical_index.search(repo_id, snapshot_id, "async function", 50)?;
//! ```

pub mod extractor;
pub mod query_router;
pub mod schema;
pub mod tantivy_index;
pub mod tokenizer;

// Re-exports
pub use extractor::{ExtractedFields, FieldExtractor, RegexExtractor};
pub use query_router::{Filter, HybridSearchConfig, QueryRouter, SearchRequest, SearchResponse};
pub use schema::{build_schema, FIELD_CONTENT, FIELD_FILE_PATH, FIELD_REPO_ID};
pub use tantivy_index::{IndexingMode, SearchHit, TantivyLexicalIndex};
pub use tokenizer::{build_code_analyzer, build_ngram_analyzer, CamelCaseTokenizer};

// Re-export from storage (PostgreSQL chunk store)
pub use crate::features::storage::{Chunk, ChunkStore, InMemoryChunkStore, SqliteChunkStore};

// Legacy compatibility: re-export storage types as chunk_store module
pub mod chunk_store {
    pub use crate::features::storage::{Chunk, ChunkStore, InMemoryChunkStore, SqliteChunkStore};
}

// Re-export from multi_index for convenience
pub use crate::features::multi_index::ports::IndexError;

/// File to index (immutable)
#[derive(Debug, Clone)]
pub struct FileToIndex {
    pub repo_id: String,
    pub file_path: String,
    pub content: String,
}

impl FileToIndex {
    pub fn new(
        repo_id: impl Into<String>,
        file_path: impl Into<String>,
        content: impl Into<String>,
    ) -> Result<Self, IndexError> {
        let repo_id = repo_id.into();
        let file_path = file_path.into();
        let content = content.into();

        if repo_id.is_empty() {
            return Err(IndexError::InvalidInput(
                "repo_id cannot be empty".to_string(),
            ));
        }
        if file_path.is_empty() {
            return Err(IndexError::InvalidInput(
                "file_path cannot be empty".to_string(),
            ));
        }

        Ok(Self {
            repo_id,
            file_path,
            content,
        })
    }
}

/// Indexing result (batch operation)
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct IndexingResult {
    pub total_files: usize,
    pub success_count: usize,
    #[serde(rename = "failures")]
    pub failed_files: Vec<(String, String)>, // (file_path, error)
    #[serde(rename = "duration")]
    pub duration_seconds: f64,
}

impl IndexingResult {
    pub fn is_complete_success(&self) -> bool {
        self.success_count == self.total_files
    }

    pub fn is_partial_success(&self) -> bool {
        self.success_count > 0 && self.success_count < self.total_files
    }

    pub fn is_complete_failure(&self) -> bool {
        self.success_count == 0
    }

    pub fn throughput(&self) -> f64 {
        self.success_count as f64 / self.duration_seconds.max(0.001)
    }
}
