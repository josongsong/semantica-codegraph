//! Lowering Domain - Port interface for L1→L2 transformation

use crate::shared::models::{Edge, Expression, ExpressionIR, Node, Result};

/// Expression Lowering Trait (Port)
///
/// Transforms Expression IR (L1) to Node/Edge IR (L2)
pub trait ExpressionLowering {
    /// Lower ExpressionIR to Node/Edge IR
    ///
    /// Returns (nodes, edges)
    fn lower(&self, expr_ir: &ExpressionIR) -> Result<(Vec<Node>, Vec<Edge>)>;

    /// Lower single expression to nodes
    fn lower_expression(&self, expr: &Expression) -> Result<Vec<Node>>;
}

/// Lowering Context (shared state during transformation)
pub struct LoweringContext {
    /// Next node ID
    pub next_node_id: usize,

    /// Next edge ID
    pub next_edge_id: usize,

    /// Expression ID → Node ID mapping
    pub expr_to_node: std::collections::HashMap<usize, String>,

    /// Accumulated nodes
    pub nodes: Vec<Node>,

    /// Accumulated edges
    pub edges: Vec<Edge>,

    /// Current function context
    pub current_function: Option<String>,
}

impl LoweringContext {
    pub fn new() -> Self {
        Self {
            next_node_id: 0,
            next_edge_id: 0,
            expr_to_node: std::collections::HashMap::new(),
            nodes: Vec::new(),
            edges: Vec::new(),
            current_function: None,
        }
    }

    /// Allocate next node ID
    pub fn next_node_id(&mut self) -> String {
        let id = format!("node_{}", self.next_node_id);
        self.next_node_id += 1;
        id
    }

    /// Allocate next edge ID
    pub fn next_edge_id(&mut self) -> String {
        let id = format!("edge_{}", self.next_edge_id);
        self.next_edge_id += 1;
        id
    }

    /// Register expression → node mapping
    pub fn register_mapping(&mut self, expr_id: usize, node_id: String) {
        self.expr_to_node.insert(expr_id, node_id);
    }

    /// Get node ID for expression
    pub fn get_node_id(&self, expr_id: usize) -> Option<&String> {
        self.expr_to_node.get(&expr_id)
    }

    /// Add node
    pub fn add_node(&mut self, node: Node) {
        self.nodes.push(node);
    }

    /// Add edge
    pub fn add_edge(&mut self, edge: Edge) {
        self.edges.push(edge);
    }
}

impl Default for LoweringContext {
    fn default() -> Self {
        Self::new()
    }
}
