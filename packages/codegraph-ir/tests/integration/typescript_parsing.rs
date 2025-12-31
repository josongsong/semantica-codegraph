//! Integration tests for TypeScript symbol extraction
//!
//! Tests the complete extraction pipeline using real TypeScript files.

use codegraph_ir::features::parsing::infrastructure::extractors::typescript::*;
use codegraph_ir::features::parsing::infrastructure::tree_sitter::languages::typescript::*;
use tree_sitter::Parser;

fn parse_typescript(source: &str) -> tree_sitter::Tree {
    let mut parser = Parser::new();
    parser.set_language(tree_sitter_typescript::language_typescript()).unwrap();
    parser.parse(source, None).unwrap()
}

#[test]
fn test_simple_class_extraction() {
    let source = include_str!("fixtures/typescript/simple_class.ts");
    let tree = parse_typescript(source);
    let root = tree.root_node();

    // Find class declaration
    let mut class_node = None;
    for i in 0..root.child_count() {
        if let Some(child) = root.child(i) {
            // May be wrapped in export_statement
            if child.kind() == node_kinds::EXPORT_STATEMENT {
                if let Some(class) = child.child_by_field_name("declaration") {
                    if class.kind() == node_kinds::CLASS_DECLARATION {
                        class_node = Some(class);
                        break;
                    }
                }
            } else if child.kind() == node_kinds::CLASS_DECLARATION {
                class_node = Some(child);
                break;
            }
        }
    }

    assert!(class_node.is_some(), "Should find UserComponent class");
    let class_node = class_node.unwrap();

    let class_info = extract_class_info(&class_node, source).unwrap();

    assert_eq!(class_info.name, "UserComponent");
    assert!(!class_info.decorators.is_empty(), "Should have decorators");
    assert!(class_info.decorators.iter().any(|d| d.contains("Component")));
    assert!(class_info.is_export, "Should be exported");
}

#[test]
fn test_function_extraction() {
    let source = include_str!("fixtures/typescript/arrow_functions.ts");
    let tree = parse_typescript(source);
    let root = tree.root_node();

    // Count arrow functions and regular functions
    let mut arrow_count = 0;
    let mut has_async = false;
    let mut has_generic = false;

    fn traverse(node: &tree_sitter::Node, source: &str, arrow_count: &mut usize, has_async: &mut bool, has_generic: &mut bool) {
        if node.kind() == node_kinds::ARROW_FUNCTION {
            *arrow_count += 1;

            if let Some(info) = extract_function_info(node, source) {
                if info.is_async {
                    *has_async = true;
                }
                if !info.type_parameters.is_empty() {
                    *has_generic = true;
                }
            }
        }

        for i in 0..node.child_count() {
            if let Some(child) = node.child(i) {
                traverse(&child, source, arrow_count, has_async, has_generic);
            }
        }
    }

    traverse(&root, source, &mut arrow_count, &mut has_async, &mut has_generic);

    assert!(arrow_count >= 5, "Should find multiple arrow functions, found {}", arrow_count);
    assert!(has_async, "Should find async arrow function");
    assert!(has_generic, "Should find generic arrow function");
}

#[test]
fn test_generic_extraction() {
    let source = include_str!("fixtures/typescript/generics.ts");
    let tree = parse_typescript(source);
    let root = tree.root_node();

    // Find the Container class
    let mut class_node = None;
    fn find_class(node: &tree_sitter::Node, source: &str) -> Option<tree_sitter::Node> {
        if node.kind() == node_kinds::CLASS_DECLARATION {
            if let Some(name) = node.child_by_field_name("name") {
                let start = name.start_byte();
                let end = name.end_byte();
                if &source[start..end] == "Container" {
                    return Some(*node);
                }
            }
        }

        for i in 0..node.child_count() {
            if let Some(child) = node.child(i) {
                if let Some(found) = find_class(&child, source) {
                    return Some(found);
                }
            }
        }

        None
    }

    class_node = find_class(&root, source);
    assert!(class_node.is_some(), "Should find Container class");

    let class_info = extract_class_info(&class_node.unwrap(), source).unwrap();
    assert_eq!(class_info.name, "Container");
    assert!(!class_info.type_parameters.is_empty(), "Should have type parameters");
    assert!(class_info.type_parameters[0].contains("extends"), "Should have constraint");
}

#[test]
fn test_union_intersection_types() {
    let source = include_str!("fixtures/typescript/union_types.ts");
    let tree = parse_typescript(source);

    // Test that we can parse union and intersection types
    // The types module should handle these correctly
    assert!(source.contains("|"), "Should have union types");
    assert!(source.contains("&"), "Should have intersection types");

    // Test type decomposition helpers
    let union = "string | number | boolean";
    let parts = decompose_union_type(union);
    assert_eq!(parts.len(), 3);
    assert_eq!(parts[0], "string");
    assert_eq!(parts[1], "number");
    assert_eq!(parts[2], "boolean");

    let intersection = "Person & Employee";
    let parts = decompose_intersection_type(intersection);
    assert_eq!(parts.len(), 2);
    assert_eq!(parts[0], "Person");
    assert_eq!(parts[1], "Employee");
}

#[test]
fn test_react_hooks_detection() {
    let source = include_str!("fixtures/typescript/react_hooks.tsx");
    let tree = parse_typescript(source);
    let root = tree.root_node();

    // Count React hooks
    let mut hook_count = 0;
    let mut custom_hook_found = false;

    fn traverse(node: &tree_sitter::Node, source: &str, hook_count: &mut usize, custom_hook_found: &mut bool) {
        if node.kind() == node_kinds::FUNCTION_DECLARATION {
            if let Some(info) = extract_function_info(node, source) {
                if info.is_react_hook {
                    *hook_count += 1;
                }
                if info.name == "useCustomHook" {
                    *custom_hook_found = true;
                }
            }
        }

        for i in 0..node.child_count() {
            if let Some(child) = node.child(i) {
                traverse(&child, source, hook_count, custom_hook_found);
            }
        }
    }

    traverse(&root, source, &mut hook_count, &mut custom_hook_found);

    assert!(hook_count > 0, "Should detect React hooks");
    assert!(custom_hook_found, "Should detect custom hook");
}

#[test]
fn test_import_extraction() {
    let source = include_str!("fixtures/typescript/imports.ts");
    let tree = parse_typescript(source);
    let root = tree.root_node();

    let mut imports = Vec::new();

    for i in 0..root.child_count() {
        if let Some(child) = root.child(i) {
            if child.kind() == node_kinds::IMPORT_STATEMENT {
                if let Some(import_info) = extract_import_info(&child, source) {
                    imports.push(import_info);
                }
            }
        }
    }

    assert!(!imports.is_empty(), "Should find imports");

    // Check for different import styles
    let has_default = imports.iter().any(|imp| {
        imp.imported_symbols.iter().any(|sym| sym.is_default)
    });

    let has_named = imports.iter().any(|imp| {
        imp.imported_symbols.iter().any(|sym| !sym.is_default && !sym.is_namespace)
    });

    let has_namespace = imports.iter().any(|imp| {
        imp.imported_symbols.iter().any(|sym| sym.is_namespace)
    });

    let has_alias = imports.iter().any(|imp| {
        imp.imported_symbols.iter().any(|sym| sym.alias.is_some())
    });

    assert!(has_default, "Should find default imports");
    assert!(has_named, "Should find named imports");
    assert!(has_namespace, "Should find namespace imports");
    assert!(has_alias, "Should find aliased imports");
}

#[test]
fn test_decorator_extraction() {
    let source = include_str!("fixtures/typescript/simple_class.ts");
    let tree = parse_typescript(source);
    let root = tree.root_node();

    // Find class with decorators
    let mut class_node = None;
    for i in 0..root.child_count() {
        if let Some(child) = root.child(i) {
            if child.kind() == node_kinds::EXPORT_STATEMENT {
                if let Some(class) = child.child_by_field_name("declaration") {
                    if class.kind() == node_kinds::CLASS_DECLARATION {
                        class_node = Some(class);
                        break;
                    }
                }
            }
        }
    }

    assert!(class_node.is_some());
    let class_info = extract_class_info(&class_node.unwrap(), source).unwrap();

    assert!(!class_info.decorators.is_empty(), "Should have decorators");

    // Check that decorator is recognized
    let decorator_name = &class_info.decorators[0];
    assert!(decorator_name.contains("Component"));
}

#[test]
fn test_builtin_types() {
    assert!(is_builtin_type("string"));
    assert!(is_builtin_type("number"));
    assert!(is_builtin_type("boolean"));
    assert!(is_builtin_type("Array"));
    assert!(is_builtin_type("Promise"));
    assert!(is_builtin_type("Map"));
    assert!(is_builtin_type("Set"));

    // Utility types
    assert!(is_builtin_type("Partial"));
    assert!(is_builtin_type("Required"));
    assert!(is_builtin_type("Readonly"));
    assert!(is_builtin_type("Pick"));
    assert!(is_builtin_type("Omit"));

    // Not builtin
    assert!(!is_builtin_type("MyCustomType"));
    assert!(!is_builtin_type("UserService"));
}

#[test]
fn test_react_hook_pattern() {
    assert!(is_react_hook("useState"));
    assert!(is_react_hook("useEffect"));
    assert!(is_react_hook("useCallback"));
    assert!(is_react_hook("useMemo"));
    assert!(is_react_hook("useRef"));

    // React 18 hooks
    assert!(is_react_hook("useId"));
    assert!(is_react_hook("useTransition"));

    // Custom hooks (use* pattern)
    assert!(is_react_hook("useCustomHook"));
    assert!(is_react_hook("useAuth"));
    assert!(is_react_hook("useFetch"));

    // Not hooks
    assert!(!is_react_hook("getUserData"));
    assert!(!is_react_hook("handleClick"));
}

#[test]
fn test_variable_extraction() {
    let source = r#"
        const foo: string = "hello";
        let bar: number = 42;
        var baz = true;
        export const PI = 3.14159;
    "#;

    let tree = parse_typescript(source);
    let root = tree.root_node();

    let mut variables = Vec::new();

    for i in 0..root.child_count() {
        if let Some(child) = root.child(i) {
            let node = if child.kind() == node_kinds::EXPORT_STATEMENT {
                child.child_by_field_name("declaration")
            } else {
                Some(child)
            };

            if let Some(node) = node {
                if node.kind() == node_kinds::VARIABLE_DECLARATION {
                    let vars = extract_variable_info(&node, source);
                    variables.extend(vars);
                }
            }
        }
    }

    assert!(!variables.is_empty(), "Should extract variables");

    let has_const = variables.iter().any(|v| v.is_const);
    let has_let = variables.iter().any(|v| v.is_let);

    assert!(has_const, "Should have const variables");
    assert!(has_let, "Should have let variables");
}

#[cfg(test)]
mod performance_tests {
    use super::*;
    use std::time::Instant;

    #[test]
    #[ignore] // Run with --ignored for benchmarking
    fn bench_typescript_parsing() {
        let source = include_str!("fixtures/typescript/simple_class.ts");

        let iterations = 1000;
        let start = Instant::now();

        for _ in 0..iterations {
            let tree = parse_typescript(source);
            let _ = tree.root_node();
        }

        let elapsed = start.elapsed();
        let avg_ms = elapsed.as_secs_f64() * 1000.0 / iterations as f64;

        println!("Average parsing time: {:.3}ms per file", avg_ms);
        assert!(avg_ms < 1.0, "Should parse in less than 1ms (got {:.3}ms)", avg_ms);
    }

    #[test]
    #[ignore]
    fn bench_class_extraction() {
        let source = include_str!("fixtures/typescript/simple_class.ts");
        let tree = parse_typescript(source);
        let root = tree.root_node();

        // Find class node first
        let mut class_node = None;
        for i in 0..root.child_count() {
            if let Some(child) = root.child(i) {
                if child.kind() == node_kinds::EXPORT_STATEMENT {
                    if let Some(class) = child.child_by_field_name("declaration") {
                        if class.kind() == node_kinds::CLASS_DECLARATION {
                            class_node = Some(class);
                            break;
                        }
                    }
                }
            }
        }

        let class_node = class_node.unwrap();
        let iterations = 10000;
        let start = Instant::now();

        for _ in 0..iterations {
            let _ = extract_class_info(&class_node, source);
        }

        let elapsed = start.elapsed();
        let avg_us = elapsed.as_micros() as f64 / iterations as f64;

        println!("Average extraction time: {:.2}µs per class", avg_us);
        assert!(avg_us < 100.0, "Should extract in less than 100µs (got {:.2}µs)", avg_us);
    }
}
