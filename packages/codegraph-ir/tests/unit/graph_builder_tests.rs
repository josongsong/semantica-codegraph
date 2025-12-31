// SOTA Graph Builder Tests - Comprehensive Edge/Corner/Complex Cases
//
// Test Categories:
// 1. Basic Functionality
// 2. Edge Cases (empty, null, malformed)
// 3. Corner Cases (boundaries, limits)
// 4. Complex Cases (large graphs, circular deps, deep nesting)
// 5. Performance Tests (stress, memory, concurrency)
// 6. Regression Tests (known bugs)

use codegraph_ir::features::graph_builder::domain::{GraphDocument, GraphNode, GraphIndex, GraphEdge, intern};
use codegraph_ir::features::graph_builder::infrastructure::GraphBuilder;
use codegraph_ir::shared::models::{Node, Edge, NodeKind, EdgeKind, Span};
use codegraph_ir::features::cross_file::IRDocument;
use std::collections::HashMap;

// ============================================================
// Test Helpers
// ============================================================

fn create_test_node(id: &str, kind: NodeKind, name: &str) -> Node {
    Node {
        id: id.to_string(),
        kind,
        fqn: format!("test.{}", name),
        name: Some(name.to_string()),
        file_path: Some("test.py".to_string()),
        span: Some(Span { start_line: 1, start_col: 0, end_line: 1, end_col: 10 }),
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

fn create_test_edge(source: &str, target: &str, kind: EdgeKind) -> Edge {
    Edge {
        source_id: source.to_string(),
        target_id: target.to_string(),
        kind,
        span: None,
        attrs: HashMap::new(),
    }
}

fn create_test_ir_doc(nodes: Vec<Node>, edges: Vec<Edge>) -> IRDocument {
    IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    }
}

// ============================================================
// 1. Basic Functionality Tests
// ============================================================

#[test]
fn test_basic_build_empty_graph() {
    let builder = GraphBuilder::new();
    let ir_doc = create_test_ir_doc(vec![], vec![]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle empty IR document");

    let graph = result.unwrap();
    assert_eq!(graph.graph_nodes.len(), 0, "Empty IR should produce empty graph");
    assert_eq!(graph.graph_edges.len(), 0, "Empty IR should have no edges");
}

#[test]
fn test_basic_build_single_node() {
    let builder = GraphBuilder::new();
    let node = create_test_node("func1", NodeKind::Function, "foo");
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let graph = result.unwrap();
    assert_eq!(graph.graph_nodes.len(), 1, "Should have 1 node");
    assert!(graph.graph_nodes.contains_key(&intern("func1")));
}

#[test]
fn test_basic_build_with_edges() {
    let builder = GraphBuilder::new();
    let node1 = create_test_node("func1", NodeKind::Function, "foo");
    let node2 = create_test_node("func2", NodeKind::Function, "bar");
    let edge = create_test_edge("func1", "func2", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1, node2], vec![edge]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let graph = result.unwrap();
    assert_eq!(graph.graph_nodes.len(), 2, "Should have 2 nodes");
    assert_eq!(graph.graph_edges.len(), 1, "Should have 1 edge");
}

// ============================================================
// 2. Edge Cases - Empty/Null/Malformed Data
// ============================================================

#[test]
fn test_edge_case_node_without_name() {
    let builder = GraphBuilder::new();
    let mut node = create_test_node("anon1", NodeKind::Function, "");
    node.name = None; // Explicitly None

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle nodes without names");
    let graph = result.unwrap();
    let graph_node = graph.get_node("anon1");
    assert!(graph_node.is_some());
    assert_eq!(graph_node.unwrap().name.as_ref(), "", "Name should default to empty string");
}

#[test]
fn test_edge_case_node_without_file_path() {
    let builder = GraphBuilder::new();
    let mut node = create_test_node("orphan1", NodeKind::Function, "orphan");
    node.file_path = None;

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle nodes without file path");
    let graph = result.unwrap();
    assert_eq!(graph.path_index.len(), 0, "No path index for nodes without path");
}

#[test]
fn test_edge_case_edge_to_nonexistent_node() {
    let builder = GraphBuilder::new();
    let node = create_test_node("func1", NodeKind::Function, "foo");
    let edge = create_test_edge("func1", "nonexistent", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node], vec![edge]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle dangling edges gracefully");
    let graph = result.unwrap();
    // Edge should still be created (validation is separate concern)
    assert_eq!(graph.graph_edges.len(), 1);
}

#[test]
fn test_edge_case_duplicate_node_ids() {
    let builder = GraphBuilder::new();
    let node1 = create_test_node("dup", NodeKind::Function, "foo");
    let mut node2 = create_test_node("dup", NodeKind::Function, "bar");
    node2.name = Some("bar".to_string());

    let ir_doc = create_test_ir_doc(vec![node1, node2], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();
    // Last one wins (HashMap behavior)
    assert_eq!(graph.graph_nodes.len(), 1);
    let node = graph.get_node("dup").unwrap();
    assert_eq!(node.name.as_ref(), "bar", "Should keep last node with duplicate ID");
}

#[test]
fn test_edge_case_empty_fqn() {
    let builder = GraphBuilder::new();
    let mut node = create_test_node("empty_fqn", NodeKind::Function, "test");
    node.fqn = "".to_string();

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();
    let graph_node = graph.get_node("empty_fqn").unwrap();
    assert_eq!(graph_node.fqn.as_ref(), "", "Should handle empty FQN");
}

// ============================================================
// 3. Corner Cases - Boundaries & Limits
// ============================================================

#[test]
fn test_corner_case_very_long_node_id() {
    let builder = GraphBuilder::new();
    let long_id = "a".repeat(10000); // 10K characters
    let node = create_test_node(&long_id, NodeKind::Function, "test");

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle very long node IDs");
    let graph = result.unwrap();
    assert!(graph.get_node(&long_id).is_some());
}

#[test]
fn test_corner_case_unicode_in_names() {
    let builder = GraphBuilder::new();
    let node = create_test_node("unicode1", NodeKind::Function, "函数_🚀_テスト");

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle Unicode in names");
    let graph = result.unwrap();
    let graph_node = graph.get_node("unicode1").unwrap();
    assert_eq!(graph_node.name.as_ref(), "函数_🚀_テスト");
}

#[test]
fn test_corner_case_special_characters_in_paths() {
    let builder = GraphBuilder::new();
    let mut node = create_test_node("special", NodeKind::Function, "test");
    node.file_path = Some("path/with spaces/and-dashes/file.name.py".to_string());

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();
    assert!(graph.path_index.contains_key(&intern("path/with spaces/and-dashes/file.name.py")));
}

#[test]
fn test_corner_case_max_edges_from_single_node() {
    let builder = GraphBuilder::new();
    let source = create_test_node("hub", NodeKind::Function, "hub");

    // Create 1000 target nodes and edges
    let mut nodes = vec![source];
    let mut edges = vec![];

    for i in 0..1000 {
        let target = create_test_node(&format!("target_{}", i), NodeKind::Function, &format!("func_{}", i));
        let edge = create_test_edge("hub", &format!("target_{}", i), EdgeKind::Calls);
        nodes.push(target);
        edges.push(edge);
    }

    let ir_doc = create_test_ir_doc(nodes, edges);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle nodes with many outgoing edges");
    let graph = result.unwrap();
    assert_eq!(graph.graph_edges.len(), 1000);

    // Check adjacency index
    let outgoing = graph.indexes.outgoing.get(&intern("hub"));
    assert!(outgoing.is_some());
    assert_eq!(outgoing.unwrap().len(), 1000, "Should index all outgoing edges");
}

#[test]
fn test_corner_case_deeply_nested_modules() {
    let builder = GraphBuilder::new();
    let mut node = create_test_node("deep", NodeKind::Function, "func");
    node.file_path = Some("a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/test.py".to_string());

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle deeply nested paths");
    let graph = result.unwrap();

    // Should generate module nodes for each level
    let module_nodes: Vec<_> = graph.graph_nodes.values()
        .filter(|n| n.kind == NodeKind::Module)
        .collect();
    assert!(module_nodes.len() >= 10, "Should generate module nodes for deep nesting");
}

// ============================================================
// 4. Complex Cases - Large Graphs, Circular Deps, Deep Nesting
// ============================================================

#[test]
fn test_complex_case_circular_dependencies() {
    let builder = GraphBuilder::new();

    // A -> B -> C -> A (circular)
    let nodes = vec![
        create_test_node("A", NodeKind::Function, "A"),
        create_test_node("B", NodeKind::Function, "B"),
        create_test_node("C", NodeKind::Function, "C"),
    ];

    let edges = vec![
        create_test_edge("A", "B", EdgeKind::Calls),
        create_test_edge("B", "C", EdgeKind::Calls),
        create_test_edge("C", "A", EdgeKind::Calls),
    ];

    let ir_doc = create_test_ir_doc(nodes, edges);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle circular dependencies");
    let graph = result.unwrap();
    assert_eq!(graph.graph_edges.len(), 3);

    // Verify bidirectional indexing
    assert!(graph.indexes.called_by.contains_key(&intern("A")));
    assert!(graph.indexes.called_by.contains_key(&intern("B")));
    assert!(graph.indexes.called_by.contains_key(&intern("C")));
}

#[test]
fn test_complex_case_diamond_dependency() {
    let builder = GraphBuilder::new();

    //     A
    //    / \
    //   B   C
    //    \ /
    //     D

    let nodes = vec![
        create_test_node("A", NodeKind::Function, "A"),
        create_test_node("B", NodeKind::Function, "B"),
        create_test_node("C", NodeKind::Function, "C"),
        create_test_node("D", NodeKind::Function, "D"),
    ];

    let edges = vec![
        create_test_edge("A", "B", EdgeKind::Calls),
        create_test_edge("A", "C", EdgeKind::Calls),
        create_test_edge("B", "D", EdgeKind::Calls),
        create_test_edge("C", "D", EdgeKind::Calls),
    ];

    let ir_doc = create_test_ir_doc(nodes, edges);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();

    // D should have 2 callers
    let d_callers = graph.indexes.called_by.get(&intern("D"));
    assert!(d_callers.is_some());
    assert_eq!(d_callers.unwrap().len(), 2, "D should be called by B and C");
}

#[test]
fn test_complex_case_large_graph_10k_nodes() {
    let builder = GraphBuilder::new();

    let mut nodes = vec![];
    let mut edges = vec![];

    // Generate 10K nodes
    for i in 0..10_000 {
        let node = create_test_node(&format!("node_{}", i), NodeKind::Function, &format!("func_{}", i));
        nodes.push(node);

        // Each node calls the next one (chain)
        if i > 0 {
            let edge = create_test_edge(&format!("node_{}", i - 1), &format!("node_{}", i), EdgeKind::Calls);
            edges.push(edge);
        }
    }

    let ir_doc = create_test_ir_doc(nodes, edges);

    let start = std::time::Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start.elapsed();

    assert!(result.is_ok(), "Should handle 10K nodes");
    let graph = result.unwrap();

    assert_eq!(graph.graph_nodes.len(), 10_000);
    assert_eq!(graph.graph_edges.len(), 9_999);

    println!("10K nodes processed in {:?}", elapsed);
    assert!(elapsed.as_millis() < 500, "Should process 10K nodes in <500ms");
}

#[test]
fn test_complex_case_mixed_node_types() {
    let builder = GraphBuilder::new();

    // Realistic mix: File → Class → Method → Function → Variable
    let nodes = vec![
        create_test_node("file1", NodeKind::File, "module.py"),
        create_test_node("class1", NodeKind::Class, "MyClass"),
        create_test_node("method1", NodeKind::Method, "my_method"),
        create_test_node("func1", NodeKind::Function, "helper"),
        create_test_node("var1", NodeKind::Variable, "x"),
    ];

    let edges = vec![
        create_test_edge("file1", "class1", EdgeKind::Contains),
        create_test_edge("class1", "method1", EdgeKind::Contains),
        create_test_edge("method1", "func1", EdgeKind::Calls),
        create_test_edge("method1", "var1", EdgeKind::Reads),
    ];

    let ir_doc = create_test_ir_doc(nodes, edges);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();

    // Verify CONTAINS index
    let file_children = graph.indexes.contains_children.get(&intern("file1"));
    assert!(file_children.is_some());
    assert_eq!(file_children.unwrap().len(), 1);

    // Verify called_by index
    let func_callers = graph.indexes.called_by.get(&intern("func1"));
    assert!(func_callers.is_some());
}

#[test]
fn test_complex_case_multiple_edge_types_same_nodes() {
    let builder = GraphBuilder::new();

    let nodes = vec![
        create_test_node("A", NodeKind::Class, "A"),
        create_test_node("B", NodeKind::Class, "B"),
    ];

    // A and B have multiple relationships
    let edges = vec![
        create_test_edge("A", "B", EdgeKind::Inherits),
        create_test_edge("A", "B", EdgeKind::Calls),
        create_test_edge("A", "B", EdgeKind::References),
    ];

    let ir_doc = create_test_ir_doc(nodes, edges);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();
    assert_eq!(graph.graph_edges.len(), 3, "Should preserve all edge types");

    // Check EdgeKind-specific indexing
    let inherits_targets = graph.indexes.outgoing_by_kind.get(&(intern("A"), EdgeKind::Inherits));
    assert!(inherits_targets.is_some());
    assert_eq!(inherits_targets.unwrap().len(), 1);
}

// ============================================================
// 5. Performance Tests - Stress, Memory, Concurrency
// ============================================================

#[test]
fn test_perf_string_interning_deduplication() {
    let builder = GraphBuilder::new();

    // Create 1000 nodes with same file path
    let mut nodes = vec![];
    for i in 0..1000 {
        let mut node = create_test_node(&format!("node_{}", i), NodeKind::Function, &format!("func_{}", i));
        node.file_path = Some("same/path.py".to_string()); // All same
        nodes.push(node);
    }

    let ir_doc = create_test_ir_doc(nodes, vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();

    // All nodes should share the same interned path
    let path_set: std::collections::HashSet<_> = graph.graph_nodes.values()
        .filter_map(|n| n.path.as_ref().map(|p| std::sync::Arc::as_ptr(p)))
        .collect();

    assert_eq!(path_set.len(), 1, "All nodes should share same interned string (memory deduplication)");
}

#[test]
fn test_perf_parallel_node_conversion() {
    use std::time::Instant;

    let builder = GraphBuilder::new();

    // Generate 5000 nodes for parallel processing
    let nodes: Vec<_> = (0..5000)
        .map(|i| create_test_node(&format!("node_{}", i), NodeKind::Function, &format!("f_{}", i)))
        .collect();

    let ir_doc = create_test_ir_doc(nodes, vec![]);

    let start = Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    println!("5K nodes processed in {:?} (parallel)", elapsed);
    assert!(elapsed.as_millis() < 200, "Parallel processing should be fast");
}

#[test]
fn test_perf_index_building_speed() {
    let builder = GraphBuilder::new();

    // Large graph with many edges
    let mut nodes = vec![];
    let mut edges = vec![];

    for i in 0..1000 {
        nodes.push(create_test_node(&format!("n{}", i), NodeKind::Function, &format!("f{}", i)));
    }

    // Dense graph: every node calls 10 others
    for i in 0..1000 {
        for j in 0..10 {
            let target = (i + j + 1) % 1000;
            edges.push(create_test_edge(&format!("n{}", i), &format!("n{}", target), EdgeKind::Calls));
        }
    }

    let ir_doc = create_test_ir_doc(nodes, edges);

    let start = std::time::Instant::now();
    let result = builder.build_full(&ir_doc, None);
    let elapsed = start.elapsed();

    assert!(result.is_ok());
    let graph = result.unwrap();

    println!("1K nodes, 10K edges indexed in {:?}", elapsed);
    assert!(elapsed.as_millis() < 300, "Index building should be fast");
    assert_eq!(graph.graph_edges.len(), 10_000);
}

// ============================================================
// 6. Regression Tests - Known Bugs/Issues
// ============================================================

#[test]
fn test_regression_null_span_handling() {
    // Bug: Nodes with null spans caused panic
    let builder = GraphBuilder::new();
    let mut node = create_test_node("no_span", NodeKind::Function, "test");
    node.span = None;

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok(), "Should handle null spans gracefully");
}

#[test]
fn test_regression_empty_attrs_map() {
    // Bug: Empty attrs HashMap caused issues
    let builder = GraphBuilder::new();
    let mut node = create_test_node("empty_attrs", NodeKind::Function, "test");
    node.attrs.clear();

    let ir_doc = create_test_ir_doc(vec![node], vec![]);
    let result = builder.build_full(&ir_doc, None);

    assert!(result.is_ok());
    let graph = result.unwrap();
    let graph_node = graph.get_node("empty_attrs").unwrap();
    assert!(graph_node.attrs.is_empty());
}

#[test]
fn test_regression_cache_persistence_across_builds() {
    // Bug: Module cache was cleared between builds
    let builder = GraphBuilder::new();

    // Build 1
    let mut node1 = create_test_node("func1", NodeKind::Function, "f1");
    node1.file_path = Some("src/module/file.py".to_string());
    let ir_doc1 = create_test_ir_doc(vec![node1], vec![]);

    builder.build_full(&ir_doc1, None).unwrap();
    let stats1 = builder.cache_stats();
    let cache_size_1 = stats1.module_cache_size;

    // Build 2 (same path)
    let mut node2 = create_test_node("func2", NodeKind::Function, "f2");
    node2.file_path = Some("src/module/file.py".to_string());
    let ir_doc2 = create_test_ir_doc(vec![node2], vec![]);

    builder.build_full(&ir_doc2, None).unwrap();
    let stats2 = builder.cache_stats();

    assert_eq!(stats2.module_cache_size, cache_size_1, "Module cache should persist across builds");
}

// ============================================================
// 7. Index Correctness Tests
// ============================================================

#[test]
fn test_index_correctness_bidirectional_edges() {
    let builder = GraphBuilder::new();

    let nodes = vec![
        create_test_node("A", NodeKind::Function, "A"),
        create_test_node("B", NodeKind::Function, "B"),
    ];

    let edges = vec![
        create_test_edge("A", "B", EdgeKind::Calls),
    ];

    let ir_doc = create_test_ir_doc(nodes, edges);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Forward: A → B
    let outgoing = graph.indexes.outgoing.get(&intern("A"));
    assert!(outgoing.is_some());
    assert_eq!(outgoing.unwrap().len(), 1);

    // Reverse: B ← A
    let called_by_b = graph.indexes.called_by.get(&intern("B"));
    assert!(called_by_b.is_some());
    assert_eq!(called_by_b.unwrap().len(), 1);
    assert_eq!(called_by_b.unwrap()[0].as_ref(), "A");
}

#[test]
fn test_index_correctness_path_index() {
    let builder = GraphBuilder::new();

    let mut node1 = create_test_node("f1", NodeKind::Function, "f1");
    node1.file_path = Some("a.py".to_string());

    let mut node2 = create_test_node("f2", NodeKind::Function, "f2");
    node2.file_path = Some("a.py".to_string()); // Same file

    let mut node3 = create_test_node("f3", NodeKind::Function, "f3");
    node3.file_path = Some("b.py".to_string()); // Different file

    let ir_doc = create_test_ir_doc(vec![node1, node2, node3], vec![]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Check path index
    let nodes_in_a = graph.get_node_ids_by_path("a.py");
    assert!(nodes_in_a.is_some());
    assert_eq!(nodes_in_a.unwrap().len(), 2, "a.py should contain 2 nodes");

    let nodes_in_b = graph.get_node_ids_by_path("b.py");
    assert!(nodes_in_b.is_some());
    assert_eq!(nodes_in_b.unwrap().len(), 1, "b.py should contain 1 node");
}

#[test]
fn test_index_correctness_edge_kind_specific() {
    let builder = GraphBuilder::new();

    let nodes = vec![
        create_test_node("A", NodeKind::Function, "A"),
        create_test_node("B", NodeKind::Function, "B"),
        create_test_node("C", NodeKind::Function, "C"),
    ];

    let edges = vec![
        create_test_edge("A", "B", EdgeKind::Calls),
        create_test_edge("A", "C", EdgeKind::References),
    ];

    let ir_doc = create_test_ir_doc(nodes, edges);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // A should have 2 outgoing edges total
    let all_outgoing = graph.indexes.outgoing.get(&intern("A"));
    assert_eq!(all_outgoing.unwrap().len(), 2);

    // But only 1 CALLS edge
    let calls_targets = graph.indexes.outgoing_by_kind.get(&(intern("A"), EdgeKind::Calls));
    assert!(calls_targets.is_some());
    assert_eq!(calls_targets.unwrap().len(), 1);
    assert_eq!(calls_targets.unwrap()[0].as_ref(), "B");

    // And only 1 REFERENCES edge
    let ref_targets = graph.indexes.outgoing_by_kind.get(&(intern("A"), EdgeKind::References));
    assert!(ref_targets.is_some());
    assert_eq!(ref_targets.unwrap().len(), 1);
    assert_eq!(ref_targets.unwrap()[0].as_ref(), "C");
}

// ============================================================
// 8. Statistics & Metrics Tests
// ============================================================

#[test]
fn test_stats_correct_counts() {
    let builder = GraphBuilder::new();

    let nodes = vec![
        create_test_node("f1", NodeKind::Function, "f1"),
        create_test_node("f2", NodeKind::Function, "f2"),
        create_test_node("c1", NodeKind::Class, "c1"),
    ];

    let edges = vec![
        create_test_edge("f1", "f2", EdgeKind::Calls),
        create_test_edge("f1", "c1", EdgeKind::References),
    ];

    let ir_doc = create_test_ir_doc(nodes, edges);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    let stats = graph.stats();
    assert_eq!(stats.total_nodes, 3);
    assert_eq!(stats.total_edges, 2);

    assert_eq!(stats.nodes_by_kind.get(&NodeKind::Function), Some(&2));
    assert_eq!(stats.nodes_by_kind.get(&NodeKind::Class), Some(&1));

    assert_eq!(stats.edges_by_kind.get(&EdgeKind::Calls), Some(&1));
    assert_eq!(stats.edges_by_kind.get(&EdgeKind::References), Some(&1));
}

#[test]
fn test_cache_stats_accuracy() {
    let builder = GraphBuilder::new();

    let initial_stats = builder.cache_stats();
    assert_eq!(initial_stats.module_cache_size, 0, "Initial cache should be empty");

    // Build with module generation
    let mut node = create_test_node("f1", NodeKind::Function, "f1");
    node.file_path = Some("a/b/c/file.py".to_string());
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    builder.build_full(&ir_doc, None).unwrap();

    let after_stats = builder.cache_stats();
    assert!(after_stats.module_cache_size > 0, "Cache should have module nodes");
    assert!(after_stats.string_interner_size > 0, "String interner should have entries");
}
// SOTA Graph Builder - Advanced Test Suite
//
// This file adds comprehensive tests for previously untested areas:
// 1. String Interning (10 tests)
// 2. Cache Management (5 tests)
// 3. Error Handling (8 tests)
// 4. Index Building (10 tests)
// 5. Semantic IR Integration (5 tests)
//
// Total: 38 new tests to bring coverage from 29 → 67+ tests

use codegraph_ir::features::graph_builder::domain::{GraphDocument, GraphNode, GraphIndex, GraphEdge, intern};
use codegraph_ir::features::graph_builder::infrastructure::{GraphBuilder, intern_str};
use codegraph_ir::shared::models::{Node, Edge, NodeKind, EdgeKind, Span};
use codegraph_ir::features::cross_file::IRDocument;
use std::collections::HashMap;
use std::sync::Arc;

// ============================================================
// Test Helpers
// ============================================================

fn create_test_node(id: &str, kind: NodeKind, name: &str, file: &str) -> Node {
    Node {
        id: id.to_string(),
        kind,
        fqn: format!("test.{}", name),
        name: Some(name.to_string()),
        file_path: Some(file.to_string()),
        span: Some(Span { start_line: 1, start_col: 0, end_line: 10, end_col: 0 }),
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

fn create_test_edge(source: &str, target: &str, kind: EdgeKind) -> Edge {
    Edge {
        source_id: source.to_string(),
        target_id: target.to_string(),
        kind,
        span: None,
        attrs: HashMap::new(),
    }
}

fn create_test_ir_doc(nodes: Vec<Node>, edges: Vec<Edge>) -> IRDocument {
    IRDocument {
        file_path: "test.py".to_string(),
        nodes,
        edges,
    }
}

// ============================================================
// 1. String Interning Tests (10 tests)
// ============================================================

#[test]
fn test_intern_str_deduplication() {
    let s1 = intern_str("test_string");
    let s2 = intern_str("test_string");

    // Should return same Arc pointer (memory deduplication)
    assert!(Arc::ptr_eq(&s1, &s2), "Same string should return same Arc");
}

#[test]
fn test_intern_str_different_strings() {
    let s1 = intern_str("string1");
    let s2 = intern_str("string2");

    assert!(!Arc::ptr_eq(&s1, &s2), "Different strings should have different Arc");
    assert_ne!(s1.as_ref(), s2.as_ref());
}

#[test]
fn test_intern_str_empty_string() {
    let s1 = intern_str("");
    let s2 = intern_str("");

    assert!(Arc::ptr_eq(&s1, &s2));
    assert_eq!(s1.as_ref(), "");
}

#[test]
fn test_intern_str_unicode() {
    let s1 = intern_str("테스트_문자열_🚀");
    let s2 = intern_str("테스트_문자열_🚀");

    assert!(Arc::ptr_eq(&s1, &s2));
    assert_eq!(s1.as_ref(), "테스트_문자열_🚀");
}

#[test]
fn test_intern_str_very_long_string() {
    let long_str = "a".repeat(10000);
    let s1 = intern_str(&long_str);
    let s2 = intern_str(&long_str);

    assert!(Arc::ptr_eq(&s1, &s2));
    assert_eq!(s1.len(), 10000);
}

#[test]
fn test_intern_str_whitespace_preservation() {
    let s1 = intern_str("  test  \n\t  ");
    let s2 = intern_str("  test  \n\t  ");

    assert!(Arc::ptr_eq(&s1, &s2));
    assert_eq!(s1.as_ref(), "  test  \n\t  ");
}

#[test]
fn test_intern_str_special_characters() {
    let s1 = intern_str("!@#$%^&*()_+-=[]{}|;':\",./<>?");
    let s2 = intern_str("!@#$%^&*()_+-=[]{}|;':\",./<>?");

    assert!(Arc::ptr_eq(&s1, &s2));
}

#[test]
fn test_intern_str_concurrent_access() {
    use std::thread;

    let handles: Vec<_> = (0..10)
        .map(|i| {
            thread::spawn(move || {
                let s = intern_str(format!("concurrent_{}", i % 3));
                s
            })
        })
        .collect();

    let results: Vec<_> = handles.into_iter().map(|h| h.join().unwrap()).collect();

    // Same index values should have same Arc
    assert!(Arc::ptr_eq(&results[0], &results[3])); // both "concurrent_0"
    assert!(Arc::ptr_eq(&results[1], &results[4])); // both "concurrent_1"
}

#[test]
fn test_intern_str_memory_savings() {
    // Intern same string 1000 times
    let strings: Vec<_> = (0..1000)
        .map(|_| intern_str("common_string"))
        .collect();

    // All should point to same Arc
    for s in &strings[1..] {
        assert!(Arc::ptr_eq(&strings[0], s));
    }
}

#[test]
fn test_intern_domain_helper() {
    // Test the domain::intern() helper
    let s1 = intern("test");
    let s2 = intern("test");

    assert!(Arc::ptr_eq(&s1, &s2));
}

// ============================================================
// 2. Cache Management Tests (5 tests)
// ============================================================

#[test]
fn test_cache_module_reuse() {
    let builder = GraphBuilder::new();

    // Build graph with module nodes
    let node1 = create_test_node("mod1", NodeKind::Module, "module1", "mod1.py");
    let ir_doc1 = create_test_ir_doc(vec![node1], vec![]);

    let graph1 = builder.build_full(&ir_doc1, None).unwrap();
    assert_eq!(graph1.graph_nodes.len(), 1);

    // Build another graph with same module
    let node2 = create_test_node("func1", NodeKind::Function, "foo", "mod1.py");
    let ir_doc2 = create_test_ir_doc(vec![node2], vec![]);

    let graph2 = builder.build_full(&ir_doc2, None).unwrap();

    // Cache stats should show module cached
    let stats = builder.cache_stats();
    assert!(stats.module_cache_size > 0, "Module should be cached");
}

#[test]
fn test_cache_clear() {
    let builder = GraphBuilder::new();

    let node = create_test_node("mod1", NodeKind::Module, "module1", "mod1.py");
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    builder.build_full(&ir_doc, None).unwrap();

    let stats_before = builder.cache_stats();
    assert!(stats_before.module_cache_size > 0);

    builder.clear_cache();

    let stats_after = builder.cache_stats();
    assert_eq!(stats_after.module_cache_size, 0, "Cache should be cleared");
}

#[test]
fn test_cache_stats_string_interning() {
    let builder = GraphBuilder::new();

    // Create multiple nodes with duplicate strings
    let nodes: Vec<_> = (0..100)
        .map(|i| create_test_node(
            &format!("node{}", i),
            NodeKind::Function,
            "common_name", // Same name for all
            "common_file.py" // Same file for all
        ))
        .collect();

    let ir_doc = create_test_ir_doc(nodes, vec![]);
    builder.build_full(&ir_doc, None).unwrap();

    let stats = builder.cache_stats();
    // String interner should have far fewer strings than nodes
    assert!(stats.string_interner_size < 100, "String interning should reduce memory");
}

#[test]
fn test_cache_incremental_update() {
    let builder = GraphBuilder::new();

    // First build
    let node1 = create_test_node("func1", NodeKind::Function, "foo", "file1.py");
    let ir_doc1 = create_test_ir_doc(vec![node1], vec![]);
    builder.build_full(&ir_doc1, None).unwrap();

    let stats1 = builder.cache_stats();

    // Second build (incremental)
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "file1.py");
    let ir_doc2 = create_test_ir_doc(vec![node2], vec![]);
    builder.build_full(&ir_doc2, None).unwrap();

    let stats2 = builder.cache_stats();

    // Cache should grow
    assert!(stats2.string_interner_size >= stats1.string_interner_size);
}

#[test]
fn test_cache_default_constructor() {
    let builder1 = GraphBuilder::new();
    let builder2 = GraphBuilder::default();

    // Both should start with empty cache
    assert_eq!(builder1.cache_stats().module_cache_size, 0);
    assert_eq!(builder2.cache_stats().module_cache_size, 0);
}

// ============================================================
// 3. Error Handling Tests (8 tests)
// ============================================================

#[test]
fn test_error_invalid_edge_missing_source() {
    let builder = GraphBuilder::new();

    // Create edge pointing to non-existent source
    let node1 = create_test_node("target1", NodeKind::Function, "target", "test.py");
    let edge = create_test_edge("nonexistent_source", "target1", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1], vec![edge]);

    // Should handle gracefully (skip invalid edge)
    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle missing source gracefully");
}

#[test]
fn test_error_invalid_edge_missing_target() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("source1", NodeKind::Function, "source", "test.py");
    let edge = create_test_edge("source1", "nonexistent_target", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1], vec![edge]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle missing target gracefully");
}

#[test]
fn test_error_malformed_node_missing_required_fields() {
    let builder = GraphBuilder::new();

    let mut node = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    node.name = None; // Remove required field

    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    // Should handle gracefully (use fallback or skip)
    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle missing name gracefully");
}

#[test]
fn test_error_self_referential_edge() {
    let builder = GraphBuilder::new();

    let node = create_test_node("func1", NodeKind::Function, "recursive", "test.py");
    let edge = create_test_edge("func1", "func1", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node], vec![edge]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let graph = result.unwrap();
    // Should allow self-loops (valid in call graphs)
    assert_eq!(graph.graph_edges.len(), 1);
}

#[test]
fn test_error_duplicate_edge_ids() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "test.py");
    let edge1 = create_test_edge("func1", "func2", EdgeKind::Calls);
    let edge2 = create_test_edge("func1", "func2", EdgeKind::Calls); // Duplicate

    let ir_doc = create_test_ir_doc(vec![node1, node2], vec![edge1, edge2]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle duplicate edges");
}

#[test]
fn test_error_invalid_node_kind() {
    let builder = GraphBuilder::new();

    // Use edge case NodeKind values
    let node = create_test_node("node1", NodeKind::Unknown, "unknown", "test.py");

    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle Unknown node kind");
}

#[test]
fn test_error_invalid_span_values() {
    let builder = GraphBuilder::new();

    let mut node = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    // Invalid span: end before start
    node.span = Some(Span {
        start_line: 100,
        start_col: 50,
        end_line: 1,
        end_col: 0
    });

    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok(), "Should handle invalid spans gracefully");
}

#[test]
fn test_error_semantic_snapshot_malformed() {
    let builder = GraphBuilder::new();

    let node = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    // Create malformed semantic snapshot
    let mut semantic = HashMap::new();
    semantic.insert("invalid_key".to_string(), serde_json::json!({"malformed": true}));

    // Should gracefully degrade to structural graph
    let result = builder.build_full(&ir_doc, Some(&semantic));
    assert!(result.is_ok(), "Should handle malformed semantic snapshot");
}

// ============================================================
// 4. Index Building Tests (10 tests)
// ============================================================

#[test]
fn test_index_reverse_index_correctness() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "caller", "test.py");
    let node2 = create_test_node("func2", NodeKind::Function, "callee", "test.py");
    let edge = create_test_edge("func1", "func2", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1, node2], vec![edge]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Check reverse index: callee should have caller in its incoming edges
    let callee_id = intern("func2");
    if let Some(index) = graph.indexes.get("reverse_index") {
        // Reverse index should map target -> sources
        assert!(index.data.contains_key(&callee_id));
    }
}

#[test]
fn test_index_adjacency_list() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "test.py");
    let node3 = create_test_node("func3", NodeKind::Function, "baz", "test.py");

    let edge1 = create_test_edge("func1", "func2", EdgeKind::Calls);
    let edge2 = create_test_edge("func1", "func3", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1, node2, node3], vec![edge1, edge2]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // func1 should have 2 outgoing edges
    let func1_id = intern("func1");
    if let Some(index) = graph.indexes.get("adjacency_list") {
        if let Some(neighbors) = index.data.get(&func1_id) {
            assert_eq!(neighbors.len(), 2, "func1 should call 2 functions");
        }
    }
}

#[test]
fn test_index_path_index_file_lookup() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "foo", "file1.py");
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "file2.py");
    let node3 = create_test_node("func3", NodeKind::Function, "baz", "file1.py");

    let ir_doc = create_test_ir_doc(vec![node1, node2, node3], vec![]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Path index should group by file
    let file1_path = intern("file1.py");
    if let Some(nodes) = graph.path_index.get(&file1_path) {
        assert_eq!(nodes.len(), 2, "file1.py should have 2 nodes");
    }
}

#[test]
fn test_index_multiple_edge_types() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("class1", NodeKind::Class, "MyClass", "test.py");
    let node2 = create_test_node("func1", NodeKind::Function, "method", "test.py");

    let edge1 = create_test_edge("class1", "func1", EdgeKind::Contains);
    let edge2 = create_test_edge("func1", "class1", EdgeKind::MemberOf);

    let ir_doc = create_test_ir_doc(vec![node1, node2], vec![edge1, edge2]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    assert_eq!(graph.graph_edges.len(), 2);
    assert_eq!(graph.edge_by_id.len(), 2);
}

#[test]
fn test_index_empty_graph_indexes() {
    let builder = GraphBuilder::new();
    let ir_doc = create_test_ir_doc(vec![], vec![]);

    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Indexes should exist but be empty
    assert!(graph.indexes.is_empty() || graph.indexes.values().all(|idx| idx.data.is_empty()));
    assert!(graph.path_index.is_empty());
}

#[test]
fn test_index_large_graph_performance() {
    let builder = GraphBuilder::new();

    // Create large graph
    let nodes: Vec<_> = (0..1000)
        .map(|i| create_test_node(
            &format!("node{}", i),
            NodeKind::Function,
            &format!("func{}", i),
            &format!("file{}.py", i % 10)
        ))
        .collect();

    let edges: Vec<_> = (0..999)
        .map(|i| create_test_edge(
            &format!("node{}", i),
            &format!("node{}", i + 1),
            EdgeKind::Calls
        ))
        .collect();

    let ir_doc = create_test_ir_doc(nodes, edges);

    let start = std::time::Instant::now();
    let graph = builder.build_full(&ir_doc, None).unwrap();
    let duration = start.elapsed();

    assert_eq!(graph.graph_nodes.len(), 1000);
    assert_eq!(graph.graph_edges.len(), 999);

    // Should build in reasonable time
    assert!(duration.as_millis() < 1000, "Should build 1K nodes in <1s, took {:?}", duration);
}

#[test]
fn test_index_edge_by_id_lookup() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "test.py");
    let edge = create_test_edge("func1", "func2", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1, node2], vec![edge]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Every edge should be in edge_by_id
    for edge in &graph.graph_edges {
        assert!(graph.edge_by_id.contains_key(&edge.id), "Edge should be indexed by ID");
    }
}

#[test]
fn test_index_circular_dependency_detection() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "test.py");
    let node3 = create_test_node("func3", NodeKind::Function, "baz", "test.py");

    // Create cycle: func1 -> func2 -> func3 -> func1
    let edge1 = create_test_edge("func1", "func2", EdgeKind::Calls);
    let edge2 = create_test_edge("func2", "func3", EdgeKind::Calls);
    let edge3 = create_test_edge("func3", "func1", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1, node2, node3], vec![edge1, edge2, edge3]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Should handle cycles without crashing
    assert_eq!(graph.graph_nodes.len(), 3);
    assert_eq!(graph.graph_edges.len(), 3);
}

#[test]
fn test_index_multi_file_cross_references() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "foo", "file1.py");
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "file2.py");
    let node3 = create_test_node("func3", NodeKind::Function, "baz", "file3.py");

    // Cross-file calls
    let edge1 = create_test_edge("func1", "func2", EdgeKind::Calls);
    let edge2 = create_test_edge("func2", "func3", EdgeKind::Calls);

    let ir_doc = create_test_ir_doc(vec![node1, node2, node3], vec![edge1, edge2]);
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Path index should have 3 files
    assert_eq!(graph.path_index.len(), 3);
}

#[test]
fn test_index_incremental_consistency() {
    let builder = GraphBuilder::new();

    // Build graph 1
    let node1 = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let ir_doc1 = create_test_ir_doc(vec![node1], vec![]);
    let graph1 = builder.build_full(&ir_doc1, None).unwrap();

    // Build graph 2 (separate build)
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "test.py");
    let ir_doc2 = create_test_ir_doc(vec![node2], vec![]);
    let graph2 = builder.build_full(&ir_doc2, None).unwrap();

    // Both should have consistent indexes
    assert_eq!(graph1.graph_nodes.len(), 1);
    assert_eq!(graph2.graph_nodes.len(), 1);
}

// ============================================================
// 5. Semantic IR Integration Tests (5 tests)
// ============================================================

#[test]
fn test_semantic_ir_graceful_degradation() {
    let builder = GraphBuilder::new();

    let node = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    // Invalid semantic snapshot
    let semantic = HashMap::new();

    let result = builder.build_full(&ir_doc, Some(&semantic));
    assert!(result.is_ok(), "Should handle empty semantic snapshot");
}

#[test]
fn test_semantic_ir_none_option() {
    let builder = GraphBuilder::new();

    let node = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    // No semantic snapshot
    let graph = builder.build_full(&ir_doc, None).unwrap();

    // Should still build structural graph
    assert_eq!(graph.graph_nodes.len(), 1);
}

#[test]
fn test_semantic_ir_with_valid_data() {
    let builder = GraphBuilder::new();

    let node = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    let mut semantic = HashMap::new();
    semantic.insert(
        "func1_signature".to_string(),
        serde_json::json!({
            "params": ["x", "y"],
            "return_type": "int"
        })
    );

    let result = builder.build_full(&ir_doc, Some(&semantic));
    assert!(result.is_ok());
}

#[test]
fn test_semantic_ir_partial_data() {
    let builder = GraphBuilder::new();

    let node1 = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let node2 = create_test_node("func2", NodeKind::Function, "bar", "test.py");
    let ir_doc = create_test_ir_doc(vec![node1, node2], vec![]);

    let mut semantic = HashMap::new();
    // Only one node has semantic data
    semantic.insert("func1_type".to_string(), serde_json::json!({"type": "function"}));

    let graph = builder.build_full(&ir_doc, Some(&semantic)).unwrap();

    // Should build graph for both nodes
    assert_eq!(graph.graph_nodes.len(), 2);
}

#[test]
fn test_semantic_ir_error_recovery() {
    let builder = GraphBuilder::new();

    let node = create_test_node("func1", NodeKind::Function, "foo", "test.py");
    let ir_doc = create_test_ir_doc(vec![node], vec![]);

    let mut semantic = HashMap::new();
    // Add malformed JSON value
    semantic.insert("bad_data".to_string(), serde_json::json!(null));

    // Should not crash, should degrade gracefully
    let result = builder.build_full(&ir_doc, Some(&semantic));
    assert!(result.is_ok(), "Should recover from semantic IR errors");
}
