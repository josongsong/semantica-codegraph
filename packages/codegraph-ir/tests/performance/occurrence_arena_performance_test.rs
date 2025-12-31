//! Performance Test: OccurrenceArena vs Standard Allocation
//!
//! Run with: cargo test --release --test occurrence_arena_performance_test -- --nocapture

use codegraph_ir::shared::models::{
    Node, NodeKind, Edge, Span,
    OccurrenceGenerator, OccurrenceArena,
};
use std::time::Instant;

fn generate_test_nodes(count: usize) -> Vec<Node> {
    (0..count)
        .map(|i| {
            let kind = match i % 4 {
                0 => NodeKind::Function,
                1 => NodeKind::Class,
                2 => NodeKind::Variable,
                _ => NodeKind::Method,
            };

            Node::builder()
                .id(format!("node:{}", i))
                .kind(kind)
                .fqn(format!("module.item{}", i))
                .file_path(format!("file{}.py", i / 100)) // 100 nodes per file
                .span(Span::new((i as u32) * 10, 0, (i as u32) * 10 + 5, 0))
                .with_name(format!("item{}", i))
                .build()
                .unwrap()
        })
        .collect()
}

fn generate_test_edges(nodes: &[Node], count: usize) -> Vec<Edge> {
    (0..count.min(nodes.len() - 1))
        .map(|i| {
            Edge::calls(&nodes[i].id, &nodes[i + 1].id)
        })
        .collect()
}

#[test]
fn test_performance_standard_vs_arena() {
    println!("\n=== Occurrence Generation Performance Test ===\n");

    for size in [100, 500, 1000, 5000] {
        let nodes = generate_test_nodes(size);
        let edges = generate_test_edges(&nodes, size / 2);

        // Standard generator
        let start = Instant::now();
        let mut generator = OccurrenceGenerator::new();
        let occurrences_standard = generator.generate(&nodes, &edges);
        let time_standard = start.elapsed();

        // Arena generator
        let start = Instant::now();
        let mut arena = OccurrenceArena::with_capacity(size * 5);
        let occurrences_arena = arena.generate(&nodes, &edges);
        let time_arena = start.elapsed();

        let speedup = time_standard.as_micros() as f64 / time_arena.as_micros() as f64;
        let improvement = (speedup - 1.0) * 100.0;

        println!("Size: {} nodes, {} edges", size, edges.len());
        println!("  Standard: {:?} ({} occurrences)", time_standard, occurrences_standard.len());
        println!("  Arena:    {:?} ({} occurrences)", time_arena, occurrences_arena.len());
        println!("  Speedup:  {:.2}x ({:.1}% improvement)", speedup, improvement);

        let stats = arena.stats();
        println!("  String deduplication: {} unique / {} total ({:.1}% savings)",
            stats.string_interner_stats.unique_strings,
            stats.string_interner_stats.total_strings,
            (1.0 - (stats.string_interner_stats.unique_strings as f64 / stats.string_interner_stats.total_strings as f64)) * 100.0
        );
        println!();

        assert_eq!(occurrences_standard.len(), occurrences_arena.len());
    }
}

#[test]
fn test_arena_reuse_performance() {
    println!("\n=== Arena Reuse Performance Test ===\n");

    let size = 1000;
    let nodes = generate_test_nodes(size);
    let edges = generate_test_edges(&nodes, size / 2);

    // First run (cold)
    let start = Instant::now();
    let mut arena = OccurrenceArena::with_capacity(size * 5);
    let _occurrences1 = arena.generate(&nodes, &edges);
    let time_cold = start.elapsed();

    // Second run (warm, reuse)
    let start = Instant::now();
    arena.reset();
    let _occurrences2 = arena.generate(&nodes, &edges);
    let time_warm = start.elapsed();

    println!("Arena Reuse (1000 nodes):");
    println!("  Cold start: {:?}", time_cold);
    println!("  Warm reuse: {:?}", time_warm);
    println!("  Speedup:    {:.2}x", time_cold.as_micros() as f64 / time_warm.as_micros() as f64);
    println!();
}

#[test]
fn test_memory_efficiency() {
    println!("\n=== Memory Efficiency Test ===\n");

    let size = 1000;
    let nodes = generate_test_nodes(size);
    let edges = generate_test_edges(&nodes, size / 2);

    let mut arena = OccurrenceArena::with_capacity(size * 5);
    let occurrences = arena.generate(&nodes, &edges);

    let stats = arena.stats();

    println!("Occurrences: {}", occurrences.len());
    println!("Total string allocations: {}", stats.string_interner_stats.total_strings);
    println!("Unique strings (interned): {}", stats.string_interner_stats.unique_strings);
    println!("Deduplication ratio: {:.2}x",
        stats.string_interner_stats.total_strings as f64 / stats.string_interner_stats.unique_strings as f64
    );

    // Verify actual deduplication works
    let file_paths: std::collections::HashSet<_> = occurrences.iter().map(|o| &o.file_path).collect();
    println!("Unique file_path values: {} (expected: ~10 for 1000 nodes / 100 per file)", file_paths.len());

    assert!(stats.string_interner_stats.unique_strings < stats.string_interner_stats.total_strings);
    assert!(file_paths.len() < 20); // Should be ~10 files
}
