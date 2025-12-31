use crate::features::data_flow::domain::DataFlowGraph;
use crate::features::ir_generation::domain::IRDocument;
use crate::features::ssa::domain::SSAGraph;
use crate::shared::models::Result;

pub trait SSABuilder: Send + Sync {
    fn build_ssa(&self, ir: &IRDocument, dfg: &[DataFlowGraph]) -> Result<Vec<SSAGraph>>;
}
