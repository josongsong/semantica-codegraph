//! Benchmarks for parsing performance
//!
//! Run with: cargo bench --bench parsing_benchmarks

use codegraph_ir::features::parsing::ports::parser::process_python_file;
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};

/// Generate a Python file with N functions
fn generate_python_functions(count: usize) -> String {
    (0..count)
        .map(|i| {
            format!(
                r#"def function_{i}(arg1, arg2):
    result = arg1 + arg2
    return result

"#
            )
        })
        .collect()
}

/// Generate a Python file with N classes
fn generate_python_classes(count: usize, methods_per_class: usize) -> String {
    (0..count)
        .map(|i| {
            let methods: String = (0..methods_per_class)
                .map(|j| {
                    format!(
                        r#"    def method_{j}(self, arg):
        return arg * 2

"#
                    )
                })
                .collect();

            format!("class Class_{i}:\n{methods}")
        })
        .collect()
}

/// Generate a Django model
fn generate_django_model(field_count: usize) -> String {
    let fields: String = (0..field_count)
        .map(|i| format!("    field_{i} = models.CharField(max_length=100)\n"))
        .collect();

    format!(
        r#"from django.db import models

class MyModel(models.Model):
{fields}
    class Meta:
        db_table = 'my_model'
"#
    )
}

/// Benchmark parsing simple functions
fn bench_parse_functions(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_functions");

    for size in [10, 50, 100, 500, 1000].iter() {
        let source = generate_python_functions(*size);

        group.throughput(Throughput::Elements(*size as u64));
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &_size| {
            b.iter(|| process_python_file(black_box(&source), "repo", "test.py", "test"));
        });
    }

    group.finish();
}

/// Benchmark parsing classes with methods
fn bench_parse_classes(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_classes");

    for (class_count, methods_per_class) in [(10, 5), (50, 5), (100, 5), (10, 20)].iter() {
        let source = generate_python_classes(*class_count, *methods_per_class);

        let total_elements = class_count * (1 + methods_per_class);
        group.throughput(Throughput::Elements(total_elements as u64));

        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{class_count}x{methods_per_class}")),
            &source,
            |b, src| {
                b.iter(|| process_python_file(black_box(src), "repo", "test.py", "test"));
            },
        );
    }

    group.finish();
}

/// Benchmark parsing Django models
fn bench_parse_django_models(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_django_models");

    for field_count in [5, 10, 20, 50].iter() {
        let source = generate_django_model(*field_count);

        group.throughput(Throughput::Elements(*field_count as u64));
        group.bench_with_input(
            BenchmarkId::from_parameter(field_count),
            &source,
            |b, src| {
                b.iter(|| process_python_file(black_box(src), "repo", "models.py", "models"));
            },
        );
    }

    group.finish();
}

/// Benchmark parsing nested structures
fn bench_parse_nested_structures(c: &mut Criterion) {
    let source = r#"
class OuterClass:
    class InnerClass1:
        def method1(self):
            pass

        def method2(self):
            pass

    class InnerClass2:
        def method1(self):
            pass

    def outer_method(self):
        pass

def top_level_function():
    def nested_function():
        def deeply_nested():
            pass
        return deeply_nested
    return nested_function
"#;

    c.bench_function("parse_nested_structures", |b| {
        b.iter(|| process_python_file(black_box(source), "repo", "nested.py", "nested"));
    });
}

/// Benchmark parsing imports
fn bench_parse_imports(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_imports");

    for import_count in [10, 50, 100, 500].iter() {
        let imports: String = (0..import_count)
            .map(|i| format!("import module_{i}\n"))
            .collect();

        let source = format!("{imports}\ndef main(): pass\n");

        group.throughput(Throughput::Elements(*import_count as u64));
        group.bench_with_input(
            BenchmarkId::from_parameter(import_count),
            &source,
            |b, src| {
                b.iter(|| process_python_file(black_box(src), "repo", "imports.py", "imports"));
            },
        );
    }

    group.finish();
}

/// Benchmark parsing real-world-like code
fn bench_parse_realistic_code(c: &mut Criterion) {
    let source = r#"
from django.db import models
from django.contrib.auth.models import User
import datetime

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=30, blank=True)
    birth_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'user_profile'
        ordering = ['-created_at']

    def get_age(self):
        if self.birth_date:
            today = datetime.date.today()
            return today.year - self.birth_date.year
        return None

    def __str__(self):
        return f"{self.user.username}'s profile"

def create_profile(user, **kwargs):
    profile = Profile.objects.create(user=user, **kwargs)
    return profile

def get_user_profiles(min_age=None):
    profiles = Profile.objects.all()
    if min_age:
        profiles = [p for p in profiles if p.get_age() and p.get_age() >= min_age]
    return profiles
"#;

    c.bench_function("parse_realistic_code", |b| {
        b.iter(|| process_python_file(black_box(source), "repo", "profile.py", "profile"));
    });
}

/// Benchmark parsing with errors
fn bench_parse_with_syntax_errors(c: &mut Criterion) {
    // Invalid Python syntax
    let source = r#"
def valid_function():
    pass

class InvalidClass
    def method(self):
        pass

def another_valid():
    return 42
"#;

    c.bench_function("parse_with_syntax_errors", |b| {
        b.iter(|| process_python_file(black_box(source), "repo", "invalid.py", "invalid"));
    });
}

criterion_group!(
    benches,
    bench_parse_functions,
    bench_parse_classes,
    bench_parse_django_models,
    bench_parse_nested_structures,
    bench_parse_imports,
    bench_parse_realistic_code,
    bench_parse_with_syntax_errors,
);

criterion_main!(benches);
