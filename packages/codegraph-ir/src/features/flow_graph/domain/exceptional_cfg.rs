//! Exceptional Control Flow Graph
//!
//! Extends CFG with exception handling edges for try/catch/finally blocks.
//! Supports all languages: Python, Java, TypeScript, Kotlin, Rust, Go

use crate::shared::models::Span;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Node ID type (alias for String)
pub type NodeId = String;

/// Exception type information
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ExceptionType {
    /// Exception class name (e.g., "ValueError", "NullPointerException")
    pub exception_class: String,

    /// Source language
    pub language: String,

    /// Optional span where exception is raised/thrown
    pub raise_span: Option<Span>,
}

/// Exception handler (catch/except block)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExceptionHandler {
    /// Handler ID
    pub handler_id: String,

    /// Exception types caught (empty = catch all)
    pub caught_types: Vec<ExceptionType>,

    /// Handler body entry node
    pub body_entry: NodeId,

    /// Variable name for caught exception (if any)
    pub exception_var: Option<String>,

    /// Span of the handler
    pub span: Span,
}

/// Finally block
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FinallyBlock {
    /// Finally block ID
    pub block_id: String,

    /// Entry node of finally block
    pub entry: NodeId,

    /// Exit node of finally block
    pub exit: NodeId,

    /// Span of the finally block
    pub span: Span,
}

/// Try-catch-finally construct
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TryBlock {
    /// Try block ID
    pub try_id: String,

    /// Try body entry node
    pub try_entry: NodeId,

    /// Try body exit node
    pub try_exit: NodeId,

    /// Exception handlers (catch/except clauses)
    pub handlers: Vec<ExceptionHandler>,

    /// Optional finally block
    pub finally_block: Option<FinallyBlock>,

    /// Normal exit after all handlers/finally
    pub normal_exit: NodeId,

    /// Span of entire try-catch-finally
    pub span: Span,
}

/// Exception edge kind
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ExceptionEdgeKind {
    /// Normal control flow (no exception)
    Normal,

    /// Exception thrown
    Throw,

    /// Caught by handler
    Catch,

    /// Finally block entry (always executed)
    Finally,

    /// Re-throw after catch
    Rethrow,
}

/// Exceptional CFG edge
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExceptionalEdge {
    /// Source node
    pub from: NodeId,

    /// Target node
    pub to: NodeId,

    /// Edge kind
    pub kind: ExceptionEdgeKind,

    /// Exception type (for Throw/Catch edges)
    pub exception_type: Option<ExceptionType>,
}

/// Exceptional Control Flow Graph
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExceptionalCFG {
    /// Function/method ID
    pub function_id: String,

    /// All try-catch-finally blocks
    pub try_blocks: Vec<TryBlock>,

    /// Exception edges
    pub exception_edges: Vec<ExceptionalEdge>,

    /// Mapping from node to enclosing try block
    pub node_to_try_block: HashMap<NodeId, String>,
}

impl ExceptionalCFG {
    /// Create new exceptional CFG
    pub fn new(function_id: String) -> Self {
        Self {
            function_id,
            try_blocks: Vec::new(),
            exception_edges: Vec::new(),
            node_to_try_block: HashMap::new(),
        }
    }

    /// Add a try-catch-finally block
    pub fn add_try_block(&mut self, try_block: TryBlock) {
        self.try_blocks.push(try_block);
    }

    /// Add an exception edge
    pub fn add_exception_edge(&mut self, edge: ExceptionalEdge) {
        self.exception_edges.push(edge);
    }

    /// Get handlers for a given node
    pub fn get_handlers(&self, node_id: &NodeId) -> Vec<&ExceptionHandler> {
        if let Some(try_id) = self.node_to_try_block.get(node_id) {
            if let Some(try_block) = self.try_blocks.iter().find(|t| &t.try_id == try_id) {
                return try_block.handlers.iter().collect();
            }
        }
        Vec::new()
    }

    /// Get finally block for a given node
    pub fn get_finally_block(&self, node_id: &NodeId) -> Option<&FinallyBlock> {
        if let Some(try_id) = self.node_to_try_block.get(node_id) {
            if let Some(try_block) = self.try_blocks.iter().find(|t| &t.try_id == try_id) {
                return try_block.finally_block.as_ref();
            }
        }
        None
    }

    /// Check if node can throw exception
    pub fn can_throw(&self, node_id: &NodeId) -> bool {
        self.exception_edges
            .iter()
            .any(|e| &e.from == node_id && e.kind == ExceptionEdgeKind::Throw)
    }

    /// Get all uncaught exception types in function
    pub fn uncaught_exceptions(&self) -> Vec<ExceptionType> {
        let mut uncaught = Vec::new();

        for edge in &self.exception_edges {
            if edge.kind == ExceptionEdgeKind::Throw {
                if let Some(exc_type) = &edge.exception_type {
                    // Check if caught by any handler
                    let handlers = self.get_handlers(&edge.from);
                    let is_caught = handlers.iter().any(|h| {
                        h.caught_types.is_empty() || // Catch all
                        h.caught_types.iter().any(|t| t.exception_class == exc_type.exception_class)
                    });

                    if !is_caught {
                        uncaught.push(exc_type.clone());
                    }
                }
            }
        }

        uncaught
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exceptional_cfg_creation() {
        let mut ecfg = ExceptionalCFG::new("test_func".to_string());

        let try_block = TryBlock {
            try_id: "try1".to_string(),
            try_entry: "node1".to_string(),
            try_exit: "node2".to_string(),
            handlers: vec![],
            finally_block: None,
            normal_exit: "node3".to_string(),
            span: Span::default(),
        };

        ecfg.add_try_block(try_block);

        assert_eq!(ecfg.try_blocks.len(), 1);
        assert_eq!(ecfg.try_blocks[0].try_id, "try1");
    }

    #[test]
    fn test_exception_edge() {
        let edge = ExceptionalEdge {
            from: "node1".to_string(),
            to: "node2".to_string(),
            kind: ExceptionEdgeKind::Throw,
            exception_type: Some(ExceptionType {
                exception_class: "ValueError".to_string(),
                language: "Python".to_string(),
                raise_span: None,
            }),
        };

        assert_eq!(edge.kind, ExceptionEdgeKind::Throw);
        assert!(edge.exception_type.is_some());
    }

    #[test]
    fn test_uncaught_exceptions() {
        let mut ecfg = ExceptionalCFG::new("test_func".to_string());

        // Add throw edge
        let throw_edge = ExceptionalEdge {
            from: "node1".to_string(),
            to: "handler1".to_string(),
            kind: ExceptionEdgeKind::Throw,
            exception_type: Some(ExceptionType {
                exception_class: "RuntimeError".to_string(),
                language: "Python".to_string(),
                raise_span: None,
            }),
        };

        ecfg.add_exception_edge(throw_edge);

        let uncaught = ecfg.uncaught_exceptions();
        assert_eq!(uncaught.len(), 1);
        assert_eq!(uncaught[0].exception_class, "RuntimeError");
    }
}
