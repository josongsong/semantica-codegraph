//! Storage Integration Tests
//!
//! Comprehensive tests for RFC-074 Storage Backend:
//! 1. Repository CRUD
//! 2. Snapshot management
//! 3. Chunk CRUD with soft delete
//! 4. Dependency graph
//! 5. Incremental updates (content-addressable)
//! 6. Multi-repo isolation

use codegraph_ir::features::storage::{
    Chunk, ChunkStore, Dependency, DependencyType, Repository, Snapshot, SqliteChunkStore,
};
use std::collections::HashMap;

/// Helper: Create test repository
fn create_test_repo(repo_id: &str) -> Repository {
    Repository {
        repo_id: repo_id.to_string(),
        name: format!("{}-name", repo_id),
        remote_url: Some(format!("https://github.com/test/{}", repo_id)),
        local_path: Some(format!("/tmp/{}", repo_id)),
        default_branch: "main".to_string(),
        created_at: chrono::Utc::now(),
        updated_at: chrono::Utc::now(),
    }
}

/// Helper: Create test snapshot
fn create_test_snapshot(repo_id: &str, branch: &str) -> Snapshot {
    Snapshot {
        snapshot_id: Snapshot::generate_id(repo_id, branch),
        repo_id: repo_id.to_string(),
        commit_hash: Some("abc123def456".to_string()),
        branch_name: Some(branch.to_string()),
        created_at: chrono::Utc::now(),
    }
}

/// Helper: Create test chunk
fn create_test_chunk(
    repo_id: &str,
    snapshot_id: &str,
    file_path: &str,
    start_line: u32,
    fqn: &str,
) -> Chunk {
    let content = format!("fn {}() {{\n    // implementation\n}}", fqn);
    Chunk::new(
        repo_id.to_string(),
        snapshot_id.to_string(),
        file_path.to_string(),
        start_line,
        start_line + 2,
        "function".to_string(),
        content,
    )
}

#[tokio::test]
async fn test_repository_crud() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // 1. Save repository
    let repo = create_test_repo("test-repo");
    store.save_repository(&repo).await.unwrap();

    // 2. Get repository
    let fetched = store.get_repository("test-repo").await.unwrap();
    assert!(fetched.is_some());
    let fetched = fetched.unwrap();
    assert_eq!(fetched.repo_id, "test-repo");
    assert_eq!(fetched.name, "test-repo-name");

    // 3. List repositories
    let repos = store.list_repositories().await.unwrap();
    assert_eq!(repos.len(), 1);

    // 4. Update repository (UPSERT)
    let mut updated_repo = repo.clone();
    updated_repo.default_branch = "develop".to_string();
    store.save_repository(&updated_repo).await.unwrap();

    let fetched = store.get_repository("test-repo").await.unwrap().unwrap();
    assert_eq!(fetched.default_branch, "develop");
}

#[tokio::test]
async fn test_snapshot_management() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup: Create repository first
    let repo = create_test_repo("test-repo");
    store.save_repository(&repo).await.unwrap();

    // 1. Save snapshot
    let snapshot = create_test_snapshot("test-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();

    // 2. Get snapshot
    let fetched = store
        .get_snapshot(&Snapshot::generate_id("test-repo", "main"))
        .await
        .unwrap();
    assert!(fetched.is_some());
    let fetched = fetched.unwrap();
    assert_eq!(fetched.branch_name, Some("main".to_string()));

    // 3. List snapshots for repo
    let snapshots = store.list_snapshots("test-repo").await.unwrap();
    assert_eq!(snapshots.len(), 1);

    // 4. Multiple snapshots
    let dev_snapshot = create_test_snapshot("test-repo", "develop");
    store.save_snapshot(&dev_snapshot).await.unwrap();

    let snapshots = store.list_snapshots("test-repo").await.unwrap();
    assert_eq!(snapshots.len(), 2);
}

#[tokio::test]
async fn test_chunk_crud_basic() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup: Repository + Snapshot
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();

    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();

    let snapshot_id = &snapshot.snapshot_id;

    // 1. Save chunk
    let chunk = create_test_chunk("my-repo", snapshot_id, "src/main.rs", 1, "main");
    store.save_chunk(&chunk).await.unwrap();

    // 2. Get chunk by ID
    let fetched = store.get_chunk(&chunk.chunk_id).await.unwrap();
    assert!(fetched.is_some());
    let fetched = fetched.unwrap();
    assert_eq!(fetched.file_path, "src/main.rs");
    assert!(!fetched.is_deleted);

    // 3. Get chunks for repo + snapshot
    let chunks = store.get_chunks("my-repo", snapshot_id).await.unwrap();
    assert_eq!(chunks.len(), 1);

    // 4. Get chunks by file
    let chunks = store
        .get_chunks_by_file("my-repo", snapshot_id, "src/main.rs")
        .await
        .unwrap();
    assert_eq!(chunks.len(), 1);
}

#[tokio::test]
async fn test_chunk_soft_delete() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();
    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();
    let snapshot_id = &snapshot.snapshot_id;

    // 1. Create 3 chunks in same file
    let chunk1 = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 1, "foo");
    let chunk2 = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 10, "bar");
    let chunk3 = create_test_chunk("my-repo", snapshot_id, "src/main.rs", 1, "main");

    store.save_chunks(&[chunk1, chunk2, chunk3]).await.unwrap();

    // Verify all chunks exist
    let chunks = store.get_chunks("my-repo", snapshot_id).await.unwrap();
    assert_eq!(chunks.len(), 3);

    // 2. Soft delete chunks for src/lib.rs
    store
        .soft_delete_file_chunks("my-repo", snapshot_id, "src/lib.rs")
        .await
        .unwrap();

    // 3. Verify only active chunks are returned
    let chunks = store.get_chunks("my-repo", snapshot_id).await.unwrap();
    assert_eq!(chunks.len(), 1); // Only src/main.rs chunk
    assert_eq!(chunks[0].file_path, "src/main.rs");

    // 4. Verify chunks are marked as deleted (not hard deleted)
    let deleted_chunks = store
        .get_chunks_by_file("my-repo", snapshot_id, "src/lib.rs")
        .await
        .unwrap();
    // get_chunks_by_file filters out deleted chunks too
    assert_eq!(deleted_chunks.len(), 0);

    // 5. UPSERT can revive deleted chunks
    let revived_chunk = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 1, "foo");
    store.save_chunk(&revived_chunk).await.unwrap();

    let chunks = store.get_chunks("my-repo", snapshot_id).await.unwrap();
    assert_eq!(chunks.len(), 2); // Revived!
}

#[tokio::test]
async fn test_chunk_batch_operations() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();
    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();
    let snapshot_id = &snapshot.snapshot_id;

    // 1. Batch save 100 chunks
    let chunks: Vec<Chunk> = (0..100)
        .map(|i| {
            create_test_chunk(
                "my-repo",
                snapshot_id,
                &format!("src/mod{}.rs", i),
                1,
                &format!("func{}", i),
            )
        })
        .collect();

    store.save_chunks(&chunks).await.unwrap();

    // 2. Verify all chunks saved
    let fetched = store.get_chunks("my-repo", snapshot_id).await.unwrap();
    assert_eq!(fetched.len(), 100);

    // 3. Count chunks
    let count = store
        .count_chunks("my-repo", snapshot_id)
        .await
        .unwrap();
    assert_eq!(count, 100);
}

#[tokio::test]
async fn test_dependency_graph() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();
    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();
    let snapshot_id = &snapshot.snapshot_id;

    // Create chunks: main -> foo -> bar
    let main_chunk = create_test_chunk("my-repo", snapshot_id, "src/main.rs", 1, "main");
    let foo_chunk = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 1, "foo");
    let bar_chunk = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 10, "bar");

    store
        .save_chunks(&[main_chunk.clone(), foo_chunk.clone(), bar_chunk.clone()])
        .await
        .unwrap();

    // 1. Create dependencies
    let dep1 = Dependency {
        id: "dep1".to_string(),
        from_chunk_id: main_chunk.chunk_id.clone(),
        to_chunk_id: foo_chunk.chunk_id.clone(),
        relationship: DependencyType::Calls,
        confidence: 1.0,
        created_at: chrono::Utc::now(),
    };

    let dep2 = Dependency {
        id: "dep2".to_string(),
        from_chunk_id: foo_chunk.chunk_id.clone(),
        to_chunk_id: bar_chunk.chunk_id.clone(),
        relationship: DependencyType::Calls,
        confidence: 1.0,
        created_at: chrono::Utc::now(),
    };

    store.save_dependencies(&[dep1, dep2]).await.unwrap();

    // 2. Get outgoing dependencies (from main)
    let deps = store
        .get_dependencies_from(&main_chunk.chunk_id)
        .await
        .unwrap();
    assert_eq!(deps.len(), 1);
    assert_eq!(deps[0].to_chunk_id, foo_chunk.chunk_id);

    // 3. Get incoming dependencies (to bar)
    let deps = store
        .get_dependencies_to(&bar_chunk.chunk_id)
        .await
        .unwrap();
    assert_eq!(deps.len(), 1);
    assert_eq!(deps[0].from_chunk_id, foo_chunk.chunk_id);

    // 4. Get transitive dependencies
    let transitive = store
        .get_transitive_dependencies(&main_chunk.chunk_id, 2)
        .await
        .unwrap();
    assert_eq!(transitive.len(), 2); // foo + bar
}

#[tokio::test]
async fn test_content_addressable_updates() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();
    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();
    let snapshot_id = &snapshot.snapshot_id;

    // 1. Initial chunk
    let chunk = create_test_chunk("my-repo", snapshot_id, "src/main.rs", 1, "main");
    let initial_hash = chunk.content_hash.clone();

    store.save_chunk(&chunk).await.unwrap();
    store
        .update_file_metadata("my-repo", snapshot_id, "src/main.rs", initial_hash.clone())
        .await
        .unwrap();

    // 2. Get file hash
    let stored_hash = store
        .get_file_hash("my-repo", snapshot_id, "src/main.rs")
        .await
        .unwrap();
    assert_eq!(stored_hash, Some(initial_hash.clone()));

    // 3. Modified content (different hash)
    let mut modified_chunk = chunk.clone();
    modified_chunk.content = "fn main() { println!(\"changed\"); }".to_string();
    modified_chunk.content_hash = Chunk::compute_content_hash(&modified_chunk.content);

    assert!(chunk.is_modified(&modified_chunk.content_hash));

    // 4. Update chunk
    store.save_chunk(&modified_chunk).await.unwrap();
    store
        .update_file_metadata(
            "my-repo",
            snapshot_id,
            "src/main.rs",
            modified_chunk.content_hash.clone(),
        )
        .await
        .unwrap();

    // 5. Verify hash updated
    let new_hash = store
        .get_file_hash("my-repo", snapshot_id, "src/main.rs")
        .await
        .unwrap();
    assert_eq!(new_hash, Some(modified_chunk.content_hash));
    assert_ne!(new_hash, Some(initial_hash));
}

#[tokio::test]
async fn test_multi_repo_isolation() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup 2 repositories
    let repo1 = create_test_repo("repo-1");
    let repo2 = create_test_repo("repo-2");
    store.save_repository(&repo1).await.unwrap();
    store.save_repository(&repo2).await.unwrap();

    let snap1 = create_test_snapshot("repo-1", "main");
    let snap2 = create_test_snapshot("repo-2", "main");
    store.save_snapshot(&snap1).await.unwrap();
    store.save_snapshot(&snap2).await.unwrap();

    // Create chunks in both repos (same file path!)
    let chunk1 = create_test_chunk("repo-1", &snap1.snapshot_id, "src/main.rs", 1, "main");
    let chunk2 = create_test_chunk("repo-2", &snap2.snapshot_id, "src/main.rs", 1, "main");

    store.save_chunks(&[chunk1, chunk2]).await.unwrap();

    // 1. Verify isolation: repo-1 only sees its chunks
    let chunks1 = store
        .get_chunks("repo-1", &snap1.snapshot_id)
        .await
        .unwrap();
    assert_eq!(chunks1.len(), 1);
    assert_eq!(chunks1[0].repo_id, "repo-1");

    // 2. Verify isolation: repo-2 only sees its chunks
    let chunks2 = store
        .get_chunks("repo-2", &snap2.snapshot_id)
        .await
        .unwrap();
    assert_eq!(chunks2.len(), 1);
    assert_eq!(chunks2[0].repo_id, "repo-2");

    // 3. Total chunks across all repos
    let stats = store.get_stats().await.unwrap();
    assert_eq!(stats.total_repos, 2);
    assert_eq!(stats.total_snapshots, 2);
    assert_eq!(stats.total_chunks, 2);
}

#[tokio::test]
async fn test_chunk_query_by_kind() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();
    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();
    let snapshot_id = &snapshot.snapshot_id;

    // Create chunks of different kinds
    let mut func_chunk = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 1, "foo");
    func_chunk.kind = "function".to_string();

    let mut class_chunk = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 10, "MyClass");
    class_chunk.kind = "class".to_string();

    let mut var_chunk = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 20, "CONSTANT");
    var_chunk.kind = "variable".to_string();

    store
        .save_chunks(&[func_chunk, class_chunk, var_chunk])
        .await
        .unwrap();

    // Query by kind
    let functions = store
        .get_chunks_by_kind("my-repo", snapshot_id, "function")
        .await
        .unwrap();
    assert_eq!(functions.len(), 1);
    assert_eq!(functions[0].kind, "function");

    let classes = store
        .get_chunks_by_kind("my-repo", snapshot_id, "class")
        .await
        .unwrap();
    assert_eq!(classes.len(), 1);
    assert_eq!(classes[0].kind, "class");
}

#[tokio::test]
async fn test_chunk_query_by_fqn() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();
    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();
    let snapshot_id = &snapshot.snapshot_id;

    // Create chunks with FQNs
    let mut chunk1 = create_test_chunk("my-repo", snapshot_id, "src/auth.rs", 1, "login");
    chunk1.fqn = Some("myapp.auth.login".to_string());

    let mut chunk2 = create_test_chunk("my-repo", snapshot_id, "src/auth.rs", 10, "logout");
    chunk2.fqn = Some("myapp.auth.logout".to_string());

    store.save_chunks(&[chunk1, chunk2]).await.unwrap();

    // Query by FQN
    let chunks = store
        .get_chunks_by_fqn("myapp.auth.login")
        .await
        .unwrap();
    assert_eq!(chunks.len(), 1);
    assert_eq!(chunks[0].fqn, Some("myapp.auth.login".to_string()));
}

#[tokio::test]
async fn test_storage_stats() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup: 2 repos, 3 snapshots, 5 chunks
    let repo1 = create_test_repo("repo-1");
    let repo2 = create_test_repo("repo-2");
    store.save_repository(&repo1).await.unwrap();
    store.save_repository(&repo2).await.unwrap();

    let snap1 = create_test_snapshot("repo-1", "main");
    let snap2 = create_test_snapshot("repo-1", "develop");
    let snap3 = create_test_snapshot("repo-2", "main");
    store.save_snapshot(&snap1).await.unwrap();
    store.save_snapshot(&snap2).await.unwrap();
    store.save_snapshot(&snap3).await.unwrap();

    let chunks: Vec<Chunk> = vec![
        create_test_chunk("repo-1", &snap1.snapshot_id, "a.rs", 1, "a"),
        create_test_chunk("repo-1", &snap1.snapshot_id, "b.rs", 1, "b"),
        create_test_chunk("repo-1", &snap2.snapshot_id, "c.rs", 1, "c"),
        create_test_chunk("repo-2", &snap3.snapshot_id, "d.rs", 1, "d"),
        create_test_chunk("repo-2", &snap3.snapshot_id, "e.rs", 1, "e"),
    ];
    store.save_chunks(&chunks).await.unwrap();

    // Get stats
    let stats = store.get_stats().await.unwrap();
    assert_eq!(stats.total_repos, 2);
    assert_eq!(stats.total_snapshots, 3);
    assert_eq!(stats.total_chunks, 5);
    assert_eq!(stats.total_dependencies, 0);
}

#[tokio::test]
async fn test_chunk_attrs_storage() {
    let store = SqliteChunkStore::in_memory().unwrap();

    // Setup
    let repo = create_test_repo("my-repo");
    store.save_repository(&repo).await.unwrap();
    let snapshot = create_test_snapshot("my-repo", "main");
    store.save_snapshot(&snapshot).await.unwrap();
    let snapshot_id = &snapshot.snapshot_id;

    // Create chunk with custom attributes
    let mut chunk = create_test_chunk("my-repo", snapshot_id, "src/lib.rs", 1, "foo");
    let mut attrs = HashMap::new();
    attrs.insert(
        "async".to_string(),
        serde_json::Value::Bool(true),
    );
    attrs.insert(
        "params".to_string(),
        serde_json::Value::Array(vec![
            serde_json::Value::String("x".to_string()),
            serde_json::Value::String("y".to_string()),
        ]),
    );
    chunk.attrs = attrs;

    store.save_chunk(&chunk).await.unwrap();

    // Retrieve and verify attrs
    let fetched = store.get_chunk(&chunk.chunk_id).await.unwrap().unwrap();
    assert_eq!(
        fetched.attrs.get("async"),
        Some(&serde_json::Value::Bool(true))
    );
    assert!(fetched.attrs.contains_key("params"));
}
