//! Query Router - Unified Search Interface
//!
//! # Purpose
//!
//! Provides a single entry point for all search queries:
//! - Lexical search (Tantivy BM25)
//! - Vector search (Future: ONNX embeddings)
//! - Hybrid search (RRF fusion)
//! - Symbol search (Future: Graph traversal)
//!
//! # Design
//!
//! ```text
//! SearchRequest → QueryRouter → Strategy Selection → Results
//!                       │
//!          ┌────────────┼────────────┐
//!          │            │            │
//!     Lexical       Vector       Symbol
//!     (Tantivy)     (ONNX)       (Graph)
//!          │            │            │
//!          └────────────┼────────────┘
//!                       │
//!                  RRF Fusion
//!                       │
//!                 SearchResponse
//! ```
//!
//! # RRF (Reciprocal Rank Fusion)
//!
//! Combines multiple result sets using reciprocal rank scoring:
//! ```text
//! RRF_score(d) = Σ (1 / (k + rank_i(d)))
//! ```
//! where k = 60 (Weaviate default), rank_i = rank in source i

use crate::features::lexical::tantivy_index::{SearchHit, TantivyLexicalIndex};
use crate::features::multi_index::ports::IndexError;
use std::collections::HashMap;
use std::sync::Arc;

/// Unified search request.
#[derive(Debug, Clone)]
pub struct SearchRequest {
    /// Search query (natural language or keywords)
    pub query: String,

    /// Filters (file path, repo ID, etc.)
    pub filters: Vec<Filter>,

    /// Result limit
    pub limit: usize,

    /// Hybrid search configuration
    pub hybrid_config: Option<HybridSearchConfig>,
}

impl SearchRequest {
    pub fn new(query: impl Into<String>) -> Self {
        Self {
            query: query.into(),
            filters: Vec::new(),
            limit: 50,
            hybrid_config: None,
        }
    }

    pub fn with_filter(mut self, filter: Filter) -> Self {
        self.filters.push(filter);
        self
    }

    pub fn with_limit(mut self, limit: usize) -> Self {
        self.limit = limit;
        self
    }

    pub fn with_hybrid(mut self, config: HybridSearchConfig) -> Self {
        self.hybrid_config = Some(config);
        self
    }
}

/// Search filter.
#[derive(Debug, Clone)]
pub enum Filter {
    /// Filter by file path (glob pattern)
    FilePath(String),

    /// Filter by repository ID
    RepoId(String),

    /// Filter by chunk kind (function, class, file)
    ChunkKind(String),

    /// Custom filter (key-value)
    Custom(String, String),
}

/// Hybrid search configuration.
#[derive(Debug, Clone)]
pub struct HybridSearchConfig {
    /// Enable lexical search (BM25)
    pub enable_lexical: bool,

    /// Enable vector search (semantic)
    pub enable_vector: bool,

    /// Enable symbol search (graph)
    pub enable_symbol: bool,

    /// RRF k parameter (default: 60)
    pub rrf_k: f32,
}

impl Default for HybridSearchConfig {
    fn default() -> Self {
        Self {
            enable_lexical: true,
            enable_vector: false, // Not implemented yet
            enable_symbol: false, // Not implemented yet
            rrf_k: 60.0,
        }
    }
}

/// Unified search response.
#[derive(Debug, Clone)]
pub struct SearchResponse {
    /// Search hits
    pub hits: Vec<SearchHit>,

    /// Total results (before limit)
    pub total: usize,

    /// Search latency (ms)
    pub latency_ms: u64,

    /// Sources used (e.g., ["lexical", "vector"])
    pub sources: Vec<String>,
}

/// Query router for unified search.
pub struct QueryRouter {
    /// Lexical index
    lexical_index: Arc<TantivyLexicalIndex>,
    // Future: Vector index, Symbol index
}

impl QueryRouter {
    /// Create a new query router.
    pub fn new(lexical_index: Arc<TantivyLexicalIndex>) -> Self {
        Self { lexical_index }
    }

    /// Execute search query.
    pub async fn search(&self, request: &SearchRequest) -> Result<SearchResponse, IndexError> {
        let start = std::time::Instant::now();

        // Determine search strategy
        let config = request
            .hybrid_config
            .clone()
            .unwrap_or_else(HybridSearchConfig::default);

        let mut sources = Vec::new();
        let mut all_results = Vec::new();

        // 1. Lexical search (always enabled for now)
        if config.enable_lexical {
            let lexical_hits = self
                .lexical_index
                .search(&request.query, request.limit * 2)?;
            all_results.push(lexical_hits);
            sources.push("lexical".to_string());
        }

        // 2. Vector search (future)
        if config.enable_vector {
            // INTEGRATION PENDING: Use codegraph-ml embedding service
            // See: packages/codegraph-ml/ for vector embedding
            sources.push("vector".to_string());
        }

        // 3. Symbol search
        if config.enable_symbol {
            // INTEGRATION PENDING: Use cross_file::SymbolIndex
            // Impl exists at: cross_file/symbol_index.rs (556 LOC)
            sources.push("symbol".to_string());
        }

        // 4. Fusion (if multiple sources)
        let hits = if all_results.len() > 1 {
            self.rrf_fusion(all_results, config.rrf_k, request.limit)
        } else if all_results.len() == 1 {
            all_results.into_iter().next().unwrap()
        } else {
            Vec::new()
        };

        let latency_ms = start.elapsed().as_millis() as u64;

        Ok(SearchResponse {
            total: hits.len(),
            hits: hits.into_iter().take(request.limit).collect(),
            latency_ms,
            sources,
        })
    }

    /// RRF (Reciprocal Rank Fusion) algorithm.
    ///
    /// Combines multiple result sets using reciprocal rank scoring:
    /// ```text
    /// RRF_score(d) = Σ (1 / (k + rank_i(d)))
    /// ```
    ///
    /// Reference: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
    fn rrf_fusion(&self, result_sets: Vec<Vec<SearchHit>>, k: f32, limit: usize) -> Vec<SearchHit> {
        let mut scores: HashMap<String, (f32, SearchHit)> = HashMap::new();

        // Calculate RRF scores
        for result_set in result_sets {
            for (rank, hit) in result_set.into_iter().enumerate() {
                let rrf_score = 1.0 / (k + (rank + 1) as f32);

                scores
                    .entry(hit.file_path.clone())
                    .and_modify(|(score, _)| *score += rrf_score)
                    .or_insert((rrf_score, hit));
            }
        }

        // Sort by RRF score (descending)
        let mut ranked: Vec<_> = scores.into_values().collect();
        ranked.sort_by(|(score_a, _), (score_b, _)| {
            score_b
                .partial_cmp(score_a)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // Return top results
        ranked.into_iter().take(limit).map(|(_, hit)| hit).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::lexical::chunk_store::SqliteChunkStore;
    use crate::features::lexical::{FileToIndex, IndexingMode};
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_search_request_builder() {
        let request = SearchRequest::new("async function")
            .with_filter(Filter::FilePath("src/*.rs".to_string()))
            .with_limit(10);

        assert_eq!(request.query, "async function");
        assert_eq!(request.limit, 10);
        assert_eq!(request.filters.len(), 1);
    }

    #[tokio::test]
    async fn test_query_router_search() {
        let temp_dir = TempDir::new().unwrap();
        let index_dir = temp_dir.path().join("index");
        let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

        let lexical_index = Arc::new(
            TantivyLexicalIndex::new(
                &index_dir,
                chunk_store,
                "test_repo".to_string(),
                IndexingMode::Balanced,
            )
            .unwrap(),
        );

        // Index a file
        let files = vec![FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/main.rs".to_string(),
            content: r#"
            async fn fetch_data() {
                // Fetch data from API
                println!("Fetching...");
            }
            "#
            .to_string(),
        }];

        lexical_index.index_files_batch(&files, false).unwrap();

        // Search via router
        let router = QueryRouter::new(lexical_index);
        let request = SearchRequest::new("fetch").with_limit(5);

        let response = router.search(&request).await.unwrap();

        assert!(!response.hits.is_empty());
        assert!(response.sources.contains(&"lexical".to_string()));
        assert!(response.latency_ms < 1000); // < 1s
    }

    #[test]
    fn test_rrf_fusion() {
        let temp_dir = TempDir::new().unwrap();
        let index_dir = temp_dir.path().join("index");
        let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

        let lexical_index = Arc::new(
            TantivyLexicalIndex::new(
                &index_dir,
                chunk_store,
                "test_repo".to_string(),
                IndexingMode::Balanced,
            )
            .unwrap(),
        );

        let router = QueryRouter::new(lexical_index);

        // Mock result sets
        let set1 = vec![
            SearchHit {
                file_path: "file1.rs".to_string(),
                content: "content".to_string(),
                score: 10.0,
                line: None,
                chunk_id: None,
            },
            SearchHit {
                file_path: "file2.rs".to_string(),
                content: "content".to_string(),
                score: 8.0,
                line: None,
                chunk_id: None,
            },
        ];

        let set2 = vec![
            SearchHit {
                file_path: "file2.rs".to_string(), // Appears in both
                content: "content".to_string(),
                score: 9.0,
                line: None,
                chunk_id: None,
            },
            SearchHit {
                file_path: "file3.rs".to_string(),
                content: "content".to_string(),
                score: 7.0,
                line: None,
                chunk_id: None,
            },
        ];

        let fused = router.rrf_fusion(vec![set1, set2], 60.0, 10);

        // file2.rs should rank highest (appeared in both sets)
        assert_eq!(fused[0].file_path, "file2.rs");
    }
}
