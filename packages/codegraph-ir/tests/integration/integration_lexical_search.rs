//! Lexical Search Integration Tests
//!
//! Tests end-to-end workflows:
//! 1. Index batch of files → Search → Verify results
//! 2. Incremental updates → Re-search → Verify changes
//! 3. ChunkStore integration → Verify chunk retrieval
//! 4. Multi-language indexing → Verify field extraction
//! 5. Query router → Verify RRF fusion

use codegraph_ir::features::lexical::{
    Chunk, ChunkKind, ChunkStore, FileToIndex, IndexingMode, SqliteChunkStore,
    TantivyLexicalIndex,
};
use std::sync::Arc;
use tempfile::TempDir;

/// Test 1: Basic indexing and search workflow
#[test]
fn test_e2e_index_and_search() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    // Create index
    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store.clone(),
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Index multiple Python files
    let files = vec![
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/auth.py".to_string(),
            content: r#"
class AuthService:
    """User authentication service"""

    def login(self, username, password):
        # Validate credentials
        if username == "admin":
            return "success"
        return "failed"
            "#
            .to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/db.py".to_string(),
            content: r#"
class DatabaseConnection:
    """Database connection manager"""

    def connect(self, host):
        # Connect to database
        print(f"Connecting to {host}")
        return True
            "#
            .to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/utils.py".to_string(),
            content: r#"
def validate_username(username):
    """Validate username format"""
    # Check username length
    if len(username) < 3:
        return False
    return True
            "#
            .to_string(),
        },
    ];

    // Index batch
    let result = index.index_files_batch(&files, false).unwrap();
    assert_eq!(result.success_count, 3);
    assert_eq!(result.total_files, 3);
    assert!(result.is_complete_success());

    // Search for "username" - should match auth.py and utils.py
    let hits = index.search("username", 10).unwrap();
    assert!(hits.len() >= 2, "Expected at least 2 hits for 'username'");

    let file_paths: Vec<String> = hits.iter().map(|h| h.file_path.clone()).collect();
    assert!(file_paths.contains(&"src/auth.py".to_string()));
    assert!(file_paths.contains(&"src/utils.py".to_string()));

    // Search for "database" - should only match db.py
    let hits = index.search("database", 10).unwrap();
    assert!(hits.len() >= 1, "Expected at least 1 hit for 'database'");
    assert!(hits[0].file_path.contains("db.py"));

    // Search for docstring content
    let hits = index.search("authentication service", 10).unwrap();
    assert!(hits.len() >= 1, "Expected to find 'authentication service' in docstring");
    assert!(hits[0].file_path.contains("auth.py"));

    // Verify BM25 scoring (more specific queries should rank higher)
    let hits = index.search("admin", 10).unwrap();
    assert!(hits.len() >= 1);
    assert!(hits[0].score > 0.0);
}

/// Test 2: Multi-language indexing with field extraction
#[tokio::test]
async fn test_multi_language_extraction() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store.clone(),
        "multi_lang_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Index Rust file
    let rust_file = FileToIndex {
        repo_id: "multi_lang_repo".to_string(),
        file_path: "src/main.rs".to_string(),
        content: r#"
/// Main entry point
fn main() {
    let greeting = "Hello, World!";
    println!("{}", greeting);
    // This is a comment
}
        "#
        .to_string(),
    };

    // Index Python file
    let python_file = FileToIndex {
        repo_id: "multi_lang_repo".to_string(),
        file_path: "app.py".to_string(),
        content: r#"
def greet():
    """Greet the user"""
    message = "Hello, Python!"
    print(message)
    # This is also a comment
        "#
        .to_string(),
    };

    let files = vec![rust_file, python_file];
    let result = index.index_files_batch(&files, false).unwrap();
    assert_eq!(result.success_count, 2);

    // Search for string literal content
    let hits = index.search("Hello", 10).unwrap();
    assert!(hits.len() >= 2, "Should find 'Hello' in both files");

    // Search for comment content
    let hits = index.search("comment", 10).unwrap();
    assert!(hits.len() >= 2, "Should find 'comment' in both files");

    // Search for docstring (Python-specific)
    let hits = index.search("Greet the user", 10).unwrap();
    assert!(hits.len() >= 1, "Should find Python docstring");
    assert!(hits[0].file_path.contains("app.py"));
}

/// Test 3: ChunkStore integration with priority system
#[tokio::test]
async fn test_chunk_store_priority() {
    let chunk_store = SqliteChunkStore::in_memory().unwrap();

    // Create overlapping chunks: file > class > function
    let file_chunk = Chunk {
        chunk_id: "file_chunk".to_string(),
        repo_id: "repo1".to_string(),
        file_path: "lib.rs".to_string(),
        start_line: 1,
        end_line: 100,
        content: "entire file content".to_string(),
        content_hash: "hash_file".to_string(),
        kind: ChunkKind::File,
        fqn: None,
        metadata: None,
    };

    let class_chunk = Chunk {
        chunk_id: "class_chunk".to_string(),
        repo_id: "repo1".to_string(),
        file_path: "lib.rs".to_string(),
        start_line: 10,
        end_line: 50,
        content: "struct MyStruct {}".to_string(),
        content_hash: "hash_class".to_string(),
        kind: ChunkKind::Class,
        fqn: Some("MyStruct".to_string()),
        metadata: None,
    };

    let function_chunk = Chunk {
        chunk_id: "func_chunk".to_string(),
        repo_id: "repo1".to_string(),
        file_path: "lib.rs".to_string(),
        start_line: 20,
        end_line: 30,
        content: "impl MyStruct { fn new() {} }".to_string(),
        content_hash: "hash_func".to_string(),
        kind: ChunkKind::Function,
        fqn: Some("MyStruct::new".to_string()),
        metadata: None,
    };

    // Save all chunks
    chunk_store.save_chunks(&[file_chunk, class_chunk, function_chunk]).await.unwrap();

    // Query line 25 (inside function) → should return function chunk (highest priority)
    let chunk = chunk_store
        .find_chunk_by_file_and_line("repo1", "lib.rs", 25)
        .await
        .unwrap();
    assert_eq!(chunk.chunk_id, "func_chunk");
    assert_eq!(chunk.kind, ChunkKind::Function);

    // Query line 15 (inside class but outside function) → should return class chunk
    let chunk = chunk_store
        .find_chunk_by_file_and_line("repo1", "lib.rs", 15)
        .await
        .unwrap();
    assert_eq!(chunk.chunk_id, "class_chunk");
    assert_eq!(chunk.kind, ChunkKind::Class);

    // Query line 5 (outside class) → should return file chunk
    let chunk = chunk_store
        .find_chunk_by_file_and_line("repo1", "lib.rs", 5)
        .await
        .unwrap();
    assert_eq!(chunk.chunk_id, "file_chunk");
    assert_eq!(chunk.kind, ChunkKind::File);
}

/// Test 4: Incremental update (file replacement)
#[test]
fn test_incremental_update() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Initial indexing
    let initial_file = FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "config.py".to_string(),
        content: r#"
# Configuration file
DATABASE_URL = "postgresql://localhost/db"
        "#
        .to_string(),
    };

    index.index_files_batch(&[initial_file], false).unwrap();

    // Verify initial search
    let hits = index.search("postgresql", 10).unwrap();
    assert_eq!(hits.len(), 1);
    assert!(hits[0].content.contains("postgresql"));

    // Update the same file (different content)
    let updated_file = FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "config.py".to_string(),
        content: r#"
# Updated configuration
DATABASE_URL = "mysql://localhost/newdb"
CACHE_ENABLED = True
        "#
        .to_string(),
    };

    index.index_files_batch(&[updated_file], false).unwrap();

    // Verify old content is gone
    let hits = index.search("postgresql", 10).unwrap();
    assert_eq!(hits.len(), 0, "Old content should be removed");

    // Verify new content is searchable
    let hits = index.search("mysql", 10).unwrap();
    assert_eq!(hits.len(), 1);
    assert!(hits[0].content.contains("mysql"));

    let hits = index.search("CACHE_ENABLED", 10).unwrap();
    assert_eq!(hits.len(), 1);
}

/// Test 5: Large batch indexing performance
#[test]
fn test_large_batch_indexing() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "perf_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Generate 100 files
    let files: Vec<FileToIndex> = (0..100)
        .map(|i| FileToIndex {
            repo_id: "perf_repo".to_string(),
            file_path: format!("src/module_{}.py", i),
            content: format!(
                r#"
class Module{}:
    """Module {} documentation"""

    def process(self, data):
        # Process data for module {}
        result = data * {}
        return result
                "#,
                i, i, i, i
            ),
        })
        .collect();

    // Index batch
    let result = index.index_files_batch(&files, false).unwrap();
    assert_eq!(result.success_count, 100);
    assert!(result.throughput() > 10.0, "Should index at least 10 files/sec");

    // Verify searchability
    let hits = index.search("Module50", 10).unwrap();
    assert!(hits.len() >= 1);
    assert!(hits[0].file_path.contains("module_50.py"));
}

/// Test 6: Query builder and filters (via SearchRequest)
#[test]
fn test_search_request_builder() {
    use codegraph_ir::features::lexical::{Filter, HybridSearchConfig, SearchRequest};

    let request = SearchRequest::new("test query")
        .with_limit(50)
        .with_filter(Filter::FilePath("*.py".to_string()))
        .with_filter(Filter::RepoId("repo1".to_string()));

    assert_eq!(request.query, "test query");
    assert_eq!(request.limit, 50);
    assert_eq!(request.filters.len(), 2);

    // Test hybrid config
    let hybrid_config = HybridSearchConfig {
        enable_lexical: true,
        enable_vector: false,
        enable_symbol: false,
        rrf_k: 60.0,
    };

    let hybrid_request = SearchRequest::new("hybrid query").with_hybrid(hybrid_config);
    assert!(hybrid_request.hybrid_config.is_some());
}

/// Test 7: Error handling - empty files, invalid content
#[test]
fn test_error_handling() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Empty file should be indexed without error
    let empty_file = FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "empty.py".to_string(),
        content: "".to_string(),
    };

    let result = index.index_files_batch(&[empty_file], false).unwrap();
    assert_eq!(result.success_count, 1);

    // File with only whitespace
    let whitespace_file = FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "whitespace.py".to_string(),
        content: "   \n\n\t\t  ".to_string(),
    };

    let result = index.index_files_batch(&[whitespace_file], false).unwrap();
    assert_eq!(result.success_count, 1);
}

/// Test 8: CamelCase tokenization in search
#[test]
fn test_camelcase_search() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    let file = FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "api.py".to_string(),
        content: r#"
class HTTPSConnectionManager:
    def getUserName(self, user_id):
        return "user"
        "#
        .to_string(),
    };

    index.index_files_batch(&[file], false).unwrap();

    // Search for class name - should find the file
    let hits = index.search("HTTPSConnectionManager", 10).unwrap();
    assert!(hits.len() >= 1, "Should find HTTPSConnectionManager class");
    assert!(hits[0].file_path.contains("api.py"));

    // Search for method name - should find the file
    let hits = index.search("getUserName", 10).unwrap();
    assert!(hits.len() >= 1, "Should find getUserName method");
    assert!(hits[0].file_path.contains("api.py"));

    // Search for generic term that appears in code
    let hits = index.search("user", 10).unwrap();
    assert!(hits.len() >= 1, "Should find content with 'user'");
}

/// Test 9: IndexPlugin trait implementation
#[test]
fn test_index_plugin_interface() {
    use codegraph_ir::features::multi_index::ports::{IndexPlugin, IndexType};

    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Test IndexPlugin trait methods
    assert_eq!(index.index_type(), IndexType::Lexical);
    assert_eq!(index.applied_up_to(), 0); // Initial watermark

    let health = index.health();
    assert!(health.is_healthy);

    let stats = index.stats();
    assert_eq!(stats.entry_count, 0); // No files indexed yet
}

/// Test 10: Batch save chunks and verify retrieval
#[tokio::test]
async fn test_chunk_batch_operations() {
    let chunk_store = SqliteChunkStore::in_memory().unwrap();

    // Create 10 chunks for different files
    let chunks: Vec<Chunk> = (0..10)
        .map(|i| Chunk {
            chunk_id: format!("chunk_{}", i),
            repo_id: "repo1".to_string(),
            file_path: format!("file_{}.py", i),
            start_line: 1,
            end_line: 100,
            content: format!("content of chunk {}", i),
            content_hash: format!("hash_{}", i),
            kind: ChunkKind::File,
            fqn: None,
            metadata: None,
        })
        .collect();

    // Batch save
    chunk_store.save_chunks(&chunks).await.unwrap();

    // Verify all chunks are retrievable
    for i in 0..10 {
        let chunk = chunk_store
            .find_chunk_by_file_and_line("repo1", &format!("file_{}.py", i), 50)
            .await
            .unwrap();
        assert_eq!(chunk.chunk_id, format!("chunk_{}", i));
    }
}
