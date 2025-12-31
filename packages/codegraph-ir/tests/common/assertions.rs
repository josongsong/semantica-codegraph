//! Custom assertions for test verification
//!
//! This module provides domain-specific assertions for codegraph-ir testing.

use codegraph_ir::pipeline::ProcessResult;
use codegraph_ir::shared::models::node::Node;
use codegraph_ir::shared::models::edge::Edge;

/// Assert that ProcessResult has no errors
pub fn assert_no_errors(result: &ProcessResult) {
    assert!(
        result.errors.is_empty(),
        "Expected no errors, got: {:?}",
        result.errors
    );
}

/// Assert that ProcessResult has specific number of nodes
pub fn assert_node_count(result: &ProcessResult, expected: usize) {
    assert_eq!(
        result.nodes.len(),
        expected,
        "Expected {expected} nodes, got {}. Nodes: {:?}",
        result.nodes.len(),
        result.nodes.iter().map(|n| &n.kind).collect::<Vec<_>>()
    );
}

/// Assert that ProcessResult has at least N nodes
pub fn assert_min_node_count(result: &ProcessResult, min: usize) {
    assert!(
        result.nodes.len() >= min,
        "Expected at least {min} nodes, got {}",
        result.nodes.len()
    );
}

/// Assert that ProcessResult has specific number of edges
pub fn assert_edge_count(result: &ProcessResult, expected: usize) {
    assert_eq!(
        result.edges.len(),
        expected,
        "Expected {expected} edges, got {}",
        result.edges.len()
    );
}

/// Assert that ProcessResult contains a node of specific kind
pub fn assert_has_node(result: &ProcessResult, kind: &str) {
    assert!(
        result.nodes.iter().any(|n| n.kind == kind),
        "Expected node of kind '{kind}', available kinds: {:?}",
        result.nodes.iter().map(|n| &n.kind).collect::<Vec<_>>()
    );
}

/// Assert that ProcessResult contains a node with specific name
pub fn assert_has_node_with_name(result: &ProcessResult, kind: &str, name: &str) {
    assert!(
        result.nodes.iter().any(|n| n.kind == kind && n.name == name),
        "Expected node of kind '{kind}' with name '{name}', found: {:?}",
        result.nodes.iter()
            .filter(|n| n.kind == kind)
            .map(|n| &n.name)
            .collect::<Vec<_>>()
    );
}

/// Assert that ProcessResult contains an edge of specific kind
pub fn assert_has_edge(result: &ProcessResult, kind: &str) {
    assert!(
        result.edges.iter().any(|e| e.kind == kind),
        "Expected edge of kind '{kind}', available kinds: {:?}",
        result.edges.iter().map(|e| &e.kind).collect::<Vec<_>>()
    );
}

/// Assert that ProcessResult contains an edge between specific nodes
pub fn assert_has_edge_between(
    result: &ProcessResult,
    kind: &str,
    source_name: &str,
    target_name: &str,
) {
    let source_node = result.nodes.iter().find(|n| n.name == source_name);
    let target_node = result.nodes.iter().find(|n| n.name == target_name);

    assert!(source_node.is_some(), "Source node '{source_name}' not found");
    assert!(target_node.is_some(), "Target node '{target_name}' not found");

    let source_id = &source_node.unwrap().id;
    let target_id = &target_node.unwrap().id;

    assert!(
        result.edges.iter().any(|e| {
            e.kind == kind && e.source == *source_id && e.target == *target_id
        }),
        "Expected edge of kind '{kind}' from '{source_name}' to '{target_name}'"
    );
}

/// Assert that a node has specific properties
pub fn assert_node_properties(node: &Node, expected_kind: &str, expected_name: &str) {
    assert_eq!(node.kind, expected_kind, "Node kind mismatch");
    assert_eq!(node.name, expected_name, "Node name mismatch");
}

/// Assert that result contains nodes with all specified kinds
pub fn assert_has_all_node_kinds(result: &ProcessResult, kinds: &[&str]) {
    for kind in kinds {
        assert_has_node(result, kind);
    }
}

/// Assert that result contains no duplicate nodes
pub fn assert_no_duplicate_nodes(result: &ProcessResult) {
    let mut seen_ids = std::collections::HashSet::new();

    for node in &result.nodes {
        assert!(
            seen_ids.insert(&node.id),
            "Duplicate node ID found: {}",
            node.id
        );
    }
}

/// Assert that result contains no duplicate edges
pub fn assert_no_duplicate_edges(result: &ProcessResult) {
    let mut seen_edges = std::collections::HashSet::new();

    for edge in &result.edges {
        let edge_tuple = (&edge.kind, &edge.source, &edge.target);
        assert!(
            seen_edges.insert(edge_tuple),
            "Duplicate edge found: {:?}",
            edge
        );
    }
}

/// Assert that all edges reference valid nodes
pub fn assert_valid_edge_references(result: &ProcessResult) {
    let node_ids: std::collections::HashSet<_> =
        result.nodes.iter().map(|n| &n.id).collect();

    for edge in &result.edges {
        assert!(
            node_ids.contains(&edge.source),
            "Edge source '{}' references non-existent node",
            edge.source
        );
        assert!(
            node_ids.contains(&edge.target),
            "Edge target '{}' references non-existent node",
            edge.target
        );
    }
}

/// Assert that ProcessResult is well-formed (no duplicates, valid references)
pub fn assert_well_formed(result: &ProcessResult) {
    assert_no_errors(result);
    assert_no_duplicate_nodes(result);
    assert_no_duplicate_edges(result);
    assert_valid_edge_references(result);
}

/// Assert that a node exists with a specific FQN
pub fn assert_has_fqn(result: &ProcessResult, fqn: &str) {
    assert!(
        result.nodes.iter().any(|n| n.fqn == fqn),
        "Expected node with FQN '{fqn}', found: {:?}",
        result.nodes.iter().map(|n| &n.fqn).collect::<Vec<_>>()
    );
}

/// Assert that ProcessResult contains specific error message
pub fn assert_has_error(result: &ProcessResult, error_substring: &str) {
    assert!(
        result.errors.iter().any(|e| e.contains(error_substring)),
        "Expected error containing '{error_substring}', got: {:?}",
        result.errors
    );
}

/// Assert that two ProcessResults are equivalent (ignoring order)
pub fn assert_results_equivalent(result1: &ProcessResult, result2: &ProcessResult) {
    assert_eq!(result1.nodes.len(), result2.nodes.len(), "Node count mismatch");
    assert_eq!(result1.edges.len(), result2.edges.len(), "Edge count mismatch");

    // Check that all nodes in result1 exist in result2
    for node in &result1.nodes {
        assert!(
            result2.nodes.iter().any(|n| n.id == node.id && n.kind == node.kind),
            "Node not found in result2: {:?}",
            node
        );
    }

    // Check that all edges in result1 exist in result2
    for edge in &result1.edges {
        assert!(
            result2.edges.iter().any(|e| {
                e.kind == edge.kind && e.source == edge.source && e.target == edge.target
            }),
            "Edge not found in result2: {:?}",
            edge
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use codegraph_ir::shared::models::node::Node;

    fn create_test_result() -> ProcessResult {
        ProcessResult {
            nodes: vec![
                Node {
                    id: "node1".to_string(),
                    kind: "function".to_string(),
                    name: "test_func".to_string(),
                    fqn: "module.test_func".to_string(),
                    ..Default::default()
                },
            ],
            edges: vec![],
            errors: vec![],
        }
    }

    #[test]
    fn test_assert_node_count() {
        let result = create_test_result();
        assert_node_count(&result, 1);
    }

    #[test]
    #[should_panic(expected = "Expected 2 nodes")]
    fn test_assert_node_count_fails() {
        let result = create_test_result();
        assert_node_count(&result, 2);
    }

    #[test]
    fn test_assert_has_node() {
        let result = create_test_result();
        assert_has_node(&result, "function");
    }

    #[test]
    fn test_assert_has_fqn() {
        let result = create_test_result();
        assert_has_fqn(&result, "module.test_func");
    }
}
