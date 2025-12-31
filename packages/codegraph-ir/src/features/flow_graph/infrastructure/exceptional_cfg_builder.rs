//! Exceptional CFG Builder
//!
//! Constructs exceptional control flow graphs from IR with try/catch/finally support

use crate::features::flow_graph::domain::exceptional_cfg::{
    ExceptionEdgeKind, ExceptionHandler, ExceptionType, ExceptionalCFG, ExceptionalEdge,
    FinallyBlock, TryBlock,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};

/// Node ID type (alias for String)
type NodeId = String;
use std::collections::HashMap;

/// Exceptional CFG Builder
pub struct ExceptionalCFGBuilder {
    /// Current function ID
    function_id: String,

    /// ECFG being built
    ecfg: ExceptionalCFG,

    /// Node ID counter
    node_counter: usize,
}

impl ExceptionalCFGBuilder {
    /// Create new builder
    pub fn new(function_id: String) -> Self {
        Self {
            ecfg: ExceptionalCFG::new(function_id.clone()),
            function_id,
            node_counter: 0,
        }
    }

    /// Generate unique node ID
    fn next_node_id(&mut self) -> String {
        let id = format!("{}:ecfg:{}", self.function_id, self.node_counter);
        self.node_counter += 1;
        id
    }

    /// Build ECFG from IR nodes and edges
    pub fn build(mut self, nodes: &[Node], edges: &[Edge]) -> ExceptionalCFG {
        // Find all try-catch-finally constructs
        for node in nodes {
            match node.kind {
                NodeKind::Try => {
                    if let Some(try_block) = self.extract_try_block(node, nodes, edges) {
                        self.ecfg.add_try_block(try_block);
                    }
                }
                NodeKind::Raise | NodeKind::Throw => {
                    if let Some(exc_edge) = self.extract_throw_edge(node, nodes, edges) {
                        self.ecfg.add_exception_edge(exc_edge);
                    }
                }
                _ => {}
            }
        }

        // Build exception edges from normal CFG
        self.build_exception_edges(nodes, edges);

        self.ecfg
    }

    /// Extract try-catch-finally block
    fn extract_try_block(
        &mut self,
        try_node: &Node,
        nodes: &[Node],
        edges: &[Edge],
    ) -> Option<TryBlock> {
        let try_id = try_node.id.clone();

        // Find try body
        let try_entry = try_node.id.clone();
        let try_exit = self.next_node_id();

        // Find catch/except handlers
        let handlers = self.extract_handlers(try_node, nodes, edges);

        // Find finally block
        let finally_block = self.extract_finally_block(try_node, nodes, edges);

        // Normal exit after handlers/finally
        let normal_exit = self.next_node_id();

        Some(TryBlock {
            try_id,
            try_entry,
            try_exit,
            handlers,
            finally_block,
            normal_exit,
            span: try_node.span.clone(),
        })
    }

    /// Extract exception handlers (catch/except clauses)
    fn extract_handlers(
        &self,
        try_node: &Node,
        nodes: &[Node],
        edges: &[Edge],
    ) -> Vec<ExceptionHandler> {
        let mut handlers = Vec::new();

        // Find nodes connected with CATCHES edge
        for edge in edges {
            if edge.kind == EdgeKind::Catches && edge.source_id == try_node.id {
                if let Some(handler_node) = nodes.iter().find(|n| n.id == edge.target_id) {
                    if let Some(handler) = self.extract_handler(handler_node, nodes, edges) {
                        handlers.push(handler);
                    }
                }
            }
        }

        handlers
    }

    /// Extract single exception handler
    fn extract_handler(
        &self,
        handler_node: &Node,
        _nodes: &[Node],
        _edges: &[Edge],
    ) -> Option<ExceptionHandler> {
        // Extract caught exception types from node metadata
        let caught_types = self.extract_exception_types(handler_node);

        // Extract exception variable name from node.name
        // Note: metadata removed, using name field instead
        let exception_var = handler_node.name.clone();

        Some(ExceptionHandler {
            handler_id: handler_node.id.clone(),
            caught_types,
            body_entry: handler_node.id.clone(),
            exception_var,
            span: handler_node.span.clone(),
        })
    }

    /// Extract exception types from node
    fn extract_exception_types(&self, node: &Node) -> Vec<ExceptionType> {
        // Use node.annotations for exception types (metadata removed)
        // Parser should populate annotations with exception type info
        // if let Some(annotations) = &node.annotations {
        //     for ann in annotations {
        //         if ann.starts_with("catches:") {
        //             let exc_name = ann.trim_start_matches("catches:");
        //             types.push(ExceptionType {
        //                         exception_class: exc_name.to_string(),
        //                         language: node.language.clone(),
        //                         raise_span: None,
        //                     });
        //                 }
        //             }
        //         }
        //     }
        // }

        Vec::new()
    }

    /// Extract finally block
    fn extract_finally_block(
        &mut self,
        try_node: &Node,
        nodes: &[Node],
        edges: &[Edge],
    ) -> Option<FinallyBlock> {
        // Find node connected with FINALLY edge
        for edge in edges {
            if edge.kind == EdgeKind::Finally && edge.source_id == try_node.id {
                if let Some(finally_node) = nodes.iter().find(|n| n.id == edge.target_id) {
                    let entry = finally_node.id.clone();
                    let exit = self.next_node_id();

                    return Some(FinallyBlock {
                        block_id: finally_node.id.clone(),
                        entry,
                        exit,
                        span: finally_node.span.clone(),
                    });
                }
            }
        }

        None
    }

    /// Extract throw/raise edge
    fn extract_throw_edge(
        &self,
        raise_node: &Node,
        _nodes: &[Node],
        _edges: &[Edge],
    ) -> Option<ExceptionalEdge> {
        // Extract exception type from raise/throw node
        let exception_type = self.extract_raised_exception_type(raise_node);

        // Find target (handler or propagate)
        let to = self.find_exception_target(raise_node);

        Some(ExceptionalEdge {
            from: raise_node.id.clone(),
            to,
            kind: ExceptionEdgeKind::Throw,
            exception_type,
        })
    }

    /// Extract exception type being raised
    fn extract_raised_exception_type(&self, node: &Node) -> Option<ExceptionType> {
        // Use node.name for exception type (e.g., "raise ValueError")
        // Parser extracts exception class name into node.name
        let exception_class = node.name.clone().unwrap_or_else(|| "Exception".to_string());

        Some(ExceptionType {
            exception_class,
            language: node.language.clone(),
            raise_span: Some(node.span.clone()),
        })
    }

    /// Find exception target (handler or propagate)
    fn find_exception_target(&self, _raise_node: &Node) -> NodeId {
        // Exception propagation: requires try-except scope tracking
        // Current: Conservative - propagate to function boundary
        "exception_propagate".to_string()
    }

    /// Build exception edges from CFG
    fn build_exception_edges(&mut self, nodes: &[Node], edges: &[Edge]) {
        // For each node that can throw, create exception edges to handlers
        for node in nodes {
            if self.can_node_throw(node) {
                self.add_exception_edges_for_node(node, nodes, edges);
            }
        }
    }

    /// Check if node can throw exception
    fn can_node_throw(&self, node: &Node) -> bool {
        matches!(
            node.kind,
            NodeKind::Call | NodeKind::Raise | NodeKind::Throw | NodeKind::Assert | NodeKind::Index // Array access
        )
    }

    /// Add exception edges for a node
    fn add_exception_edges_for_node(&mut self, node: &Node, _nodes: &[Node], _edges: &[Edge]) {
        // Find enclosing try block and collect data before mutating
        let edges_to_add: Vec<ExceptionalEdge> =
            if let Some(try_id) = self.ecfg.node_to_try_block.get(&node.id) {
                if let Some(try_block) = self.ecfg.try_blocks.iter().find(|t| &t.try_id == try_id) {
                    let mut edges = Vec::new();

                    // Add edges to each handler
                    for handler in &try_block.handlers {
                        edges.push(ExceptionalEdge {
                            from: node.id.clone(),
                            to: handler.body_entry.clone(),
                            kind: ExceptionEdgeKind::Catch,
                            exception_type: None, // Will be refined by type analysis
                        });
                    }

                    // Add edge to finally if present
                    if let Some(finally) = &try_block.finally_block {
                        edges.push(ExceptionalEdge {
                            from: node.id.clone(),
                            to: finally.entry.clone(),
                            kind: ExceptionEdgeKind::Finally,
                            exception_type: None,
                        });
                    }

                    edges
                } else {
                    Vec::new()
                }
            } else {
                Vec::new()
            };

        // Now add all edges
        for edge in edges_to_add {
            self.ecfg.add_exception_edge(edge);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builder_creation() {
        let builder = ExceptionalCFGBuilder::new("test_func".to_string());
        assert_eq!(builder.function_id, "test_func");
    }

    #[test]
    fn test_can_node_throw() {
        let builder = ExceptionalCFGBuilder::new("test".to_string());

        let call_node = Node::new(
            "call1".to_string(),
            NodeKind::Call,
            "func()".to_string(),
            "test.py".to_string(),
            Span::default(),
        );

        assert!(builder.can_node_throw(&call_node));

        let assign_node = Node::new(
            "assign1".to_string(),
            NodeKind::Variable,
            "x = 1".to_string(),
            "test.py".to_string(),
            Span::default(),
        );

        assert!(!builder.can_node_throw(&assign_node));
    }

    #[test]
    fn test_build_empty() {
        let builder = ExceptionalCFGBuilder::new("test_func".to_string());
        let ecfg = builder.build(&[], &[]);

        assert_eq!(ecfg.try_blocks.len(), 0);
        assert_eq!(ecfg.exception_edges.len(), 0);
    }
}
