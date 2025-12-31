//! SSA Graph domain model

#[derive(Debug, Clone)]
pub struct SSAVariable {
    pub name: String,
    pub version: usize,
    pub def_block_id: String,
}

#[derive(Debug, Clone)]
pub struct PhiNode {
    pub variable: String,
    pub version: usize,
    pub predecessors: Vec<(String, usize)>, // (block_id, version)
}

#[derive(Debug, Clone)]
pub struct SSAGraph {
    pub function_id: String,
    pub variables: Vec<SSAVariable>,
    pub phi_nodes: Vec<PhiNode>,
}
