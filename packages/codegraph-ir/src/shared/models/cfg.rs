//! Control Flow Graph types (moved from features/flow_graph/domain)
//!
//! These are shared types used across multiple features, so they belong in shared/models
//! to avoid circular dependencies.

use serde::{Deserialize, Serialize};
use crate::shared::models::Span;

/// CFG edge kind (control flow edge types)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CFGEdgeKind {
    /// Sequential execution (fall-through)
    Sequential,
    /// Alias for Sequential (backward compatibility)
    Normal,
    /// True branch of conditional
    TrueBranch,
    /// False branch of conditional
    FalseBranch,
    /// Loop back edge
    LoopBack,
    /// Loop exit edge
    LoopExit,
    /// Exception handler edge
    Exception,
    /// Finally block edge
    Finally,
}

/// CFG edge connecting two basic blocks
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CFGEdge {
    /// Source block ID
    pub source_block_id: String,
    /// Target block ID
    pub target_block_id: String,
    /// Edge kind
    pub kind: CFGEdgeKind,
}

/// CFG basic block
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CFGBlock {
    /// Unique block ID
    pub id: String,
    /// Statements in this block (string representation)
    pub statements: Vec<String>,
    /// Predecessor block IDs
    pub predecessors: Vec<String>,
    /// Successor block IDs
    pub successors: Vec<String>,
    /// Function this block belongs to
    pub function_node_id: Option<String>,
    /// Block kind (e.g., "entry", "exit", "normal")
    pub kind: Option<String>,
    /// Source code span
    pub span: Option<Span>,
    /// Variable IDs defined in this block
    pub defined_variable_ids: Vec<String>,
    /// Variable IDs used in this block
    pub used_variable_ids: Vec<String>,
}
