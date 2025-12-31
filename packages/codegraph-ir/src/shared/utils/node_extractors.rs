//! Node Extraction Utilities
//!
//! SOTA Design: DRY principle applied to common node extraction patterns.
//! This eliminates code duplication across stage executors.
//!
//! # Purpose
//!
//! This module provides shared utilities for extracting information from IR nodes and edges.
//! These functions are used by multiple pipeline stages ([`processor.rs`], [`stages_executor.rs`])
//! to avoid code duplication and maintain a single source of truth.
//!
//! # Architecture Benefits
//!
//! - **DRY Principle**: Eliminates ~200 LOC of duplicated extraction logic
//! - **Single Source of Truth**: All extraction logic lives in one place
//! - **Zero Circular Dependencies**: Shared utilities break pipeline ⇄ features cycles
//! - **Type Safety**: All functions are `#[must_use]` for compiler-enforced usage
//! - **Performance**: Zero-cost abstractions with no runtime overhead
//!
//! # Functions
//!
//! - [`extract_variables_for_function`] - Extract variable definitions for a function
//! - [`extract_variables_for_ssa`] - Extract variables with block mapping for SSA
//! - [`extract_variable_uses`] - Extract variable uses from READS edges
//! - [`find_function_by_name`] - Find function node by name
//!
//! # Example
//!
//! ```ignore
//! use codegraph_ir::shared::utils::{find_function_by_name, extract_variables_for_function};
//!
//! // Find a function by name
//! let func = find_function_by_name(&nodes, "my_function").unwrap();
//!
//! // Extract all variable definitions in that function
//! let variables = extract_variables_for_function(&nodes, &func.id);
//!
//! // Extract variable uses from edges
//! let uses = extract_variable_uses(&edges, &func.id);
//! ```
//!
//! # Design Patterns
//!
//! This module follows Rust best practices:
//! - Iterator-based APIs for efficient processing
//! - Borrowing (`&str`) instead of ownership (`String`) where possible
//! - `#[must_use]` attributes on all pure functions
//! - Zero unsafe code

use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};

/// Extract variable definitions for a given function
///
/// Filters all nodes to find variables that are children of the specified function.
/// This is used by the Data Flow Graph (DFG) stage to identify variable definitions.
///
/// # Arguments
/// * `nodes` - All nodes in the IR
/// * `func_id` - The function ID to extract variables from
///
/// # Returns
/// Vector of (`variable_name`, `span`) tuples representing each variable definition
///
/// # Example
/// ```ignore
/// let variables = extract_variables_for_function(&nodes, "func_123");
/// // Returns: [("x", Span{...}), ("y", Span{...})]
/// ```
#[must_use]
pub fn extract_variables_for_function(nodes: &[Node], func_id: &str) -> Vec<(String, Span)> {
    nodes
        .iter()
        .filter(|n| n.kind == NodeKind::Variable)
        .filter(|n| n.parent_id.as_deref() == Some(func_id))
        .map(|n| (n.name.clone().unwrap_or_default(), n.span))
        .collect()
}

/// Extract variable definitions with block mapping for SSA
///
/// Similar to [`extract_variables_for_function`] but maps variables to their basic block.
/// This is used by the Static Single Assignment (SSA) stage to build phi nodes and def-use chains.
///
/// # Arguments
/// * `nodes` - All nodes in the IR
/// * `func_id` - The function ID to extract variables from
/// * `block_id` - The block ID to map variables to (typically the entry block)
///
/// # Returns
/// Vector of (`variable_name`, `block_id`) tuples for SSA construction
///
/// # Example
/// ```ignore
/// let ssa_vars = extract_variables_for_ssa(&nodes, "func_123", "block_entry");
/// // Returns: [("x", "block_entry"), ("y", "block_entry")]
/// ```
#[must_use]
pub fn extract_variables_for_ssa(
    nodes: &[Node],
    func_id: &str,
    block_id: &str,
) -> Vec<(String, String)> {
    nodes
        .iter()
        .filter(|n| n.kind == NodeKind::Variable)
        .filter(|n| n.parent_id.as_deref() == Some(func_id))
        .map(|n| (n.name.clone().unwrap_or_default(), block_id.to_string()))
        .collect()
}

/// Extract variable uses from READS edges
///
/// Filters edges to find all READS relationships where the source is the specified function.
/// This identifies where a function reads/uses variables, which is essential for DFG analysis.
///
/// # Arguments
/// * `edges` - All edges in the IR
/// * `func_id` - The function ID to extract uses from
///
/// # Returns
/// Vector of (`target_id`, `span`) tuples representing variable uses
///
/// # Example
/// ```ignore
/// let uses = extract_variable_uses(&edges, "func_123");
/// // Returns: [("var_456", Span{line: 10, ...}), ("var_789", Span{line: 12, ...})]
/// ```
#[must_use]
pub fn extract_variable_uses(edges: &[Edge], func_id: &str) -> Vec<(String, Span)> {
    edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Reads && e.source_id == func_id)
        .filter_map(|e| e.span.map(|span| (e.target_id.clone(), span)))
        .collect()
}

/// Find function node by name
///
/// Searches for a function or method node with the specified name.
/// This is the primary entry point for pipeline stages that need to locate functions.
///
/// # Arguments
/// * `nodes` - All nodes in the IR
/// * `function_name` - The function name to search for
///
/// # Returns
/// `Option` containing the function node if found, `None` otherwise
///
/// # Example
/// ```ignore
/// let func = find_function_by_name(&nodes, "process_data");
/// if let Some(f) = func {
///     println!("Found function at {}", f.span.start_line);
/// }
/// ```
#[must_use]
pub fn find_function_by_name<'a>(nodes: &'a [Node], function_name: &str) -> Option<&'a Node> {
    nodes.iter().find(|n| {
        (n.kind == NodeKind::Function || n.kind == NodeKind::Method)
            && n.name.as_deref() == Some(function_name)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    // Test helper functions for cleaner test code
    fn create_test_node(
        id: &str,
        kind: NodeKind,
        name: Option<&str>,
        parent_id: Option<&str>,
    ) -> Node {
        Node {
            id: id.to_string(),
            kind,
            fqn: format!("test.{}", id),
            file_path: "test.py".to_string(),
            span: Span::new(0, 0, 0, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: name.map(String::from),
            module_path: None,
            parent_id: parent_id.map(String::from),
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }
    }

    fn create_test_edge(
        _id: &str,
        source_id: &str,
        target_id: &str,
        kind: EdgeKind,
        span: Option<Span>,
    ) -> Edge {
        Edge {
            source_id: source_id.to_string(),
            target_id: target_id.to_string(),
            kind,
            span,
            metadata: None,
            attrs: None,
        }
    }

    #[test]
    fn test_extract_variables_for_function() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("test_func"), None),
            create_test_node("var1", NodeKind::Variable, Some("x"), Some("func1")),
        ];

        let result = extract_variables_for_function(&nodes, "func1");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].0, "x");
    }

    #[test]
    fn test_find_function_by_name() {
        let nodes = vec![create_test_node(
            "func1",
            NodeKind::Function,
            Some("test_func"),
            None,
        )];

        let result = find_function_by_name(&nodes, "test_func");
        assert!(result.is_some());
        assert_eq!(result.unwrap().id, "func1");
    }

    #[test]
    fn test_extract_variable_uses() {
        let edges = vec![create_test_edge(
            "edge1",
            "func1",
            "var1",
            EdgeKind::Reads,
            Some(Span::new(2, 0, 2, 1)),
        )];

        let result = extract_variable_uses(&edges, "func1");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].0, "var1");
    }

    #[test]
    fn test_extract_variables_for_ssa_returns_correct_count() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("test_func"), None),
            create_test_node("var1", NodeKind::Variable, Some("x"), Some("func1")),
            create_test_node("var2", NodeKind::Variable, Some("y"), Some("func1")),
        ];

        let result = extract_variables_for_ssa(&nodes, "func1", "block_entry");
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn test_extract_variables_for_ssa_maps_to_block() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("test_func"), None),
            create_test_node("var1", NodeKind::Variable, Some("x"), Some("func1")),
        ];

        let result = extract_variables_for_ssa(&nodes, "func1", "block_entry");
        assert_eq!(result[0].0, "x");
        assert_eq!(result[0].1, "block_entry");
    }

    // Edge case tests
    #[test]
    fn test_extract_variables_empty_nodes() {
        let nodes: Vec<Node> = vec![];
        let result = extract_variables_for_function(&nodes, "func1");
        assert_eq!(result.len(), 0);
    }

    #[test]
    fn test_extract_variables_nonexistent_function() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("test_func"), None),
            create_test_node("var1", NodeKind::Variable, Some("x"), Some("func1")),
        ];
        let result = extract_variables_for_function(&nodes, "nonexistent");
        assert_eq!(result.len(), 0);
    }

    #[test]
    fn test_extract_variables_with_none_name() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("test_func"), None),
            create_test_node("var1", NodeKind::Variable, None, Some("func1")),
            create_test_node("var2", NodeKind::Variable, Some("y"), Some("func1")),
        ];
        let result = extract_variables_for_function(&nodes, "func1");
        assert_eq!(result.len(), 2);
        assert_eq!(result[0].0, ""); // None becomes empty string
        assert_eq!(result[1].0, "y");
    }

    #[test]
    fn test_find_function_multiple_functions() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("first"), None),
            create_test_node("func2", NodeKind::Function, Some("second"), None),
            create_test_node("func3", NodeKind::Method, Some("first"), None), // Same name, different kind
        ];
        let result = find_function_by_name(&nodes, "first");
        assert!(result.is_some());
        assert_eq!(result.unwrap().id, "func1"); // Returns first match
    }

    #[test]
    fn test_extract_variable_uses_empty_edges() {
        let edges: Vec<Edge> = vec![];
        let result = extract_variable_uses(&edges, "func1");
        assert_eq!(result.len(), 0);
    }

    #[test]
    fn test_extract_variable_uses_filters_reads_only() {
        let edges = vec![
            create_test_edge(
                "e1",
                "func1",
                "var1",
                EdgeKind::Reads,
                Some(Span::new(1, 0, 1, 1)),
            ),
            create_test_edge(
                "e2",
                "func1",
                "var2",
                EdgeKind::Writes,
                Some(Span::new(2, 0, 2, 1)),
            ),
        ];
        let result = extract_variable_uses(&edges, "func1");
        assert_eq!(result.len(), 1); // Only Reads edges
    }

    #[test]
    fn test_extract_variable_uses_returns_correct_targets() {
        let edges = vec![
            create_test_edge(
                "e1",
                "func1",
                "var1",
                EdgeKind::Reads,
                Some(Span::new(1, 0, 1, 1)),
            ),
            create_test_edge(
                "e3",
                "func1",
                "var3",
                EdgeKind::Reads,
                Some(Span::new(3, 0, 3, 1)),
            ),
        ];
        let result = extract_variable_uses(&edges, "func1");
        assert_eq!(result[0].0, "var1");
        assert_eq!(result[1].0, "var3");
    }

    #[test]
    fn test_extract_variables_filters_by_parent() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("first"), None),
            create_test_node("var1", NodeKind::Variable, Some("x"), Some("func1")),
            create_test_node("func2", NodeKind::Function, Some("second"), None),
            create_test_node("var2", NodeKind::Variable, Some("y"), Some("func2")),
        ];
        let result = extract_variables_for_function(&nodes, "func1");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].0, "x");
    }

    #[test]
    fn test_extract_variables_multiple_vars_same_function() {
        let nodes = vec![
            create_test_node("func1", NodeKind::Function, Some("first"), None),
            create_test_node("var1", NodeKind::Variable, Some("x"), Some("func1")),
            create_test_node("var3", NodeKind::Variable, Some("z"), Some("func1")),
        ];
        let result = extract_variables_for_function(&nodes, "func1");
        assert_eq!(result.len(), 2);
        assert_eq!(result[1].0, "z");
    }
}
