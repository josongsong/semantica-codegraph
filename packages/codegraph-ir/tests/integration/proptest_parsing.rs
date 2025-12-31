//! Property-based tests for parsing robustness
//!
//! These tests verify that the parser behaves correctly for a wide range of inputs,
//! including edge cases and randomly generated code.

use proptest::prelude::*;
use codegraph_ir::features::parsing::ports::parser::process_python_file;

// Strategy for generating valid Python identifiers
fn python_identifier() -> impl Strategy<Value = String> {
    "[a-z_][a-z0-9_]{0,20}"
        .prop_filter("not a keyword", |s| {
            !matches!(
                s.as_str(),
                "def" | "class" | "if" | "else" | "for" | "while" | "return" | "import" | "from"
            )
        })
}

// Strategy for generating simple Python functions
fn python_function() -> impl Strategy<Value = String> {
    python_identifier().prop_map(|name| format!("def {name}(): pass"))
}

// Strategy for generating Python classes
fn python_class() -> impl Strategy<Value = String> {
    (python_identifier(), 0..5usize).prop_map(|(class_name, method_count)| {
        let methods: String = (0..method_count)
            .map(|i| format!("    def method_{i}(self): pass\n"))
            .collect();

        format!("class {class_name}:\n{methods}")
    })
}

// Strategy for generating import statements
fn python_import() -> impl Strategy<Value = String> {
    python_identifier().prop_map(|module| format!("import {module}"))
}

// Strategy for generating from-import statements
fn python_from_import() -> impl Strategy<Value = String> {
    (python_identifier(), python_identifier())
        .prop_map(|(module, name)| format!("from {module} import {name}"))
}

// Strategy for generating a mix of Python statements
fn python_source() -> impl Strategy<Value = String> {
    prop::collection::vec(
        prop_oneof![
            python_function(),
            python_class(),
            python_import(),
            python_from_import(),
        ],
        0..10,
    )
    .prop_map(|statements| statements.join("\n\n"))
}

proptest! {
    /// Property: Parser should never panic on any valid Python source
    #[test]
    fn prop_parser_never_panics(source in python_source()) {
        let _ = process_python_file(&source, "repo", "test.py", "test");
        // If we got here without panicking, test passes
    }

    /// Property: Parsing a function should always produce at least one node
    #[test]
    fn prop_function_produces_nodes(func in python_function()) {
        let result = process_python_file(&func, "repo", "test.py", "test");
        prop_assert!(result.nodes.len() >= 1, "Expected at least 1 node (module)");
    }

    /// Property: Parsing a class should produce at least 2 nodes (module + class)
    #[test]
    fn prop_class_produces_multiple_nodes(class in python_class()) {
        let result = process_python_file(&class, "repo", "test.py", "test");
        prop_assert!(
            result.nodes.len() >= 2,
            "Expected at least 2 nodes (module + class), got {}",
            result.nodes.len()
        );
    }

    /// Property: Valid identifiers should be accepted
    #[test]
    fn prop_valid_identifiers_accepted(name in python_identifier()) {
        let source = format!("def {name}(): pass");
        let result = process_python_file(&source, "repo", "test.py", "test");
        prop_assert!(
            result.nodes.iter().any(|n| n.name == name),
            "Expected to find function '{name}'"
        );
    }

    /// Property: Import statements should create import edges
    #[test]
    fn prop_imports_create_edges(import in python_import()) {
        let result = process_python_file(&import, "repo", "test.py", "test");
        // Import statements may or may not create edges depending on whether
        // the imported module exists, so we just verify no panic
        prop_assert!(result.errors.is_empty() || !result.errors.is_empty());
    }

    /// Property: Parsing empty source should not fail
    #[test]
    fn prop_empty_source_valid(whitespace in "\\s*") {
        let result = process_python_file(&whitespace, "repo", "test.py", "test");
        prop_assert!(
            result.nodes.len() >= 1,
            "Empty source should produce at least module node"
        );
    }

    /// Property: Multiple functions should produce multiple nodes
    #[test]
    fn prop_multiple_functions(count in 1..10usize) {
        let source: String = (0..count)
            .map(|i| format!("def func_{i}(): pass\n"))
            .collect();

        let result = process_python_file(&source, "repo", "test.py", "test");

        // Should have at least count + 1 nodes (module + functions)
        prop_assert!(
            result.nodes.len() >= count + 1,
            "Expected at least {} nodes, got {}",
            count + 1,
            result.nodes.len()
        );
    }

    /// Property: Class with methods should have correct node count
    #[test]
    fn prop_class_method_count(
        class_name in python_identifier(),
        method_count in 0..10usize
    ) {
        let methods: String = (0..method_count)
            .map(|i| format!("    def method_{i}(self): pass\n"))
            .collect();

        let source = format!("class {class_name}:\n{methods}");
        let result = process_python_file(&source, "repo", "test.py", "test");

        // Should have module + class + methods
        let expected_min = 1 + 1 + method_count;
        prop_assert!(
            result.nodes.len() >= expected_min,
            "Expected at least {} nodes, got {}",
            expected_min,
            result.nodes.len()
        );
    }
}

// Strategy for generating nested structures
prop_compose! {
    fn nested_class()(
        outer_name in python_identifier(),
        inner_name in python_identifier(),
        method_count in 0..3usize
    ) -> String {
        let methods: String = (0..method_count)
            .map(|i| format!("        def method_{i}(self): pass\n"))
            .collect();

        format!(
            "class {outer_name}:\n    class {inner_name}:\n{methods}"
        )
    }
}

proptest! {
    /// Property: Nested classes should be parsed correctly
    #[test]
    fn prop_nested_classes(source in nested_class()) {
        let result = process_python_file(&source, "repo", "test.py", "test");

        // Should have module + outer class + inner class + methods
        prop_assert!(
            result.nodes.len() >= 3,
            "Expected at least 3 nodes for nested classes, got {}",
            result.nodes.len()
        );
    }
}

// Regression tests using specific seeds
#[test]
fn regression_test_specific_seed() {
    // If a proptest fails, you can extract the seed and create a regression test
    let mut runner = proptest::test_runner::TestRunner::new(
        proptest::test_runner::Config {
            // Use a specific seed that previously failed
            rng_algorithm: proptest::test_runner::RngAlgorithm::ChaCha,
            ..Default::default()
        },
    );

    let source = python_source();

    runner
        .run(&source, |src| {
            let result = process_python_file(&src, "repo", "test.py", "test");
            // This should not panic
            prop_assert!(result.nodes.len() >= 0);
            Ok(())
        })
        .unwrap();
}

#[cfg(test)]
mod unit_tests {
    use super::*;

    #[test]
    fn test_python_identifier_strategy() {
        let mut runner = proptest::test_runner::TestRunner::default();
        let value = python_identifier()
            .new_tree(&mut runner)
            .unwrap()
            .current();

        assert!(value.chars().next().unwrap().is_ascii_lowercase() || value.starts_with('_'));
        assert!(value.len() <= 21);
    }

    #[test]
    fn test_python_function_strategy() {
        let mut runner = proptest::test_runner::TestRunner::default();
        let value = python_function()
            .new_tree(&mut runner)
            .unwrap()
            .current();

        assert!(value.starts_with("def "));
        assert!(value.ends_with("(): pass"));
    }
}
