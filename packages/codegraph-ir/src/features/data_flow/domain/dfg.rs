//! Data Flow Graph domain model

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DFNodeKind {
    Definition,
    Use,
}

#[derive(Debug, Clone)]
pub struct DFNode {
    pub id: String,
    pub variable: String,
    pub kind: DFNodeKind,
    pub block_id: String,
}

#[derive(Debug, Clone)]
pub struct DataFlowGraph {
    pub function_id: String,
    pub nodes: Vec<DFNode>,
    pub def_use_edges: Vec<(String, String)>,
}
