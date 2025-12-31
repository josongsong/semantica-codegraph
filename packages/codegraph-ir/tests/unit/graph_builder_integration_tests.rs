// SOTA Graph Builder Integration Tests
//
// Real-world scenarios and end-to-end workflows

use codegraph_ir::features::graph_builder::infrastructure::GraphBuilder;
use codegraph_ir::features::graph_builder::domain::intern;
use codegraph_ir::shared::models::{Node, Edge, NodeKind, EdgeKind, Span};
use codegraph_ir::features::cross_file::IRDocument;
use std::collections::HashMap;

// ============================================================
// Real-World Scenarios
// ============================================================

#[test]
fn integration_realistic_python_module() {
    // Simulate realistic Python module structure
    let builder = GraphBuilder::new();

    let mut nodes = vec![];
    let mut edges = vec![];

    // File node
    let mut file = Node {
        id: "file:module.py".to_string(),
        kind: NodeKind::File,
        fqn: "myapp.module".to_string(),
        name: Some("module.py".to_string()),
        file_path: Some("myapp/module.py".to_string()),
        span: None,
        language: Some("python".to_string()),
        docstring: Some("Main module".to_string()),
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: Some("myapp.module".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(file);

    // Class node
    let mut class = Node {
        id: "class:MyClass".to_string(),
        kind: NodeKind::Class,
        fqn: "myapp.module.MyClass".to_string(),
        name: Some("MyClass".to_string()),
        file_path: Some("myapp/module.py".to_string()),
        span: Some(Span { start_line: 5, start_col: 0, end_line: 20, end_col: 0 }),
        language: Some("python".to_string()),
        docstring: Some("My class docstring".to_string()),
        role: Some("model".to_string()),
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: Some("myapp.module".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(class.clone());

    // Method node
    let mut method = Node {
        id: "method:MyClass.process".to_string(),
        kind: NodeKind::Method,
        fqn: "myapp.module.MyClass.process".to_string(),
        name: Some("process".to_string()),
        file_path: Some("myapp/module.py".to_string()),
        span: Some(Span { start_line: 10, start_col: 4, end_line: 15, end_col: 0 }),
        language: Some("python".to_string()),
        docstring: Some("Process data".to_string()),
        role: None,
        is_test_file: Some(false),
        signature_id: Some("sig:process".to_string()),
        declared_type_id: None,
        module_path: Some("myapp.module".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(method.clone());

    // Variable node
    let mut var = Node {
        id: "var:MyClass.data".to_string(),
        kind: NodeKind::Variable,
        fqn: "myapp.module.MyClass.data".to_string(),
        name: Some("data".to_string()),
        file_path: Some("myapp/module.py".to_string()),
        span: Some(Span { start_line: 11, start_col: 8, end_line: 11, end_col: 20 }),
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: Some("type:dict".to_string()),
        module_path: Some("myapp.module".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(var.clone());

    // Edges
    edges.push(Edge {
        source_id: "file:module.py".to_string(),
        target_id: "class:MyClass".to_string(),
        kind: EdgeKind::Contains,
        span: None,
        attrs: HashMap::new(),
    });

    edges.push(Edge {
        source_id: "class:MyClass".to_string(),
        target_id: "method:MyClass.process".to_string(),
        kind: EdgeKind::Contains,
        span: None,
        attrs: HashMap::new(),
    });

    edges.push(Edge {
        source_id: "method:MyClass.process".to_string(),
        target_id: "var:MyClass.data".to_string(),
        kind: EdgeKind::Reads,
        span: None,
        attrs: HashMap::new(),
    });

    let ir_doc = IRDocument {
        file_path: "myapp/module.py".to_string(),
        nodes,
        edges,
    };

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let graph = result.unwrap();

    // Verify structure
    assert_eq!(graph.graph_nodes.len(), 4); // file, class, method, var
    assert_eq!(graph.graph_edges.len(), 3);

    // Verify containment hierarchy
    let file_children = graph.indexes.contains_children.get(&intern("file:module.py"));
    assert!(file_children.is_some());
    assert_eq!(file_children.unwrap().len(), 1);

    // Verify reads relationship
    let var_readers = graph.indexes.reads_by.get(&intern("var:MyClass.data"));
    assert!(var_readers.is_some());
    assert_eq!(var_readers.unwrap()[0].as_ref(), "method:MyClass.process");

    // Verify path index
    let nodes_in_file = graph.get_node_ids_by_path("myapp/module.py");
    assert!(nodes_in_file.is_some());
    assert_eq!(nodes_in_file.unwrap().len(), 4);

    // Verify module generation
    let module_nodes: Vec<_> = graph.graph_nodes.values()
        .filter(|n| n.kind == NodeKind::Module)
        .collect();
    assert!(module_nodes.len() >= 1, "Should generate myapp module");

    println!("✅ Realistic Python module structure verified");
}

#[test]
fn integration_cross_file_imports() {
    // Simulate cross-file imports
    let builder = GraphBuilder::new();

    let mut nodes = vec![];
    let mut edges = vec![];

    // File A
    let file_a = Node {
        id: "file:a.py".to_string(),
        kind: NodeKind::File,
        fqn: "myapp.a".to_string(),
        name: Some("a.py".to_string()),
        file_path: Some("myapp/a.py".to_string()),
        span: None,
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: Some("myapp.a".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(file_a);

    // File B
    let file_b = Node {
        id: "file:b.py".to_string(),
        kind: NodeKind::File,
        fqn: "myapp.b".to_string(),
        name: Some("b.py".to_string()),
        file_path: Some("myapp/b.py".to_string()),
        span: None,
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: Some("myapp.b".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(file_b);

    // Function in A
    let mut func_a = Node {
        id: "func:a.foo".to_string(),
        kind: NodeKind::Function,
        fqn: "myapp.a.foo".to_string(),
        name: Some("foo".to_string()),
        file_path: Some("myapp/a.py".to_string()),
        span: Some(Span { start_line: 1, start_col: 0, end_line: 3, end_col: 0 }),
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: Some("myapp.a".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(func_a);

    // Function in B
    let mut func_b = Node {
        id: "func:b.bar".to_string(),
        kind: NodeKind::Function,
        fqn: "myapp.b.bar".to_string(),
        name: Some("bar".to_string()),
        file_path: Some("myapp/b.py".to_string()),
        span: Some(Span { start_line: 1, start_col: 0, end_line: 3, end_col: 0 }),
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: Some("myapp.b".to_string()),
        attrs: HashMap::new(),
    };
    nodes.push(func_b);

    // Import edge: B imports A
    edges.push(Edge {
        source_id: "file:b.py".to_string(),
        target_id: "file:a.py".to_string(),
        kind: EdgeKind::Imports,
        span: None,
        attrs: HashMap::new(),
    });

    // Call edge: B.bar() calls A.foo()
    edges.push(Edge {
        source_id: "func:b.bar".to_string(),
        target_id: "func:a.foo".to_string(),
        kind: EdgeKind::Calls,
        span: None,
        attrs: HashMap::new(),
    });

    let ir_doc = IRDocument {
        file_path: "combined".to_string(),
        nodes,
        edges,
    };

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let graph = result.unwrap();

    // Verify imports
    let imported_by_a = graph.indexes.imported_by.get(&intern("file:a.py"));
    assert!(imported_by_a.is_some());
    assert_eq!(imported_by_a.unwrap()[0].as_ref(), "file:b.py");

    // Verify calls
    let foo_callers = graph.indexes.called_by.get(&intern("func:a.foo"));
    assert!(foo_callers.is_some());
    assert_eq!(foo_callers.unwrap()[0].as_ref(), "func:b.bar");

    // Verify path index for multiple files
    let nodes_in_a = graph.get_node_ids_by_path("myapp/a.py");
    assert_eq!(nodes_in_a.unwrap().len(), 2); // file + func

    let nodes_in_b = graph.get_node_ids_by_path("myapp/b.py");
    assert_eq!(nodes_in_b.unwrap().len(), 2); // file + func

    println!("✅ Cross-file imports and calls verified");
}

#[test]
fn integration_test_file_detection() {
    // Test that test files are properly marked
    let builder = GraphBuilder::new();

    let mut test_file = Node {
        id: "file:test_module.py".to_string(),
        kind: NodeKind::File,
        fqn: "tests.test_module".to_string(),
        name: Some("test_module.py".to_string()),
        file_path: Some("tests/test_module.py".to_string()),
        span: None,
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(true), // Marked as test
        signature_id: None,
        declared_type_id: None,
        module_path: None,
        attrs: HashMap::new(),
    };

    let ir_doc = IRDocument {
        file_path: "tests/test_module.py".to_string(),
        nodes: vec![test_file],
        edges: vec![],
    };

    let result = builder.build_full(&ir_doc, None);
    assert!(result.is_ok());

    let graph = result.unwrap();
    let test_node = graph.get_node("file:test_module.py").unwrap();

    let is_test = test_node.attrs.get("is_test_file")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    assert!(is_test, "Test file should be marked");

    println!("✅ Test file detection verified");
}

#[test]
fn integration_incremental_update_simulation() {
    // Simulate incremental updates (cache persistence)
    let builder = GraphBuilder::new();

    // Build 1: Initial graph
    let mut node1 = Node {
        id: "func:v1".to_string(),
        kind: NodeKind::Function,
        fqn: "app.func".to_string(),
        name: Some("func".to_string()),
        file_path: Some("app/core/module.py".to_string()),
        span: None,
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: None,
        attrs: HashMap::new(),
    };

    let ir_doc1 = IRDocument {
        file_path: "app/core/module.py".to_string(),
        nodes: vec![node1],
        edges: vec![],
    };

    builder.build_full(&ir_doc1, None).unwrap();
    let cache_size_1 = builder.cache_stats().module_cache_size;

    // Build 2: Same path, different node (simulates file modification)
    let mut node2 = Node {
        id: "func:v2".to_string(),
        kind: NodeKind::Function,
        fqn: "app.func_updated".to_string(),
        name: Some("func_updated".to_string()),
        file_path: Some("app/core/module.py".to_string()), // Same path
        span: None,
        language: Some("python".to_string()),
        docstring: None,
        role: None,
        is_test_file: Some(false),
        signature_id: None,
        declared_type_id: None,
        module_path: None,
        attrs: HashMap::new(),
    };

    let ir_doc2 = IRDocument {
        file_path: "app/core/module.py".to_string(),
        nodes: vec![node2],
        edges: vec![],
    };

    builder.build_full(&ir_doc2, None).unwrap();
    let cache_size_2 = builder.cache_stats().module_cache_size;

    // Cache should be reused (same path modules)
    assert_eq!(cache_size_2, cache_size_1, "Module cache should persist");

    println!("✅ Incremental update simulation verified");
}

#[test]
fn integration_stats_collection() {
    // Verify comprehensive stats collection
    let builder = GraphBuilder::new();

    let nodes = vec![
        Node {
            id: "f1".to_string(),
            kind: NodeKind::Function,
            fqn: "f1".to_string(),
            name: Some("f1".to_string()),
            file_path: Some("a.py".to_string()),
            span: None,
            language: Some("python".to_string()),
            docstring: None,
            role: None,
            is_test_file: Some(false),
            signature_id: None,
            declared_type_id: None,
            module_path: None,
            attrs: HashMap::new(),
        },
        Node {
            id: "c1".to_string(),
            kind: NodeKind::Class,
            fqn: "c1".to_string(),
            name: Some("c1".to_string()),
            file_path: Some("a.py".to_string()),
            span: None,
            language: Some("python".to_string()),
            docstring: None,
            role: None,
            is_test_file: Some(false),
            signature_id: None,
            declared_type_id: None,
            module_path: None,
            attrs: HashMap::new(),
        },
    ];

    let edges = vec![
        Edge {
            source_id: "f1".to_string(),
            target_id: "c1".to_string(),
            kind: EdgeKind::Calls,
            span: None,
            attrs: HashMap::new(),
        },
    ];

    let ir_doc = IRDocument {
        file_path: "a.py".to_string(),
        nodes,
        edges,
    };

    let graph = builder.build_full(&ir_doc, None).unwrap();

    let stats = graph.stats();

    assert_eq!(stats.total_nodes, 2);
    assert_eq!(stats.total_edges, 1);
    assert_eq!(stats.nodes_by_kind.get(&NodeKind::Function), Some(&1));
    assert_eq!(stats.nodes_by_kind.get(&NodeKind::Class), Some(&1));
    assert_eq!(stats.edges_by_kind.get(&EdgeKind::Calls), Some(&1));

    let cache_stats = builder.cache_stats();
    assert!(cache_stats.string_interner_size > 0);

    println!("✅ Stats collection verified");
    println!("   Nodes: {}, Edges: {}", stats.total_nodes, stats.total_edges);
    println!("   String interner: {} unique strings", cache_stats.string_interner_size);
}
