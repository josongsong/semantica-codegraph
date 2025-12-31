use crate::checkpoint::CheckpointManager;
use crate::dag::CacheKeyManager;
use crate::error::Result;
use crate::job::StageId;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use uuid::Uuid;

/// Stage context passed to handlers
#[derive(Clone)]
pub struct StageContext {
    pub job_id: Uuid,
    pub repo_id: String,
    pub snapshot_id: String,
    pub cache_keys: CacheKeyManager,
    pub checkpoint_mgr: std::sync::Arc<CheckpointManager>,
    /// Changed files (for incremental update mode)
    pub changed_files: Option<HashSet<PathBuf>>,
    /// Previous snapshot ID (for incremental delta)
    pub previous_snapshot_id: Option<String>,
}

/// Stage configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageConfig {
    pub parallel_workers: usize,
    pub batch_size: usize,
}

impl Default for StageConfig {
    fn default() -> Self {
        Self {
            parallel_workers: num_cpus::get() * 3 / 4, // 75% of cores
            batch_size: 100,
        }
    }
}

/// Stage input
pub struct StageInput {
    /// All files to process (full mode) or affected files (incremental mode)
    pub files: Vec<PathBuf>,
    /// Cached outputs from dependency stages
    pub cache: HashMap<String, Vec<u8>>,
    /// Stage configuration
    pub config: StageConfig,
    /// Incremental mode: only process changed + affected files
    pub incremental: bool,
    /// Changed files (subset of files) that triggered the update
    pub changed_files: Option<HashSet<PathBuf>>,
}

/// Stage output
pub struct StageOutput {
    pub cache_data: Vec<u8>, // Serialized output (bincode)
    pub metrics: StageMetrics,
}

/// Stage metrics
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct StageMetrics {
    pub files_processed: usize,
    pub nodes_created: usize,
    pub chunks_created: usize,
    pub duration_ms: u64,
    pub errors: Vec<String>,
}

/// Stage handler trait (pluggable stages)
#[async_trait]
pub trait StageHandler: Send + Sync {
    /// Stage identifier
    fn stage_id(&self) -> StageId;

    /// Can this stage be skipped? (e.g., cache hit)
    async fn can_skip(&self, _ctx: &StageContext) -> bool {
        false
    }

    /// Execute stage
    async fn execute(&self, input: StageInput, ctx: &mut StageContext) -> Result<StageOutput>;

    /// Get required cache keys from dependencies
    fn required_cache_keys(&self, _ctx: &StageContext) -> Vec<String> {
        vec![]
    }

    /// Output cache key
    fn output_cache_key(&self, ctx: &StageContext) -> String;
}

/// Pipeline orchestrator (placeholder, will be implemented with DAG execution)
pub struct PipelineOrchestrator {
    // Will be populated with DAG, checkpoint manager, etc.
}

impl PipelineOrchestrator {
    pub fn new() -> Self {
        Self {}
    }
}

impl Default for PipelineOrchestrator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stage_config_default() {
        let config = StageConfig::default();
        assert!(config.parallel_workers > 0);
        assert_eq!(config.batch_size, 100);
    }

    #[test]
    fn test_stage_metrics_default() {
        let metrics = StageMetrics::default();
        assert_eq!(metrics.files_processed, 0);
        assert_eq!(metrics.nodes_created, 0);
        assert_eq!(metrics.errors.len(), 0);
    }

    // Mock stage handler for testing
    struct MockStage {
        id: StageId,
    }

    #[async_trait]
    impl StageHandler for MockStage {
        fn stage_id(&self) -> StageId {
            self.id
        }

        async fn execute(&self, input: StageInput, _ctx: &mut StageContext) -> Result<StageOutput> {
            Ok(StageOutput {
                cache_data: vec![1, 2, 3],
                metrics: StageMetrics {
                    files_processed: input.files.len(),
                    nodes_created: 10,
                    chunks_created: 5,
                    duration_ms: 100,
                    errors: vec![],
                },
            })
        }

        fn output_cache_key(&self, ctx: &StageContext) -> String {
            ctx.cache_keys.key_for_stage(self.id)
        }
    }

    #[tokio::test]
    async fn test_mock_stage_execution() {
        let stage = MockStage { id: StageId::L1_IR };

        let checkpoint_mgr = std::sync::Arc::new(CheckpointManager::new_in_memory());
        let mut ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "repo1".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("repo1".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let input = StageInput {
            files: vec![PathBuf::from("test.py")],
            cache: HashMap::new(),
            config: StageConfig::default(),
            incremental: false,
            changed_files: None,
        };

        let output = stage.execute(input, &mut ctx).await.unwrap();

        assert_eq!(output.metrics.files_processed, 1);
        assert_eq!(output.metrics.nodes_created, 10);
        assert_eq!(output.cache_data, vec![1, 2, 3]);
    }

    #[tokio::test]
    async fn test_stage_output_cache_key() {
        let stage = MockStage { id: StageId::L1_IR };

        let checkpoint_mgr = std::sync::Arc::new(CheckpointManager::new_in_memory());
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
        assert_eq!(key, "ir:repo1:snap1");
    }
}
