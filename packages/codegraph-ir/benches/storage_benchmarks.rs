//! Storage Performance Benchmarks
//!
//! Measures RFC-074 Storage Backend performance:
//! 1. Chunk CRUD operations
//! 2. Batch insert scaling
//! 3. Query performance (by file, by FQN, by kind)
//! 4. Dependency graph traversal
//! 5. Content-addressable hash lookups
//! 6. Soft delete operations

use codegraph_ir::features::storage::{
    Chunk, ChunkStore, Dependency, DependencyType, Repository, Snapshot, SqliteChunkStore,
};
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};

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
    let mut chunk = Chunk::new(
        repo_id.to_string(),
        snapshot_id.to_string(),
        file_path.to_string(),
        start_line,
        start_line + 10,
        "function".to_string(),
        content,
    );
    chunk.fqn = Some(format!("myapp.{}", fqn));
    chunk
}

/// Benchmark 1: Single chunk save (UPSERT)
fn bench_chunk_save_single(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    c.bench_function("chunk_save_single", |b| {
        b.to_async(&rt).iter(|| async {
            let store = SqliteChunkStore::in_memory().unwrap();
            let repo = create_test_repo("bench-repo");
            store.save_repository(&repo).await.unwrap();
            let snapshot = create_test_snapshot("bench-repo", "main");
            store.save_snapshot(&snapshot).await.unwrap();

            let chunk = create_test_chunk(
                "bench-repo",
                &snapshot.snapshot_id,
                "src/main.rs",
                1,
                "main",
            );

            black_box(store.save_chunk(&chunk).await.unwrap());
        });
    });
}

/// Benchmark 2: Batch chunk insert (scaling)
fn bench_chunk_batch_insert(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();
    let mut group = c.benchmark_group("chunk_batch_insert");

    for num_chunks in [10, 100, 1000].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_chunks),
            num_chunks,
            |b, &num_chunks| {
                b.to_async(&rt).iter(|| async move {
                    let store = SqliteChunkStore::in_memory().unwrap();
                    let repo = create_test_repo("bench-repo");
                    store.save_repository(&repo).await.unwrap();
                    let snapshot = create_test_snapshot("bench-repo", "main");
                    store.save_snapshot(&snapshot).await.unwrap();

                    // Generate chunks
                    let chunks: Vec<Chunk> = (0..num_chunks)
                        .map(|i| {
                            create_test_chunk(
                                "bench-repo",
                                &snapshot.snapshot_id,
                                &format!("src/mod{}.rs", i),
                                1,
                                &format!("func{}", i),
                            )
                        })
                        .collect();

                    black_box(store.save_chunks(&chunks).await.unwrap());
                });
            },
        );
    }

    group.finish();
}

/// Benchmark 3: Query chunks by repo + snapshot
fn bench_query_chunks_by_repo(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    // Setup: Pre-populate with 1000 chunks
    let (store, snapshot_id) = rt.block_on(async {
        let store = SqliteChunkStore::in_memory().unwrap();
        let repo = create_test_repo("bench-repo");
        store.save_repository(&repo).await.unwrap();
        let snapshot = create_test_snapshot("bench-repo", "main");
        store.save_snapshot(&snapshot).await.unwrap();

        let chunks: Vec<Chunk> = (0..1000)
            .map(|i| {
                create_test_chunk(
                    "bench-repo",
                    &snapshot.snapshot_id,
                    &format!("src/mod{}.rs", i),
                    1,
                    &format!("func{}", i),
                )
            })
            .collect();
        store.save_chunks(&chunks).await.unwrap();

        (store, snapshot.snapshot_id)
    });

    c.bench_function("query_chunks_by_repo", |b| {
        b.to_async(&rt).iter(|| async {
            let chunks = store
                .get_chunks("bench-repo", black_box(&snapshot_id))
                .await
                .unwrap();
            black_box(chunks);
        });
    });
}

/// Benchmark 4: Query chunks by file path
fn bench_query_chunks_by_file(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    // Setup: 100 chunks in same file
    let (store, snapshot_id) = rt.block_on(async {
        let store = SqliteChunkStore::in_memory().unwrap();
        let repo = create_test_repo("bench-repo");
        store.save_repository(&repo).await.unwrap();
        let snapshot = create_test_snapshot("bench-repo", "main");
        store.save_snapshot(&snapshot).await.unwrap();

        let chunks: Vec<Chunk> = (0..100)
            .map(|i| {
                create_test_chunk(
                    "bench-repo",
                    &snapshot.snapshot_id,
                    "src/large_file.rs",
                    i * 10,
                    &format!("func{}", i),
                )
            })
            .collect();
        store.save_chunks(&chunks).await.unwrap();

        (store, snapshot.snapshot_id)
    });

    c.bench_function("query_chunks_by_file", |b| {
        b.to_async(&rt).iter(|| async {
            let chunks = store
                .get_chunks_by_file("bench-repo", black_box(&snapshot_id), "src/large_file.rs")
                .await
                .unwrap();
            black_box(chunks);
        });
    });
}

/// Benchmark 5: Query chunks by FQN
fn bench_query_chunks_by_fqn(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    // Setup: 1000 chunks with different FQNs
    let (store, _) = rt.block_on(async {
        let store = SqliteChunkStore::in_memory().unwrap();
        let repo = create_test_repo("bench-repo");
        store.save_repository(&repo).await.unwrap();
        let snapshot = create_test_snapshot("bench-repo", "main");
        store.save_snapshot(&snapshot).await.unwrap();

        let chunks: Vec<Chunk> = (0..1000)
            .map(|i| {
                create_test_chunk(
                    "bench-repo",
                    &snapshot.snapshot_id,
                    &format!("src/mod{}.rs", i),
                    1,
                    &format!("func{}", i),
                )
            })
            .collect();
        store.save_chunks(&chunks).await.unwrap();

        (store, snapshot.snapshot_id)
    });

    c.bench_function("query_chunks_by_fqn", |b| {
        b.to_async(&rt).iter(|| async {
            let chunks = store
                .get_chunks_by_fqn(black_box("myapp.func500"))
                .await
                .unwrap();
            black_box(chunks);
        });
    });
}

/// Benchmark 6: Query chunks by kind
fn bench_query_chunks_by_kind(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    // Setup: Mix of functions and classes
    let (store, snapshot_id) = rt.block_on(async {
        let store = SqliteChunkStore::in_memory().unwrap();
        let repo = create_test_repo("bench-repo");
        store.save_repository(&repo).await.unwrap();
        let snapshot = create_test_snapshot("bench-repo", "main");
        store.save_snapshot(&snapshot).await.unwrap();

        let chunks: Vec<Chunk> = (0..1000)
            .map(|i| {
                let mut chunk = create_test_chunk(
                    "bench-repo",
                    &snapshot.snapshot_id,
                    &format!("src/mod{}.rs", i),
                    1,
                    &format!("item{}", i),
                );
                chunk.kind = if i % 2 == 0 {
                    "function".to_string()
                } else {
                    "class".to_string()
                };
                chunk
            })
            .collect();
        store.save_chunks(&chunks).await.unwrap();

        (store, snapshot.snapshot_id)
    });

    c.bench_function("query_chunks_by_kind", |b| {
        b.to_async(&rt).iter(|| async {
            let chunks = store
                .get_chunks_by_kind("bench-repo", black_box(&snapshot_id), "function")
                .await
                .unwrap();
            black_box(chunks);
        });
    });
}

/// Benchmark 7: Content-addressable hash lookup
fn bench_content_hash_lookup(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    // Setup: 1000 files with metadata
    let (store, snapshot_id) = rt.block_on(async {
        let store = SqliteChunkStore::in_memory().unwrap();
        let repo = create_test_repo("bench-repo");
        store.save_repository(&repo).await.unwrap();
        let snapshot = create_test_snapshot("bench-repo", "main");
        store.save_snapshot(&snapshot).await.unwrap();

        for i in 0..1000 {
            let hash = format!("hash{:04}", i);
            store
                .update_file_metadata(
                    "bench-repo",
                    &snapshot.snapshot_id,
                    &format!("src/file{}.rs", i),
                    hash,
                )
                .await
                .unwrap();
        }

        (store, snapshot.snapshot_id)
    });

    c.bench_function("content_hash_lookup", |b| {
        b.to_async(&rt).iter(|| async {
            let hash = store
                .get_file_hash("bench-repo", black_box(&snapshot_id), "src/file500.rs")
                .await
                .unwrap();
            black_box(hash);
        });
    });
}

/// Benchmark 8: Soft delete file chunks
fn bench_soft_delete_file(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    c.bench_function("soft_delete_file", |b| {
        b.to_async(&rt).iter(|| async {
            let store = SqliteChunkStore::in_memory().unwrap();
            let repo = create_test_repo("bench-repo");
            store.save_repository(&repo).await.unwrap();
            let snapshot = create_test_snapshot("bench-repo", "main");
            store.save_snapshot(&snapshot).await.unwrap();

            // Create 50 chunks in same file
            let chunks: Vec<Chunk> = (0..50)
                .map(|i| {
                    create_test_chunk(
                        "bench-repo",
                        &snapshot.snapshot_id,
                        "src/target.rs",
                        i * 10,
                        &format!("func{}", i),
                    )
                })
                .collect();
            store.save_chunks(&chunks).await.unwrap();

            black_box(
                store
                    .soft_delete_file_chunks("bench-repo", &snapshot.snapshot_id, "src/target.rs")
                    .await
                    .unwrap(),
            );
        });
    });
}

/// Benchmark 9: Dependency graph traversal
fn bench_dependency_traversal(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    // Setup: Linear dependency chain (0 -> 1 -> 2 -> ... -> 99)
    let (store, root_chunk_id) = rt.block_on(async {
        let store = SqliteChunkStore::in_memory().unwrap();
        let repo = create_test_repo("bench-repo");
        store.save_repository(&repo).await.unwrap();
        let snapshot = create_test_snapshot("bench-repo", "main");
        store.save_snapshot(&snapshot).await.unwrap();

        let chunks: Vec<Chunk> = (0..100)
            .map(|i| {
                create_test_chunk(
                    "bench-repo",
                    &snapshot.snapshot_id,
                    &format!("src/mod{}.rs", i),
                    1,
                    &format!("func{}", i),
                )
            })
            .collect();
        store.save_chunks(&chunks).await.unwrap();

        // Create linear chain
        let mut deps = Vec::new();
        for i in 0..99 {
            deps.push(Dependency {
                id: format!("dep{}", i),
                from_chunk_id: chunks[i].chunk_id.clone(),
                to_chunk_id: chunks[i + 1].chunk_id.clone(),
                relationship: DependencyType::Calls,
                confidence: 1.0,
                created_at: chrono::Utc::now(),
            });
        }
        store.save_dependencies(&deps).await.unwrap();

        (store, chunks[0].chunk_id.clone())
    });

    c.bench_function("dependency_traversal_depth_10", |b| {
        b.to_async(&rt).iter(|| async {
            let deps = store
                .get_transitive_dependencies(black_box(&root_chunk_id), 10)
                .await
                .unwrap();
            black_box(deps);
        });
    });
}

/// Benchmark 10: Realistic workload (incremental update simulation)
fn bench_incremental_update(c: &mut Criterion) {
    let rt = tokio::runtime::Runtime::new().unwrap();

    c.bench_function("incremental_update_simulation", |b| {
        b.to_async(&rt).iter(|| async {
            let store = SqliteChunkStore::in_memory().unwrap();
            let repo = create_test_repo("bench-repo");
            store.save_repository(&repo).await.unwrap();
            let snapshot = create_test_snapshot("bench-repo", "main");
            store.save_snapshot(&snapshot).await.unwrap();

            // 1. Initial index: 100 chunks across 10 files
            let initial_chunks: Vec<Chunk> = (0..10)
                .flat_map(|file_idx| {
                    (0..10).map(move |chunk_idx| {
                        create_test_chunk(
                            "bench-repo",
                            &snapshot.snapshot_id,
                            &format!("src/file{}.rs", file_idx),
                            chunk_idx * 10,
                            &format!("func{}_{}", file_idx, chunk_idx),
                        )
                    })
                })
                .collect();
            store.save_chunks(&initial_chunks).await.unwrap();

            // 2. Incremental update: 1 file changed (10 chunks)
            let changed_file = "src/file5.rs";

            // a) Soft delete old chunks
            store
                .soft_delete_file_chunks("bench-repo", &snapshot.snapshot_id, changed_file)
                .await
                .unwrap();

            // b) Insert new chunks
            let new_chunks: Vec<Chunk> = (0..10)
                .map(|i| {
                    create_test_chunk(
                        "bench-repo",
                        &snapshot.snapshot_id,
                        changed_file,
                        i * 10,
                        &format!("new_func_{}", i),
                    )
                })
                .collect();
            store.save_chunks(&new_chunks).await.unwrap();

            // c) Update file metadata
            let new_hash = Chunk::compute_content_hash("new content");
            store
                .update_file_metadata("bench-repo", &snapshot.snapshot_id, changed_file, new_hash)
                .await
                .unwrap();

            black_box(());
        });
    });
}

criterion_group!(
    benches,
    bench_chunk_save_single,
    bench_chunk_batch_insert,
    bench_query_chunks_by_repo,
    bench_query_chunks_by_file,
    bench_query_chunks_by_fqn,
    bench_query_chunks_by_kind,
    bench_content_hash_lookup,
    bench_soft_delete_file,
    bench_dependency_traversal,
    bench_incremental_update,
);
criterion_main!(benches);
