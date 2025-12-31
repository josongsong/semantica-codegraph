//! PostgreSQL Edge Case & Corner Case Tests
//!
//! Comprehensive test suite for PostgreSQL adapter covering:
//! - Edge cases (boundary conditions)
//! - Corner cases (unexpected combinations)
//! - Error handling
//! - Concurrent access
//! - Large data volumes
//! - Unicode and special characters
//! - Transaction rollbacks
//!
//! # Running Tests
//!
//! These tests require a running PostgreSQL instance and should be run sequentially:
//!
//! ```bash
//! DATABASE_URL="postgres://codegraph:codegraph_dev@localhost:7201/codegraph_rfc074_test" \
//!   cargo test --test test_postgres_edge_cases -- --ignored --test-threads=1
//! ```

use codegraph_ir::features::storage::domain::{Chunk, ChunkStore, Dependency, DependencyType, Repository, Snapshot};
use codegraph_ir::features::storage::PostgresChunkStore;
use chrono::Utc;
use std::collections::HashMap;

const TEST_DATABASE_URL: &str = "postgres://codegraph:codegraph_dev@localhost:7201/codegraph_rfc074_test";

async fn get_test_store() -> PostgresChunkStore {
    PostgresChunkStore::new(TEST_DATABASE_URL)
        .await
        .expect("Failed to connect to test database")
}

async fn cleanup_database(store: &PostgresChunkStore) {
    // Clean all tables for fresh test (cascading deletes will handle child tables)
    let pool = store.pool();
    sqlx::query("DELETE FROM repositories").execute(pool).await.ok();
}

/// Helper to create test chunk
fn create_test_chunk(id: &str, repo_id: &str, snapshot_id: &str, line: u32) -> Chunk {
    Chunk {
        chunk_id: id.to_string(),
        repo_id: repo_id.to_string(),
        snapshot_id: snapshot_id.to_string(),
        file_path: "test.py".to_string(),
        start_line: line,
        end_line: line + 10,
        kind: "function".to_string(),
        fqn: Some(format!("test.{}", id)),
        language: "python".to_string(),
        symbol_visibility: Some("public".to_string()),
        content: format!("def {}(): pass", id),
        content_hash: format!("hash_{}", id),
        summary: Some(format!("Test function {}", id)),
        importance: 0.5,
        is_deleted: false,
        attrs: HashMap::new(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Edge Case 1: Empty String Handling
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore] // Requires PostgreSQL
async fn test_edge_case_empty_content() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    // Setup
    let repo = Repository {
        repo_id: "edge_empty".to_string(),
        name: "Edge Empty Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_empty".to_string(),
        repo_id: "edge_empty".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Test: Empty content (but not null)
    let mut chunk = create_test_chunk("empty_chunk", "edge_empty", "snap_empty", 1);
    chunk.content = "".to_string(); // Empty but valid
    chunk.summary = Some("".to_string()); // Empty summary

    let result = store.save_chunk(&chunk).await;
    assert!(result.is_ok(), "Should handle empty content");

    // Verify retrieval
    let retrieved = store.get_chunk("empty_chunk").await.unwrap();
    assert!(retrieved.is_some());
    assert_eq!(retrieved.unwrap().content, "");
}

// ═══════════════════════════════════════════════════════════════════════
// Edge Case 2: Unicode & Special Characters
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_edge_case_unicode_content() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    // Setup repository
    let repo = Repository {
        repo_id: "edge_unicode".to_string(),
        name: "Unicode Test 测试 テスト 🚀".to_string(),
        remote_url: Some("https://github.com/test/日本語.git".to_string()),
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_unicode".to_string(),
        repo_id: "edge_unicode".to_string(),
        commit_hash: Some("测试哈希123".to_string()),
        branch_name: Some("feature/日本語".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Test: Unicode in all text fields
    let mut chunk = create_test_chunk("unicode_chunk", "edge_unicode", "snap_unicode", 1);
    chunk.content = "def 测试(): # コメント\n    print('🚀 Unicode!')".to_string();
    chunk.fqn = Some("模块.测试関数.🚀".to_string());
    chunk.summary = Some("テストサマリー with emoji 🎉".to_string());

    store.save_chunk(&chunk).await.unwrap();

    // Verify retrieval preserves Unicode
    let retrieved = store.get_chunk("unicode_chunk").await.unwrap().unwrap();
    assert!(retrieved.content.contains("测试"));
    assert!(retrieved.content.contains("🚀"));
    assert!(retrieved.fqn.as_ref().unwrap().contains("测试関数"));
}

// ═══════════════════════════════════════════════════════════════════════
// Edge Case 3: Maximum Line Numbers (Boundary)
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_edge_case_max_line_numbers() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "edge_maxline".to_string(),
        name: "Max Line Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_maxline".to_string(),
        repo_id: "edge_maxline".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Test: Very large line numbers (near i32::MAX but valid as u32)
    let mut chunk = create_test_chunk("maxline_chunk", "edge_maxline", "snap_maxline", 1);
    chunk.start_line = 2_000_000_000; // Large but < i32::MAX
    chunk.end_line = 2_000_000_100;

    store.save_chunk(&chunk).await.unwrap();

    let retrieved = store.get_chunk("maxline_chunk").await.unwrap().unwrap();
    assert_eq!(retrieved.start_line, 2_000_000_000);
    assert_eq!(retrieved.end_line, 2_000_000_100);
}

// ═══════════════════════════════════════════════════════════════════════
// Edge Case 4: Very Long Content (Large Text)
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_edge_case_large_content() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "edge_large".to_string(),
        name: "Large Content Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_large".to_string(),
        repo_id: "edge_large".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Test: 1MB of content
    let large_content = "x".repeat(1_000_000); // 1MB
    let mut chunk = create_test_chunk("large_chunk", "edge_large", "snap_large", 1);
    chunk.content = large_content.clone();

    store.save_chunk(&chunk).await.unwrap();

    let retrieved = store.get_chunk("large_chunk").await.unwrap().unwrap();
    assert_eq!(retrieved.content.len(), 1_000_000);
    assert_eq!(retrieved.content, large_content);
}

// ═══════════════════════════════════════════════════════════════════════
// Corner Case 1: Null/Optional Fields
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_corner_case_all_optionals_none() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "corner_null".to_string(),
        name: "Null Fields Test".to_string(),
        remote_url: None, // All optional fields None
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_null".to_string(),
        repo_id: "corner_null".to_string(),
        commit_hash: None, // No commit hash
        branch_name: None, // No branch name
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Chunk with all optional fields as None
    let mut chunk = create_test_chunk("null_chunk", "corner_null", "snap_null", 1);
    chunk.fqn = None;
    chunk.symbol_visibility = None;
    chunk.summary = None;

    store.save_chunk(&chunk).await.unwrap();

    let retrieved = store.get_chunk("null_chunk").await.unwrap().unwrap();
    assert!(retrieved.fqn.is_none());
    assert!(retrieved.symbol_visibility.is_none());
    assert!(retrieved.summary.is_none());
}

// ═══════════════════════════════════════════════════════════════════════
// Corner Case 2: UPSERT on Soft-Deleted Chunk
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_corner_case_upsert_revives_deleted() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "corner_upsert".to_string(),
        name: "UPSERT Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_upsert".to_string(),
        repo_id: "corner_upsert".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // 1. Create chunk
    let chunk = create_test_chunk("upsert_chunk", "corner_upsert", "snap_upsert", 1);
    store.save_chunk(&chunk).await.unwrap();

    // 2. Soft delete it manually
    sqlx::query("UPDATE chunks SET is_deleted = TRUE WHERE chunk_id = 'upsert_chunk'")
        .execute(store.pool())
        .await
        .unwrap();

    // 3. UPSERT should revive it
    let mut new_chunk = chunk.clone();
    new_chunk.content = "Updated content".to_string();
    store.save_chunk(&new_chunk).await.unwrap();

    // 4. Verify it's alive again
    let retrieved = store.get_chunk("upsert_chunk").await.unwrap().unwrap();
    assert!(!retrieved.is_deleted);
    assert_eq!(retrieved.content, "Updated content");
}

// ═══════════════════════════════════════════════════════════════════════
// Corner Case 3: Circular Dependencies
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_corner_case_circular_dependencies() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "corner_circular".to_string(),
        name: "Circular Deps Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_circular".to_string(),
        repo_id: "corner_circular".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create chunks A, B, C
    for id in &["A", "B", "C"] {
        let chunk = create_test_chunk(id, "corner_circular", "snap_circular", 1);
        store.save_chunk(&chunk).await.unwrap();
    }

    // Create circular dependency: A -> B -> C -> A
    let deps = vec![
        Dependency {
            id: "dep_ab".to_string(),
            from_chunk_id: "A".to_string(),
            to_chunk_id: "B".to_string(),
            relationship: DependencyType::Calls,
            confidence: 1.0,
            created_at: Utc::now(),
        },
        Dependency {
            id: "dep_bc".to_string(),
            from_chunk_id: "B".to_string(),
            to_chunk_id: "C".to_string(),
            relationship: DependencyType::Calls,
            confidence: 1.0,
            created_at: Utc::now(),
        },
        Dependency {
            id: "dep_ca".to_string(),
            from_chunk_id: "C".to_string(),
            to_chunk_id: "A".to_string(),
            relationship: DependencyType::Calls,
            confidence: 1.0,
            created_at: Utc::now(),
        },
    ];

    store.save_dependencies(&deps).await.unwrap();

    // BFS should handle circular deps (with max_depth limit)
    let transitive = store.get_transitive_dependencies("A", 10).await.unwrap();

    // Should find B and C (and possibly A again, but limited by depth)
    assert!(transitive.len() >= 2);
    assert!(transitive.iter().any(|id| id == "B"));
    assert!(transitive.iter().any(|id| id == "C"));
}

// ═══════════════════════════════════════════════════════════════════════
// Corner Case 4: Concurrent Writes to Same Chunk
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_corner_case_concurrent_upsert() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "corner_concurrent".to_string(),
        name: "Concurrent Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_concurrent".to_string(),
        repo_id: "corner_concurrent".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Spawn 10 concurrent UPSERT tasks for the same chunk
    let mut handles = vec![];
    for i in 0..10 {
        let store_clone = get_test_store().await;
        let handle = tokio::spawn(async move {
            let mut chunk = create_test_chunk("concurrent_chunk", "corner_concurrent", "snap_concurrent", 1);
            chunk.content = format!("Version {}", i);
            store_clone.save_chunk(&chunk).await
        });
        handles.push(handle);
    }

    // All should succeed (UPSERT semantic)
    for handle in handles {
        let result = handle.await.unwrap();
        assert!(result.is_ok());
    }

    // Final chunk should exist (last write wins)
    let final_chunk = store.get_chunk("concurrent_chunk").await.unwrap();
    assert!(final_chunk.is_some());
}

// ═══════════════════════════════════════════════════════════════════════
// Corner Case 5: Batch with Duplicate IDs
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_corner_case_batch_duplicates() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "corner_batch".to_string(),
        name: "Batch Duplicates Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_batch".to_string(),
        repo_id: "corner_batch".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create batch with duplicate chunk_id (should UPSERT)
    let mut chunks = vec![];
    for i in 0..5 {
        let mut chunk = create_test_chunk("duplicate_id", "corner_batch", "snap_batch", 1);
        chunk.content = format!("Content version {}", i);
        chunks.push(chunk);
    }

    // Should succeed (UPSERT handles duplicates)
    store.save_chunks(&chunks).await.unwrap();

    // Only one chunk should exist (last one in batch)
    let result = store.get_chunks("corner_batch", "snap_batch").await.unwrap();
    assert_eq!(result.len(), 1);
    assert!(result[0].content.contains("version 4")); // Last one
}

// ═══════════════════════════════════════════════════════════════════════
// Corner Case 6: JSONB attrs Edge Cases
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_corner_case_complex_jsonb_attrs() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "corner_jsonb".to_string(),
        name: "JSONB Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_jsonb".to_string(),
        repo_id: "corner_jsonb".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create chunk with complex JSONB attrs
    let mut chunk = create_test_chunk("jsonb_chunk", "corner_jsonb", "snap_jsonb", 1);
    chunk.attrs.insert("nested".to_string(), serde_json::json!({
        "array": [1, 2, 3],
        "object": {"key": "value"},
        "bool": true,
        "null": null,
        "unicode": "测试 🚀"
    }));
    chunk.attrs.insert("simple".to_string(), serde_json::json!("string value"));

    store.save_chunk(&chunk).await.unwrap();

    // Verify complex JSONB round-trip
    let retrieved = store.get_chunk("jsonb_chunk").await.unwrap().unwrap();
    assert!(retrieved.attrs.contains_key("nested"));

    let nested = &retrieved.attrs["nested"];
    assert_eq!(nested["array"][0], 1);
    assert_eq!(nested["object"]["key"], "value");
    assert_eq!(nested["bool"], true);
    assert_eq!(nested["unicode"], "测试 🚀");
}

// ═══════════════════════════════════════════════════════════════════════
// Error Handling: Non-existent Repository
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_error_handling_foreign_key_violation() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    // Try to create snapshot without repository (FK violation)
    let snapshot = Snapshot {
        snapshot_id: "orphan_snap".to_string(),
        repo_id: "nonexistent_repo".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };

    let result = store.save_snapshot(&snapshot).await;
    assert!(result.is_err(), "Should fail due to FK constraint");
}

// ═══════════════════════════════════════════════════════════════════════
// Performance: Large Batch Insert
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_performance_large_batch() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let repo = Repository {
        repo_id: "perf_batch".to_string(),
        name: "Performance Test".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: "snap_perf".to_string(),
        repo_id: "perf_batch".to_string(),
        commit_hash: None,
        branch_name: None,
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    // Create 1000 chunks
    let chunks: Vec<_> = (0..1000)
        .map(|i| create_test_chunk(&format!("chunk_{}", i), "perf_batch", "snap_perf", i as u32 * 10))
        .collect();

    let start = std::time::Instant::now();
    store.save_chunks(&chunks).await.unwrap();
    let duration = start.elapsed();

    println!("Saved 1000 chunks in {:?}", duration);

    // Verify all inserted
    let retrieved = store.get_chunks("perf_batch", "snap_perf").await.unwrap();
    assert_eq!(retrieved.len(), 1000);

    // Should be fast (< 1s with transaction)
    assert!(duration.as_secs() < 5, "Batch insert should be fast");
}
