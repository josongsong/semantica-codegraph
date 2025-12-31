//! Direct Lexical Index Integration Test
//!
//! Tests Lexical Index integration without full orchestrator complexity.
//! Focuses on verifying apply_delta() and rebuild() work in integration scenarios.

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
// Integration Test 1: IndexPlugin trait implementation verified
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_index_plugin_trait_implemented() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Verify IndexPlugin methods are available
    assert_eq!(index.applied_up_to(), 0);

    let health = index.health();
    assert!(health.is_healthy);

    println!("✅ IndexPlugin trait fully implemented");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 2: Box<dyn IndexPlugin> works
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_boxed_index_plugin() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Box it as dyn IndexPlugin (this is what orchestrator does)
    let boxed: Box<dyn IndexPlugin> = Box::new(index);

    // Verify trait methods work through Box
    assert_eq!(boxed.applied_up_to(), 0);
    assert!(boxed.health().is_healthy);

    println!("✅ Box<dyn IndexPlugin> works correctly");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 3: Full workflow with apply_delta()
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_full_workflow_with_delta() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let mut index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Step 1: Initial indexing (simulate L1-L3 pipeline output)
    let initial_files = vec![
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/main.py".to_string(),
            content: "def main():\n    print('hello')".to_string(),
        },
        FileToIndex {
            repo_id: "test_repo".to_string(),
            file_path: "src/utils.py".to_string(),
            content: "def helper():\n    return 42".to_string(),
        },
    ];
    index.index_files_batch(&initial_files, false).unwrap();

    // Verify initial state
    let main_hits = index.search("main", 10).unwrap();
    assert!(main_hits.len() > 0, "Should find 'main'");

    let helper_hits = index.search("helper", 10).unwrap();
    assert!(helper_hits.len() > 0, "Should find 'helper'");

    assert_eq!(index.applied_up_to(), 0, "Initial watermark should be 0");

    // Step 2: Agent makes changes (simulate orchestrator commit)
    let delta = TransactionDelta {
        from_txn: 0,
        to_txn: 1,
        added_nodes: vec![create_test_node("new_func", "src/new.py", "process")],
        removed_nodes: vec![],
        modified_nodes: vec![create_test_node("main_func", "src/main.py", "main_v2")],
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(0, 1);
    analysis.affected_regions = vec![
        create_region("src/new.py"),
        create_region("src/main.py"),
    ];

    // Step 3: Apply delta (orchestrator would call this)
    let result = index.apply_delta(&delta, &analysis);
    assert!(result.is_ok(), "apply_delta should succeed");

    let (success, cost_ms) = result.unwrap();
    assert!(success, "Update should be successful");
    println!("✅ apply_delta() completed in {}ms", cost_ms);

    // Verify watermark updated
    assert_eq!(index.applied_up_to(), 1, "Watermark should be updated to 1");

    println!("✅ Full workflow with delta succeeded");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 4: Full workflow with rebuild()
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_full_workflow_with_rebuild() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let mut index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Initial state
    let initial_files = vec![FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "src/old.py".to_string(),
        content: "def old_code(): pass".to_string(),
    }];
    index.index_files_batch(&initial_files, false).unwrap();

    // Verify old content exists
    let old_hits = index.search("old_code", 10).unwrap();
    assert!(old_hits.len() > 0, "Old content should exist");

    // Create new snapshot (simulate full graph snapshot)
    let mut nodes = HashMap::new();
    for i in 0..10 {
        let node = create_test_node(
            &format!("func_{}", i),
            &format!("src/file_{}.py", i / 2),
            &format!("function_{}", i),
        );
        nodes.insert(node.id.clone(), node);
    }

    let snapshot = Snapshot {
        txn_id: 5,
        nodes,
        edges: vec![],
    };

    // Rebuild from snapshot
    let result = index.rebuild(&snapshot);
    assert!(result.is_ok(), "rebuild should succeed");

    let cost_ms = result.unwrap();
    println!("✅ rebuild() completed in {}ms", cost_ms);

    // Verify watermark
    assert_eq!(index.applied_up_to(), 5, "Watermark should be 5");

    // Verify old content is gone
    let old_hits_after = index.search("old_code", 10).unwrap();
    assert_eq!(old_hits_after.len(), 0, "Old content should be removed");

    // Verify stats
    let stats = index.stats();
    assert_eq!(stats.entry_count, 5, "Should have 5 files (10 nodes / 2)");

    println!("✅ Full workflow with rebuild succeeded");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 5: Multiple sequential deltas (MVCC simulation)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_mvcc_simulation_multiple_deltas() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let mut index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Initial files
    let initial = vec![FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "src/main.py".to_string(),
        content: "def v1(): pass".to_string(),
    }];
    index.index_files_batch(&initial, false).unwrap();

    // Simulate 5 consecutive commits (like agent iterations)
    for i in 1..=5 {
        let delta = TransactionDelta {
            from_txn: i - 1,
            to_txn: i,
            added_nodes: vec![],
            removed_nodes: vec![],
            modified_nodes: vec![create_test_node(
                "main_func",
                "src/main.py",
                &format!("v{}", i + 1),
            )],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let mut analysis = create_empty_analysis(i - 1, i);
        analysis.affected_regions = vec![create_region("src/main.py")];

        let result = index.apply_delta(&delta, &analysis);
        assert!(result.is_ok(), "Delta {} should succeed", i);

        // Verify watermark progression
        assert_eq!(index.applied_up_to(), i, "Watermark should be {}", i);
    }

    assert_eq!(index.applied_up_to(), 5, "Final watermark should be 5");
    println!("✅ MVCC simulation with 5 sequential deltas succeeded");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 6: Performance benchmark
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_performance_benchmark() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let mut index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Benchmark: Large delta with 100 files
    let mut nodes = vec![];
    for i in 0..100 {
        nodes.push(create_test_node(
            &format!("node_{}", i),
            &format!("src/file_{}.py", i),
            &format!("func_{}", i),
        ));
    }

    let delta = TransactionDelta {
        from_txn: 0,
        to_txn: 1,
        added_nodes: nodes.clone(),
        removed_nodes: vec![],
        modified_nodes: vec![],
        added_edges: vec![],
        removed_edges: vec![],
    };

    let mut analysis = create_empty_analysis(0, 1);
    analysis.affected_regions = (0..100)
        .map(|i| create_region(&format!("src/file_{}.py", i)))
        .collect();

    let start = std::time::Instant::now();
    let result = index.apply_delta(&delta, &analysis);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    let (success, cost_ms) = result.unwrap();
    assert!(success);

    println!("✅ Performance: 100 files indexed in {:?} (reported: {}ms)", elapsed, cost_ms);
    assert!(elapsed.as_secs() < 5, "Should complete within 5 seconds");
}
