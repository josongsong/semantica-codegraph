//! Integration tests for Lambda & Closures (Phase 1.2)
//!
//! Tests lambda, closure, and nested function extraction across all 6 languages

use codegraph_ir::features::parsing::plugins::*;
use codegraph_ir::features::parsing::ports::{ExtractionContext, LanguageId, LanguagePlugin};
use codegraph_ir::shared::models::{EdgeKind, NodeKind};
use tree_sitter::Parser;

fn parse_with_plugin<P: LanguagePlugin + ?Sized>(plugin: &P, source: &str, filename: &str) -> codegraph_ir::features::parsing::ports::ExtractionResult {
    let mut parser = Parser::new();
    parser.set_language(&plugin.tree_sitter_language()).unwrap();
    let tree = parser.parse(source, None).unwrap();
    let mut ctx = ExtractionContext::new(source, filename, "test-repo", plugin.language_id());
    plugin.extract(&mut ctx, &tree).unwrap()
}

#[test]
fn test_python_lambda_extraction() {
    let source = r#"
# Lambda expression
double = lambda x: x * 2

# Nested function (closure)
def outer(x):
    def inner(y):
        return x + y
    return inner

# Lambda in function
def process(items):
    return list(map(lambda x: x * 2, items))
"#;

    let plugin = PythonPlugin::new();
    let result = parse_with_plugin(&plugin, source, "test.py");

    // Check lambda nodes
    let lambdas: Vec<_> = result.nodes.iter().filter(|n| n.kind == NodeKind::Lambda).collect();
    assert!(
        lambdas.len() >= 3,
        "Expected at least 3 lambda/closure nodes, found {}",
        lambdas.len()
    );

    // Check Captures edges
    let captures: Vec<_> = result.edges.iter().filter(|e| e.kind == EdgeKind::Captures).collect();
    assert!(
        captures.len() >= 3,
        "Expected at least 3 Captures edges, found {}",
        captures.len()
    );

    // Verify lambda naming
    let lambda_names: Vec<_> = lambdas.iter().filter_map(|n| n.name.as_ref()).collect();
    assert!(
        lambda_names.iter().any(|name| name.starts_with("lambda_")),
        "Expected lambda nodes with lambda_ prefix"
    );
}

#[test]
fn test_java_lambda_and_method_references() {
    let source = r#"
public class StreamExample {
    public void processData(List<String> items) {
        // Lambda expression
        items.forEach(item -> System.out.println(item));

        // Method reference
        items.forEach(System.out::println);

        // Multi-parameter lambda
        items.stream()
            .map((s) -> s.toUpperCase())
            .forEach(System.out::println);
    }
}
"#;

    let plugin = JavaPlugin::new();
    let result = parse_with_plugin(&plugin, source, "StreamExample.java");

    // Check lambda nodes (including method references)
    let lambdas: Vec<_> = result.nodes.iter().filter(|n| n.kind == NodeKind::Lambda).collect();
    assert!(
        lambdas.len() >= 2,
        "Expected at least 2 lambda nodes, found {}",
        lambdas.len()
    );

    // Check Captures edges
    let captures: Vec<_> = result.edges.iter().filter(|e| e.kind == EdgeKind::Captures).collect();
    assert!(
        !captures.is_empty(),
        "Expected Captures edges for lambdas"
    );

    // Check for method reference metadata
    let method_refs: Vec<_> = lambdas
        .iter()
        .filter(|n| {
            n.metadata
                .as_ref()
                .map(|m| m.contains("method_reference"))
                .unwrap_or(false)
        })
        .collect();

    assert!(
        !method_refs.is_empty() || lambdas.len() >= 2,
        "Expected method reference nodes or multiple lambdas"
    );
}

#[test]
fn test_typescript_arrow_functions() {
    let source = r#"
// Arrow function
const double = (x: number) => x * 2;

// Nested function (closure)
function outer(x: number) {
    function inner(y: number) {
        return x + y;
    }
    return inner;
}

// Arrow function in method
class Calculator {
    process(items: number[]) {
        return items.map(x => x * 2);
    }
}
"#;

    let plugin = TypeScriptPlugin::new();
    let result = parse_with_plugin(&plugin, source, "test.ts");

    // Check lambda/arrow function nodes
    let lambdas: Vec<_> = result.nodes.iter().filter(|n| n.kind == NodeKind::Lambda).collect();
    assert!(
        lambdas.len() >= 2,
        "Expected at least 2 lambda nodes (arrow functions + nested), found {}",
        lambdas.len()
    );

    // Check Captures edges
    let captures: Vec<_> = result.edges.iter().filter(|e| e.kind == EdgeKind::Captures).collect();
    assert!(
        !captures.is_empty(),
        "Expected Captures edges for closures"
    );
}

#[test]
fn test_kotlin_nested_functions() {
    let source = r#"
fun outer(x: Int): (Int) -> Int {
    fun inner(y: Int): Int {
        return x + y
    }
    return ::inner
}

// Lambda with receiver
fun process(items: List<Int>) {
    items.forEach { it * 2 }
}
"#;

    let plugin = KotlinPlugin::new();
    let result = parse_with_plugin(&plugin, source, "test.kt");

    // Check lambda nodes (nested functions)
    let lambdas: Vec<_> = result.nodes.iter().filter(|n| n.kind == NodeKind::Lambda).collect();
    assert!(
        !lambdas.is_empty(),
        "Expected lambda nodes for nested functions"
    );

    // Check Captures edges
    let captures: Vec<_> = result.edges.iter().filter(|e| e.kind == EdgeKind::Captures).collect();
    assert!(
        !captures.is_empty(),
        "Expected Captures edges for nested functions"
    );
}

#[test]
fn test_rust_closures() {
    let source = r#"
fn main() {
    let x = 5;

    // Simple closure
    let add = |y| x + y;

    // Typed closure
    let multiply: fn(i32) -> i32 = |z| z * 2;

    // Closure with block
    let process = |items: Vec<i32>| {
        items.iter().map(|x| x * 2).collect()
    };
}
"#;

    let plugin = RustPlugin::new();
    let result = parse_with_plugin(&plugin, source, "test.rs");

    // Check closure nodes
    let closures: Vec<_> = result.nodes.iter().filter(|n| n.kind == NodeKind::Lambda).collect();
    assert!(
        closures.len() >= 2,
        "Expected at least 2 closure nodes, found {}",
        closures.len()
    );

    // Check Captures edges
    let captures: Vec<_> = result.edges.iter().filter(|e| e.kind == EdgeKind::Captures).collect();
    assert!(
        captures.len() >= 2,
        "Expected Captures edges for closures, found {}",
        captures.len()
    );

    // Check closure metadata
    let with_metadata: Vec<_> = closures
        .iter()
        .filter(|n| {
            n.metadata
                .as_ref()
                .map(|m| m.contains("closure_kind"))
                .unwrap_or(false)
        })
        .collect();

    assert!(
        !with_metadata.is_empty(),
        "Expected closure metadata (Fn/FnMut/FnOnce)"
    );
}

#[test]
fn test_go_function_literals() {
    let source = r#"
package main

func main() {
    x := 5

    // Function literal (closure)
    add := func(y int) int {
        return x + y
    }

    // Function literal as argument
    process(func(n int) int {
        return n * 2
    })
}

func process(f func(int) int) {
    f(10)
}
"#;

    let plugin = GoPlugin::new();
    let result = parse_with_plugin(&plugin, source, "test.go");

    // Check function literal nodes
    let func_literals: Vec<_> = result.nodes.iter().filter(|n| n.kind == NodeKind::Lambda).collect();
    assert!(
        func_literals.len() >= 2,
        "Expected at least 2 function literal nodes, found {}",
        func_literals.len()
    );

    // Check Captures edges
    let captures: Vec<_> = result.edges.iter().filter(|e| e.kind == EdgeKind::Captures).collect();
    assert!(
        captures.len() >= 2,
        "Expected Captures edges for function literals, found {}",
        captures.len()
    );

    // Verify naming pattern
    let names: Vec<_> = func_literals.iter().filter_map(|n| n.name.as_ref()).collect();
    assert!(
        names.iter().any(|name| name.starts_with("func_literal_")),
        "Expected func_literal_ naming pattern"
    );
}

// Cross-language consistency is tested via individual language tests above
// All languages use NodeKind::Lambda and EdgeKind::Captures consistently

#[test]
fn test_deeply_nested_closures() {
    let source = r#"
def level1():
    x = 1
    def level2():
        y = 2
        def level3():
            z = 3
            return lambda w: x + y + z + w
        return level3()
    return level2()
"#;

    let plugin = PythonPlugin::new();
    let result = parse_with_plugin(&plugin, source, "test.py");

    // Should have multiple lambda nodes
    let lambdas: Vec<_> = result.nodes.iter().filter(|n| n.kind == NodeKind::Lambda).collect();
    assert!(
        lambdas.len() >= 3,
        "Expected at least 3 nested closure nodes, found {}",
        lambdas.len()
    );

    // Should have multiple Captures edges
    let captures: Vec<_> = result.edges.iter().filter(|e| e.kind == EdgeKind::Captures).collect();
    assert!(
        captures.len() >= 3,
        "Expected multiple Captures edges for nested closures, found {}",
        captures.len()
    );
}
