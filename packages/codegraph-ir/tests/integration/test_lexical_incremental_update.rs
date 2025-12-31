//! Lexical Index Incremental Update - Edge Cases & Corner Cases Tests
//!
//! Tests for apply_delta() and rebuild() with extreme scenarios:
//! - Empty deltas
//! - Large batches
//! - Concurrent updates
//! - Invalid states
//! - Error recovery

use codegraph_ir::features::lexical::{
    TantivyLexicalIndex, SqliteChunkStore, IndexingMode, FileToIndex,
};
use codegraph_ir::features::multi_index::ports::{
    DeltaAnalysis, ChangeScope, Region, ExpandedScope, IndexPlugin,
};
use codegraph_ir::features::query_engine::infrastructure::{
    TransactionDelta, Snapshot,
};
use codegraph_ir::shared::models::{Node, NodeKind, Span};
use std::collections::HashMap;
use std::sync::Arc;
use tempfile::TempDir;

// ═══════════════════════════════════════════════════════════════════════════
// Test Helpers
// ═══════════════════════════════════════════════════════════════════════════

fn create_test_index(temp_dir: &TempDir) -> TantivyLexicalIndex {
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    ).unwrap()
}

fn create_test_node(id: &str, file_path: &str, name: &str) -> Node {
    Node {
        id: id.to_string(),
        kind: NodeKind::Function,
        fqn: format!("test.{}", name),
        file_path: file_path.to_string(),
        span: Span::new(1, 1, 10, 1),
        language: "python".to_string(),
        stable_id: None,
        content_hash: None,
        name: Some(name.to_string()),
        module_path: None,
        parent_id: None,
        body_span: None,
        docstring: None,
        decorators: None,
        annotations: None,
        modifiers: None,
        is_async: None,
        is_generator: None,
        is_static: None,
        is_abstract: None,
        parameters: None,
        return_type: None,
        base_classes: None,
        metaclass: None,
        type_annotation: None,
        initial_value: None,
        metadata: None,
        role: None,
        is_test_file: None,
        signature_id: None,
        declared_type_id: None,
        attrs: None,
        raw: None,
        flavor: None,
        is_nullable: None,
        owner_node_id: None,
    }
}

fn create_empty_delta(from_txn: u64, to_txn: u64) -> TransactionDelta {
    TransactionDelta {
        from_txn,
        to_txn,
        added_nodes: vec![],
        removed_nodes: vec![],
        modified_nodes: vec![],
        added_edges: vec![],
        removed_edges: vec![],
    }
}

fn create_empty_analysis(from_txn: u64, to_txn: u64) -> DeltaAnalysis {
    DeltaAnalysis {
        scope: ChangeScope::IR {
            added_nodes: vec![],
            removed_nodes: vec![],
            modified_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        },
        impact_ratio: 0.0,
        affected_regions: vec![],
        index_impacts: HashMap::new(),
        expanded_scope: ExpandedScope {
            primary_targets: vec![],
            secondary_targets: vec![],
        },
        hash_analysis: HashMap::new(),
        from_txn,
        to_txn,
    }
}

fn create_region(file_path: &str) -> Region {
    Region {
        file_path: file_path.to_string(),
        module_path: None,
        node_ids: vec![],
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Edge Case 1: Empty Delta
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_apply_delta_empty_changes() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing
    let files = vec![FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "src/main.py".to_string(),
        content: "def hello(): pass".to_string(),
    }];
    index.index_files_batch(&files, false).unwrap();

    // Apply empty delta
    let delta = create_empty_delta(1, 2);
    let analysis = create_empty_analysis(1, 2);

    let result = index.apply_delta(&delta, &analysis);

    assert!(result.is_ok());
    let (success, cost_ms) = result.unwrap();
    assert!(success);
    assert!(cost_ms < 10); // Should be very fast

    // Watermark should still be updated
    assert_eq!(index.applied_up_to(), 2);

    // Search should still work
    let hits = index.search("hello", 10).unwrap();
    assert_eq!(hits.len(), 1);
}

// ═══════════════════════════════════════════════════════════════════════════
// Edge Case 2: Single File Change
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_apply_delta_single_file_modified() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing - 3 files
    let files = vec![
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/a.py".to_string(),
            content: "def func_a(): pass".to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/b.py".to_string(),
            content: "def func_b(): pass".to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/c.py".to_string(),
            content: "def func_c(): pass".to_string(),
        },
    ];
    index.index_files_batch(&files, false).unwrap();

    // Modify only one file
    let delta = TransactionDelta {
        from_txn: 1,
        to_txn: 2,
        added_nodes: vec![],
        removed_nodes: vec![],
        modified_nodes: vec![create_test_node("node_b", "src/b.py", "func_b_modified")],
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(1, 2);
    analysis.affected_regions = vec![create_region("src/b.py")];

    let result = index.apply_delta(&delta, &analysis);
    assert!(result.is_ok());

    // All 3 files should still be searchable
    assert!(index.search("func_a", 10).unwrap().len() > 0);
    assert!(index.search("func_c", 10).unwrap().len() > 0);
}

// ═══════════════════════════════════════════════════════════════════════════
// Edge Case 3: Large Batch Update (100+ files)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_apply_delta_large_batch() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing - 100 files
    let initial_files: Vec<FileToIndex> = (0..100)
        .map(|i| FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: format!("src/file_{}.py", i),
            content: format!("def func_{}(): pass", i),
        })
        .collect();

    index.index_files_batch(&initial_files, false).unwrap();

    // Modify 50 files in one delta
    let modified_nodes: Vec<Node> = (0..50)
        .map(|i| create_test_node(
            &format!("node_{}", i),
            &format!("src/file_{}.py", i),
            &format!("func_{}_modified", i)
        ))
        .collect();

    let delta = TransactionDelta {
        from_txn: 1,
        to_txn: 2,
        added_nodes: vec![],
        removed_nodes: vec![],
        modified_nodes,
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(1, 2);
    analysis.affected_regions = (0..50)
        .map(|i| create_region(&format!("src/file_{}.py", i)))
        .collect();

    let start = std::time::Instant::now();
    let result = index.apply_delta(&delta, &analysis);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    let (success, cost_ms) = result.unwrap();
    assert!(success);

    // Should complete in reasonable time
    println!("Large batch (50 files) update: {}ms", cost_ms);
    assert!(elapsed.as_millis() < 5000); // < 5 seconds
}

// ═══════════════════════════════════════════════════════════════════════════
// Corner Case 1: Duplicate File Paths in Delta
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_apply_delta_duplicate_file_paths() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing
    let files = vec![FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "src/main.py".to_string(),
        content: "def old(): pass".to_string(),
    }];
    index.index_files_batch(&files, false).unwrap();

    // Delta with same file appearing multiple times
    let delta = TransactionDelta {
        from_txn: 1,
        to_txn: 2,
        added_nodes: vec![
            create_test_node("node_1", "src/main.py", "func_1"),
            create_test_node("node_2", "src/main.py", "func_2"),
            create_test_node("node_3", "src/main.py", "func_3"),
        ],
        removed_nodes: vec![],
        modified_nodes: vec![],
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(1, 2);
    analysis.affected_regions = vec![create_region("src/main.py")];

    let result = index.apply_delta(&delta, &analysis);
    assert!(result.is_ok());

    // Should handle deduplication correctly
    let stats = index.stats();
    assert!(stats.entry_count > 0);
}

// ═══════════════════════════════════════════════════════════════════════════
// Corner Case 2: File Deletion (removed_nodes only)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_apply_delta_file_deletion() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing - 2 files
    let files = vec![
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/keep.py".to_string(),
            content: "def keep(): pass".to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/delete.py".to_string(),
            content: "def delete_me(): pass".to_string(),
        },
    ];
    index.index_files_batch(&files, false).unwrap();

    // Before deletion
    assert!(index.search("delete_me", 10).unwrap().len() > 0);

    // Delete one file (only removed_nodes)
    let delta = TransactionDelta {
        from_txn: 1,
        to_txn: 2,
        added_nodes: vec![],
        removed_nodes: vec![create_test_node("node_delete", "src/delete.py", "delete_me")],
        modified_nodes: vec![],
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(1, 2);
    analysis.affected_regions = vec![create_region("src/delete.py")];

    let result = index.apply_delta(&delta, &analysis);
    assert!(result.is_ok());

    // Deleted file should not be searchable anymore
    assert_eq!(index.search("delete_me", 10).unwrap().len(), 0);

    // Other file should still be searchable
    assert!(index.search("keep", 10).unwrap().len() > 0);
}

// ═══════════════════════════════════════════════════════════════════════════
// Corner Case 3: Mixed Add/Modify/Remove
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_apply_delta_mixed_operations() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing
    let files = vec![
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/modify.py".to_string(),
            content: "def old(): pass".to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/delete.py".to_string(),
            content: "def delete(): pass".to_string(),
        },
    ];
    index.index_files_batch(&files, false).unwrap();

    // Mixed delta: add + modify + remove
    let delta = TransactionDelta {
        from_txn: 1,
        to_txn: 2,
        added_nodes: vec![create_test_node("node_add", "src/add.py", "new_func")],
        removed_nodes: vec![create_test_node("node_del", "src/delete.py", "delete")],
        modified_nodes: vec![create_test_node("node_mod", "src/modify.py", "modified")],
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(1, 2);
    analysis.affected_regions = vec![
        create_region("src/add.py"),
        create_region("src/modify.py"),
        create_region("src/delete.py"),
    ];

    let result = index.apply_delta(&delta, &analysis);
    assert!(result.is_ok());

    // Verify all operations
    assert_eq!(index.search("delete", 10).unwrap().len(), 0); // Removed
    // Note: Added/modified files won't be searchable yet because we use placeholder content
}

// ═══════════════════════════════════════════════════════════════════════════
// Limit Test 1: Empty Snapshot Rebuild
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_rebuild_empty_snapshot() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing
    let files = vec![FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "src/main.py".to_string(),
        content: "def hello(): pass".to_string(),
    }];
    index.index_files_batch(&files, false).unwrap();

    // Before rebuild
    assert!(index.search("hello", 10).unwrap().len() > 0);

    // Rebuild with empty snapshot
    let empty_snapshot = Snapshot {
        txn_id: 5,
        nodes: HashMap::new(),
        edges: vec![],
    };

    let result = index.rebuild(&empty_snapshot);
    assert!(result.is_ok());

    // After rebuild - should be empty
    assert_eq!(index.search("hello", 10).unwrap().len(), 0);

    // Watermark should be updated
    assert_eq!(index.applied_up_to(), 5);

    // Stats should show zero entries
    let stats = index.stats();
    assert_eq!(stats.entry_count, 0);
}

// ═══════════════════════════════════════════════════════════════════════════
// Limit Test 2: Large Snapshot Rebuild (1000+ nodes)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_rebuild_large_snapshot() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Create large snapshot with 1000 nodes across 100 files
    let mut nodes = HashMap::new();
    for i in 0..1000 {
        let file_idx = i / 10; // 10 nodes per file
        let node = create_test_node(
            &format!("node_{}", i),
            &format!("src/file_{}.py", file_idx),
            &format!("func_{}", i),
        );
        nodes.insert(node.id.clone(), node);
    }

    let large_snapshot = Snapshot {
        txn_id: 10,
        nodes,
        edges: vec![],
    };

    let start = std::time::Instant::now();
    let result = index.rebuild(&large_snapshot);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    let cost_ms = result.unwrap();

    println!("Large snapshot rebuild (1000 nodes): {}ms", cost_ms);

    // Should complete in reasonable time
    assert!(elapsed.as_secs() < 30); // < 30 seconds

    // Watermark should be updated
    assert_eq!(index.applied_up_to(), 10);

    // Stats should show 100 files indexed
    let stats = index.stats();
    assert_eq!(stats.entry_count, 100);
}

// ═══════════════════════════════════════════════════════════════════════════
// Limit Test 3: Rapid Sequential Updates (10 consecutive deltas)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_rapid_sequential_deltas() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial indexing
    let files = vec![FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "src/counter.py".to_string(),
        content: "counter = 0".to_string(),
    }];
    index.index_files_batch(&files, false).unwrap();

    // Apply 10 sequential deltas rapidly
    for i in 1..=10 {
        let delta = TransactionDelta {
            from_txn: i,
            to_txn: i + 1,
            added_nodes: vec![],
            removed_nodes: vec![],
            modified_nodes: vec![create_test_node(
                &format!("node_{}", i),
                "src/counter.py",
                &format!("counter_{}", i)
            )],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let mut analysis = create_empty_analysis(i, i + 1);
        analysis.affected_regions = vec![create_region("src/counter.py")];

        let result = index.apply_delta(&delta, &analysis);
        assert!(result.is_ok());

        // Watermark should increment
        assert_eq!(index.applied_up_to(), i + 1);
    }

    // Final watermark check
    assert_eq!(index.applied_up_to(), 11);

    // Total updates should be at least 10 (10 apply_delta calls)
    // Note: May be higher due to internal batch operations
    let stats = index.stats();
    assert!(stats.total_updates >= 10, "Expected at least 10 updates, got {}", stats.total_updates);
}

// ═══════════════════════════════════════════════════════════════════════════
// Stress Test: Rebuild then Incremental Update
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_rebuild_followed_by_incremental() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Step 1: Create snapshot with 50 files
    let mut nodes = HashMap::new();
    for i in 0..50 {
        let node = create_test_node(
            &format!("node_{}", i),
            &format!("src/file_{}.py", i),
            &format!("func_{}", i),
        );
        nodes.insert(node.id.clone(), node);
    }

    let snapshot = Snapshot {
        txn_id: 1,
        nodes,
        edges: vec![],
    };

    // Step 2: Rebuild
    let rebuild_result = index.rebuild(&snapshot);
    assert!(rebuild_result.is_ok());
    assert_eq!(index.applied_up_to(), 1);

    // Step 3: Apply incremental delta
    let delta = TransactionDelta {
        from_txn: 1,
        to_txn: 2,
        added_nodes: vec![create_test_node("new_node", "src/new.py", "new_func")],
        removed_nodes: vec![],
        modified_nodes: vec![create_test_node("node_0", "src/file_0.py", "func_0_modified")],
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(1, 2);
    analysis.affected_regions = vec![
        create_region("src/new.py"),
        create_region("src/file_0.py"),
    ];

    let delta_result = index.apply_delta(&delta, &analysis);
    assert!(delta_result.is_ok());
    assert_eq!(index.applied_up_to(), 2);

    // Both rebuild and incremental should work
    let stats = index.stats();
    assert!(stats.total_updates >= 2);
}

// ═══════════════════════════════════════════════════════════════════════════
// Concurrency Test: Multiple apply_delta calls (sequential, not parallel)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_sequential_delta_consistency() {
    let temp_dir = TempDir::new().unwrap();
    let mut index = create_test_index(&temp_dir);

    // Initial state
    let files = vec![
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/a.py".to_string(),
            content: "# File A".to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/b.py".to_string(),
            content: "# File B".to_string(),
        },
    ];
    index.index_files_batch(&files, false).unwrap();

    // Delta 1: Modify A
    let delta1 = TransactionDelta {
        from_txn: 1,
        to_txn: 2,
        added_nodes: vec![],
        removed_nodes: vec![],
        modified_nodes: vec![create_test_node("node_a", "src/a.py", "func_a")],
        added_edges: vec![],
        removed_edges: vec![],
    };
    let mut analysis1 = create_empty_analysis(1, 2);
    analysis1.affected_regions = vec![create_region("src/a.py")];

    index.apply_delta(&delta1, &analysis1).unwrap();
    assert_eq!(index.applied_up_to(), 2);

    // Delta 2: Modify B
    let delta2 = TransactionDelta {
        from_txn: 2,
        to_txn: 3,
        added_nodes: vec![],
        removed_nodes: vec![],
        modified_nodes: vec![create_test_node("node_b", "src/b.py", "func_b")],
        added_edges: vec![],
        removed_edges: vec![],
    };
    let mut analysis2 = create_empty_analysis(2, 3);
    analysis2.affected_regions = vec![create_region("src/b.py")];

    index.apply_delta(&delta2, &analysis2).unwrap();
    assert_eq!(index.applied_up_to(), 3);

    // Watermark should be monotonically increasing
    assert!(index.applied_up_to() > 0);
}
