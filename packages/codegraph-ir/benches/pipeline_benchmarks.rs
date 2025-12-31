//! Benchmarks for pipeline performance
//!
//! Run with: cargo bench --bench pipeline_benchmarks

use codegraph_ir::pipeline::LayeredOrchestrator;
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};

/// Generate test files for benchmarking
fn generate_test_files(file_count: usize, functions_per_file: usize) -> Vec<(String, String)> {
    (0..file_count)
        .map(|i| {
            let file_path = format!("module_{i}.py");
            let content: String = (0..functions_per_file)
                .map(|j| format!("def func_{i}_{j}(): pass\n"))
                .collect();

            (file_path, content)
        })
        .collect()
}

/// Generate interconnected files with imports
fn generate_interconnected_files(file_count: usize) -> Vec<(String, String)> {
    (0..file_count)
        .map(|i| {
            let file_path = format!("module_{i}.py");

            // Each file imports from the previous file
            let imports = if i > 0 {
                format!("from module_{} import func_0\n\n", i - 1)
            } else {
                String::new()
            };

            let content = format!("{}def func_{i}(): pass\n\nclass Class_{i}: pass\n", imports);

            (file_path, content)
        })
        .collect()
}

/// Benchmark full pipeline processing
fn bench_pipeline_process_batch(c: &mut Criterion) {
    let mut group = c.benchmark_group("pipeline_process_batch");

    for (file_count, funcs_per_file) in [(10, 10), (50, 10), (100, 10), (10, 50)].iter() {
        let files = generate_test_files(*file_count, *funcs_per_file);

        let total_elements = file_count * funcs_per_file;
        group.throughput(Throughput::Elements(total_elements as u64));

        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{file_count}files_{funcs_per_file}funcs")),
            &files,
            |b, files| {
                b.iter(|| {
                    let mut orchestrator = LayeredOrchestrator::new();
                    orchestrator.process_batch(black_box(files.clone()), "repo", "snapshot")
                });
            },
        );
    }

    group.finish();
}

/// Benchmark incremental update
fn bench_pipeline_incremental_update(c: &mut Criterion) {
    let mut group = c.benchmark_group("pipeline_incremental_update");

    // Set up initial state
    let initial_files = generate_test_files(100, 10);
    let mut orchestrator = LayeredOrchestrator::new();
    let initial_result = orchestrator
        .process_batch(initial_files.clone(), "repo", "v1")
        .expect("Initial build failed");

    // Test incremental updates with varying change sizes
    for change_count in [1, 5, 10, 20].iter() {
        let changed_files: Vec<(String, String)> = (0..*change_count)
            .map(|i| {
                let file_path = format!("module_{i}.py");
                let content = format!("def func_{i}_modified(): pass\n");
                (file_path, content)
            })
            .collect();

        group.throughput(Throughput::Elements(*change_count as u64));

        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{change_count}_changed")),
            change_count,
            |b, _| {
                b.iter(|| {
                    let mut orch = LayeredOrchestrator::new();
                    orch.incremental_update(
                        black_box(&initial_result),
                        black_box(changed_files.clone()),
                        black_box(initial_files.clone()),
                        "repo",
                        "v2",
                    )
                });
            },
        );
    }

    group.finish();
}

/// Benchmark cross-file resolution
fn bench_pipeline_cross_file_resolution(c: &mut Criterion) {
    let mut group = c.benchmark_group("pipeline_cross_file_resolution");

    for file_count in [10, 50, 100].iter() {
        let files = generate_interconnected_files(*file_count);

        group.throughput(Throughput::Elements(*file_count as u64));

        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{file_count}_files")),
            &files,
            |b, files| {
                b.iter(|| {
                    let mut orchestrator = LayeredOrchestrator::new();
                    orchestrator.process_batch(black_box(files.clone()), "repo", "snapshot")
                });
            },
        );
    }

    group.finish();
}

/// Benchmark parallel processing vs sequential
fn bench_pipeline_parallel_vs_sequential(c: &mut Criterion) {
    let files = generate_test_files(100, 10);

    let mut group = c.benchmark_group("pipeline_parallel_vs_sequential");
    group.throughput(Throughput::Elements(100));

    // Parallel (default)
    group.bench_function("parallel", |b| {
        b.iter(|| {
            let mut orchestrator = LayeredOrchestrator::new();
            orchestrator.process_batch(black_box(files.clone()), "repo", "snapshot")
        });
    });

    group.finish();
}

/// Benchmark impact of file size
fn bench_pipeline_file_size_impact(c: &mut Criterion) {
    let mut group = c.benchmark_group("pipeline_file_size");

    for lines_per_file in [100, 500, 1000, 2000].iter() {
        let files = vec![(
            "large_file.py".to_string(),
            (0..*lines_per_file)
                .map(|i| format!("def func_{i}(): pass\n"))
                .collect::<String>(),
        )];

        group.throughput(Throughput::Elements(*lines_per_file as u64));

        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{lines_per_file}_lines")),
            &files,
            |b, files| {
                b.iter(|| {
                    let mut orchestrator = LayeredOrchestrator::new();
                    orchestrator.process_batch(black_box(files.clone()), "repo", "snapshot")
                });
            },
        );
    }

    group.finish();
}

/// Benchmark real-world Django app scenario
fn bench_pipeline_django_app(c: &mut Criterion) {
    // Simulate a small Django app structure
    let files = vec![
        (
            "models.py".to_string(),
            r#"
from django.db import models

class User(models.Model):
    username = models.CharField(max_length=100)
    email = models.EmailField()

class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()
"#
            .to_string(),
        ),
        (
            "views.py".to_string(),
            r#"
from .models import User, Post

def list_posts(request):
    posts = Post.objects.all()
    return render(request, 'posts.html', {'posts': posts})

def create_post(request):
    if request.method == 'POST':
        post = Post.objects.create(**request.POST)
        return redirect('post_detail', pk=post.pk)
"#
            .to_string(),
        ),
        (
            "serializers.py".to_string(),
            r#"
from rest_framework import serializers
from .models import User, Post

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class PostSerializer(serializers.ModelSerializer):
    author = UserSerializer()

    class Meta:
        model = Post
        fields = ['id', 'author', 'title', 'content']
"#
            .to_string(),
        ),
    ];

    c.bench_function("pipeline_django_app", |b| {
        b.iter(|| {
            let mut orchestrator = LayeredOrchestrator::new();
            orchestrator.process_batch(black_box(files.clone()), "django_app", "snapshot")
        });
    });
}

criterion_group!(
    benches,
    bench_pipeline_process_batch,
    bench_pipeline_incremental_update,
    bench_pipeline_cross_file_resolution,
    bench_pipeline_parallel_vs_sequential,
    bench_pipeline_file_size_impact,
    bench_pipeline_django_app,
);

criterion_main!(benches);
