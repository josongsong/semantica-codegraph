//! Pipeline result types

use crate::features::data_flow::domain::DataFlowGraph;
use crate::features::flow_graph::domain::{BasicFlowGraph, CFGEdge};
use crate::features::ir_generation::domain::IRDocument;
use crate::features::ssa::domain::SSAGraph;
use crate::features::type_resolution::domain::TypeEntity;
use crate::shared::models::Occurrence;

#[derive(Debug, Clone)]
pub struct ProcessResult {
    pub ir: IRDocument,
    pub bfg: Vec<BasicFlowGraph>,
    pub cfg: Vec<CFGEdge>,
    pub types: Vec<TypeEntity>,
    pub dfg: Vec<DataFlowGraph>,
    pub ssa: Vec<SSAGraph>,
    /// 🚀 SOTA: Occurrences generated in L1 (when enable_occurrences=true)
    pub occurrences: Vec<Occurrence>,
}
