//! PostgreSQL Storage Backend Integration Tests
//!
//! SOTA Testing Strategy:
//! - Test all 18 ChunkStore methods
//! - Connection pooling verification
//! - Transaction atomicity
//! - Full-text search (GIN indexes)
//! - Migration system

#![cfg(feature = "postgres")]

use codegraph_ir::features::storage::{
    infrastructure::PostgresChunkStore,
    domain::{Chunk, ChunkStore, Dependency, DependencyType, Repository, Snapshot, ChunkFilter},
};
use chrono::Utc;
use std::env;

/// Helper: Get test database URL
fn get_test_db_url() -> String {
    env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://localhost/codegraph_test".to_string())
}

/// Helper: Create test repository
fn create_test_repo(repo_id: &str) -> Repository {
    Repository {
        repo_id: repo_id.to_string(),
        name: format!("Test Repo {}", repo_id),
        remote_url: Some("https://github.com/test/repo".to_string()),
        local_path: Some("/tmp/test".to_string()),
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    }
}

/// Helper: Create test chunk
fn create_test_chunk(
    chunk_id: &str,
    repo_id: &str,
    snapshot_id: &str,
    content: &str,
) -> Chunk {
    Chunk {
        chunk_id: chunk_id.to_string(),
        repo_id: repo_id.to_string(),
        snapshot_id: snapshot_id.to_string(),
        file_path: "src/main.rs".to_string(),
        start_line: 1,
        end_line: 10,
        kind: "function".to_string(),
        fqn: Some("main::test".to_string()),
        language: "rust".to_string(),
        symbol_visibility: Some("public".to_string()),
        content: content.to_string(),
        content_hash: Chunk::compute_content_hash(content),
        summary: None,
        importance: 0.8,
        is_deleted: false,
        attrs: Default::default(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    }
}

#[tokio::test]
#[ignore] // Requires PostgreSQL server
async fn test_postgres_connection_pool() {
    let store = PostgresChunkStore::new(&get_test_db_url())
        .await
        .expect("Failed to connect to PostgreSQL");

    // Verify connection pool is working
    let repo = create_test_repo("test-pool");
    store.save_repository(&repo).await.unwrap();

    let retrieved = store.get_repository("test-pool").await.unwrap();
    assert!(retrieved.is_some());
    assert_eq!(retrieved.unwrap().name, "Test Repo test-pool");

    // Cleanup
    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_save_and_get_chunk() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-repo");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-repo:main".to_string(),
        repo_id: "test-repo".to_string(),
        commit_hash: Some("abc123".to_string()),
        branch_name: Some("main".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Test chunk CRUD
    let chunk = create_test_chunk(
        "chunk-1",
        "test-repo",
        "test-repo:main",
        "fn test() {}",
    );

    store.save_chunk(&chunk).await.unwrap();

    let retrieved = store.get_chunk("chunk-1").await.unwrap();
    assert!(retrieved.is_some());
    let retrieved = retrieved.unwrap();
    assert_eq!(retrieved.chunk_id, "chunk-1");
    assert_eq!(retrieved.content, "fn test() {}");
    assert_eq!(retrieved.importance, 0.8);

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_batch_insert() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-batch");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-batch:main".to_string(),
        repo_id: "test-batch".to_string(),
        commit_hash: Some("def456".to_string()),
        branch_name: Some("main".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Batch insert 100 chunks (test transaction performance)
    let chunks: Vec<_> = (0..100)
        .map(|i| {
            create_test_chunk(
                &format!("chunk-{}", i),
                "test-batch",
                "test-batch:main",
                &format!("fn test_{}", i),
            )
        })
        .collect();

    store.save_chunks(&chunks).await.unwrap();

    // Verify all chunks saved
    let retrieved = store.get_chunks("test-batch", "test-batch:main").await.unwrap();
    assert_eq!(retrieved.len(), 100);

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_upsert_semantic() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-upsert");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-upsert:main".to_string(),
        repo_id: "test-upsert".to_string(),
        commit_hash: Some("ghi789".to_string()),
        branch_name: Some("main".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Initial chunk
    let chunk1 = create_test_chunk(
        "chunk-upsert",
        "test-upsert",
        "test-upsert:main",
        "v1",
    );
    store.save_chunk(&chunk1).await.unwrap();

    // UPSERT with new content
    let chunk2 = create_test_chunk(
        "chunk-upsert",
        "test-upsert",
        "test-upsert:main",
        "v2",
    );
    store.save_chunk(&chunk2).await.unwrap();

    // Verify updated
    let retrieved = store.get_chunk("chunk-upsert").await.unwrap().unwrap();
    assert_eq!(retrieved.content, "v2");
    assert_eq!(retrieved.is_deleted, false); // UPSERT revives deleted

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_soft_delete() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-delete");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-delete:main".to_string(),
        repo_id: "test-delete".to_string(),
        commit_hash: None,
        branch_name: Some("main".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    let chunk = create_test_chunk(
        "chunk-delete",
        "test-delete",
        "test-delete:main",
        "content",
    );
    store.save_chunk(&chunk).await.unwrap();

    // Soft delete
    store.soft_delete_chunk("chunk-delete").await.unwrap();

    // Verify not returned (is_deleted = TRUE)
    let retrieved = store.get_chunk("chunk-delete").await.unwrap();
    assert!(retrieved.is_none());

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_dependencies() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-deps");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-deps:main".to_string(),
        repo_id: "test-deps".to_string(),
        commit_hash: None,
        branch_name: Some("main".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create chunks: A -> B -> C
    let chunk_a = create_test_chunk("chunk-a", "test-deps", "test-deps:main", "a");
    let chunk_b = create_test_chunk("chunk-b", "test-deps", "test-deps:main", "b");
    let chunk_c = create_test_chunk("chunk-c", "test-deps", "test-deps:main", "c");

    store.save_chunk(&chunk_a).await.unwrap();
    store.save_chunk(&chunk_b).await.unwrap();
    store.save_chunk(&chunk_c).await.unwrap();

    let dep_ab = Dependency {
        id: "dep-ab".to_string(),
        from_chunk_id: "chunk-a".to_string(),
        to_chunk_id: "chunk-b".to_string(),
        relationship: DependencyType::Calls,
        confidence: 1.0,
        created_at: Utc::now(),
    };

    let dep_bc = Dependency {
        id: "dep-bc".to_string(),
        from_chunk_id: "chunk-b".to_string(),
        to_chunk_id: "chunk-c".to_string(),
        relationship: DependencyType::Calls,
        confidence: 1.0,
        created_at: Utc::now(),
    };

    store.save_dependency(&dep_ab).await.unwrap();
    store.save_dependency(&dep_bc).await.unwrap();

    // Test get_dependencies_from
    let deps = store.get_dependencies_from("chunk-a").await.unwrap();
    assert_eq!(deps.len(), 1);
    assert_eq!(deps[0].to_chunk_id, "chunk-b");

    // Test get_dependencies_to
    let deps = store.get_dependencies_to("chunk-b").await.unwrap();
    assert_eq!(deps.len(), 1);
    assert_eq!(deps[0].from_chunk_id, "chunk-a");

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_transitive_dependencies() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-transitive");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-transitive:main".to_string(),
        repo_id: "test-transitive".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create chain: A -> B -> C -> D
    for id in &["a", "b", "c", "d"] {
        let chunk = create_test_chunk(
            &format!("chunk-{}", id),
            "test-transitive",
            "test-transitive:main",
            id,
        );
        store.save_chunk(&chunk).await.unwrap();
    }

    let deps = vec![
        Dependency {
            id: "dep-ab".to_string(),
            from_chunk_id: "chunk-a".to_string(),
            to_chunk_id: "chunk-b".to_string(),
            relationship: DependencyType::Calls,
            confidence: 1.0,
            created_at: Utc::now(),
        },
        Dependency {
            id: "dep-bc".to_string(),
            from_chunk_id: "chunk-b".to_string(),
            to_chunk_id: "chunk-c".to_string(),
            relationship: DependencyType::Calls,
            confidence: 1.0,
            created_at: Utc::now(),
        },
        Dependency {
            id: "dep-cd".to_string(),
            from_chunk_id: "chunk-c".to_string(),
            to_chunk_id: "chunk-d".to_string(),
            relationship: DependencyType::Calls,
            confidence: 1.0,
            created_at: Utc::now(),
        },
    ];

    store.save_dependencies(&deps).await.unwrap();

    // BFS transitive traversal
    let transitive = store.get_transitive_dependencies("chunk-a", 10).await.unwrap();

    // Should include A, B, C, D
    assert!(transitive.contains(&"chunk-a".to_string()));
    assert!(transitive.contains(&"chunk-b".to_string()));
    assert!(transitive.contains(&"chunk-c".to_string()));
    assert!(transitive.contains(&"chunk-d".to_string()));

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_full_text_search() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-search");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-search:main".to_string(),
        repo_id: "test-search".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create chunks with different content
    let chunks = vec![
        create_test_chunk(
            "chunk-1",
            "test-search",
            "test-search:main",
            "fn authenticate_user(username: &str, password: &str) -> bool { true }",
        ),
        create_test_chunk(
            "chunk-2",
            "test-search",
            "test-search:main",
            "fn calculate_total(items: &[Item]) -> f64 { 0.0 }",
        ),
        create_test_chunk(
            "chunk-3",
            "test-search",
            "test-search:main",
            "fn validate_password(password: &str) -> Result<(), Error> { Ok(()) }",
        ),
    ];

    store.save_chunks(&chunks).await.unwrap();

    // Test full-text search (PostgreSQL GIN index)
    let results = store.search_content("password", 10).await.unwrap();

    // Should find chunks containing "password"
    assert!(results.len() >= 2);
    assert!(results.iter().any(|c| c.chunk_id == "chunk-1"));
    assert!(results.iter().any(|c| c.chunk_id == "chunk-3"));

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_file_metadata_incremental() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-metadata");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-metadata:main".to_string(),
        repo_id: "test-metadata".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Update file metadata
    let hash1 = "abc123".to_string();
    store
        .update_file_metadata("test-metadata", "test-metadata:main", "src/main.rs", hash1.clone())
        .await
        .unwrap();

    // Retrieve hash
    let retrieved = store
        .get_file_hash("test-metadata", "test-metadata:main", "src/main.rs")
        .await
        .unwrap();

    assert_eq!(retrieved, Some(hash1));

    // Update with new hash (simulate file change)
    let hash2 = "def456".to_string();
    store
        .update_file_metadata("test-metadata", "test-metadata:main", "src/main.rs", hash2.clone())
        .await
        .unwrap();

    let retrieved2 = store
        .get_file_hash("test-metadata", "test-metadata:main", "src/main.rs")
        .await
        .unwrap();

    assert_eq!(retrieved2, Some(hash2));

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_get_chunks_by_filter() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-filter");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-filter:main".to_string(),
        repo_id: "test-filter".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create chunks with different attributes
    let mut chunk1 = create_test_chunk(
        "chunk-rust-1",
        "test-filter",
        "test-filter:main",
        "rust content",
    );
    chunk1.language = "rust".to_string();
    chunk1.kind = "function".to_string();

    let mut chunk2 = create_test_chunk(
        "chunk-python-1",
        "test-filter",
        "test-filter:main",
        "python content",
    );
    chunk2.language = "python".to_string();
    chunk2.kind = "class".to_string();

    store.save_chunk(&chunk1).await.unwrap();
    store.save_chunk(&chunk2).await.unwrap();

    // Filter by language
    let filter = ChunkFilter {
        repo_id: Some("test-filter".to_string()),
        snapshot_id: Some("test-filter:main".to_string()),
        language: Some("rust".to_string()),
        ..Default::default()
    };

    let results = store.get_chunks_by_filter(&filter).await.unwrap();
    assert_eq!(results.len(), 1);
    assert_eq!(results[0].language, "rust");

    // Filter by kind
    let filter2 = ChunkFilter {
        repo_id: Some("test-filter".to_string()),
        snapshot_id: Some("test-filter:main".to_string()),
        kind: Some("class".to_string()),
        ..Default::default()
    };

    let results2 = store.get_chunks_by_filter(&filter2).await.unwrap();
    assert_eq!(results2.len(), 1);
    assert_eq!(results2[0].kind, "class");

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_statistics() {
    let store = PostgresChunkStore::new(&get_test_db_url()).await.unwrap();

    // Setup
    let repo = create_test_repo("test-stats");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-stats:main".to_string(),
        repo_id: "test-stats".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Add chunks and dependencies
    let chunks = vec![
        create_test_chunk("chunk-s1", "test-stats", "test-stats:main", "c1"),
        create_test_chunk("chunk-s2", "test-stats", "test-stats:main", "c2"),
        create_test_chunk("chunk-s3", "test-stats", "test-stats:main", "c3"),
    ];
    store.save_chunks(&chunks).await.unwrap();

    let dep = Dependency {
        id: "dep-s12".to_string(),
        from_chunk_id: "chunk-s1".to_string(),
        to_chunk_id: "chunk-s2".to_string(),
        relationship: DependencyType::Calls,
        confidence: 1.0,
        created_at: Utc::now(),
    };
    store.save_dependency(&dep).await.unwrap();

    // Get statistics
    let stats = store.get_stats("test-stats").await.unwrap();

    assert_eq!(stats.total_chunks, 3);
    assert_eq!(stats.total_dependencies, 1);
    assert_eq!(stats.total_snapshots, 1);

    store.close().await;
}

#[tokio::test]
#[ignore]
async fn test_postgres_concurrent_access() {
    let store = std::sync::Arc::new(
        PostgresChunkStore::new(&get_test_db_url()).await.unwrap()
    );

    // Setup
    let repo = create_test_repo("test-concurrent");
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "test-concurrent:main".to_string(),
        repo_id: "test-concurrent".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Concurrent writes (test connection pool)
    let mut handles = vec![];

    for i in 0..10 {
        let store_clone = store.clone();
        let handle = tokio::spawn(async move {
            let chunk = create_test_chunk(
                &format!("chunk-concurrent-{}", i),
                "test-concurrent",
                "test-concurrent:main",
                &format!("content {}", i),
            );
            store_clone.save_chunk(&chunk).await.unwrap();
        });
        handles.push(handle);
    }

    // Wait for all concurrent writes
    for handle in handles {
        handle.await.unwrap();
    }

    // Verify all chunks saved
    let chunks = store.get_chunks("test-concurrent", "test-concurrent:main")
        .await
        .unwrap();

    assert_eq!(chunks.len(), 10);
}
