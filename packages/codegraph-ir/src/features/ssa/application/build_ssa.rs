use crate::features::data_flow::domain::DataFlowGraph;
use crate::features::ir_generation::domain::IRDocument;
use crate::features::ssa::domain::SSAGraph;
use crate::features::ssa::ports::SSABuilder;
use crate::shared::models::Result;

pub struct BuildSSAUseCase<B: SSABuilder> {
    builder: B,
}

impl<B: SSABuilder> BuildSSAUseCase<B> {
    pub fn new(builder: B) -> Self {
        Self { builder }
    }

    pub fn execute(&self, ir: &IRDocument, dfg: &[DataFlowGraph]) -> Result<Vec<SSAGraph>> {
        self.builder.build_ssa(ir, dfg)
    }
}
