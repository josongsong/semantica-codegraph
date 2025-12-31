use crate::features::data_flow::domain::DataFlowGraph;
use crate::features::flow_graph::domain::BasicFlowGraph;
use crate::features::ir_generation::domain::IRDocument;
use crate::shared::models::Result;

pub trait DFGAnalyzer: Send + Sync {
    fn build_dfg(&self, ir: &IRDocument, bfg: &[BasicFlowGraph]) -> Result<Vec<DataFlowGraph>>;
}
