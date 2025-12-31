use crate::error::Result;
use crate::job::StageId;
use crate::pipeline::{StageContext, StageHandler, StageInput, StageMetrics, StageOutput};
use crate::stages::ir_stage::IRResult;
use async_trait::async_trait;
use codegraph_ir::features::chunking::{Chunk, ChunkBuilder, ChunkIdGenerator};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Instant;
use tracing::{info, warn};

/// Serializable chunk result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkResult {
    pub file_path: String,
    pub chunks: Vec<Chunk>,
    pub errors: Vec<String>,
}

/// Chunk Building Stage (L2) - Real ChunkBuilder integration
///
/// Uses codegraph-ir::ChunkBuilder for structural chunks
pub struct ChunkStage {
    repo_id: String,
}

impl ChunkStage {
    pub fn new(repo_id: String) -> Self {
        Self { repo_id }
    }
}

impl Default for ChunkStage {
    fn default() -> Self {
        Self::new("default-repo".to_string())
    }
}

#[async_trait]
impl StageHandler for ChunkStage {
    fn stage_id(&self) -> StageId {
        StageId::L2_Chunk
    }

    async fn execute(&self, input: StageInput, ctx: &mut StageContext) -> Result<StageOutput> {
        let start = Instant::now();

        // Incremental mode detection
        if input.incremental {
            info!(
                "ChunkStage: INCREMENTAL mode - processing {} affected files (changed: {})",
                input.files.len(),
                input.changed_files.as_ref().map(|c| c.len()).unwrap_or(0)
            );
        } else {
            info!(
                "ChunkStage: FULL mode - processing {} files with {} workers",
                input.files.len(),
                input.config.parallel_workers
            );
        }

        // Load IR cache from L1
        let ir_cache_key = ctx.cache_keys.ir_key();
        let ir_data = ctx
            .checkpoint_mgr
            .load_checkpoint(&ir_cache_key)
            .await?
            .ok_or_else(|| {
                crate::error::OrchestratorError::MissingDependency(format!(
                    "Missing IR cache: {}",
                    ir_cache_key
                ))
            })?;

        info!(
            "ChunkStage: Loaded {} bytes of IR data from L1",
            ir_data.len()
        );

        // Deserialize IR results from L1
        let ir_results: Vec<IRResult> = bincode::deserialize(&ir_data).map_err(|e| {
            crate::error::OrchestratorError::DeserializationError(format!(
                "Failed to deserialize IR data: {}",
                e
            ))
        })?;

        info!("ChunkStage: Deserialized {} IR results", ir_results.len());

        // Build chunks using real ChunkBuilder
        let results: Vec<ChunkResult> = ir_results
            .par_iter()
            .map(|ir_result| {
                // Create ChunkBuilder for this file
                let id_gen = ChunkIdGenerator::new(&self.repo_id);
                let mut builder = ChunkBuilder::new(id_gen);

                // Build structural chunks (repo → project → module → file)
                let (chunks, _chunk_to_ir, _chunk_to_graph) = builder.build(
                    &self.repo_id,
                    &ir_result.file_path,
                    "python",
                    Some(&ctx.snapshot_id),
                );

                ChunkResult {
                    file_path: ir_result.file_path.clone(),
                    chunks,
                    errors: vec![],
                }
            })
            .collect();

        // Collect results and count metrics
        let mut all_errors = Vec::new();
        let mut files_processed = 0;
        let mut chunks_created = 0;

        for result in &results {
            if result.errors.is_empty() {
                files_processed += 1;
            } else {
                all_errors.extend(result.errors.clone());
            }
            chunks_created += result.chunks.len();
        }

        let duration_ms = start.elapsed().as_millis() as u64;

        info!(
            "ChunkStage: Completed {} files, {} chunks in {}ms ({}  errors)",
            files_processed,
            chunks_created,
            duration_ms,
            all_errors.len()
        );

        // Serialize chunk results
        let cache_data = bincode::serialize(&results)?;

        Ok(StageOutput {
            cache_data,
            metrics: StageMetrics {
                files_processed,
                nodes_created: 0,
                chunks_created,
                duration_ms,
                errors: all_errors,
            },
        })
    }

    fn required_cache_keys(&self, ctx: &StageContext) -> Vec<String> {
        vec![ctx.cache_keys.ir_key()]
    }

    fn output_cache_key(&self, ctx: &StageContext) -> String {
        ctx.cache_keys.chunk_key()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checkpoint::CheckpointManager;
    use crate::dag::CacheKeyManager;
    use crate::pipeline::StageConfig;
    use std::path::PathBuf;
    use uuid::Uuid;

    #[tokio::test]
    async fn test_chunk_stage_creation() {
        let stage = ChunkStage::new("test-repo".to_string());
        assert_eq!(stage.stage_id(), StageId::L2_Chunk);
    }

    #[tokio::test]
    async fn test_chunk_stage_required_cache_keys() {
        let stage = ChunkStage::new("repo1".to_string());
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "repo1".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("repo1".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let keys = stage.required_cache_keys(&ctx);
        assert_eq!(keys.len(), 1);
        assert_eq!(keys[0], "ir:repo1:snap1");
    }

    #[tokio::test]
    async fn test_chunk_stage_output_cache_key() {
        let stage = ChunkStage::new("repo1".to_string());
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "repo1".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("repo1".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let key = stage.output_cache_key(&ctx);
        assert_eq!(key, "chunks:repo1:snap1");
    }
}
