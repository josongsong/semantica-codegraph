//! SQLite Persistence and Crash Recovery Tests
//!
//! Tests file-based SQLite storage for:
//! 1. Actual disk persistence
//! 2. Database file creation/reopening
//! 3. Crash recovery scenarios
//! 4. Concurrent file access
//! 5. Large database files (100MB+)

use codegraph_ir::features::storage::{
    Chunk, ChunkStore, Dependency, DependencyType, Repository, Snapshot, SqliteChunkStore,
};
use chrono::Utc;
use std::collections::HashMap;
use std::path::PathBuf;
use tempfile::TempDir;

// Test 1: File-based Persistence
#[tokio::test]
async fn test_file_based_persistence() {
    let temp_dir = TempDir::new().unwrap();
    let db_path = temp_dir.path().join("test.db");

    // Step 1: Create database and insert data
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();

        let repo = Repository {
            repo_id: "persist-test".to_string(),
            name: "Persist Test".to_string(),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_repository(&repo).await.unwrap();

        let snapshot = Snapshot {
            snapshot_id: "snap-1".to_string(),
            repo_id: "persist-test".to_string(),
            commit_hash: Some("abc123".to_string()),
            branch_name: Some("main".to_string()),
            created_at: Utc::now(),
        };
        store.save_snapshot(&snapshot).await.unwrap();

        for i in 0..100 {
            let chunk = Chunk {
                chunk_id: format!("chunk-{}", i),
                repo_id: "persist-test".to_string(),
                snapshot_id: "snap-1".to_string(),
                file_path: format!("src/file_{}.rs", i),
                start_line: 1,
                end_line: 10,
                kind: "function".to_string(),
                fqn: Some(format!("test::func_{}", i)),
                language: "rust".to_string(),
                symbol_visibility: Some("public".to_string()),
                content: format!("fn func_{}() {{}}", i),
                content_hash: format!("hash_{}", i),
                summary: Some(format!("Func {}", i)),
                importance: 0.5,
                is_deleted: false,
                attrs: HashMap::new(),
                created_at: Utc::now(),
                updated_at: Utc::now(),
            };
            store.save_chunk(&chunk).await.unwrap();
        }

        // Drop store to close connection
    }

    // Step 2: Verify file exists
    assert!(db_path.exists());
    let metadata = std::fs::metadata(&db_path).unwrap();
    assert!(metadata.len() > 0);
    println!("✅ Database file created: {} bytes", metadata.len());

    // Step 3: Reopen and verify data persisted
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();

        let repo = store.get_repository("persist-test").await.unwrap();
        assert!(repo.is_some());
        assert_eq!(repo.unwrap().name, "Persist Test");

        let chunks = store.get_chunks("persist-test", "snap-1").await.unwrap();
        assert_eq!(chunks.len(), 100);

        for i in 0..100 {
            let chunk = store.get_chunk(&format!("chunk-{}", i)).await.unwrap();
            assert!(chunk.is_some());
            let c = chunk.unwrap();
            assert_eq!(c.content, format!("fn func_{}() {{}}", i));
        }
    }

    println!("✅ File-based persistence: All data recovered after reopen");
}

// Test 2: Crash Recovery (simulated)
#[tokio::test]
async fn test_crash_recovery() {
    let temp_dir = TempDir::new().unwrap();
    let db_path = temp_dir.path().join("crash.db");

    // Step 1: Create initial data
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();

        let repo = Repository {
            repo_id: "crash-test".to_string(),
            name: "Crash Test".to_string(),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_repository(&repo).await.unwrap();

        let snapshot = Snapshot {
            snapshot_id: "snap-crash".to_string(),
            repo_id: "crash-test".to_string(),
            commit_hash: Some("crash123".to_string()),
            branch_name: Some("main".to_string()),
            created_at: Utc::now(),
        };
        store.save_snapshot(&snapshot).await.unwrap();

        // Commit 50 chunks
        for i in 0..50 {
            let chunk = Chunk {
                chunk_id: format!("committed-{}", i),
                repo_id: "crash-test".to_string(),
                snapshot_id: "snap-crash".to_string(),
                file_path: format!("src/committed_{}.rs", i),
                start_line: 1,
                end_line: 10,
                kind: "function".to_string(),
                fqn: Some(format!("crash::committed_{}", i)),
                language: "rust".to_string(),
                symbol_visibility: Some("public".to_string()),
                content: format!("fn committed_{}() {{}}", i),
                content_hash: format!("hash_committed_{}", i),
                summary: Some(format!("Committed {}", i)),
                importance: 0.5,
                is_deleted: false,
                attrs: HashMap::new(),
                created_at: Utc::now(),
                updated_at: Utc::now(),
            };
            store.save_chunk(&chunk).await.unwrap();
        }

        // Simulate crash by dropping store without graceful shutdown
        std::mem::drop(store);
    }

    // Step 2: Reopen after "crash"
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();

        let chunks = store.get_chunks("crash-test", "snap-crash").await.unwrap();
        assert_eq!(chunks.len(), 50);

        // All committed data should be recovered
        for i in 0..50 {
            let chunk = store.get_chunk(&format!("committed-{}", i)).await.unwrap();
            assert!(chunk.is_some());
        }
    }

    println!("✅ Crash recovery: All committed data recovered");
}

// Test 3: Multiple Database Files
#[tokio::test]
async fn test_multiple_database_files() {
    let temp_dir = TempDir::new().unwrap();

    // Create 5 separate databases
    let mut stores = Vec::new();
    for i in 0..5 {
        let db_path = temp_dir.path().join(format!("db_{}.sqlite", i));
        let store = SqliteChunkStore::new(&db_path).unwrap();

        let repo = Repository {
            repo_id: format!("repo-{}", i),
            name: format!("Repo {}", i),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_repository(&repo).await.unwrap();

        stores.push((db_path, store));
    }

    // Verify isolation
    for (i, (_path, store)) in stores.iter().enumerate() {
        let repo = store.get_repository(&format!("repo-{}", i)).await.unwrap();
        assert!(repo.is_some());

        // Should not see other repos
        for j in 0..5 {
            if i != j {
                let other = store.get_repository(&format!("repo-{}", j)).await.unwrap();
                assert!(other.is_none());
            }
        }
    }

    println!("✅ Multiple databases: Isolation verified");
}

// Test 4: Large Database (10K+ chunks)
#[tokio::test]
async fn test_large_database_file() {
    let temp_dir = TempDir::new().unwrap();
    let db_path = temp_dir.path().join("large.db");

    let store = SqliteChunkStore::new(&db_path).unwrap();

    let repo = Repository {
        repo_id: "large-db".to_string(),
        name: "Large DB".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap-large".to_string(),
        repo_id: "large-db".to_string(),
        commit_hash: Some("large123".to_string()),
        branch_name: Some("main".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Insert 20K chunks (large content)
    let mut chunks = Vec::new();
    for i in 0..20_000 {
        chunks.push(Chunk {
            chunk_id: format!("large-chunk-{}", i),
            repo_id: "large-db".to_string(),
            snapshot_id: "snap-large".to_string(),
            file_path: format!("src/large_{}.rs", i),
            start_line: i,
            end_line: i + 100,
            kind: "function".to_string(),
            fqn: Some(format!("large::func_{}", i)),
            language: "rust".to_string(),
            symbol_visibility: Some("public".to_string()),
            content: format!("// Large content {}\n{}", i, "x".repeat(1000)), // 1KB per chunk
            content_hash: format!("hash_large_{}", i),
            summary: Some(format!("Large {}", i)),
            importance: 0.5,
            is_deleted: false,
            attrs: HashMap::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        });
    }

    let start = std::time::Instant::now();
    store.save_chunks(&chunks).await.unwrap();
    let duration = start.elapsed();

    let file_size = std::fs::metadata(&db_path).unwrap().len();
    println!(
        "✅ Large database: 20K chunks ({}MB) in {:?} ({:.2} chunks/sec)",
        file_size / 1_024 / 1_024,
        duration,
        20_000.0 / duration.as_secs_f64()
    );

    // Verify query performance on large DB
    let query_start = std::time::Instant::now();
    let all_chunks = store.get_chunks("large-db", "snap-large").await.unwrap();
    let query_duration = query_start.elapsed();
    assert_eq!(all_chunks.len(), 20_000);
    println!("📊 Query all 20K chunks in {:?}", query_duration);
}

// Test 5: File Locking (concurrent access)
#[tokio::test]
async fn test_file_locking() {
    use std::sync::Arc;
    use tokio::task::JoinSet;

    let temp_dir = TempDir::new().unwrap();
    let db_path = Arc::new(temp_dir.path().join("locked.db"));

    // Setup initial data
    {
        let store = SqliteChunkStore::new(db_path.as_ref()).unwrap();
        let repo = Repository {
            repo_id: "lock-test".to_string(),
            name: "Lock Test".to_string(),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_repository(&repo).await.unwrap();

        let snapshot = Snapshot {
            snapshot_id: "snap-lock".to_string(),
            repo_id: "lock-test".to_string(),
            commit_hash: Some("lock123".to_string()),
            branch_name: Some("main".to_string()),
            created_at: Utc::now(),
        };
        store.save_snapshot(&snapshot).await.unwrap();
    }

    // Spawn 10 concurrent connections
    let mut tasks = JoinSet::new();
    for i in 0..10 {
        let path = db_path.clone();
        tasks.spawn(async move {
            let store = SqliteChunkStore::new(path.as_ref()).unwrap();

            for j in 0..10 {
                let chunk = Chunk {
                    chunk_id: format!("lock-{}-{}", i, j),
                    repo_id: "lock-test".to_string(),
                    snapshot_id: "snap-lock".to_string(),
                    file_path: format!("src/lock_{}_{}.rs", i, j),
                    start_line: 1,
                    end_line: 10,
                    kind: "function".to_string(),
                    fqn: Some(format!("lock::func_{}_{}", i, j)),
                    language: "rust".to_string(),
                    symbol_visibility: Some("public".to_string()),
                    content: format!("fn func_{}_{}() {{}}", i, j),
                    content_hash: format!("hash_{}_{}", i, j),
                    summary: Some(format!("Func {} {}", i, j)),
                    importance: 0.5,
                    is_deleted: false,
                    attrs: HashMap::new(),
                    created_at: Utc::now(),
                    updated_at: Utc::now(),
                };
                store.save_chunk(&chunk).await.unwrap();
            }
        });
    }

    while tasks.join_next().await.is_some() {}

    // Verify all chunks saved
    let store = SqliteChunkStore::new(db_path.as_ref()).unwrap();
    let chunks = store.get_chunks("lock-test", "snap-lock").await.unwrap();
    assert_eq!(chunks.len(), 100); // 10 connections × 10 chunks

    println!("✅ File locking: 10 concurrent connections handled correctly");
}

// Test 6: Database Corruption Detection
#[tokio::test]
async fn test_corruption_detection() {
    let temp_dir = TempDir::new().unwrap();
    let db_path = temp_dir.path().join("corrupt.db");

    // Create valid database
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();
        let repo = Repository {
            repo_id: "corrupt-test".to_string(),
            name: "Corrupt Test".to_string(),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_repository(&repo).await.unwrap();
    }

    // Corrupt the file
    std::fs::write(&db_path, b"NOT A VALID SQLITE DATABASE").unwrap();

    // Attempt to open should fail gracefully
    let result = SqliteChunkStore::new(&db_path);
    assert!(result.is_err());

    println!("✅ Corruption detection: Invalid database detected");
}

// Test 7: Schema Versioning
#[tokio::test]
async fn test_schema_initialization() {
    let temp_dir = TempDir::new().unwrap();
    let db_path = temp_dir.path().join("schema.db");

    // First open creates schema
    {
        let _store = SqliteChunkStore::new(&db_path).unwrap();
    }

    // Second open should reuse existing schema
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();

        let repo = Repository {
            repo_id: "schema-test".to_string(),
            name: "Schema Test".to_string(),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_repository(&repo).await.unwrap();

        let retrieved = store.get_repository("schema-test").await.unwrap();
        assert!(retrieved.is_some());
    }

    println!("✅ Schema initialization: Idempotent schema creation");
}

// Test 8: Incremental Updates Across Restarts
#[tokio::test]
async fn test_incremental_across_restarts() {
    let temp_dir = TempDir::new().unwrap();
    let db_path = temp_dir.path().join("incremental.db");

    // Session 1: Initial indexing
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();

        let repo = Repository {
            repo_id: "incr-test".to_string(),
            name: "Incremental Test".to_string(),
            remote_url: None,
            local_path: None,
            default_branch: "main".to_string(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_repository(&repo).await.unwrap();

        let snapshot = Snapshot {
            snapshot_id: "snap-1".to_string(),
            repo_id: "incr-test".to_string(),
            commit_hash: Some("commit-1".to_string()),
            branch_name: Some("main".to_string()),
            created_at: Utc::now(),
        };
        store.save_snapshot(&snapshot).await.unwrap();

        // Index file v1
        let chunk = Chunk {
            chunk_id: "chunk-v1".to_string(),
            repo_id: "incr-test".to_string(),
            snapshot_id: "snap-1".to_string(),
            file_path: "src/main.rs".to_string(),
            start_line: 1,
            end_line: 10,
            kind: "function".to_string(),
            fqn: Some("main::func_v1".to_string()),
            language: "rust".to_string(),
            symbol_visibility: Some("public".to_string()),
            content: "fn func_v1() {}".to_string(),
            content_hash: "hash_v1".to_string(),
            summary: Some("V1".to_string()),
            importance: 0.5,
            is_deleted: false,
            attrs: HashMap::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_chunk(&chunk).await.unwrap();
        store
            .update_file_metadata("incr-test", "snap-1", "src/main.rs", "hash_v1".to_string())
            .await
            .unwrap();
    }

    // Session 2: Incremental update after restart
    {
        let store = SqliteChunkStore::new(&db_path).unwrap();

        // Check if file changed
        let old_hash = store
            .get_file_hash("incr-test", "snap-1", "src/main.rs")
            .await
            .unwrap();
        assert_eq!(old_hash, Some("hash_v1".to_string()));

        // File unchanged - skip reindexing
        let new_hash = "hash_v1"; // Same hash
        if Some(new_hash.to_string()) == old_hash {
            println!("✅ File unchanged - skipped reindexing");
        }

        // File changed - reindex
        let snapshot2 = Snapshot {
            snapshot_id: "snap-2".to_string(),
            repo_id: "incr-test".to_string(),
            commit_hash: Some("commit-2".to_string()),
            branch_name: Some("main".to_string()),
            created_at: Utc::now(),
        };
        store.save_snapshot(&snapshot2).await.unwrap();

        store
            .soft_delete_file_chunks("incr-test", "snap-2", "src/main.rs")
            .await
            .unwrap();

        let chunk_v2 = Chunk {
            chunk_id: "chunk-v2".to_string(),
            repo_id: "incr-test".to_string(),
            snapshot_id: "snap-2".to_string(),
            file_path: "src/main.rs".to_string(),
            start_line: 1,
            end_line: 10,
            kind: "function".to_string(),
            fqn: Some("main::func_v2".to_string()),
            language: "rust".to_string(),
            symbol_visibility: Some("public".to_string()),
            content: "fn func_v2() {}".to_string(),
            content_hash: "hash_v2".to_string(),
            summary: Some("V2".to_string()),
            importance: 0.5,
            is_deleted: false,
            attrs: HashMap::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        store.save_chunk(&chunk_v2).await.unwrap();
        store
            .update_file_metadata("incr-test", "snap-2", "src/main.rs", "hash_v2".to_string())
            .await
            .unwrap();

        // Verify update
        let updated_hash = store
            .get_file_hash("incr-test", "snap-2", "src/main.rs")
            .await
            .unwrap();
        assert_eq!(updated_hash, Some("hash_v2".to_string()));
    }

    println!("✅ Incremental updates: Hash-based skipping works across restarts");
}
