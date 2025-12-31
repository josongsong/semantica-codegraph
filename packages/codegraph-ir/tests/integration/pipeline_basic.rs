// End-to-end integration tests for the L1-L6 pipeline
// Tests the full processing pipeline with realistic Python code

mod common;
use common::{
    assert_no_errors, assert_node_count, fixture_n_functions, fixture_simple_class,
    fixture_simple_function, fixture_with_imports,
};

use codegraph_ir::pipeline::process_python_file;

#[test]
fn test_process_empty_file() {
    let result = process_python_file("", "test-repo", "empty.py", "empty");

    // Empty file should parse without errors
    assert_no_errors(&result);
    // Should have minimal nodes (possibly file/module node)
    assert!(result.nodes.len() <= 1, "Empty file should have at most 1 node");
}

#[test]
fn test_process_simple_function() {
    let source = fixture_simple_function("hello");
    let result = process_python_file(&source, "test-repo", "test.py", "test");

    assert_no_errors(&result);
    assert_node_count(&result, 1); // 1 function node

    // Verify function node properties
    let func_node = &result.nodes[0];
    assert_eq!(func_node.kind.as_str(), "function");
    assert_eq!(func_node.name, Some("hello".to_string()));
}

#[test]
fn test_process_simple_class() {
    let source = fixture_simple_class("MyClass", 3);
    let result = process_python_file(&source, "test-repo", "test.py", "test");

    assert_no_errors(&result);

    // Should have 1 class + 3 methods = 4 nodes
    assert_node_count(&result, 4);

    // Verify we have class and method nodes
    let class_count = result
        .nodes
        .iter()
        .filter(|n| n.kind.as_str() == "class")
        .count();
    let method_count = result
        .nodes
        .iter()
        .filter(|n| n.kind.as_str() == "method")
        .count();

    assert_eq!(class_count, 1, "Should have 1 class");
    assert_eq!(method_count, 3, "Should have 3 methods");
}

#[test]
fn test_process_with_imports() {
    let source = fixture_with_imports(&["os", "sys", "json"]);
    let result = process_python_file(&source, "test-repo", "test.py", "test");

    assert_no_errors(&result);

    // Should have import nodes
    let import_count = result
        .nodes
        .iter()
        .filter(|n| n.kind.as_str() == "import")
        .count();

    assert!(import_count >= 3, "Should have at least 3 import nodes");
}

#[test]
fn test_process_generates_bfg() {
    let source = r#"
def calculate(x: int, y: int) -> int:
    if x > y:
        return x
    else:
        return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    assert_no_errors(&result);

    // Should generate BFG (Basic Flow Graph)
    assert!(
        !result.bfg_graphs.is_empty(),
        "Should generate at least 1 BFG"
    );

    let bfg = &result.bfg_graphs[0];
    assert!(bfg.blocks.len() >= 3, "Should have multiple blocks for if/else");
    assert!(
        bfg.total_statements >= 3,
        "Should have at least 3 statements"
    );
}

#[test]
fn test_process_generates_cfg_edges() {
    let source = r#"
def loop_example(n: int) -> int:
    total = 0
    for i in range(n):
        total += i
    return total
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    assert_no_errors(&result);

    // Should generate CFG edges
    assert!(
        !result.cfg_edges.is_empty(),
        "Should generate CFG edges for control flow"
    );
}

#[test]
fn test_process_generates_type_entities() {
    let source = r#"
def typed_function(name: str, age: int) -> dict[str, int]:
    return {"name": name, "age": age}
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    assert_no_errors(&result);

    // Should extract type annotations
    assert!(
        !result.type_entities.is_empty(),
        "Should generate type entities from annotations"
    );
}

#[test]
fn test_process_generates_occurrences() {
    let source = fixture_simple_function("test_func");
    let result = process_python_file(&source, "test-repo", "test.py", "test");

    assert_no_errors(&result);

    // Should generate occurrences (L1 optimization)
    assert!(
        !result.occurrences.is_empty(),
        "Should generate occurrences in Rust L1"
    );
}

#[test]
#[ignore] // Mark as slow test (>1s)
fn test_process_large_file_performance() {
    // Generate large Python file (1000 functions)
    let source = fixture_n_functions(1000);
    let result = process_python_file(&source, "test-repo", "large.py", "large");

    assert_no_errors(&result);
    assert_eq!(result.nodes.len(), 1000, "Should process all functions");
}

#[test]
fn test_process_invalid_syntax_returns_error() {
    let source = "def broken(:\n    invalid syntax here";
    let result = process_python_file(source, "test-repo", "broken.py", "broken");

    // Should have errors for invalid syntax
    assert!(
        !result.errors.is_empty(),
        "Should report errors for invalid syntax"
    );
}

#[test]
fn test_process_real_world_django_model() {
    let source = r#"
from django.db import models

class User(models.Model):
    """User model with authentication."""

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.username

    def activate(self) -> None:
        """Activate the user account."""
        self.is_active = True
        self.save()
"#;

    let result = process_python_file(source, "test-repo", "models.py", "app.models");

    assert_no_errors(&result);

    // Should parse Django model correctly
    let class_nodes: Vec<_> = result
        .nodes
        .iter()
        .filter(|n| n.kind.as_str() == "class")
        .collect();
    assert_eq!(class_nodes.len(), 1, "Should have 1 class");

    let method_nodes: Vec<_> = result
        .nodes
        .iter()
        .filter(|n| n.kind.as_str() == "method")
        .collect();
    assert!(method_nodes.len() >= 2, "Should have at least 2 methods");
}
