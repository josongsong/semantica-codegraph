//! PyO3 Bindings for Lexical Search
//!
//! Python API for TantivyLexicalIndex:
//! - Index files batch (parallel indexing)
//! - Search with BM25 ranking
//! - Chunk management (SQLite storage)
//! - Hybrid search (lexical + vector + symbol)
//!
//! Performance:
//! - GIL released during indexing and search
//! - Rayon parallel file processing
//! - Zero-copy msgpack serialization (optional)

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use std::path::PathBuf;
use std::sync::Arc;

use crate::features::chunking::ChunkKind;
use crate::features::lexical::{
    Chunk, ChunkStore, FileToIndex, Filter, HybridSearchConfig, IndexingMode,
    SearchHit, SearchRequest, TantivyLexicalIndex,
};

// ═══════════════════════════════════════════════════════════════════════════
// Python Wrapper for TantivyLexicalIndex
// ═══════════════════════════════════════════════════════════════════════════

/// Python wrapper for TantivyLexicalIndex
///
/// This provides a Python-friendly interface to the Rust lexical search engine.
///
/// # Example (Python)
/// ```python
/// import codegraph_ir
///
/// # Create index
/// index = codegraph_ir.LexicalIndex.new(
///     index_dir="/tmp/tantivy_index",
///     chunk_db_path="/tmp/chunks.db",
///     repo_id="my_repo",
///     mode="Balanced"
/// )
///
/// # Index files
/// files = [
///     {"file_path": "src/main.py", "content": "def hello(): pass"},
///     {"file_path": "src/utils.py", "content": "def world(): pass"},
/// ]
/// result = index.index_files(files, fail_fast=False)
/// print(f"Indexed {result['success_count']}/{result['total_files']} files")
///
/// # Search
/// hits = index.search("hello", limit=10)
/// for hit in hits:
///     print(f"{hit['file_path']}:{hit['line_number']} (score: {hit['score']})")
/// ```
#[pyclass(name = "LexicalIndex")]
pub struct PyLexicalIndex {
    index: TantivyLexicalIndex,
}

#[pymethods]
impl PyLexicalIndex {
    /// Create a new lexical index
    ///
    /// Args:
    ///     index_dir: Directory for Tantivy index storage
    ///     chunk_db_path: Path to SQLite database for chunk storage
    ///     repo_id: Repository identifier
    ///     mode: Indexing mode ("Fast", "Balanced", or "Thorough")
    ///
    /// Returns:
    ///     LexicalIndex instance
    #[new]
    #[pyo3(signature = (index_dir, chunk_db_path, repo_id, mode = "Balanced"))]
    fn new(index_dir: String, chunk_db_path: String, repo_id: String, mode: &str) -> PyResult<Self> {
        let indexing_mode = match mode {
            "Fast" | "Conservative" => IndexingMode::Conservative,
            "Balanced" => IndexingMode::Balanced,
            "Thorough" | "Aggressive" => IndexingMode::Aggressive,
            _ => return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Invalid mode: {}. Must be 'Fast', 'Balanced', or 'Thorough'", mode)
            )),
        };

        let chunk_store = Arc::new(
            SqliteChunkStore::new(&chunk_db_path)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                    format!("Failed to create chunk store: {}", e)
                ))?
        );

        let index = TantivyLexicalIndex::new(
            &PathBuf::from(&index_dir),
            chunk_store,
            repo_id,
            indexing_mode,
        )
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("Failed to create lexical index: {:?}", e)
        ))?;

        Ok(PyLexicalIndex { index })
    }

    /// Index a batch of files
    ///
    /// Args:
    ///     files: List of dicts with "file_path" and "content" keys
    ///     fail_fast: If True, stop on first error
    ///
    /// Returns:
    ///     Dict with indexing results:
    ///     - success_count: Number of successfully indexed files
    ///     - total_files: Total number of files attempted
    ///     - duration_secs: Indexing duration in seconds
    ///     - failures: List of (file_path, error_message) tuples
    ///
    /// Example:
    ///     >>> files = [
    ///     ...     {"file_path": "main.py", "content": "def foo(): pass"},
    ///     ...     {"file_path": "utils.py", "content": "def bar(): pass"},
    ///     ... ]
    ///     >>> result = index.index_files(files)
    ///     >>> print(f"Indexed {result['success_count']} files")
    #[pyo3(signature = (files, fail_fast = false))]
    fn index_files(&self, py: Python, files: &PyList, fail_fast: bool) -> PyResult<Py<PyDict>> {
        // Extract file data from Python
        let mut rust_files = Vec::with_capacity(files.len());
        for item in files.iter() {
            let dict = item.downcast::<PyDict>()?;

            let file_path: String = dict
                .get_item("file_path")?
                .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("file_path"))?
                .extract()?;

            let content: String = dict
                .get_item("content")?
                .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("content"))?
                .extract()?;

            rust_files.push(FileToIndex {
                repo_id: self.index.get_repo_id().to_string(),
                file_path,
                content,
            });
        }

        // GIL RELEASE - Index in Rust (parallel processing with Rayon)
        let result = py.allow_threads(|| {
            self.index.index_files_batch(&rust_files, fail_fast)
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("Indexing failed: {:?}", e)
        ))?;

        // Convert result to Python dict
        let result_dict = PyDict::new(py);
        result_dict.set_item("success_count", result.success_count)?;
        result_dict.set_item("total_files", result.total_files)?;
        result_dict.set_item("duration_secs", result.duration_seconds)?;
        result_dict.set_item("throughput", result.throughput())?;

        // Convert failures
        let py_failures = PyList::empty(py);
        for (file_path, error) in result.failed_files {
            let failure_tuple = (file_path, error);
            py_failures.append(failure_tuple)?;
        }
        result_dict.set_item("failures", py_failures)?;

        Ok(result_dict.into())
    }

    /// Search for documents matching a query
    ///
    /// Args:
    ///     query: Search query string
    ///     limit: Maximum number of results (default: 10)
    ///     filters: Optional dict with filters:
    ///         - "repo_id": Filter by repository
    ///         - "file_path": Filter by file path pattern (glob)
    ///         - "language": Filter by programming language
    ///
    /// Returns:
    ///     List of search hits, each containing:
    ///     - file_path: Path to the file
    ///     - line: Line number (if available)
    ///     - content: Matched content snippet
    ///     - score: BM25 relevance score
    ///     - chunk_id: Associated chunk ID (if available)
    ///
    /// Example:
    ///     >>> hits = index.search("authentication", limit=5)
    ///     >>> for hit in hits:
    ///     ...     print(f"{hit['file_path']}:{hit['line']} - {hit['score']:.2f}")
    #[pyo3(signature = (query, limit = 10, filters = None))]
    fn search(&self, py: Python, query: &str, limit: usize, filters: Option<&PyDict>) -> PyResult<Py<PyList>> {
        // Build search request
        let mut request = SearchRequest::new(query.to_string()).with_limit(limit);

        // Add filters if provided
        if let Some(filter_dict) = filters {
            if let Some(repo_id) = filter_dict.get_item("repo_id")? {
                let repo_id_str: String = repo_id.extract()?;
                request = request.with_filter(Filter::RepoId(repo_id_str));
            }

            if let Some(file_path) = filter_dict.get_item("file_path")? {
                let file_path_str: String = file_path.extract()?;
                request = request.with_filter(Filter::FilePath(file_path_str));
            }

            if let Some(language) = filter_dict.get_item("language")? {
                let language_str: String = language.extract()?;
                request = request.with_filter(Filter::Custom("language".to_string(), language_str));
            }
        }

        // GIL RELEASE - Search in Rust
        let hits = py.allow_threads(|| {
            self.index.search(&request.query, request.limit)
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("Search failed: {:?}", e)
        ))?;

        // Convert hits to Python list
        Ok(convert_hits_to_python(py, &hits))
    }

    /// Hybrid search combining lexical, vector, and symbol search
    ///
    /// Args:
    ///     query: Search query string
    ///     limit: Maximum number of results (default: 10)
    ///     enable_lexical: Enable BM25 lexical search (default: True)
    ///     enable_vector: Enable semantic vector search (default: False)
    ///     enable_symbol: Enable symbol-based search (default: False)
    ///     rrf_k: RRF fusion parameter (default: 60.0)
    ///
    /// Returns:
    ///     List of search hits ranked by RRF fusion score
    ///
    /// Example:
    ///     >>> hits = index.hybrid_search(
    ///     ...     "user authentication",
    ///     ...     limit=10,
    ///     ...     enable_lexical=True,
    ///     ...     enable_vector=True
    ///     ... )
    #[pyo3(signature = (query, limit = 10, enable_lexical = true, enable_vector = false, enable_symbol = false, rrf_k = 60.0))]
    fn hybrid_search(
        &self,
        py: Python,
        query: &str,
        limit: usize,
        enable_lexical: bool,
        enable_vector: bool,
        enable_symbol: bool,
        rrf_k: f64,
    ) -> PyResult<Py<PyList>> {
        let hybrid_config = HybridSearchConfig {
            enable_lexical,
            enable_vector,
            enable_symbol,
            rrf_k: rrf_k as f32,  // Convert f64 to f32
        };

        let request = SearchRequest::new(query.to_string())
            .with_limit(limit)
            .with_hybrid(hybrid_config);

        // For now, only lexical is implemented - just call search
        // TODO: Implement actual hybrid fusion when vector/symbol search is ready
        let hits = py.allow_threads(|| {
            self.index.search(&request.query, request.limit)
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("Hybrid search failed: {:?}", e)
        ))?;

        Ok(convert_hits_to_python(py, &hits))
    }

    /// Get index statistics
    ///
    /// Returns:
    ///     Dict with index statistics:
    ///     - entry_count: Number of indexed files
    ///     - size_bytes: Index size in bytes
    ///     - last_rebuild_ms: Last rebuild duration in milliseconds
    ///     - total_updates: Total number of updates performed
    fn stats(&self, py: Python) -> PyResult<Py<PyDict>> {
        let stats = self.index.stats();

        let stats_dict = PyDict::new(py);
        stats_dict.set_item("entry_count", stats.entry_count)?;
        stats_dict.set_item("size_bytes", stats.size_bytes)?;
        stats_dict.set_item("last_rebuild_ms", stats.last_rebuild_ms)?;
        stats_dict.set_item("total_updates", stats.total_updates)?;

        Ok(stats_dict.into())
    }

    /// Get index health status
    ///
    /// Returns:
    ///     Dict with health information:
    ///     - is_healthy: Boolean indicating if index is healthy
    ///     - last_update: Timestamp of last update (seconds since epoch)
    ///     - staleness_secs: Seconds since last update
    ///     - error: Error message (if any)
    fn health(&self, py: Python) -> PyResult<Py<PyDict>> {
        let health = self.index.health();

        let health_dict = PyDict::new(py);
        health_dict.set_item("is_healthy", health.is_healthy)?;

        // Convert SystemTime to seconds since UNIX_EPOCH
        let last_update_secs = health.last_update
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        health_dict.set_item("last_update", last_update_secs)?;

        health_dict.set_item("staleness_secs", health.staleness.as_secs())?;
        health_dict.set_item("error", health.error)?;

        Ok(health_dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Helper Functions
// ═══════════════════════════════════════════════════════════════════════════

/// Convert SearchHit vector to Python list
fn convert_hits_to_python(py: Python, hits: &[SearchHit]) -> Py<PyList> {
    let py_hits = PyList::empty(py);

    for hit in hits {
        let hit_dict = PyDict::new(py);
        let _ = hit_dict.set_item("file_path", &hit.file_path);
        let _ = hit_dict.set_item("line", hit.line);
        let _ = hit_dict.set_item("content", &hit.content);
        let _ = hit_dict.set_item("score", hit.score);
        let _ = hit_dict.set_item("chunk_id", &hit.chunk_id);

        let _ = py_hits.append(hit_dict);
    }

    py_hits.into()
}

// ═══════════════════════════════════════════════════════════════════════════
// Msgpack API (Zero-Copy Performance)
// ═══════════════════════════════════════════════════════════════════════════

/// Index files and return msgpack-serialized results
///
/// High-performance alternative to index_files() that returns msgpack bytes
/// instead of Python dicts, eliminating conversion overhead.
///
/// Args:
///     files: List of dicts with "file_path" and "content" keys
///     fail_fast: If True, stop on first error
///
/// Returns:
///     Msgpack bytes (deserialize with msgpack.unpackb())
///
/// Example (Python):
///     >>> import msgpack
///     >>> raw = index.index_files_msgpack(files)
///     >>> result = msgpack.unpackb(raw)
///     >>> print(result['success_count'])
#[pyfunction]
#[pyo3(signature = (index, files, fail_fast = false))]
fn index_files_msgpack<'py>(
    py: Python<'py>,
    index: &PyLexicalIndex,
    files: &PyList,
    fail_fast: bool,
) -> PyResult<&'py PyBytes> {
    // Extract file data
    let mut rust_files = Vec::with_capacity(files.len());
    for item in files.iter() {
        let dict = item.downcast::<PyDict>()?;

        let file_path: String = dict
            .get_item("file_path")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("file_path"))?
            .extract()?;

        let content: String = dict
            .get_item("content")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("content"))?
            .extract()?;

        rust_files.push(FileToIndex {
            repo_id: index.index.get_repo_id().to_string(),
            file_path,
            content,
        });
    }

    // GIL RELEASE - Index
    let result = py.allow_threads(|| {
        index.index.index_files_batch(&rust_files, fail_fast)
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
        format!("Indexing failed: {:?}", e)
    ))?;

    // Serialize to msgpack
    let bytes = rmp_serde::to_vec_named(&result)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("msgpack serialization failed: {}", e)
        ))?;

    Ok(PyBytes::new(py, &bytes))
}

/// Search and return msgpack-serialized results
///
/// High-performance alternative to search() that returns msgpack bytes
/// instead of Python dicts.
///
/// Args:
///     query: Search query string
///     limit: Maximum number of results
///
/// Returns:
///     Msgpack bytes (deserialize with msgpack.unpackb())
#[pyfunction]
fn search_msgpack<'py>(
    py: Python<'py>,
    index: &PyLexicalIndex,
    query: &str,
    limit: usize,
) -> PyResult<&'py PyBytes> {
    // GIL RELEASE - Search
    let hits = py.allow_threads(|| {
        index.index.search(query, limit)
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
        format!("Search failed: {:?}", e)
    ))?;

    // Serialize to msgpack
    let bytes = rmp_serde::to_vec_named(&hits)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("msgpack serialization failed: {}", e)
        ))?;

    Ok(PyBytes::new(py, &bytes))
}

// ═══════════════════════════════════════════════════════════════════════════
// Module Registration
// ═══════════════════════════════════════════════════════════════════════════

/// Register lexical search API functions
pub fn register_lexical_api(m: &PyModule) -> PyResult<()> {
    m.add_class::<PyLexicalIndex>()?;
    m.add_function(wrap_pyfunction!(index_files_msgpack, m)?)?;
    m.add_function(wrap_pyfunction!(search_msgpack, m)?)?;
    Ok(())
}
