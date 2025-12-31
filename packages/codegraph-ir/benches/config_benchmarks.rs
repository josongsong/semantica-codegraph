//! Performance benchmarks for RFC-CONFIG
//!
//! Ensures config operations meet performance targets:
//! - Build from preset: < 1μs
//! - YAML parsing: < 100μs
//! - Validation: < 10μs
//! - Clone: < 1μs

use codegraph_ir::config::*;
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};

// ============================================================================
// Basic Operations
// ============================================================================

fn bench_preset_build(c: &mut Criterion) {
    let mut group = c.benchmark_group("preset_build");

    for preset in [Preset::Fast, Preset::Balanced, Preset::Thorough] {
        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{:?}", preset)),
            &preset,
            |b, &preset| {
                b.iter(|| {
                    let config = PipelineConfig::preset(preset).build();
                    black_box(config)
                });
            },
        );
    }

    group.finish();
}

fn bench_stage_override(c: &mut Criterion) {
    c.bench_function("stage_override", |b| {
        b.iter(|| {
            let config = PipelineConfig::preset(Preset::Balanced)
                .taint(|c| c.max_depth(50).max_paths(500))
                .pta(|c| c.auto_threshold(5000))
                .build();
            black_box(config)
        });
    });
}

fn bench_yaml_parsing(c: &mut Criterion) {
    use std::io::Write;

    let yaml_content = r#"version: 1
preset: Balanced
stages:
  taint: true
  pta: true
overrides:
  taint:
    max_depth: 50
    max_paths: 500
  pta:
    auto_threshold: 5000
"#;

    // Write YAML to temp file
    let yaml_path = "/tmp/bench_config.yaml";
    let mut file = std::fs::File::create(yaml_path).unwrap();
    file.write_all(yaml_content.as_bytes()).unwrap();
    drop(file);

    let mut group = c.benchmark_group("yaml_parsing");
    group.throughput(Throughput::Bytes(yaml_content.len() as u64));

    group.bench_function("parse", |b| {
        b.iter(|| {
            let config = PipelineConfig::from_yaml(black_box(yaml_path));
            black_box(config)
        });
    });

    group.finish();
    std::fs::remove_file(yaml_path).ok();
}

fn bench_yaml_roundtrip(c: &mut Criterion) {
    let config = PipelineConfig::preset(Preset::Balanced)
        .taint(|c| c.max_depth(50))
        .build()
        .unwrap()
        .into_inner();

    c.bench_function("yaml_roundtrip", |b| {
        b.iter(|| {
            let yaml = config.to_yaml().unwrap();
            let yaml_path = "/tmp/bench_roundtrip.yaml";
            std::fs::write(yaml_path, &yaml).unwrap();
            let recovered = PipelineConfig::from_yaml(yaml_path);
            std::fs::remove_file(yaml_path).ok();
            black_box(recovered)
        });
    });
}

fn bench_validation(c: &mut Criterion) {
    let mut group = c.benchmark_group("validation");

    // Valid config
    let valid = TaintConfig::from_preset(Preset::Fast)
        .max_depth(50)
        .max_paths(500);
    group.bench_function("valid_config", |b| {
        b.iter(|| {
            let result = valid.validate();
            black_box(result)
        });
    });

    // Invalid config (should fail fast)
    let invalid = TaintConfig::from_preset(Preset::Fast)
        .max_depth(0) // Invalid: must be >= 1
        .max_paths(500);
    group.bench_function("invalid_config", |b| {
        b.iter(|| {
            let result = invalid.validate();
            black_box(result)
        });
    });

    group.finish();
}

fn bench_config_copy(c: &mut Criterion) {
    // Benchmark creating identical configs (no clone trait available)
    c.bench_function("config_copy", |b| {
        b.iter(|| {
            let config = PipelineConfig::preset(Preset::Thorough)
                .taint(|c| c.max_depth(100))
                .pta(|c| c.auto_threshold(10000))
                .build()
                .unwrap();
            black_box(config)
        });
    });
}

fn bench_describe(c: &mut Criterion) {
    let config = PipelineConfig::preset(Preset::Balanced)
        .build()
        .unwrap()
        .into_inner();

    c.bench_function("describe", |b| {
        b.iter(|| {
            let desc = config.describe();
            black_box(desc)
        });
    });
}

// ============================================================================
// Stress Tests
// ============================================================================

fn bench_builder_chaining(c: &mut Criterion) {
    let mut group = c.benchmark_group("builder_chaining");

    for chain_length in [1, 5, 10, 20] {
        group.bench_with_input(
            BenchmarkId::from_parameter(chain_length),
            &chain_length,
            |b, &n| {
                b.iter(|| {
                    let mut builder = PipelineConfig::preset(Preset::Fast);
                    for i in 0..n {
                        let depth = 10 + i * 5;
                        builder = builder.taint(|c| c.max_depth(depth));
                    }
                    let config = builder.build();
                    black_box(config)
                });
            },
        );
    }

    group.finish();
}

fn bench_many_configs(c: &mut Criterion) {
    let mut group = c.benchmark_group("many_configs");

    for count in [10, 100, 1000] {
        group.bench_with_input(BenchmarkId::from_parameter(count), &count, |b, &n| {
            b.iter(|| {
                let configs: Vec<_> = (0..n)
                    .map(|i| {
                        let preset = match i % 3 {
                            0 => Preset::Fast,
                            1 => Preset::Balanced,
                            _ => Preset::Thorough,
                        };
                        PipelineConfig::preset(preset).build().unwrap()
                    })
                    .collect();
                black_box(configs)
            });
        });
    }

    group.finish();
}

// ============================================================================
// Regression Tests (Performance Targets)
// ============================================================================

fn bench_regression_targets(c: &mut Criterion) {
    let mut group = c.benchmark_group("regression_targets");

    // Target: Build from preset < 1μs
    group.bench_function("preset_build_target", |b| {
        b.iter(|| {
            let config = PipelineConfig::preset(Preset::Fast).build();
            black_box(config)
        });
    });

    // Target: YAML parsing < 100μs
    let yaml_content = "version: 1\npreset: Fast\nstages:\n  taint: true\n";
    let yaml_path = "/tmp/bench_regression.yaml";
    std::fs::write(yaml_path, yaml_content).unwrap();

    group.bench_function("yaml_parse_target", |b| {
        b.iter(|| {
            let config = PipelineConfig::from_yaml(black_box(yaml_path));
            black_box(config)
        });
    });

    // Target: Validation < 10μs
    let config = TaintConfig::from_preset(Preset::Fast);
    group.bench_function("validation_target", |b| {
        b.iter(|| {
            let result = config.validate();
            black_box(result)
        });
    });

    // Target: Build < 1μs (replacing clone)
    group.bench_function("build_target", |b| {
        b.iter(|| {
            let config = PipelineConfig::preset(Preset::Fast).build();
            black_box(config)
        });
    });

    std::fs::remove_file(yaml_path).ok();

    group.finish();
}

// ============================================================================
// Memory Benchmarks
// ============================================================================

fn bench_memory_usage(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_usage");

    // Measure memory usage of storing many configs
    group.bench_function("1000_configs", |b| {
        b.iter(|| {
            let configs: Vec<_> = (0..1000)
                .map(|_| PipelineConfig::preset(Preset::Balanced).build().unwrap())
                .collect();
            black_box(configs)
        });
    });

    group.finish();
}

criterion_group!(
    benches,
    bench_preset_build,
    bench_stage_override,
    bench_yaml_parsing,
    bench_yaml_roundtrip,
    bench_validation,
    bench_config_copy,
    bench_describe,
    bench_builder_chaining,
    bench_many_configs,
    bench_regression_targets,
    bench_memory_usage,
);

criterion_main!(benches);
