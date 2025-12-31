use crate::error::Result;
use crate::job::StageId;
use crate::pipeline::{StageContext, StageHandler, StageInput, StageMetrics, StageOutput};
use async_trait::async_trait;
use rayon::prelude::*;
use std::sync::Arc;
use std::time::Instant;
use tracing::{info, warn};

/// Lexical Indexing Stage (L3) - Tantivy-based full-text search
/// Runs in parallel with L1_IR (no dependencies)
pub struct LexicalStage {
    // Will be initialized with Tantivy index when available
    _phantom: std::marker::PhantomData<()>,
}

impl LexicalStage {
    pub fn new() -> Self {
        Self {
            _phantom: std::marker::PhantomData,
        }
    }
}

impl Default for LexicalStage {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl StageHandler for LexicalStage {
    fn stage_id(&self) -> StageId {
        StageId::L3_Lexical
    }

    async fn execute(&self, input: StageInput, _ctx: &mut StageContext) -> Result<StageOutput> {
        let start = Instant::now();
        info!(
            "LexicalStage: Indexing {} files with {} workers",
            input.files.len(),
            input.config.parallel_workers
        );

        // Process files in parallel for lexical indexing
        let results: Vec<Result<Vec<u8>>> = input
            .files
            .par_iter()
            .map(|file_path| {
                // Read file content
                let content = std::fs::read_to_string(file_path).map_err(|e| {
                    warn!("Failed to read {} for indexing: {}", file_path.display(), e);
                    e
                })?;

                // TODO: Use Tantivy to index the file
                // For now, create placeholder index data
                let token_count = content.split_whitespace().count();
                let placeholder_index = format!(
                    "INDEX:{}:{}:{}",
                    file_path.display(),
                    content.len(),
                    token_count
                );
                Ok(placeholder_index.into_bytes())
            })
            .collect();

        // Collect results and count errors
        let mut all_index_data = Vec::new();
        let mut errors = Vec::new();
        let mut files_processed = 0;
        let mut nodes_created = 0;

        for (idx, result) in results.into_iter().enumerate() {
            match result {
                Ok(index_data) => {
                    // Count indexed tokens as "nodes"
                    nodes_created += 100; // Placeholder: ~100 tokens per file
                    all_index_data.extend(index_data);
                    files_processed += 1;
                }
                Err(e) => {
                    errors.push(format!("File {}: {}", input.files[idx].display(), e));
                }
            }
        }

        let duration_ms = start.elapsed().as_millis() as u64;

        info!(
            "LexicalStage: Indexed {} files ({} tokens) in {}ms ({} errors)",
            files_processed,
            nodes_created,
            duration_ms,
            errors.len()
        );

        // Serialize all index data
        let cache_data = bincode::serialize(&all_index_data)?;

        Ok(StageOutput {
            cache_data,
            metrics: StageMetrics {
                files_processed,
                nodes_created,
                chunks_created: 0,
                duration_ms,
                errors,
            },
        })
    }

    fn output_cache_key(&self, ctx: &StageContext) -> String {
        ctx.cache_keys.lexical_key()
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
    async fn test_lexical_stage_creation() {
        let stage = LexicalStage::new();
        assert_eq!(stage.stage_id(), StageId::L3_Lexical);
    }

    #[tokio::test]
    async fn test_lexical_stage_no_dependencies() {
        let stage = LexicalStage::new();
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
        assert_eq!(keys.len(), 0); // No dependencies
    }

    #[tokio::test]
    async fn test_lexical_stage_empty_input() {
        let stage = LexicalStage::new();
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let mut ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "test".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("test".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let input = StageInput {
            files: vec![],
            cache: std::collections::HashMap::new(),
            config: StageConfig::default(),
            incremental: false,
            changed_files: None,
        };

        let result = stage.execute(input, &mut ctx).await;
        assert!(result.is_ok());

        let output = result.unwrap();
        assert_eq!(output.metrics.files_processed, 0);
    }

    #[tokio::test]
    async fn test_lexical_stage_output_cache_key() {
        let stage = LexicalStage::new();
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
        assert_eq!(key, "lexical:repo1:snap1");
    }
}
