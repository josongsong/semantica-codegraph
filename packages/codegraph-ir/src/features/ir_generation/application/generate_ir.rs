use crate::features::ir_generation::domain::IRDocument;
use crate::features::ir_generation::ports::IRGenerator;
use crate::features::parsing::domain::ParsedTree;
use crate::shared::models::Result;

pub struct GenerateIRUseCase<G: IRGenerator> {
    generator: G,
}

impl<G: IRGenerator> GenerateIRUseCase<G> {
    pub fn new(generator: G) -> Self {
        Self { generator }
    }

    pub fn execute(&self, tree: &ParsedTree, repo_id: &str) -> Result<IRDocument> {
        self.generator.generate(tree, repo_id)
    }
}
