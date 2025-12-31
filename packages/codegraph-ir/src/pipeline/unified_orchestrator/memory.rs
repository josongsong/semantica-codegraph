//! Arc-Based Memory Management
//!
//! Zero-copy memory sharing using Arc (Atomic Reference Counting).
//!
//! # Design
//!
//! All indexed data is wrapped in Arc for zero-copy sharing:
//! - Nodes: Arc<Vec<Node>>
//! - Edges: Arc<Vec<Edge>>
//! - Chunks: Arc<Vec<Chunk>>
//!
//! When you call `get_context()`, you get an Arc clone (8 bytes),
//! not a full data clone (potentially GB).

use crate::shared::models::{Node, Edge, Occurrence};
use std::sync::Arc;
use std::collections::HashMap;

/// Immutable graph context (Arc-wrapped for zero-copy sharing)
///
/// This is the main data structure returned by `get_context()`.
/// All fields are Arc-wrapped, so cloning this struct only copies pointers.
#[derive(Clone)]
pub struct GraphContext {
    /// All nodes in the graph (Arc-wrapped)
    pub nodes: Arc<Vec<Node>>,

    /// All edges in the graph (Arc-wrapped)
    pub edges: Arc<Vec<Edge>>,

    /// All occurrences (SCIP) (Arc-wrapped)
    pub occurrences: Arc<Vec<Occurrence>>,

    /// Chunks for semantic search (Arc-wrapped)
    pub chunks: Arc<Vec<ChunkData>>,

    /// Symbols for navigation (Arc-wrapped)
    pub symbols: Arc<Vec<SymbolData>>,

    /// Stage-specific results (Arc-wrapped)
    pub stage_data: Arc<HashMap<String, Arc<dyn std::any::Any + Send + Sync>>>,

    /// Repository metadata
    pub repo_name: String,
    pub repo_root: String,
}

impl GraphContext {
    /// Create new empty context
    pub fn new(repo_name: String, repo_root: String) -> Self {
        Self {
            nodes: Arc::new(Vec::new()),
            edges: Arc::new(Vec::new()),
            occurrences: Arc::new(Vec::new()),
            chunks: Arc::new(Vec::new()),
            symbols: Arc::new(Vec::new()),
            stage_data: Arc::new(HashMap::new()),
            repo_name,
            repo_root,
        }
    }

    /// Get node by ID
    pub fn get_node(&self, node_id: &str) -> Option<&Node> {
        self.nodes.iter().find(|n| n.id == node_id)
    }

    /// Get nodes by kind
    pub fn get_nodes_by_kind(&self, kind: &str) -> Vec<&Node> {
        self.nodes.iter().filter(|n| n.kind.as_str() == kind).collect()
    }

    /// Get outgoing edges from node
    pub fn get_outgoing_edges(&self, node_id: &str) -> Vec<&Edge> {
        self.edges.iter().filter(|e| e.source_id == node_id).collect()
    }

    /// Get incoming edges to node
    pub fn get_incoming_edges(&self, node_id: &str) -> Vec<&Edge> {
        self.edges.iter().filter(|e| e.target_id == node_id).collect()
    }

    /// Get stage-specific data
    pub fn get_stage_data<T: 'static + Send + Sync>(&self, key: &str) -> Option<Arc<T>> {
        self.stage_data.get(key)?
            .clone()
            .downcast::<T>()
            .ok()
    }
}

/// Handle to context (type alias for clarity)
pub type ContextHandle = Arc<GraphContext>;

/// Chunk data (simplified from full Chunk model)
#[derive(Debug, Clone)]
pub struct ChunkData {
    pub id: String,
    pub file_path: String,
    pub content: String,
    pub start_line: usize,
    pub end_line: usize,
    pub chunk_type: String,
    pub symbol_id: Option<String>,
}

/// Symbol data (for navigation)
#[derive(Debug, Clone)]
pub struct SymbolData {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub file_path: String,
    pub definition: (usize, usize), // (line, column)
    pub documentation: Option<String>,
}

/// Builder for GraphContext
pub struct GraphContextBuilder {
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    occurrences: Vec<Occurrence>,
    chunks: Vec<ChunkData>,
    symbols: Vec<SymbolData>,
    stage_data: HashMap<String, Arc<dyn std::any::Any + Send + Sync>>,
    repo_name: String,
    repo_root: String,
}

impl GraphContextBuilder {
    pub fn new(repo_name: String, repo_root: String) -> Self {
        Self {
            nodes: Vec::new(),
            edges: Vec::new(),
            occurrences: Vec::new(),
            chunks: Vec::new(),
            symbols: Vec::new(),
            stage_data: HashMap::new(),
            repo_name,
            repo_root,
        }
    }

    pub fn with_nodes(mut self, nodes: Vec<Node>) -> Self {
        self.nodes = nodes;
        self
    }

    pub fn with_edges(mut self, edges: Vec<Edge>) -> Self {
        self.edges = edges;
        self
    }

    pub fn with_occurrences(mut self, occurrences: Vec<Occurrence>) -> Self {
        self.occurrences = occurrences;
        self
    }

    pub fn with_chunks(mut self, chunks: Vec<ChunkData>) -> Self {
        self.chunks = chunks;
        self
    }

    pub fn with_symbols(mut self, symbols: Vec<SymbolData>) -> Self {
        self.symbols = symbols;
        self
    }

    pub fn with_stage_data<T: 'static + Send + Sync>(
        mut self,
        key: String,
        data: T,
    ) -> Self {
        self.stage_data.insert(key, Arc::new(data));
        self
    }

    pub fn build(self) -> GraphContext {
        GraphContext {
            nodes: Arc::new(self.nodes),
            edges: Arc::new(self.edges),
            occurrences: Arc::new(self.occurrences),
            chunks: Arc::new(self.chunks),
            symbols: Arc::new(self.symbols),
            stage_data: Arc::new(self.stage_data),
            repo_name: self.repo_name,
            repo_root: self.repo_root,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_arc_sharing() {
        let ctx = GraphContextBuilder::new("test".to_string(), "/test".to_string())
            .build();

        let handle1 = Arc::new(ctx);
        let handle2 = Arc::clone(&handle1);

        // Both handles point to same memory
        assert_eq!(Arc::strong_count(&handle1), 2);

        // Cloning GraphContext only copies Arc pointers
        let nodes_ref1 = Arc::clone(&handle1.nodes);
        let nodes_ref2 = Arc::clone(&handle2.nodes);

        assert_eq!(Arc::strong_count(&nodes_ref1), 4); // handle1.nodes + handle2.nodes + nodes_ref1 + nodes_ref2
    }

    #[test]
    fn test_context_builder() {
        use crate::shared::models::{Node, NodeKind, Span};

        let nodes = vec![
            Node {
                id: "node1".to_string(),
                kind: NodeKind::Function,
                fqn: "test.func".to_string(),
                file_path: "test.py".to_string(),
                language: "python".to_string(),
                span: Span { start_line: 1, end_line: 10, start_col: 0, end_col: 0 },
                name: Some("func".to_string()),
                ..Default::default()
            },
        ];

        let ctx = GraphContextBuilder::new("test".to_string(), "/test".to_string())
            .with_nodes(nodes.clone())
            .build();

        assert_eq!(ctx.nodes.len(), 1);
        assert_eq!(ctx.nodes[0].id, "node1");

        // Arc allows zero-copy access
        let nodes_ref = Arc::clone(&ctx.nodes);
        assert_eq!(nodes_ref.len(), 1);
    }
}
