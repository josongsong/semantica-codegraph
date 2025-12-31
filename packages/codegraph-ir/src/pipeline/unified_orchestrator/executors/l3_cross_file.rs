//! L3: Cross-File Resolution Executor
//!
//! Resolves imports and cross-file references.

use super::base::{StageExecutor, StageResult};
use super::context::PipelineContext;
use crate::pipeline::dag::StageId;
use crate::shared::models::CodegraphError;
use std::time::Instant;

/// L3: Cross-File Resolution Executor
pub struct CrossFileExecutor {}

impl CrossFileExecutor {
    pub fn new() -> Self {
        Self {}
    }
}

impl StageExecutor for CrossFileExecutor {
    fn stage_id(&self) -> StageId {
        StageId::L3CrossFile
    }

    fn execute(&self, context: &mut PipelineContext) -> Result<StageResult, CodegraphError> {
        let start = Instant::now();

        eprintln!("[L3] Starting Cross-File Resolution");

        // Get nodes and edges (Arc references)
        let nodes = context.get_nodes()?;
        let edges = context.get_edges()?;

        eprintln!(
            "[L3] Processing {} nodes, {} edges",
            nodes.len(),
            edges.len()
        );

        // TODO: Implement cross-file resolution logic
        // For now, just validate dependencies are met

        let duration = start.elapsed();

        Ok(StageResult::success(StageId::L3CrossFile, duration, nodes.len()))
    }

    fn dependencies(&self) -> Vec<StageId> {
        vec![StageId::L1IrBuild]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{Node, NodeKind, Span};

    #[test]
    fn test_l3_cross_file() {
        let mut ctx = PipelineContext::new(
            std::path::PathBuf::from("/test"),
            "test-repo".to_string(),
        );

        let nodes = vec![Node {
            id: "node1".to_string(),
            kind: NodeKind::Module,
            fqn: "test.module".to_string(),
            file_path: "test.py".to_string(),
            language: "python".to_string(),
            span: Span::default(),
            ..Default::default()
        }];

        ctx.set_nodes(nodes);
        ctx.set_edges(vec![]);
        ctx.mark_completed(StageId::L1IrBuild);

        let executor = CrossFileExecutor::new();
        let result = executor.execute(&mut ctx).unwrap();

        assert!(result.success);
    }
}
