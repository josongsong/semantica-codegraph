use codegraph_ir::features::effect_analysis::domain::EffectType;
use codegraph_ir::features::effect_analysis::infrastructure::patterns::{
    create_default_registry, MatchContext,
};
/// Performance benchmarks for Pattern Registry vs Hardcoded approach
///
/// Measures:
/// - Pattern matching speed
/// - Registry lookup overhead
/// - Memory usage
/// - Scalability with multiple patterns
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use std::collections::HashSet;

// ============================================================================
// BASELINE: Hardcoded Pattern Matching (Original Implementation)
// ============================================================================

fn hardcoded_pattern_match(name: &str) -> HashSet<EffectType> {
    let mut effects = HashSet::new();
    let name_lower = name.to_lowercase();

    // I/O operations
    if name_lower.contains("print")
        || name_lower.contains("write")
        || name_lower.contains("read")
        || name_lower.contains("open")
        || name_lower.contains("close")
        || name_lower.contains("file")
    {
        effects.insert(EffectType::Io);
    }

    // Database operations (read)
    if name_lower.contains("query")
        || name_lower.contains("select")
        || name_lower.contains("find")
        || name_lower.contains("search")
    {
        effects.insert(EffectType::DbRead);
    }

    // Database operations (write)
    if name_lower.contains("insert")
        || name_lower.contains("update")
        || name_lower.contains("delete")
        || name_lower.contains("create")
        || name_lower.contains("drop")
        || name_lower.contains("alter")
        || name_lower.contains("commit")
        || name_lower.contains("rollback")
    {
        effects.insert(EffectType::DbWrite);
    }

    // Network operations
    if name_lower.contains("http")
        || name_lower.contains("request")
        || name_lower.contains("fetch")
        || name_lower.contains("api")
        || name_lower.contains("socket")
        || name_lower.contains("websocket")
    {
        effects.insert(EffectType::Network);
    }

    // Logging
    if name_lower.contains("log")
        || name_lower.contains("debug")
        || name_lower.contains("info")
        || name_lower.contains("warn")
        || name_lower.contains("error")
    {
        effects.insert(EffectType::Log);
    }

    // Exception handling
    if name_lower.contains("throw") || name_lower.contains("raise") || name_lower.contains("reject")
    {
        effects.insert(EffectType::Throws);
    }

    // Global mutation
    if name_lower.contains("cache")
        || name_lower.contains("singleton")
        || name_lower.contains("global")
    {
        effects.insert(EffectType::GlobalMutation);
    }

    // External calls
    if name_lower.contains("callback")
        || name_lower.contains("handler")
        || name_lower.contains("listener")
    {
        effects.insert(EffectType::ExternalCall);
    }

    effects
}

// ============================================================================
// BENCHMARKS
// ============================================================================

fn bench_single_pattern_match(c: &mut Criterion) {
    let registry = create_default_registry();

    let test_cases = vec![
        ("print", "python"),
        ("console.log", "javascript"),
        ("http_get", "python"),
        ("db_query", "javascript"),
        ("logger", "go"),
    ];

    let mut group = c.benchmark_group("Single Pattern Match");

    for (name, language) in &test_cases {
        // Benchmark registry approach
        group.bench_with_input(
            BenchmarkId::new("Registry", format!("{}/{}", name, language)),
            &(name, language),
            |b, &(name, lang)| {
                b.iter(|| {
                    let ctx = MatchContext::new(black_box(name), black_box(lang));
                    let result = registry.match_patterns(&ctx);
                    black_box(result);
                })
            },
        );

        // Benchmark hardcoded approach
        group.bench_with_input(BenchmarkId::new("Hardcoded", name), name, |b, &name| {
            b.iter(|| {
                let result = hardcoded_pattern_match(black_box(name));
                black_box(result);
            })
        });
    }

    group.finish();
}

fn bench_pattern_categories(c: &mut Criterion) {
    let registry = create_default_registry();

    let categories = vec![
        ("I/O", vec!["print", "write", "read", "open"]),
        ("Database", vec!["insert", "select", "update", "query"]),
        ("Network", vec!["http_get", "fetch", "api_call", "socket"]),
        ("Logging", vec!["log", "debug", "info", "warn"]),
        ("Async", vec!["Promise", "async", "setTimeout", "callback"]),
    ];

    let mut group = c.benchmark_group("Pattern Categories");

    for (category, patterns) in &categories {
        group.bench_with_input(
            BenchmarkId::new("Registry", category),
            patterns,
            |b, patterns| {
                b.iter(|| {
                    for pattern in patterns {
                        let ctx = MatchContext::new(black_box(*pattern), "python");
                        let result = registry.match_patterns(&ctx);
                        black_box(result);
                    }
                })
            },
        );

        group.bench_with_input(
            BenchmarkId::new("Hardcoded", category),
            patterns,
            |b, patterns| {
                b.iter(|| {
                    for pattern in patterns {
                        let result = hardcoded_pattern_match(black_box(*pattern));
                        black_box(result);
                    }
                })
            },
        );
    }

    group.finish();
}

fn bench_language_specific_patterns(c: &mut Criterion) {
    let registry = create_default_registry();

    let languages = vec![
        ("Python", vec!["print", "raise", "_global", "open"]),
        (
            "JavaScript",
            vec!["console.log", "throw", "fetch", "Promise"],
        ),
    ];

    let mut group = c.benchmark_group("Language-Specific Patterns");

    for (language, patterns) in &languages {
        group.bench_with_input(
            BenchmarkId::new("Registry", language),
            &(language.to_lowercase().as_str(), patterns),
            |b, &(lang, patterns)| {
                b.iter(|| {
                    for pattern in patterns {
                        let ctx = MatchContext::new(black_box(*pattern), black_box(lang));
                        let result = registry.match_patterns(&ctx);
                        black_box(result);
                    }
                })
            },
        );

        group.bench_with_input(
            BenchmarkId::new("Hardcoded", language),
            patterns,
            |b, patterns| {
                b.iter(|| {
                    for pattern in patterns {
                        let result = hardcoded_pattern_match(black_box(*pattern));
                        black_box(result);
                    }
                })
            },
        );
    }

    group.finish();
}

fn bench_worst_case_no_match(c: &mut Criterion) {
    let registry = create_default_registry();

    let unknown_patterns = vec![
        "unknownVar1",
        "unknownVar2",
        "randomFunction",
        "noMatchHere",
        "testVariable123",
    ];

    let mut group = c.benchmark_group("Worst Case (No Match)");

    group.bench_function("Registry", |b| {
        b.iter(|| {
            for pattern in &unknown_patterns {
                let ctx = MatchContext::new(black_box(*pattern), "python");
                let result = registry.match_patterns(&ctx);
                black_box(result);
            }
        })
    });

    group.bench_function("Hardcoded", |b| {
        b.iter(|| {
            for pattern in &unknown_patterns {
                let result = hardcoded_pattern_match(black_box(*pattern));
                black_box(result);
            }
        })
    });

    group.finish();
}

fn bench_registry_creation(c: &mut Criterion) {
    let mut group = c.benchmark_group("Registry Creation");

    group.bench_function("create_default_registry", |b| {
        b.iter(|| {
            let registry = create_default_registry();
            black_box(registry);
        })
    });

    group.finish();
}

fn bench_scalability(c: &mut Criterion) {
    let registry = create_default_registry();

    let pattern_counts = vec![1, 5, 10, 20, 50];

    let all_patterns = vec![
        "print",
        "console.log",
        "http_get",
        "db_query",
        "logger",
        "fetch",
        "insert",
        "update",
        "async",
        "Promise",
        "throw",
        "callback",
        "cache",
        "singleton",
        "alert",
        "localStorage",
        "querySelector",
        "setTimeout",
        "WebSocket",
        "innerHTML",
        "appendChild",
        "open",
        "write",
        "select",
        "delete",
        "rollback",
        "api_call",
        "debug",
        "warn",
        "error",
        "raise",
        "_global",
        "handler",
        "listener",
        "observer",
        "commit",
        "session",
        "cookie",
        "reject",
        "socket",
        "request",
        "response",
        "log_info",
        "log_error",
        "db_insert",
        "http_post",
        "file_read",
        "file_write",
        "query_all",
        "find_one",
    ];

    let mut group = c.benchmark_group("Scalability");

    for &count in &pattern_counts {
        let patterns: Vec<&str> = all_patterns.iter().take(count).copied().collect();

        group.bench_with_input(
            BenchmarkId::new("Registry", count),
            &patterns,
            |b, patterns| {
                b.iter(|| {
                    for pattern in patterns {
                        let ctx = MatchContext::new(black_box(*pattern), "python");
                        let result = registry.match_patterns(&ctx);
                        black_box(result);
                    }
                })
            },
        );

        group.bench_with_input(
            BenchmarkId::new("Hardcoded", count),
            &patterns,
            |b, patterns| {
                b.iter(|| {
                    for pattern in patterns {
                        let result = hardcoded_pattern_match(black_box(*pattern));
                        black_box(result);
                    }
                })
            },
        );
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_single_pattern_match,
    bench_pattern_categories,
    bench_language_specific_patterns,
    bench_worst_case_no_match,
    bench_registry_creation,
    bench_scalability
);
criterion_main!(benches);
