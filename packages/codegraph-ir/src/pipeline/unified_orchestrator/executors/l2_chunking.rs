//! L2: Chunking Executor
//!
//! Creates hierarchical searchable chunks from IR nodes.

use super::base::{StageExecutor, StageResult};
use super::context::PipelineContext;
use super::super::memory::ChunkData;
use crate::pipeline::dag::StageId;
use crate::shared::models::{CodegraphError, NodeKind};
use std::time::Instant;

/// L2: Chunking Executor
pub struct ChunkingExecutor {
    /// Minimum chunk size (lines)
    min_chunk_size: usize,
    /// Maximum chunk size (lines)
    max_chunk_size: usize,
}

impl ChunkingExecutor {
    pub fn new() -> Self {
        Self {
            min_chunk_size: 10,
            max_chunk_size: 500,
        }
    }

    pub fn with_config(min_chunk_size: usize, max_chunk_size: usize) -> Self {
        Self {
            min_chunk_size,
            max_chunk_size,
        }
    }
}

impl StageExecutor for ChunkingExecutor {
    fn stage_id(&self) -> StageId {
        StageId::L2Chunking
    }

    fn execute(&self, context: &mut PipelineContext) -> Result<StageResult, CodegraphError> {
        let start = Instant::now();

        eprintln!("[L2] Starting Chunking");

        // Get nodes from L1 (Arc reference, zero-copy!)
        let nodes = context.get_nodes()?;

        eprintln!("[L2] Processing {} nodes", nodes.len());

        // Build chunks from nodes
        let mut chunks = Vec::new();

        for node in nodes.iter() {
            // Create chunks for functions and classes
            match node.kind {
                NodeKind::Function | NodeKind::Class => {
                    let chunk_size = node.span.end_line - node.span.start_line;

                    // Skip too small or too large chunks (convert to u32 for comparison)
                    if chunk_size < self.min_chunk_size as u32 || chunk_size > self.max_chunk_size as u32 {
                        continue;
                    }

                    let chunk = ChunkData {
                        id: format!("chunk:{}", node.id),
                        file_path: node.file_path.clone(),
                        content: format!(
                            "{}::{}",
                            node.kind.as_str(),
                            node.name.as_deref().unwrap_or(&node.fqn)
                        ), // Simplified content
                        start_line: node.span.start_line as usize,
                        end_line: node.span.end_line as usize,
                        chunk_type: node.kind.as_str().to_string(),
                        symbol_id: Some(node.id.clone()),
                    };

                    chunks.push(chunk);
                }
                _ => {
                    // Skip other node types for now
                }
            }
        }

        eprintln!("[L2] Created {} chunks", chunks.len());

        // Store in context
        context.set_chunks(chunks.clone());

        let duration = start.elapsed();

        Ok(StageResult::success(StageId::L2Chunking, duration, chunks.len()))
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
    fn test_l2_chunking() {
        let mut ctx = PipelineContext::new(
            std::path::PathBuf::from("/test"),
            "test-repo".to_string(),
        );

        // Create test nodes
        let nodes = vec![
            Node {
                id: "func1".to_string(),
                kind: NodeKind::Function,
                fqn: "test.func1".to_string(),
                file_path: "test.py".to_string(),
                language: "python".to_string(),
                span: Span {
                    start_line: 1,
                    end_line: 50,
                    start_col: 0,
                    end_col: 0,
                },
                name: Some("func1".to_string()),
                ..Default::default()
            },
            Node {
                id: "func2".to_string(),
                kind: NodeKind::Function,
                fqn: "test.func2".to_string(),
                file_path: "test.py".to_string(),
                language: "python".to_string(),
                span: Span {
                    start_line: 60,
                    end_line: 65,
                    start_col: 0,
                    end_col: 0,
                }, // Too small (5 lines)
                name: Some("func2".to_string()),
                ..Default::default()
            },
        ];

        ctx.set_nodes(nodes);
        ctx.mark_completed(StageId::L1IrBuild);

        // Execute L2
        let executor = ChunkingExecutor::new();
        let result = executor.execute(&mut ctx).unwrap();

        assert!(result.success);
        assert_eq!(result.items_processed, 1); // Only func1 (func2 too small)

        // Check chunks in context
        let chunks = ctx.get_chunks().unwrap();
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].chunk_type, "Function");
    }
}
