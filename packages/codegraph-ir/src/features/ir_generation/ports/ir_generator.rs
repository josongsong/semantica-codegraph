use crate::features::ir_generation::domain::IRDocument;
use crate::features::parsing::domain::ParsedTree;
use crate::shared::models::Result;

pub trait IRGenerator: Send + Sync {
    fn generate(&self, tree: &ParsedTree, repo_id: &str) -> Result<IRDocument>;
}
