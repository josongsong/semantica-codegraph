use crate::dependency_graph::{compute_affected_files, ReverseDependencyIndex};
use crate::error::Result;
use crate::job::StageId;
use crate::pipeline::{StageContext, StageHandler, StageInput, StageMetrics, StageOutput};
use crate::stages::chunk_stage::ChunkResult;
use async_trait::async_trait;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use tracing::{info, warn};

/// Serializable vector embedding result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VectorResult {
    pub chunk_id: String,
    pub file_path: String,
    pub embedding_dim: usize,
    pub errors: Vec<String>,
}

/// Vector Indexing Stage (L4) - Qdrant embedded for semantic search
/// Depends on L2_Chunk (needs chunks for embedding)
pub struct VectorStage {
    repo_id: String,
}

impl VectorStage {
    pub fn new(repo_id: String) -> Self {
        Self { repo_id }
    }
}

impl Default for VectorStage {
    fn default() -> Self {
        Self::new("default-repo".to_string())
    }
}

#[async_trait]
impl StageHandler for VectorStage {
    fn stage_id(&self) -> StageId {
        StageId::L4_Vector
    }

    async fn execute(&self, input: StageInput, ctx: &mut StageContext) -> Result<StageOutput> {
        let start = Instant::now();

        // Load chunk cache from L2
        let chunk_cache_key = ctx.cache_keys.chunk_key();
        let chunk_data = ctx
            .checkpoint_mgr
            .load_checkpoint(&chunk_cache_key)
            .await?
            .ok_or_else(|| {
                crate::error::OrchestratorError::MissingDependency(format!(
                    "Missing chunk cache: {}",
                    chunk_cache_key
                ))
            })?;

        info!(
            "VectorStage: Loaded {} bytes of chunk data from L2",
            chunk_data.len()
        );

        // Deserialize chunk results
        let chunk_results: Vec<ChunkResult> = bincode::deserialize(&chunk_data).map_err(|e| {
            crate::error::OrchestratorError::DeserializationError(format!(
                "Failed to deserialize chunk data: {}",
                e
            ))
        })?;

        info!(
            "VectorStage: Deserialized {} chunk results",
            chunk_results.len()
        );

        // Incremental mode detection
        let (chunks_to_embed, previous_vectors): (Vec<ChunkResult>, Option<Vec<VectorResult>>) =
            if input.incremental {
                info!(
                    "VectorStage: INCREMENTAL mode - {} changed files",
                    input.changed_files.as_ref().map(|c| c.len()).unwrap_or(0)
                );

                // 1. Load previous vector results
                let prev_vectors = if let Some(prev_snapshot_id) = &ctx.previous_snapshot_id {
                    let prev_cache_key = format!("vector:{}:{}", ctx.repo_id, prev_snapshot_id);
                    match ctx.checkpoint_mgr.load_checkpoint(&prev_cache_key).await {
                        Ok(Some(data)) => match bincode::deserialize::<Vec<VectorResult>>(&data) {
                            Ok(results) => {
                                info!(
                                    "VectorStage: Loaded {} previous vector results",
                                    results.len()
                                );
                                Some(results)
                            }
                            Err(e) => {
                                warn!("VectorStage: Failed to deserialize previous vectors: {}", e);
                                None
                            }
                        },
                        _ => {
                            warn!("VectorStage: No previous vectors found, falling back to full rebuild");
                            None
                        }
                    }
                } else {
                    None
                };

                // 2. Compute affected chunks from changed files
                let changed_files = input.changed_files.as_ref().unwrap();
                let reverse_deps = ReverseDependencyIndex::new();
                let affected = compute_affected_files(changed_files, &reverse_deps);

                info!(
                    "VectorStage: Changed {} files → affects {} files",
                    changed_files.len(),
                    affected.len()
                );

                // 3. Filter chunks to re-embed (only affected files)
                let affected_chunks: Vec<ChunkResult> = chunk_results
                    .into_iter()
                    .filter(|chunk| {
                        let path = PathBuf::from(&chunk.file_path);
                        affected.contains(&path)
                    })
                    .collect();

                info!(
                    "VectorStage: Will embed {} affected chunks (from {} affected files)",
                    affected_chunks
                        .iter()
                        .map(|c| c.chunks.len())
                        .sum::<usize>(),
                    affected_chunks.len()
                );

                (affected_chunks, prev_vectors)
            } else {
                info!(
                    "VectorStage: FULL mode - embedding {} files with {} workers",
                    chunk_results.len(),
                    input.config.parallel_workers
                );
                (chunk_results, None)
            };

        // Process chunks in parallel for vector embedding
        let new_vectors: Vec<VectorResult> = chunks_to_embed
            .par_iter()
            .flat_map(|chunk_result| {
                // For each file's chunks, create vector results
                chunk_result
                    .chunks
                    .iter()
                    .map(|chunk| {
                        // TODO: Use actual embedding model (OpenAI, local model, etc.)
                        // For now, create placeholder 768-dim embedding
                        VectorResult {
                            chunk_id: chunk.id.clone(),
                            file_path: chunk_result.file_path.clone(),
                            embedding_dim: 768,
                            errors: vec![],
                        }
                    })
                    .collect::<Vec<_>>()
            })
            .collect();

        // 4. Merge with previous vectors (if incremental)
        let final_vectors: Vec<VectorResult> = if input.incremental && previous_vectors.is_some() {
            let prev_vectors = previous_vectors.unwrap();
            let affected_paths: HashSet<String> = chunks_to_embed
                .iter()
                .map(|c| c.file_path.clone())
                .collect();

            info!(
                "VectorStage: Merging {} new vectors with {} previous vectors",
                new_vectors.len(),
                prev_vectors.len()
            );

            // Keep previous vectors for unchanged files, use new vectors for affected files
            let mut merged = Vec::new();
            for prev in prev_vectors {
                if !affected_paths.contains(&prev.file_path) {
                    merged.push(prev);
                }
            }
            merged.extend(new_vectors);

            info!("VectorStage: Final merged vectors: {} chunks", merged.len());
            merged
        } else {
            new_vectors
        };

        // Collect results and count errors
        let mut errors = Vec::new();
        let files_processed = chunks_to_embed.len();
        let chunks_embedded = final_vectors.len();

        for result in &final_vectors {
            if !result.errors.is_empty() {
                errors.extend(result.errors.clone());
            }
        }

        let duration_ms = start.elapsed().as_millis() as u64;

        if input.incremental {
            info!(
                "VectorStage: INCREMENTAL - Embedded {} chunks from {} affected files, merged {} total chunks in {}ms ({} errors)",
                new_vectors.len(),
                chunks_to_embed.len(),
                final_vectors.len(),
                duration_ms,
                errors.len()
            );
        } else {
            info!(
                "VectorStage: FULL - Embedded {} files ({} chunks) in {}ms ({} errors)",
                files_processed,
                chunks_embedded,
                duration_ms,
                errors.len()
            );
        }

        // Serialize all vector data
        let cache_data = bincode::serialize(&final_vectors)?;

        Ok(StageOutput {
            cache_data,
            metrics: StageMetrics {
                files_processed,
                nodes_created: chunks_embedded,
                chunks_created: chunks_embedded,
                duration_ms,
                errors,
            },
        })
    }

    fn required_cache_keys(&self, ctx: &StageContext) -> Vec<String> {
        vec![ctx.cache_keys.chunk_key()]
    }

    fn output_cache_key(&self, ctx: &StageContext) -> String {
        ctx.cache_keys.vector_key()
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
    async fn test_vector_stage_creation() {
        let stage = VectorStage::new("test-repo".to_string());
        assert_eq!(stage.stage_id(), StageId::L4_Vector);
    }

    #[tokio::test]
    async fn test_vector_stage_required_cache_keys() {
        let stage = VectorStage::new("repo1".to_string());
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
        assert_eq!(keys[0], "chunks:repo1:snap1");
    }

    #[tokio::test]
    async fn test_vector_stage_output_cache_key() {
        let stage = VectorStage::new("repo1".to_string());
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
        assert_eq!(key, "vector:repo1:snap1");
    }
}
