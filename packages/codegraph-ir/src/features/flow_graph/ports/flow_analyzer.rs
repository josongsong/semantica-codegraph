use crate::features::flow_graph::domain::{BasicFlowGraph, CFGEdge};
use crate::features::ir_generation::domain::IRDocument;
use crate::shared::models::Result;

pub trait FlowAnalyzer: Send + Sync {
    fn build_bfg(&self, ir: &IRDocument) -> Result<Vec<BasicFlowGraph>>;
    fn build_cfg(&self, bfg: &[BasicFlowGraph]) -> Result<Vec<CFGEdge>>;
}
