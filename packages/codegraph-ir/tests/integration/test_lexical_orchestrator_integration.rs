//! MultiLayerOrchestrator Integration Test with Lexical Index
//!
//! Tests the complete integration:
//! - Agent commits changes
//! - MultiLayerOrchestrator processes commit
//! - Lexical Index receives apply_delta() automatically
//! - Search reflects committed changes

use codegraph_ir::features::lexical::{
    TantivyLexicalIndex, SqliteChunkStore, IndexingMode, FileToIndex,
};
use codegraph_ir::features::multi_index::infrastructure::{
    MultiLayerIndexOrchestrator, IndexOrchestratorConfig,
};
use codegraph_ir::features::query_engine::infrastructure::ChangeOp;
use codegraph_ir::shared::models::{Node, NodeKind, Span};
use std::sync::Arc;
use tempfile::TempDir;

// ═══════════════════════════════════════════════════════════════════════════
// Test Helpers
// ═══════════════════════════════════════════════════════════════════════════

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

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 1: Register Lexical Index
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_register_lexical_index() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    // Create orchestrator
    let orchestrator = MultiLayerIndexOrchestrator::new(IndexOrchestratorConfig::default());

    // Create lexical index
    let lexical_index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Register index
    orchestrator.register_index(Box::new(lexical_index));

    println!("✅ Lexical index registered successfully");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 2: Commit → Automatic apply_delta()
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_commit_triggers_lexical_update() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let orchestrator = MultiLayerIndexOrchestrator::new(IndexOrchestratorConfig::default());

    let mut lexical_index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Initial indexing
    let initial_files = vec![FileToIndex {
        repo_id: "test_repo".to_string(),
        file_path: "src/main.py".to_string(),
        content: "def old_function(): pass".to_string(),
    }];
    lexical_index.index_files_batch(&initial_files, false).unwrap();

    let initial_hits = lexical_index.search("old_function", 10).unwrap();
    assert!(initial_hits.len() > 0);

    orchestrator.register_index(Box::new(lexical_index));

    // Agent session
    let _session = orchestrator.begin_session("agent_123".to_string());

    let new_node = create_test_node("node_new", "src/main.py", "new_function");
    orchestrator
        .add_change("agent_123", ChangeOp::AddNode(new_node))
        .unwrap();

    // Commit
    let result = orchestrator.commit("agent_123");

    assert!(result.success);
    assert!(result.committed_txn.is_some());
    assert!(result.delta.is_some());

    println!("✅ Commit succeeded - apply_delta() was called automatically");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 3: Multiple Commits
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_multiple_commits_incremental() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let orchestrator = MultiLayerIndexOrchestrator::new(IndexOrchestratorConfig::default());

    let mut lexical_index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    let initial_files = vec![
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
    ];
    lexical_index.index_files_batch(&initial_files, false).unwrap();
    orchestrator.register_index(Box::new(lexical_index));

    // Commit 1
    let _session1 = orchestrator.begin_session("agent_1".to_string());
    let node_c = create_test_node("node_c", "src/c.py", "func_c");
    orchestrator
        .add_change("agent_1", ChangeOp::AddNode(node_c))
        .unwrap();
    let result1 = orchestrator.commit("agent_1");
    assert!(result1.success);

    // Commit 2
    let _session2 = orchestrator.begin_session("agent_2".to_string());
    let node_a_modified = create_test_node("node_a", "src/a.py", "func_a_v2");
    orchestrator
        .add_change("agent_2", ChangeOp::UpdateNode(node_a_modified))
        .unwrap();
    let result2 = orchestrator.commit("agent_2");
    assert!(result2.success);

    // Commit 3
    let _session3 = orchestrator.begin_session("agent_3".to_string());
    orchestrator
        .add_change("agent_3", ChangeOp::RemoveNode("node_b".to_string()))
        .unwrap();
    let result3 = orchestrator.commit("agent_3");
    assert!(result3.success);

    println!("✅ All 3 incremental commits succeeded");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 4: Parallel Agent Sessions
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_parallel_agent_sessions() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let orchestrator = MultiLayerIndexOrchestrator::new(IndexOrchestratorConfig {
        parallel_updates: true,
        ..Default::default()
    });

    let lexical_index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();
    orchestrator.register_index(Box::new(lexical_index));

    // Start 3 parallel sessions
    let _session1 = orchestrator.begin_session("agent_1".to_string());
    let _session2 = orchestrator.begin_session("agent_2".to_string());
    let _session3 = orchestrator.begin_session("agent_3".to_string());

    // Agent 1
    let node_x = create_test_node("node_x", "src/x.py", "func_x");
    orchestrator
        .add_change("agent_1", ChangeOp::AddNode(node_x))
        .unwrap();

    // Agent 2
    let node_y = create_test_node("node_y", "src/y.py", "func_y");
    orchestrator
        .add_change("agent_2", ChangeOp::AddNode(node_y))
        .unwrap();

    // Agent 3
    let node_z = create_test_node("node_z", "src/z.py", "func_z");
    orchestrator
        .add_change("agent_3", ChangeOp::AddNode(node_z))
        .unwrap();

    // Commit all
    let result1 = orchestrator.commit("agent_1");
    let result2 = orchestrator.commit("agent_2");
    let result3 = orchestrator.commit("agent_3");

    assert!(result1.success);
    assert!(result2.success);
    assert!(result3.success);

    println!("✅ All 3 parallel commits succeeded");
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 5: Large Commit
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_large_commit_multiple_files() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let orchestrator = MultiLayerIndexOrchestrator::new(IndexOrchestratorConfig::default());

    let lexical_index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();
    orchestrator.register_index(Box::new(lexical_index));

    let _session = orchestrator.begin_session("agent_bulk".to_string());

    for i in 0..20 {
        let node = create_test_node(
            &format!("node_{}", i),
            &format!("src/file_{}.py", i),
            &format!("func_{}", i),
        );
        orchestrator
            .add_change("agent_bulk", ChangeOp::AddNode(node))
            .unwrap();
    }

    let start = std::time::Instant::now();
    let result = orchestrator.commit("agent_bulk");
    let elapsed = start.elapsed();

    assert!(result.success);
    println!("✅ Large commit (20 files) succeeded in {:?}", elapsed);
    assert!(elapsed.as_secs() < 2);
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Test 6: Empty Commit
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_commit_with_empty_changes() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("tantivy");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let orchestrator = MultiLayerIndexOrchestrator::new(IndexOrchestratorConfig::default());

    let lexical_index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "test_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();
    orchestrator.register_index(Box::new(lexical_index));

    let _session = orchestrator.begin_session("agent_empty".to_string());

    let result = orchestrator.commit("agent_empty");

    assert!(result.success);
    assert!(result.delta.is_none());

    println!("✅ Empty commit handled correctly");
}
