//! Control Flow Graph edges and blocks

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CFGEdgeKind {
    Sequential,
    Normal, // Alias for Sequential (backward compatibility)
    TrueBranch,
    FalseBranch,
    LoopBack,
    LoopExit,
    Exception,
    Finally,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CFGEdge {
    pub source_block_id: String,
    pub target_block_id: String,
    pub kind: CFGEdgeKind,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CFGBlock {
    pub id: String,
    pub statements: Vec<String>,
    pub predecessors: Vec<String>,
    pub successors: Vec<String>,
    pub function_node_id: Option<String>,
    pub kind: Option<String>,
    pub span: Option<crate::shared::models::Span>,
    pub defined_variable_ids: Vec<String>,
    pub used_variable_ids: Vec<String>,
}
