use crate::features::data_flow::domain::DataFlowGraph;
use crate::features::data_flow::ports::DFGAnalyzer;
use crate::features::flow_graph::domain::BasicFlowGraph;
use crate::features::ir_generation::domain::IRDocument;
use crate::shared::models::Result;

pub struct BuildDFGUseCase<A: DFGAnalyzer> {
    analyzer: A,
}

impl<A: DFGAnalyzer> BuildDFGUseCase<A> {
    pub fn new(analyzer: A) -> Self {
        Self { analyzer }
    }

    pub fn execute(&self, ir: &IRDocument, bfg: &[BasicFlowGraph]) -> Result<Vec<DataFlowGraph>> {
        self.analyzer.build_dfg(ir, bfg)
    }
}
