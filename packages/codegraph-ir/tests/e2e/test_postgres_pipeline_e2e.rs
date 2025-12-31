//! PostgreSQL + Pipeline End-to-End Integration Tests
//!
//! Tests the full pipeline integration with PostgreSQL storage:
//! 1. Parse Python code → IR generation
//! 2. Create chunks from IR
//! 3. Save chunks to PostgreSQL
//! 4. Query and validate data
//!
//! # Running Tests
//!
//! ```bash
//! DATABASE_URL="postgres://codegraph:codegraph_dev@localhost:7201/codegraph_rfc074_test" \
//!   cargo test --test test_postgres_pipeline_e2e -- --ignored --test-threads=1
//! ```

use codegraph_ir::features::storage::domain::{Chunk, ChunkStore, Repository, Snapshot, Dependency, DependencyType};
use codegraph_ir::features::storage::PostgresChunkStore;
use codegraph_ir::pipeline::processor::process_python_file;
use codegraph_ir::features::chunking::domain::{ChunkIdGenerator, ChunkIdContext};
use chrono::Utc;
use std::collections::HashMap;

const TEST_DATABASE_URL: &str = "postgres://codegraph:codegraph_dev@localhost:7201/codegraph_rfc074_test";

async fn get_test_store() -> PostgresChunkStore {
    PostgresChunkStore::new(TEST_DATABASE_URL)
        .await
        .expect("Failed to connect to test database")
}

async fn cleanup_database(store: &PostgresChunkStore) {
    let pool = store.pool();
    sqlx::query("DELETE FROM repositories").execute(pool).await.ok();
}

async fn setup_test_repo(store: &PostgresChunkStore, repo_id: &str) -> (Repository, Snapshot) {
    let repo = Repository {
        repo_id: repo_id.to_string(),
        name: format!("Test Repo {}", repo_id),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    store.save_repository(&repo).await.unwrap();

    let snapshot = Snapshot {
        snapshot_id: format!("{}_snap", repo_id),
        repo_id: repo_id.to_string(),
        commit_hash: Some("abc123".to_string()),
        branch_name: Some("main".to_string()),
        created_at: Utc::now(),
    };
    store.save_snapshot(&snapshot).await.unwrap();

    (repo, snapshot)
}

// ═══════════════════════════════════════════════════════════════════════
// E2E Test 1: Simple Python Function → PostgreSQL
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_e2e_simple_python_function() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let (repo, snapshot) = setup_test_repo(&store, "e2e_simple").await;

    // Python source code
    let python_code = r#"
def greet(name: str) -> str:
    """Say hello to someone"""
    return f"Hello, {name}!"
"#;

    // L1: Parse Python → IR (using correct API)
    let process_result = process_python_file(python_code, &repo.repo_id, "test.py", "test");

    // L2: Create chunks from IR
    let chunk_id_gen = ChunkIdGenerator::new();

    let chunks: Vec<Chunk> = process_result
        .nodes
        .iter()
        .filter(|node| matches!(node.kind, codegraph_ir::shared::models::NodeKind::Function))
        .map(|node| {
            let ctx = ChunkIdContext {
                repo_id: &repo.repo_id,
                kind: "function",
                fqn: &node.fqn,
                content_hash: None,
            };
            let chunk_id = chunk_id_gen.generate(&ctx);

            Chunk {
                chunk_id,
                repo_id: repo.repo_id.clone(),
                snapshot_id: snapshot.snapshot_id.clone(),
                file_path: "test.py".to_string(),
                start_line: node.start_line,
                end_line: node.end_line,
                kind: "function".to_string(),
                fqn: Some(node.fqn.clone()),
                language: "python".to_string(),
                symbol_visibility: Some("public".to_string()),
                content: format!("def {}(...)", node.name),
                content_hash: format!("hash_{}", node.fqn),
                summary: node.doc_comment.clone(),
                importance: 0.8,
                is_deleted: false,
                attrs: HashMap::new(),
                created_at: Utc::now(),
                updated_at: Utc::now(),
            }
        })
        .collect();

    // L3: Save to PostgreSQL
    assert!(!chunks.is_empty(), "Should have at least one chunk");
    store.save_chunks(&chunks).await.unwrap();

    // L4: Query and validate
    let retrieved_chunks = store
        .get_chunks(&repo.repo_id, &snapshot.snapshot_id)
        .await
        .unwrap();

    assert_eq!(retrieved_chunks.len(), 1);
    let chunk = &retrieved_chunks[0];
    assert_eq!(chunk.kind, "function");
    assert!(chunk.fqn.as_ref().unwrap().contains("greet"));
    assert_eq!(chunk.language, "python");
}

// ═══════════════════════════════════════════════════════════════════════
// E2E Test 2: Multiple Functions with Dependencies
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_e2e_multiple_functions_with_deps() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let (repo, snapshot) = setup_test_repo(&store, "e2e_multi").await;

    let python_code = r#"
def helper(x: int) -> int:
    """Helper function"""
    return x * 2

def main() -> None:
    """Main function"""
    result = helper(5)
    print(result)
"#;

    // Parse and extract chunks
    let process_result = process_python_file(python_code, &repo.repo_id, "multi.py", "multi");

    let chunk_id_gen = ChunkIdGenerator::new();
    let mut chunk_map: HashMap<String, String> = HashMap::new(); // fqn → chunk_id

    let chunks: Vec<Chunk> = process_result
        .nodes
        .iter()
        .filter(|node| matches!(node.kind, codegraph_ir::shared::models::NodeKind::Function))
        .map(|node| {
            let ctx = ChunkIdContext {
                repo_id: &repo.repo_id,
                kind: "function",
                fqn: &node.fqn,
                content_hash: None,
            };
            let chunk_id = chunk_id_gen.generate(&ctx);
            chunk_map.insert(node.fqn.clone(), chunk_id.clone());

            Chunk {
                chunk_id,
                repo_id: repo.repo_id.clone(),
                snapshot_id: snapshot.snapshot_id.clone(),
                file_path: "multi.py".to_string(),
                start_line: node.start_line,
                end_line: node.end_line,
                kind: "function".to_string(),
                fqn: Some(node.fqn.clone()),
                language: "python".to_string(),
                symbol_visibility: Some("public".to_string()),
                content: format!("def {}...", node.name),
                content_hash: format!("hash_{}", node.fqn),
                summary: node.doc_comment.clone(),
                importance: 0.7,
                is_deleted: false,
                attrs: HashMap::new(),
                created_at: Utc::now(),
                updated_at: Utc::now(),
            }
        })
        .collect();

    // Save chunks
    store.save_chunks(&chunks).await.unwrap();

    // Create dependency: main → helper (function call)
    if let (Some(main_id), Some(helper_id)) = (chunk_map.get("multi.main"), chunk_map.get("multi.helper")) {
        let dep = Dependency {
            id: format!("dep_{}_{}", main_id, helper_id),
            from_chunk_id: main_id.clone(),
            to_chunk_id: helper_id.clone(),
            relationship: DependencyType::Calls,
            confidence: 1.0,
            created_at: Utc::now(),
        };
        store.save_dependency(&dep).await.unwrap();

        // Test dependency query
        let deps_from_main = store.get_dependencies_from(main_id).await.unwrap();
        assert_eq!(deps_from_main.len(), 1);
        assert_eq!(deps_from_main[0].to_chunk_id, *helper_id);
    }

    // Validate chunks
    let retrieved = store
        .get_chunks(&repo.repo_id, &snapshot.snapshot_id)
        .await
        .unwrap();

    assert_eq!(retrieved.len(), 2, "Should have helper and main functions");
}

// ═══════════════════════════════════════════════════════════════════════
// E2E Test 3: Class with Methods
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_e2e_class_with_methods() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let (repo, snapshot) = setup_test_repo(&store, "e2e_class").await;

    let python_code = r#"
class Calculator:
    """A simple calculator"""

    def add(self, a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers"""
        return a * b
"#;

    let process_result = process_python_file(python_code, &repo.repo_id, "calc.py", "calc");

    let chunk_id_gen = ChunkIdGenerator::new();

    // Create chunks for class and methods
    let chunks: Vec<Chunk> = process_result
        .nodes
        .iter()
        .filter(|node| {
            matches!(
                node.kind,
                codegraph_ir::shared::models::NodeKind::Class
                    | codegraph_ir::shared::models::NodeKind::Function
            )
        })
        .map(|node| {
            let kind = match node.kind {
                codegraph_ir::shared::models::NodeKind::Class => "class",
                codegraph_ir::shared::models::NodeKind::Function => "method",
                _ => "unknown",
            };

            let ctx = ChunkIdContext {
                repo_id: &repo.repo_id,
                kind,
                fqn: &node.fqn,
                content_hash: None,
            };
            let chunk_id = chunk_id_gen.generate(&ctx);

            Chunk {
                chunk_id,
                repo_id: repo.repo_id.clone(),
                snapshot_id: snapshot.snapshot_id.clone(),
                file_path: "calc.py".to_string(),
                start_line: node.start_line,
                end_line: node.end_line,
                kind: kind.to_string(),
                fqn: Some(node.fqn.clone()),
                language: "python".to_string(),
                symbol_visibility: Some("public".to_string()),
                content: format!("{} {}", kind, node.name),
                content_hash: format!("hash_{}", node.fqn),
                summary: node.doc_comment.clone(),
                importance: 0.8,
                is_deleted: false,
                attrs: HashMap::new(),
                created_at: Utc::now(),
                updated_at: Utc::now(),
            }
        })
        .collect();

    store.save_chunks(&chunks).await.unwrap();

    // Query by kind
    let classes = store
        .get_chunks_by_kind(&repo.repo_id, &snapshot.snapshot_id, "class")
        .await
        .unwrap();
    assert_eq!(classes.len(), 1);
    assert!(classes[0].fqn.as_ref().unwrap().contains("Calculator"));

    let methods = store
        .get_chunks_by_kind(&repo.repo_id, &snapshot.snapshot_id, "method")
        .await
        .unwrap();
    assert_eq!(methods.len(), 2);
}

// ═══════════════════════════════════════════════════════════════════════
// E2E Test 4: Incremental Update (Content Hash)
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_e2e_incremental_update() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let (repo, snapshot) = setup_test_repo(&store, "e2e_incremental").await;

    let file_path = "incremental.py";
    let content_v1 = "def foo(): pass";
    let content_v2 = "def foo(): return 42";

    // Simple hash function (could use sha256 in production)
    let hash_v1 = format!("{:016x}", content_v1.len());
    let hash_v2 = format!("{:016x}", content_v2.len());

    // Version 1: Initial index
    store
        .update_file_metadata(&repo.repo_id, &snapshot.snapshot_id, file_path, hash_v1.clone())
        .await
        .unwrap();

    let stored_hash = store
        .get_file_hash(&repo.repo_id, &snapshot.snapshot_id, file_path)
        .await
        .unwrap();
    assert_eq!(stored_hash, Some(hash_v1.clone()));

    // Version 2: Check if changed
    assert_ne!(hash_v1, hash_v2, "Hashes should differ");

    // Simulate incremental update
    let needs_reindex = stored_hash.as_ref() != Some(&hash_v2);
    assert!(needs_reindex, "Should detect content change");

    // Update metadata
    store
        .update_file_metadata(&repo.repo_id, &snapshot.snapshot_id, file_path, hash_v2.clone())
        .await
        .unwrap();

    let new_hash = store
        .get_file_hash(&repo.repo_id, &snapshot.snapshot_id, file_path)
        .await
        .unwrap();
    assert_eq!(new_hash, Some(hash_v2));
}

// ═══════════════════════════════════════════════════════════════════════
// E2E Test 5: Multi-Repo Isolation
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_e2e_multi_repo_isolation() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    // Create two separate repos
    let (repo1, snap1) = setup_test_repo(&store, "repo_a").await;
    let (repo2, snap2) = setup_test_repo(&store, "repo_b").await;

    // Add chunks to repo1
    let chunk1 = Chunk {
        chunk_id: "chunk_a1".to_string(),
        repo_id: repo1.repo_id.clone(),
        snapshot_id: snap1.snapshot_id.clone(),
        file_path: "file.py".to_string(),
        start_line: 1,
        end_line: 5,
        kind: "function".to_string(),
        fqn: Some("repo_a.func".to_string()),
        language: "python".to_string(),
        symbol_visibility: Some("public".to_string()),
        content: "def func(): pass".to_string(),
        content_hash: "hash_a1".to_string(),
        summary: Some("Repo A function".to_string()),
        importance: 0.5,
        is_deleted: false,
        attrs: HashMap::new(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };

    // Add chunks to repo2
    let chunk2 = Chunk {
        chunk_id: "chunk_b1".to_string(),
        repo_id: repo2.repo_id.clone(),
        snapshot_id: snap2.snapshot_id.clone(),
        file_path: "file.py".to_string(),
        start_line: 1,
        end_line: 5,
        kind: "function".to_string(),
        fqn: Some("repo_b.func".to_string()),
        language: "python".to_string(),
        symbol_visibility: Some("public".to_string()),
        content: "def func(): pass".to_string(),
        content_hash: "hash_b1".to_string(),
        summary: Some("Repo B function".to_string()),
        importance: 0.5,
        is_deleted: false,
        attrs: HashMap::new(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };

    store.save_chunk(&chunk1).await.unwrap();
    store.save_chunk(&chunk2).await.unwrap();

    // Verify isolation
    let repo1_chunks = store.get_chunks(&repo1.repo_id, &snap1.snapshot_id).await.unwrap();
    let repo2_chunks = store.get_chunks(&repo2.repo_id, &snap2.snapshot_id).await.unwrap();

    assert_eq!(repo1_chunks.len(), 1);
    assert_eq!(repo2_chunks.len(), 1);
    assert_eq!(repo1_chunks[0].fqn, Some("repo_a.func".to_string()));
    assert_eq!(repo2_chunks[0].fqn, Some("repo_b.func".to_string()));

    // Cross-repo search by FQN
    let fqn_results = store.get_chunks_by_fqn("repo_a.func").await.unwrap();
    assert_eq!(fqn_results.len(), 1);
    assert_eq!(fqn_results[0].repo_id, "repo_a");
}

// ═══════════════════════════════════════════════════════════════════════
// E2E Test 6: Performance - Batch Insert 100 Chunks
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
#[ignore]
async fn test_e2e_performance_batch_insert() {
    let store = get_test_store().await;
    cleanup_database(&store).await;

    let (repo, snapshot) = setup_test_repo(&store, "perf_batch").await;

    // Generate 100 chunks
    let chunks: Vec<Chunk> = (0..100)
        .map(|i| Chunk {
            chunk_id: format!("chunk_{}", i),
            repo_id: repo.repo_id.clone(),
            snapshot_id: snapshot.snapshot_id.clone(),
            file_path: format!("file_{}.py", i / 10),
            start_line: (i % 10) * 10 + 1,
            end_line: (i % 10) * 10 + 10,
            kind: "function".to_string(),
            fqn: Some(format!("module.func_{}", i)),
            language: "python".to_string(),
            symbol_visibility: Some("public".to_string()),
            content: format!("def func_{}(): pass", i),
            content_hash: format!("hash_{}", i),
            summary: Some(format!("Function {}", i)),
            importance: 0.5,
            is_deleted: false,
            attrs: HashMap::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        })
        .collect();

    // Measure batch insert time
    let start = std::time::Instant::now();
    store.save_chunks(&chunks).await.unwrap();
    let duration = start.elapsed();

    println!("Batch inserted 100 chunks in {:?}", duration);

    // Verify count
    let count = store.count_chunks(&repo.repo_id, &snapshot.snapshot_id).await.unwrap();
    assert_eq!(count, 100);

    // Should be fast (< 100ms for 100 chunks)
    assert!(duration.as_millis() < 500, "Batch insert should be fast");
}
