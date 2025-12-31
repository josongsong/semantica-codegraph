use crate::features::flow_graph::domain::{BasicFlowGraph, CFGEdge};
use crate::features::flow_graph::ports::FlowAnalyzer;
use crate::features::ir_generation::domain::IRDocument;
use crate::shared::models::Result;

pub struct FlowGraphResult {
    pub bfg: Vec<BasicFlowGraph>,
    pub cfg: Vec<CFGEdge>,
}

pub struct BuildFlowGraphsUseCase<A: FlowAnalyzer> {
    analyzer: A,
}

impl<A: FlowAnalyzer> BuildFlowGraphsUseCase<A> {
    pub fn new(analyzer: A) -> Self {
        Self { analyzer }
    }

    pub fn execute(&self, ir: &IRDocument) -> Result<FlowGraphResult> {
        let bfg = self.analyzer.build_bfg(ir)?;
        let cfg = self.analyzer.build_cfg(&bfg)?;
        Ok(FlowGraphResult { bfg, cfg })
    }
}
