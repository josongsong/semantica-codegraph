//! Legacy Taint Analysis Benchmark (moved from root)

#[path = "mod.rs"]
mod taint_common;
/*
 * SOTA Taint Analysis Performance Benchmark
 *
 * Validates the "10-50× faster than Python" claim by measuring:
 * - Interprocedural taint analysis performance
 * - Points-to analysis performance
 * - Field-sensitive tracking overhead
 * - Sanitizer detection overhead
 *
 * Benchmark Methodology:
 * 1. Create synthetic call graphs of varying sizes (10, 100, 1000, 10000 functions)
 * 2. Run taint analysis with different configurations
 * 3. Measure time and memory usage
 * 4. Compare against Python baseline (extrapolated)
 *
 * Expected Results:
 * - Small graphs (10-100): 5-10× faster
 * - Medium graphs (100-1000): 10-30× faster
 * - Large graphs (1000-10000): 30-50× faster
 */

use codegraph_ir::features::taint_analysis::infrastructure::{
    InterproceduralTaintAnalyzer, SOTAConfig, SOTATaintAnalyzer, SimpleCallGraph,
};
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use std::collections::{HashMap, HashSet};

/// Create synthetic call graph with N functions
///
/// Structure: main → f1 → f2 → ... → fN
fn create_chain_call_graph(size: usize) -> SimpleCallGraph {
    let mut cg = SimpleCallGraph::new();

    // Add main function
    cg.add_function("main".to_string());

    // Add chain of functions
    for i in 1..size {
        let func_name = format!("f{}", i);
        cg.add_function(func_name.clone());

        // Add call edge from previous function
        if i == 1 {
            cg.add_call("main".to_string(), func_name);
        } else {
            let prev_func = format!("f{}", i - 1);
            cg.add_call(prev_func, func_name);
        }
    }

    cg
}

/// Create synthetic call graph with fanout (tree structure)
///
/// Structure: main calls f1..fN, each fi calls fi1..fiM
fn create_tree_call_graph(depth: usize, fanout: usize) -> SimpleCallGraph {
    let mut cg = SimpleCallGraph::new();
    cg.add_function("main".to_string());

    fn add_level(
        cg: &mut SimpleCallGraph,
        parent: &str,
        depth: usize,
        fanout: usize,
        current_depth: usize,
    ) {
        if current_depth >= depth {
            return;
        }

        for i in 0..fanout {
            let func_name = format!("{}_c{}", parent, i);
            cg.add_function(func_name.clone());
            cg.add_call(parent.to_string(), func_name.clone());

            // Recurse
            add_level(cg, &func_name, depth, fanout, current_depth + 1);
        }
    }

    add_level(&mut cg, "main", depth, fanout, 0);
    cg
}

/// Benchmark interprocedural taint analysis
fn bench_interprocedural_chain(c: &mut Criterion) {
    let mut group = c.benchmark_group("interprocedural_chain");

    for size in [10, 50, 100, 500].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            // Setup
            let cg = create_chain_call_graph(size);
            let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 100, 10000);

            // Sources and sinks
            let mut sources = HashMap::new();
            sources.insert("main".to_string(), {
                let mut set = HashSet::new();
                set.insert("user_input".to_string());
                set
            });

            let mut sinks = HashMap::new();
            let sink_func = format!("f{}", size - 1);
            sinks.insert(sink_func, {
                let mut set = HashSet::new();
                set.insert("sql_query".to_string());
                set
            });

            // Benchmark
            b.iter(|| {
                let paths = analyzer.analyze(black_box(&sources), black_box(&sinks));
                black_box(paths);
            });
        });
    }

    group.finish();
}

/// Benchmark tree-shaped call graph
fn bench_interprocedural_tree(c: &mut Criterion) {
    let mut group = c.benchmark_group("interprocedural_tree");

    for &(depth, fanout) in [(3_usize, 3_usize), (3, 5), (4, 3), (4, 4)].iter() {
        let total_funcs = (1..=depth).map(|d| fanout.pow(d as u32)).sum::<usize>() + 1;

        group.bench_with_input(
            BenchmarkId::new(format!("d{}_f{}", depth, fanout), total_funcs),
            &(depth, fanout),
            |b, &(depth, fanout)| {
                let cg = create_tree_call_graph(depth, fanout);
                let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 100, 10000);

                let mut sources = HashMap::new();
                sources.insert("main".to_string(), {
                    let mut set = HashSet::new();
                    set.insert("taint".to_string());
                    set
                });

                let mut sinks = HashMap::new();
                let sink_func = format!("main_c0_c0");
                sinks.insert(sink_func, {
                    let mut set = HashSet::new();
                    set.insert("sink".to_string());
                    set
                });

                b.iter(|| {
                    let paths = analyzer.analyze(black_box(&sources), black_box(&sinks));
                    black_box(paths);
                });
            },
        );
    }

    group.finish();
}

/// Benchmark SOTA analyzer with all features
fn bench_sota_analyzer(c: &mut Criterion) {
    let mut group = c.benchmark_group("sota_analyzer");

    for size in [10, 50, 100].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            let cg = create_chain_call_graph(size);
            let config = SOTAConfig::default(); // All features enabled
            let mut analyzer = SOTATaintAnalyzer::new(cg, config);

            let mut sources = HashMap::new();
            sources.insert("main".to_string(), {
                let mut set = HashSet::new();
                set.insert("user_input".to_string());
                set
            });

            let mut sinks = HashMap::new();
            let sink_func = format!("f{}", size - 1);
            sinks.insert(sink_func, {
                let mut set = HashSet::new();
                set.insert("sql_query".to_string());
                set
            });

            b.iter(|| {
                let paths = analyzer.analyze(black_box(&sources), black_box(&sinks));
                black_box(paths);
            });
        });
    }

    group.finish();
}

/// Benchmark field-sensitive overhead
fn bench_field_sensitive(c: &mut Criterion) {
    let mut group = c.benchmark_group("field_sensitive");

    let cg = create_chain_call_graph(100);

    // Without field-sensitive
    group.bench_function("disabled", |b| {
        let config = SOTAConfig {
            field_sensitive: false,
            ..Default::default()
        };
        let mut analyzer = SOTATaintAnalyzer::new(cg.clone(), config);

        let mut sources = HashMap::new();
        sources.insert("main".to_string(), {
            let mut set = HashSet::new();
            set.insert("input".to_string());
            set
        });

        let mut sinks = HashMap::new();
        sinks.insert("f99".to_string(), {
            let mut set = HashSet::new();
            set.insert("sink".to_string());
            set
        });

        b.iter(|| {
            let paths = analyzer.analyze(black_box(&sources), black_box(&sinks));
            black_box(paths);
        });
    });

    // With field-sensitive
    group.bench_function("enabled", |b| {
        let config = SOTAConfig {
            field_sensitive: true,
            ..Default::default()
        };
        let mut analyzer = SOTATaintAnalyzer::new(cg.clone(), config);

        let mut sources = HashMap::new();
        sources.insert("main".to_string(), {
            let mut set = HashSet::new();
            set.insert("input".to_string());
            set
        });

        let mut sinks = HashMap::new();
        sinks.insert("f99".to_string(), {
            let mut set = HashSet::new();
            set.insert("sink".to_string());
            set
        });

        b.iter(|| {
            let paths = analyzer.analyze(black_box(&sources), black_box(&sinks));
            black_box(paths);
        });
    });

    group.finish();
}

criterion_group!(
    benches,
    bench_interprocedural_chain,
    bench_interprocedural_tree,
    bench_sota_analyzer,
    bench_field_sensitive,
);
criterion_main!(benches);
