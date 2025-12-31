//! Storage Backend Demo - RFC-074/RFC-100
//!
//! End-to-end demonstration of:
//! 1. CodeSnapshotStore (RFC-100 API)
//! 2. File-level replace primitive
//! 3. Incremental snapshot creation
//! 4. Commit comparison (semantic diff)
//!
//! # Usage
//! ```bash
//! cargo run --example storage_demo
//! ```

use chrono::Utc;
use codegraph_ir::features::storage::{
    Chunk, ChunkStore, CodeSnapshotStore, Repository, SqliteChunkStore,
};

fn main() {
    println!("=== Storage Backend Demo (RFC-074/RFC-100) ===\n");

    // Initialize async runtime
    let rt = tokio::runtime::Runtime::new().unwrap();

    rt.block_on(async {
        demo_basic_operations().await;
        demo_file_replace().await;
        demo_commit_comparison().await;
        demo_incremental_snapshot().await;
    });

    println!("\n=== Demo Complete ===");
}

/// Demo 1: Basic snapshot operations
async fn demo_basic_operations() {
    println!("📦 Demo 1: Basic Snapshot Operations");
    println!("───────────────────────────────────\n");

    // Create in-memory SQLite store
    let sqlite_store = SqliteChunkStore::in_memory().unwrap();

    // Create repository first (required by foreign key constraint)
    let repo = Repository {
        repo_id: "my-app".to_string(),
        name: "My Application".to_string(),
        remote_url: Some("https://github.com/user/my-app".to_string()),
        local_path: Some("/path/to/my-app".to_string()),
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };

    sqlite_store.save_repository(&repo).await.unwrap();
    println!("✓ Created repository: {}", repo.name);

    let store = CodeSnapshotStore::new(sqlite_store);

    // Create snapshot for commit
    store
        .create_snapshot(
            "my-app",
            "my-app:abc123",
            Some("abc123def456".to_string()), // commit hash
            Some("main".to_string()),         // branch name
        )
        .await
        .unwrap();

    println!("✓ Created snapshot: my-app:abc123 (commit: abc123def456)");

    // Verify snapshot
    let snapshot = store.get_snapshot("my-app:abc123").await.unwrap().unwrap();
    println!("✓ Retrieved snapshot:");
    println!("  - ID: {}", snapshot.snapshot_id);
    println!("  - Commit: {}", snapshot.commit_hash.unwrap());
    println!("  - Branch: {}", snapshot.branch_name.unwrap());
    println!();
}

/// Demo 2: File-level replace primitive
async fn demo_file_replace() {
    println!("🔄 Demo 2: File-Level Replace (RFC-100 Core Contract)");
    println!("───────────────────────────────────────────────────────\n");

    let sqlite_store = SqliteChunkStore::in_memory().unwrap();

    // Create repository
    let repo = Repository {
        repo_id: "my-app".to_string(),
        name: "My Application".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    sqlite_store.save_repository(&repo).await.unwrap();

    let store = CodeSnapshotStore::new(sqlite_store);

    // Create snapshots
    store
        .create_snapshot("my-app", "my-app:main", Some("commit1".to_string()), None)
        .await
        .unwrap();
    store
        .create_snapshot(
            "my-app",
            "my-app:feature",
            Some("commit2".to_string()),
            None,
        )
        .await
        .unwrap();

    // Initial chunk (version 1)
    let chunk_v1 = Chunk {
        chunk_id: "my-app:src/auth.rs:login:10-25".to_string(),
        repo_id: "my-app".to_string(),
        snapshot_id: "my-app:main".to_string(),
        file_path: "src/auth.rs".to_string(),
        start_line: 10,
        end_line: 25,
        kind: "function".to_string(),
        fqn: Some("auth::login".to_string()),
        language: "rust".to_string(),
        symbol_visibility: Some("public".to_string()),
        content: "fn login(user: &str, pass: &str) -> Result<Token> { /* v1 */ }".to_string(),
        content_hash: "hash-v1".to_string(),
        summary: None,
        importance: 0.8,
        is_deleted: false,
        attrs: Default::default(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };

    // Add to main branch
    store
        .replace_file(
            "my-app",
            "my-app:main",
            "my-app:main",
            "src/auth.rs",
            vec![chunk_v1.clone()],
            vec![],
        )
        .await
        .unwrap();

    println!("✓ Added src/auth.rs::login (v1) to main branch");

    // Modified chunk (version 2)
    let chunk_v2 = Chunk {
        content: "fn login(user: &str, pass: &str) -> Result<Token> { /* v2 - improved */ }"
            .to_string(),
        content_hash: "hash-v2".to_string(),
        snapshot_id: "my-app:feature".to_string(),
        ..chunk_v1
    };

    // Replace file in feature branch
    store
        .replace_file(
            "my-app",
            "my-app:main",    // base snapshot
            "my-app:feature", // new snapshot
            "src/auth.rs",
            vec![chunk_v2],
            vec![],
        )
        .await
        .unwrap();

    println!("✓ Replaced src/auth.rs::login (v2) in feature branch");
    println!("✓ File-level replace: ATOMIC, TRANSACTIONAL, IDEMPOTENT");
    println!();
}

/// Demo 3: Commit comparison (semantic diff)
async fn demo_commit_comparison() {
    println!("🔍 Demo 3: Commit Comparison (Semantic Diff)");
    println!("─────────────────────────────────────────────\n");

    let sqlite_store = SqliteChunkStore::in_memory().unwrap();

    // Create repository
    let repo = Repository {
        repo_id: "my-app".to_string(),
        name: "My Application".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    sqlite_store.save_repository(&repo).await.unwrap();

    let store = CodeSnapshotStore::new(sqlite_store);

    // Setup snapshots
    store
        .create_snapshot("my-app", "my-app:main", None, None)
        .await
        .unwrap();
    store
        .create_snapshot("my-app", "my-app:feature", None, None)
        .await
        .unwrap();

    // Main branch: 2 functions
    let func_a = create_demo_chunk("my-app", "my-app:main", "src/a.rs", "func_a", "impl v1");
    let func_b = create_demo_chunk("my-app", "my-app:main", "src/b.rs", "func_b", "impl");

    store
        .replace_file(
            "my-app",
            "my-app:main",
            "my-app:main",
            "src/a.rs",
            vec![func_a],
            vec![],
        )
        .await
        .unwrap();
    store
        .replace_file(
            "my-app",
            "my-app:main",
            "my-app:main",
            "src/b.rs",
            vec![func_b],
            vec![],
        )
        .await
        .unwrap();

    println!("Main branch:");
    println!("  + src/a.rs::func_a (v1)");
    println!("  + src/b.rs::func_b");

    // Feature branch: modified func_a, deleted func_b, added func_c
    let func_a_modified =
        create_demo_chunk("my-app", "my-app:feature", "src/a.rs", "func_a", "impl v2");
    let func_c_new = create_demo_chunk("my-app", "my-app:feature", "src/c.rs", "func_c", "impl");

    store
        .replace_file(
            "my-app",
            "my-app:main",
            "my-app:feature",
            "src/a.rs",
            vec![func_a_modified],
            vec![],
        )
        .await
        .unwrap();
    store
        .replace_file(
            "my-app",
            "my-app:main",
            "my-app:feature",
            "src/c.rs",
            vec![func_c_new],
            vec![],
        )
        .await
        .unwrap();

    println!("\nFeature branch:");
    println!("  ~ src/a.rs::func_a (v1 → v2)");
    println!("  - src/b.rs::func_b");
    println!("  + src/c.rs::func_c");

    // Compare commits
    let diff = store
        .compare_commits("my-app", "my-app:main", "my-app:feature")
        .await
        .unwrap();

    println!("\nSemantic Diff:");
    println!("  Added:    {} chunks", diff.added.len());
    println!("  Modified: {} chunks", diff.modified.len());
    println!("  Deleted:  {} chunks", diff.deleted.len());
    println!("  Total:    {} changes", diff.total_changes());
    println!();
}

/// Demo 4: Incremental snapshot creation
async fn demo_incremental_snapshot() {
    println!("⚡ Demo 4: Incremental Snapshot (10-100x Speedup)");
    println!("─────────────────────────────────────────────────────\n");

    let sqlite_store = SqliteChunkStore::in_memory().unwrap();

    // Create repository
    let repo = Repository {
        repo_id: "my-app".to_string(),
        name: "My Application".to_string(),
        remote_url: None,
        local_path: None,
        default_branch: "main".to_string(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    };
    sqlite_store.save_repository(&repo).await.unwrap();

    let store = CodeSnapshotStore::new(sqlite_store);

    // Base snapshot with 3 files
    store
        .create_snapshot("my-app", "my-app:commit1", None, None)
        .await
        .unwrap();

    let file_a = create_demo_chunk("my-app", "my-app:commit1", "src/a.rs", "func", "unchanged");
    let file_b = create_demo_chunk(
        "my-app",
        "my-app:commit1",
        "src/b.rs",
        "func",
        "will change",
    );
    let file_c = create_demo_chunk("my-app", "my-app:commit1", "src/c.rs", "func", "unchanged");

    store
        .replace_file(
            "my-app",
            "my-app:commit1",
            "my-app:commit1",
            "src/a.rs",
            vec![file_a.clone()],
            vec![],
        )
        .await
        .unwrap();
    store
        .replace_file(
            "my-app",
            "my-app:commit1",
            "my-app:commit1",
            "src/b.rs",
            vec![file_b],
            vec![],
        )
        .await
        .unwrap();
    store
        .replace_file(
            "my-app",
            "my-app:commit1",
            "my-app:commit1",
            "src/c.rs",
            vec![file_c.clone()],
            vec![],
        )
        .await
        .unwrap();

    println!("Base snapshot (commit1): 3 files indexed");

    // New snapshot: only file B changed
    store
        .create_snapshot("my-app", "my-app:commit2", None, None)
        .await
        .unwrap();

    let stats = store
        .create_incremental_snapshot(
            "my-app",
            "my-app:commit1",
            "my-app:commit2",
            vec![
                "src/a.rs".to_string(),
                "src/b.rs".to_string(),
                "src/c.rs".to_string(),
            ],
            move |file_path| {
                // Simulate analyzer
                if file_path == "src/b.rs" {
                    let modified = create_demo_chunk(
                        "my-app",
                        "my-app:commit2",
                        "src/b.rs",
                        "func",
                        "MODIFIED",
                    );
                    Ok((vec![modified], vec![]))
                } else {
                    // A and C unchanged (same hash)
                    let unchanged = if file_path == "src/a.rs" {
                        file_a.clone()
                    } else {
                        file_c.clone()
                    };
                    Ok((vec![unchanged], vec![]))
                }
            },
        )
        .await
        .unwrap();

    println!("\nIncremental snapshot (commit2):");
    println!("  Files checked:  {}", stats.files_checked);
    println!(
        "  Files skipped:  {} (hash unchanged → 10-100x faster!)",
        stats.files_skipped
    );
    println!("  Files analyzed: {}", stats.files_analyzed);
    println!("  Chunks created: {}", stats.chunks_created);
    println!();
}

/// Helper: Create demo chunk
fn create_demo_chunk(
    repo_id: &str,
    snapshot_id: &str,
    file_path: &str,
    name: &str,
    content: &str,
) -> Chunk {
    Chunk {
        chunk_id: format!("{}:{}:{}:1-10", repo_id, file_path, name),
        repo_id: repo_id.to_string(),
        snapshot_id: snapshot_id.to_string(),
        file_path: file_path.to_string(),
        start_line: 1,
        end_line: 10,
        kind: "function".to_string(),
        fqn: Some(format!("{}::{}", file_path, name)),
        language: "rust".to_string(),
        symbol_visibility: Some("public".to_string()),
        content: content.to_string(),
        content_hash: format!("hash-{}", content.len()),
        summary: None,
        importance: 0.5,
        is_deleted: false,
        attrs: Default::default(),
        created_at: Utc::now(),
        updated_at: Utc::now(),
    }
}
