//! Benchmark for incremental update performance
//!
//! Measures:
//! - Full rebuild time
//! - Incremental update time
//! - Speedup factor
//! - Scaling with repository size

use codegraph_orchestration::{CheckpointManager, IncrementalOrchestrator};
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use std::sync::Arc;
use uuid::Uuid;

/// Generate Python file content for benchmarking
fn generate_python_file(module_id: usize, num_functions: usize) -> String {
    let mut content = String::new();

    for i in 0..num_functions {
        content.push_str(&format!(
            r#"
def function_{}_{}():
    """Function {} in module {}"""
    x = {}
    y = {}
    return x + y

"#,
            module_id,
            i,
            i,
            module_id,
            i,
            i + 1
        ));
    }

    content.push_str(&format!(
        r#"
class Module{}Class:
    """Main class for module {}"""

    def __init__(self):
        self.id = {}

    def process(self):
        result = 0
"#,
        module_id, module_id, module_id
    ));

    for i in 0..num_functions {
        content.push_str(&format!(
            "        result += function_{}_{}()\n",
            module_id, i
        ));
    }

    content.push_str("        return result\n");

    content
}

/// Benchmark full build
fn bench_full_build(c: &mut Criterion) {
    let mut group = c.benchmark_group("full_build");

    for num_files in [10, 50, 100].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_files),
            num_files,
            |b, &num_files| {
                b.iter(|| {
                    let rt = tokio::runtime::Runtime::new().unwrap();
                    rt.block_on(async {
                        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
                        let mut orch = IncrementalOrchestrator::new(checkpoint_mgr);

                        let files: Vec<_> = (0..num_files)
                            .map(|i| (format!("module_{}.py", i), generate_python_file(i, 5)))
                            .collect();

                        let job_id = Uuid::new_v4();
                        let result = orch
                            .incremental_update(
                                job_id,
                                "bench-repo",
                                "snapshot-1",
                                files.clone(),
                                files.clone(),
                                None,
                            )
                            .await
                            .expect("Full build failed");

                        black_box(result);
                    });
                });
            },
        );
    }

    group.finish();
}

/// Benchmark incremental update with 1% file change
fn bench_incremental_1_percent(c: &mut Criterion) {
    let mut group = c.benchmark_group("incremental_1_percent");

    for num_files in [10, 50, 100].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_files),
            num_files,
            |b, &num_files| {
                // Setup: perform full build first
                let rt = tokio::runtime::Runtime::new().unwrap();
                let (checkpoint_mgr, files, cache) = rt.block_on(async {
                    let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
                    let mut orch = IncrementalOrchestrator::new(checkpoint_mgr.clone());

                    let files: Vec<_> = (0..num_files)
                        .map(|i| (format!("module_{}.py", i), generate_python_file(i, 5)))
                        .collect();

                    let job_id = Uuid::new_v4();
                    orch.incremental_update(
                        job_id,
                        "bench-repo",
                        "snapshot-1",
                        files.clone(),
                        files.clone(),
                        None,
                    )
                    .await
                    .expect("Full build failed");

                    // Load cache
                    let cache_key = format!("global_context:bench-repo:snapshot-1");
                    let cache = checkpoint_mgr
                        .load_checkpoint(&cache_key)
                        .await
                        .expect("Load failed")
                        .expect("No cache");

                    (checkpoint_mgr, files, cache)
                });

                // Benchmark: incremental update
                b.iter(|| {
                    rt.block_on(async {
                        let mut orch = IncrementalOrchestrator::new(checkpoint_mgr.clone());

                        // Change 1% of files (at least 1)
                        let num_changed = (num_files / 100).max(1);
                        let mut changed_files = Vec::new();
                        let mut all_files = files.clone();

                        for i in 0..num_changed {
                            let modified = (
                                format!("module_{}.py", i),
                                generate_python_file(i, 6), // 6 instead of 5
                            );
                            changed_files.push(modified.clone());
                            all_files[i] = modified;
                        }

                        let job_id = Uuid::new_v4();
                        let result = orch
                            .incremental_update(
                                job_id,
                                "bench-repo",
                                "snapshot-2",
                                changed_files,
                                all_files,
                                Some(cache.clone()),
                            )
                            .await
                            .expect("Incremental update failed");

                        black_box(result);
                    });
                });
            },
        );
    }

    group.finish();
}

/// Benchmark incremental update with 10% file change
fn bench_incremental_10_percent(c: &mut Criterion) {
    let mut group = c.benchmark_group("incremental_10_percent");

    for num_files in [10, 50, 100].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_files),
            num_files,
            |b, &num_files| {
                let rt = tokio::runtime::Runtime::new().unwrap();
                let (checkpoint_mgr, files, cache) = rt.block_on(async {
                    let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
                    let mut orch = IncrementalOrchestrator::new(checkpoint_mgr.clone());

                    let files: Vec<_> = (0..num_files)
                        .map(|i| (format!("module_{}.py", i), generate_python_file(i, 5)))
                        .collect();

                    let job_id = Uuid::new_v4();
                    orch.incremental_update(
                        job_id,
                        "bench-repo",
                        "snapshot-1",
                        files.clone(),
                        files.clone(),
                        None,
                    )
                    .await
                    .expect("Full build failed");

                    let cache_key = format!("global_context:bench-repo:snapshot-1");
                    let cache = checkpoint_mgr
                        .load_checkpoint(&cache_key)
                        .await
                        .expect("Load failed")
                        .expect("No cache");

                    (checkpoint_mgr, files, cache)
                });

                b.iter(|| {
                    rt.block_on(async {
                        let mut orch = IncrementalOrchestrator::new(checkpoint_mgr.clone());

                        let num_changed = (num_files / 10).max(1);
                        let mut changed_files = Vec::new();
                        let mut all_files = files.clone();

                        for i in 0..num_changed {
                            let modified = (format!("module_{}.py", i), generate_python_file(i, 6));
                            changed_files.push(modified.clone());
                            all_files[i] = modified;
                        }

                        let job_id = Uuid::new_v4();
                        let result = orch
                            .incremental_update(
                                job_id,
                                "bench-repo",
                                "snapshot-2",
                                changed_files,
                                all_files,
                                Some(cache.clone()),
                            )
                            .await
                            .expect("Incremental update failed");

                        black_box(result);
                    });
                });
            },
        );
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_full_build,
    bench_incremental_1_percent,
    bench_incremental_10_percent
);
criterion_main!(benches);
