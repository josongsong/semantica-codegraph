// SOTA Graph Builder Stress Tests
//
// Extreme cases that push the limits:
// - Memory pressure
// - Concurrent access
// - Pathological inputs
// - Performance regression detection

use codegraph_ir::features::graph_builder::infrastructure::GraphBuilder;
use codegraph_ir::shared::models::{Node, Edge, NodeKind, EdgeKind, Span};
use codegraph_ir::features::cross_file::IRDocument;
use std::collections::HashMap;

// ============================================================
// Test Helpers
// ============================================================

fn create_minimal_node(id: &str, kind: NodeKind) -> Node {
    Node {
        id: id.to_string(),
        kind,
        fqn: format!("test.{}", id),
        name: Some(id.to_string()),
        file_path: Some("test.py".to_string()),
        span: None,
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: None,
        attrs: HashMap::new(),
    }
}

fn create_minimal_edge(source: &str, target: &str, kind: EdgeKind) -> Edge {
    Edge {
        source_id: source.to_string(),
        target_id: target.to_string(),
        kind,
        span: None,
        attrs: HashMap::new(),
    }
}

// ============================================================
// 1. Extreme Scale Tests
// ============================================================

#[test]
#[ignore] // Slow test - run with `cargo test -- --ignored`
fn stress_100k_nodes() {
    let builder = GraphBuilder::new();

    println!("Generating 100K nodes...");
    let start_gen = std::time::Instant::now();

    let nodes: Vec<_> = (0..100_000)
        .map(|i| create_minimal_node(&format!("n{}", i), NodeKind::Function))
        .collect();

    println!("Generated in {:?}", start_gen.elapsed());

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges: vec![],
    };

    println!("Building graph...");
    let start_build = std::time::Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start_build.elapsed();

    assert!(result.is_ok(), "Should handle 100K nodes");
    let graph = result.unwrap();
    assert_eq!(graph.graph_nodes.len(), 100_000);

    println!("✅ 100K nodes processed in {:?}", elapsed);
    println!("   Throughput: {} nodes/ms", 100_000 / elapsed.as_millis().max(1));

    // Performance assertion: should be <500ms
    assert!(elapsed.as_millis() < 500, "100K nodes should process in <500ms");
}

#[test]
#[ignore]
fn stress_1_million_edges() {
    let builder = GraphBuilder::new();

    // Create 1K nodes
    let nodes: Vec<_> = (0..1000)
        .map(|i| create_minimal_node(&format!("n{}", i), NodeKind::Function))
        .collect();

    println!("Generating 1M edges...");
    let start_gen = std::time::Instant::now();

    // Each node calls 1000 others = 1M edges
    let mut edges = vec![];
    for i in 0..1000 {
        for j in 0..1000 {
            let target = (i + j) % 1000;
            edges.push(create_minimal_edge(&format!("n{}", i), &format!("n{}", target), EdgeKind::Calls));
        }
    }

    println!("Generated 1M edges in {:?}", start_gen.elapsed());

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    };

    println!("Building graph with 1M edges...");
    let start_build = std::time::Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start_build.elapsed();

    assert!(result.is_ok());
    let graph = result.unwrap();
    assert_eq!(graph.graph_edges.len(), 1_000_000);

    println!("✅ 1M edges processed in {:?}", elapsed);
    println!("   Throughput: {} edges/ms", 1_000_000 / elapsed.as_millis().max(1));

    assert!(elapsed.as_secs() < 5, "1M edges should process in <5s");
}

#[test]
#[ignore]
fn stress_memory_usage_string_interning() {
    let builder = GraphBuilder::new();

    // Create 10K nodes all with same strings (test deduplication)
    let same_name = "test_function_with_a_very_long_name_that_would_waste_memory_if_not_interned";
    let same_path = "very/long/path/that/should/be/deduplicated/across/all/nodes/test.py";

    let nodes: Vec<_> = (0..10_000)
        .map(|i| {
            let mut node = create_minimal_node(&format!("n{}", i), NodeKind::Function);
            node.name = Some(same_name.to_string());
            node.file_path = Some(same_path.to_string());
            node
        })
        .collect();

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges: vec![],
    };

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let stats = builder.cache_stats();
    println!("String interner size: {} unique strings", stats.string_interner_size);

    // With perfect interning, should have only a few unique strings
    // (node IDs will be unique, but names/paths should be shared)
    assert!(stats.string_interner_size < 10_100, "Should heavily deduplicate strings");
}

// ============================================================
// 2. Pathological Inputs
// ============================================================

#[test]
fn stress_all_nodes_connected_to_one() {
    // Star topology: 1 hub with 10K connections
    let builder = GraphBuilder::new();

    let mut nodes = vec![create_minimal_node("hub", NodeKind::Function)];
    let mut edges = vec![];

    for i in 0..10_000 {
        let spoke_id = format!("spoke_{}", i);
        nodes.push(create_minimal_node(&spoke_id, NodeKind::Function));
        edges.push(create_minimal_edge("hub", &spoke_id, EdgeKind::Calls));
    }

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    };

    let start = std::time::Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    let graph = result.unwrap();

    // Check hub has 10K outgoing edges
    let hub_outgoing = graph.indexes.outgoing.get(&codegraph_ir::features::graph_builder::domain::intern("hub"));
    assert!(hub_outgoing.is_some());
    assert_eq!(hub_outgoing.unwrap().len(), 10_000);

    println!("Star topology (1→10K) processed in {:?}", elapsed);
}

#[test]
fn stress_long_chain_dependency() {
    // Linear chain: A→B→C→D...→Z (10K deep)
    let builder = GraphBuilder::new();

    let mut nodes = vec![];
    let mut edges = vec![];

    for i in 0..10_000 {
        nodes.push(create_minimal_node(&format!("n{}", i), NodeKind::Function));
        if i > 0 {
            edges.push(create_minimal_edge(&format!("n{}", i - 1), &format!("n{}", i), EdgeKind::Calls));
        }
    }

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    };

    let start = std::time::Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    println!("10K deep chain processed in {:?}", elapsed);
}

#[test]
fn stress_complete_graph() {
    // Every node connected to every other node (N² edges)
    // Use small N to avoid explosion
    let n = 100;
    let builder = GraphBuilder::new();

    let nodes: Vec<_> = (0..n)
        .map(|i| create_minimal_node(&format!("n{}", i), NodeKind::Function))
        .collect();

    let mut edges = vec![];
    for i in 0..n {
        for j in 0..n {
            if i != j {
                edges.push(create_minimal_edge(&format!("n{}", i), &format!("n{}", j), EdgeKind::Calls));
            }
        }
    }

    let expected_edges = n * (n - 1);
    println!("Complete graph: {} nodes, {} edges", n, expected_edges);

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    };

    let start = std::time::Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    let graph = result.unwrap();
    assert_eq!(graph.graph_edges.len(), expected_edges);

    println!("Complete graph processed in {:?}", elapsed);
}

#[test]
fn stress_self_loops() {
    // Recursive functions (self-calling)
    let builder = GraphBuilder::new();

    let mut nodes = vec![];
    let mut edges = vec![];

    for i in 0..1000 {
        let id = format!("recursive_{}", i);
        nodes.push(create_minimal_node(&id, NodeKind::Function));
        edges.push(create_minimal_edge(&id, &id, EdgeKind::Calls)); // Self-loop
    }

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    };

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle self-loops");

    let graph = result.unwrap();
    assert_eq!(graph.graph_edges.len(), 1000);
}

// ============================================================
// 3. Concurrent Access Tests
// ============================================================

#[test]
fn stress_concurrent_builds_same_builder() {
    use std::sync::Arc;
    use std::thread;

    let builder = Arc::new(GraphBuilder::new());
    let mut handles = vec![];

    // Spawn 10 threads, each building a graph
    for thread_id in 0..10 {
        let builder_clone = Arc::clone(&builder);

        let handle = thread::spawn(move || {
            let nodes: Vec<_> = (0..100)
                .map(|i| create_minimal_node(&format!("t{}_n{}", thread_id, i), NodeKind::Function))
                .collect();

            let ir_doc = IRDocument {
                file_path: format!("thread_{}.py", thread_id),
                nodes,
                edges: vec![],
            };

            builder_clone.build_full(&ir_doc, None)
        });

        handles.push(handle);
    }

    // Wait for all threads
    for (i, handle) in handles.into_iter().enumerate() {
        let result = handle.join().expect(&format!("Thread {} panicked", i));
        assert!(result.is_ok(), "Thread {} build should succeed", i);
    }

    println!("✅ Concurrent builds from 10 threads succeeded");
}

#[test]
fn stress_cache_thrashing() {
    // Repeatedly build and clear cache to test stability
    let builder = GraphBuilder::new();

    for iteration in 0..100 {
        let mut node = create_minimal_node(&format!("node_{}", iteration), NodeKind::Function);
        node.file_path = Some("src/module/test.py".to_string());

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![node],
            edges: vec![],
        };

        let result = builder.build_full(&ir_doc, None);
        assert!(result.is_ok());

        if iteration % 10 == 0 {
            builder.clear_cache();
        }
    }

    println!("✅ 100 builds with periodic cache clearing succeeded");
}

// ============================================================
// 4. Edge Case Combinations
// ============================================================

#[test]
fn stress_all_edge_types_simultaneously() {
    let builder = GraphBuilder::new();

    let nodes = vec![
        create_minimal_node("A", NodeKind::Class),
        create_minimal_node("B", NodeKind::Class),
        create_minimal_node("C", NodeKind::Function),
        create_minimal_node("D", NodeKind::Variable),
    ];

    let edges = vec![
        create_minimal_edge("A", "B", EdgeKind::Inherits),
        create_minimal_edge("A", "B", EdgeKind::Calls),
        create_minimal_edge("A", "C", EdgeKind::Contains),
        create_minimal_edge("C", "D", EdgeKind::Reads),
        create_minimal_edge("C", "D", EdgeKind::Writes),
        create_minimal_edge("A", "B", EdgeKind::References),
        create_minimal_edge("A", "B", EdgeKind::Imports),
    ];

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    };

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let graph = result.unwrap();
    assert_eq!(graph.graph_edges.len(), 7, "Should preserve all edge types");

    // Check each edge kind has correct index
    let edge_kinds = [
        EdgeKind::Inherits,
        EdgeKind::Calls,
        EdgeKind::Contains,
        EdgeKind::Reads,
        EdgeKind::Writes,
        EdgeKind::References,
        EdgeKind::Imports,
    ];

    for kind in edge_kinds {
        let edges_of_kind = graph.get_edges_by_kind(kind);
        assert!(!edges_of_kind.is_empty(), "{:?} edges should be indexed", kind);
    }
}

#[test]
fn stress_mixed_unicode_and_ascii() {
    let builder = GraphBuilder::new();

    let nodes = vec![
        create_minimal_node("函数_1", NodeKind::Function),
        create_minimal_node("función_2", NodeKind::Function),
        create_minimal_node("функция_3", NodeKind::Function),
        create_minimal_node("関数_4", NodeKind::Function),
        create_minimal_node("regular_5", NodeKind::Function),
        create_minimal_node("🚀_emoji_6", NodeKind::Function),
    ];

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges: vec![],
    };

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle mixed Unicode/ASCII");

    let graph = result.unwrap();
    assert_eq!(graph.graph_nodes.len(), 6);
}

// ============================================================
// 5. Regression & Stability Tests
// ============================================================

#[test]
fn stress_repeated_builds_same_input() {
    let builder = GraphBuilder::new();

    let nodes = vec![
        create_minimal_node("f1", NodeKind::Function),
        create_minimal_node("f2", NodeKind::Function),
    ];
    let edges = vec![
        create_minimal_edge("f1", "f2", EdgeKind::Calls),
    ];

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: nodes.clone(),
        edges: edges.clone(),
    };

    // Build same graph 1000 times
    for i in 0..1000 {
        let result = builder.build_full(&ir_doc, None);
        assert!(result.is_ok(), "Build {} should succeed", i);

        let graph = result.unwrap();
        assert_eq!(graph.graph_nodes.len(), 2);
        assert_eq!(graph.graph_edges.len(), 1);
    }

    println!("✅ 1000 repeated builds succeeded");
}

#[test]
fn stress_memory_leak_detection() {
    // Build many graphs and ensure memory doesn't grow unbounded
    let builder = GraphBuilder::new();

    let initial_stats = builder.cache_stats();

    for i in 0..1000 {
        let nodes = vec![
            create_minimal_node(&format!("unique_{}", i), NodeKind::Function),
        ];

        let ir_doc = IRDocument {
            file_path: format!("file_{}.py", i),
            nodes,
            edges: vec![],
        };

        builder.build_full(&ir_doc, None).unwrap();

        // Clear cache periodically to prevent unbounded growth
        if i % 100 == 0 {
            builder.clear_cache();
        }
    }

    let final_stats = builder.cache_stats();

    // Cache should not grow to 1000 (due to periodic clearing)
    assert!(final_stats.module_cache_size < 500, "Cache should be bounded");

    println!("Initial cache: {}, Final cache: {}", initial_stats.module_cache_size, final_stats.module_cache_size);
}

// ============================================================
// 6. Performance Benchmarks
// ============================================================

#[test]
#[ignore]
fn bench_baseline_python_parity() {
    // Target: 10-20x faster than Python
    // Python baseline: ~500ms for 10K nodes
    // Rust target: <50ms for 10K nodes

    let builder = GraphBuilder::new();

    let nodes: Vec<_> = (0..10_000)
        .map(|i| create_minimal_node(&format!("n{}", i), NodeKind::Function))
        .collect();

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges: vec![],
    };

    let iterations = 10;
    let mut times = vec![];

    for _ in 0..iterations {
        let start = std::time::Instant::now();
        builder.build_full(&ir_doc, None).unwrap();
        times.push(start.elapsed());
    }

    let avg_time = times.iter().sum::<std::time::Duration>() / iterations as u32;
    let min_time = times.iter().min().unwrap();
    let max_time = times.iter().max().unwrap();

    println!("📊 Performance Benchmark (10K nodes):");
    println!("   Min:  {:?}", min_time);
    println!("   Avg:  {:?}", avg_time);
    println!("   Max:  {:?}", max_time);
    println!("   Target: <50ms (10-20x faster than Python ~500ms)");

    assert!(avg_time.as_millis() < 50, "Should average <50ms for 10K nodes");
}

#[test]
#[ignore]
fn bench_index_build_performance() {
    // Separate benchmark for index building
    let builder = GraphBuilder::new();

    let mut nodes = vec![];
    let mut edges = vec![];

    for i in 0..5000 {
        nodes.push(create_minimal_node(&format!("n{}", i), NodeKind::Function));
    }

    // Dense graph: 50K edges
    for i in 0..5000 {
        for j in 0..10 {
            let target = (i + j + 1) % 5000;
            edges.push(create_minimal_edge(&format!("n{}", i), &format!("n{}", target), EdgeKind::Calls));
        }
    }

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    };

    let start = std::time::Instant::now();
    let graph = builder.build_full(&ir_doc, None).unwrap();
    let elapsed = start.elapsed();

    println!("📊 Index Build Benchmark:");
    println!("   Nodes: {}", graph.graph_nodes.len());
    println!("   Edges: {}", graph.graph_edges.len());
    println!("   Time:  {:?}", elapsed);
    println!("   Rate:  {} edges/ms", 50_000 / elapsed.as_millis().max(1));

    assert!(elapsed.as_millis() < 300, "Should build indexes in <300ms");
}
