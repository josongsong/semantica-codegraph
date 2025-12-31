//! Test data builders
//!
//! This module provides builder patterns for creating test data structures.

use codegraph_ir::pipeline::ProcessResult;
use codegraph_ir::shared::models::node::Node;
use codegraph_ir::shared::models::edge::Edge;

/// Builder for ProcessResult
#[derive(Debug, Default)]
pub struct ProcessResultBuilder {
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    errors: Vec<String>,
}

impl ProcessResultBuilder {
    /// Create a new builder
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a node to the result
    pub fn with_node(mut self, node: Node) -> Self {
        self.nodes.push(node);
        self
    }

    /// Add multiple nodes
    pub fn with_nodes(mut self, nodes: Vec<Node>) -> Self {
        self.nodes.extend(nodes);
        self
    }

    /// Add an edge to the result
    pub fn with_edge(mut self, edge: Edge) -> Self {
        self.edges.push(edge);
        self
    }

    /// Add multiple edges
    pub fn with_edges(mut self, edges: Vec<Edge>) -> Self {
        self.edges.extend(edges);
        self
    }

    /// Add an error message
    pub fn with_error(mut self, error: String) -> Self {
        self.errors.push(error);
        self
    }

    /// Add multiple errors
    pub fn with_errors(mut self, errors: Vec<String>) -> Self {
        self.errors.extend(errors);
        self
    }

    /// Build the final ProcessResult
    pub fn build(self) -> ProcessResult {
        ProcessResult {
            nodes: self.nodes,
            edges: self.edges,
            errors: self.errors,
        }
    }
}

/// Builder for Node
#[derive(Debug)]
pub struct NodeBuilder {
    id: String,
    kind: String,
    name: String,
    fqn: String,
    file_path: String,
    start_line: usize,
    end_line: usize,
}

impl NodeBuilder {
    /// Create a new node builder with required fields
    pub fn new(id: String, kind: String, name: String) -> Self {
        Self {
            id: id.clone(),
            kind,
            name: name.clone(),
            fqn: name,
            file_path: String::new(),
            start_line: 0,
            end_line: 0,
        }
    }

    /// Set the FQN
    pub fn fqn(mut self, fqn: String) -> Self {
        self.fqn = fqn;
        self
    }

    /// Set the file path
    pub fn file_path(mut self, file_path: String) -> Self {
        self.file_path = file_path;
        self
    }

    /// Set the line range
    pub fn lines(mut self, start: usize, end: usize) -> Self {
        self.start_line = start;
        self.end_line = end;
        self
    }

    /// Build the final Node
    pub fn build(self) -> Node {
        Node {
            id: self.id,
            kind: self.kind,
            name: self.name,
            fqn: self.fqn,
            file_path: self.file_path,
            start_line: self.start_line,
            end_line: self.end_line,
            ..Default::default()
        }
    }
}

/// Builder for Edge
#[derive(Debug)]
pub struct EdgeBuilder {
    id: String,
    kind: String,
    source: String,
    target: String,
}

impl EdgeBuilder {
    /// Create a new edge builder
    pub fn new(kind: String, source: String, target: String) -> Self {
        let id = format!("{}_{}_to_{}", kind, source, target);
        Self {
            id,
            kind,
            source,
            target,
        }
    }

    /// Set custom ID
    pub fn id(mut self, id: String) -> Self {
        self.id = id;
        self
    }

    /// Build the final Edge
    pub fn build(self) -> Edge {
        Edge {
            id: self.id,
            kind: self.kind,
            source: self.source,
            target: self.target,
            ..Default::default()
        }
    }
}

/// Helper to create a simple function node
pub fn function_node(id: &str, name: &str) -> Node {
    NodeBuilder::new(id.to_string(), "function_definition".to_string(), name.to_string())
        .fqn(format!("module.{name}"))
        .build()
}

/// Helper to create a simple class node
pub fn class_node(id: &str, name: &str) -> Node {
    NodeBuilder::new(id.to_string(), "class_definition".to_string(), name.to_string())
        .fqn(format!("module.{name}"))
        .build()
}

/// Helper to create a method node
pub fn method_node(id: &str, class_name: &str, method_name: &str) -> Node {
    NodeBuilder::new(
        id.to_string(),
        "function_definition".to_string(),
        method_name.to_string(),
    )
    .fqn(format!("module.{class_name}.{method_name}"))
    .build()
}

/// Helper to create a call edge
pub fn call_edge(source_id: &str, target_id: &str) -> Edge {
    EdgeBuilder::new("call".to_string(), source_id.to_string(), target_id.to_string())
        .build()
}

/// Helper to create an import edge
pub fn import_edge(source_id: &str, target_id: &str) -> Edge {
    EdgeBuilder::new("import".to_string(), source_id.to_string(), target_id.to_string())
        .build()
}

/// Helper to create a contains edge (e.g., class contains method)
pub fn contains_edge(source_id: &str, target_id: &str) -> Edge {
    EdgeBuilder::new("contains".to_string(), source_id.to_string(), target_id.to_string())
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_result_builder() {
        let result = ProcessResultBuilder::new()
            .with_node(function_node("f1", "test_func"))
            .with_node(class_node("c1", "TestClass"))
            .with_edge(call_edge("f1", "c1"))
            .build();

        assert_eq!(result.nodes.len(), 2);
        assert_eq!(result.edges.len(), 1);
        assert_eq!(result.errors.len(), 0);
    }

    #[test]
    fn test_node_builder() {
        let node = NodeBuilder::new("n1".to_string(), "function".to_string(), "test".to_string())
            .fqn("module.test".to_string())
            .file_path("test.py".to_string())
            .lines(10, 20)
            .build();

        assert_eq!(node.id, "n1");
        assert_eq!(node.kind, "function");
        assert_eq!(node.name, "test");
        assert_eq!(node.fqn, "module.test");
        assert_eq!(node.file_path, "test.py");
        assert_eq!(node.start_line, 10);
        assert_eq!(node.end_line, 20);
    }

    #[test]
    fn test_edge_builder() {
        let edge = EdgeBuilder::new("call".to_string(), "n1".to_string(), "n2".to_string())
            .build();

        assert_eq!(edge.kind, "call");
        assert_eq!(edge.source, "n1");
        assert_eq!(edge.target, "n2");
    }

    #[test]
    fn test_helper_functions() {
        let func = function_node("f1", "my_func");
        assert_eq!(func.kind, "function_definition");
        assert_eq!(func.name, "my_func");
        assert_eq!(func.fqn, "module.my_func");

        let cls = class_node("c1", "MyClass");
        assert_eq!(cls.kind, "class_definition");
        assert_eq!(cls.name, "MyClass");

        let method = method_node("m1", "MyClass", "my_method");
        assert_eq!(method.fqn, "module.MyClass.my_method");

        let edge = call_edge("f1", "c1");
        assert_eq!(edge.kind, "call");
    }
}
