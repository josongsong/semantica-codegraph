//! Basic Flow Graph domain model
use crate::shared::models::Span;

/// Block kind (matches Python BFGBlockKind exactly)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockKind {
    Entry,
    Exit,
    Statement,
    Condition,
    LoopHeader,
    Try,
    Catch,
    Finally,
    Suspend,
    Resume,
    Dispatcher,
    Yield,
    ResumeYield,
}

impl BlockKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            BlockKind::Entry => "Entry",
            BlockKind::Exit => "Exit",
            BlockKind::Statement => "Statement",
            BlockKind::Condition => "Condition",
            BlockKind::LoopHeader => "LoopHeader",
            BlockKind::Try => "Try",
            BlockKind::Catch => "Catch",
            BlockKind::Finally => "Finally",
            BlockKind::Suspend => "Suspend",
            BlockKind::Resume => "Resume",
            BlockKind::Dispatcher => "Dispatcher",
            BlockKind::Yield => "Yield",
            BlockKind::ResumeYield => "ResumeYield",
        }
    }
}

#[derive(Debug, Clone)]
pub struct BasicFlowBlock {
    pub id: String,
    pub kind: BlockKind,
    pub function_node_id: String,
    pub span: Span,
    pub statement_count: usize,
}

#[derive(Debug, Clone)]
pub struct BasicFlowGraph {
    pub id: String,
    pub function_id: String,
    pub entry_block_id: String,
    pub exit_block_id: String,
    pub blocks: Vec<BasicFlowBlock>,
    pub total_statements: usize,
}
