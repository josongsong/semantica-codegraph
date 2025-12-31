use crate::checkpoint::{Checkpoint, CheckpointManager};
use crate::dag::{CacheKeyManager, PipelineDAG, StageNode};
use crate::error::{ErrorCategory, OrchestratorError, Result};
use crate::job::{Job, JobState, JobStateMachine, StageId};
use crate::pipeline::{StageConfig, StageContext, StageHandler, StageInput, StageOutput};
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use tracing::{error, info, warn};
use uuid::Uuid;

/// Pipeline result (aggregated metrics from all stages)
#[derive(Debug, Clone, Default)]
pub struct PipelineResult {
    pub files_processed: usize,
    pub nodes_created: usize,
    pub chunks_created: usize,
    pub duration_ms: u64,
    pub errors: Vec<String>,
}

impl PipelineResult {
    pub fn merge_metrics(&mut self, metrics: &crate::pipeline::StageMetrics) {
        self.files_processed += metrics.files_processed;
        self.nodes_created += metrics.nodes_created;
        self.chunks_created += metrics.chunks_created;
        self.duration_ms += metrics.duration_ms;
        self.errors.extend(metrics.errors.clone());
    }
}

/// Pipeline orchestrator with DAG execution (inspired by semantica-task-engine)
pub struct PipelineOrchestrator {
    dag: Arc<PipelineDAG>,
    checkpoint_mgr: Arc<CheckpointManager>,
    stage_handlers: HashMap<StageId, Arc<dyn StageHandler>>,
    worker_id: String,
}

impl PipelineOrchestrator {
    /// Create a new orchestrator with default pipeline
    pub fn new(checkpoint_mgr: Arc<CheckpointManager>) -> Result<Self> {
        let dag = PipelineDAG::default_pipeline()?;

        Ok(Self {
            dag: Arc::new(dag),
            checkpoint_mgr,
            stage_handlers: HashMap::new(),
            worker_id: format!("worker-{}", Uuid::new_v4()),
        })
    }

    /// Create with custom DAG
    pub fn with_dag(dag: PipelineDAG, checkpoint_mgr: Arc<CheckpointManager>) -> Self {
        Self {
            dag: Arc::new(dag),
            checkpoint_mgr,
            stage_handlers: HashMap::new(),
            worker_id: format!("worker-{}", Uuid::new_v4()),
        }
    }

    /// Register a stage handler
    pub fn register_handler(&mut self, handler: Arc<dyn StageHandler>) {
        self.stage_handlers.insert(handler.stage_id(), handler);
    }

    /// Execute a job (main entry point)
    pub async fn execute_job(
        &self,
        mut job: Job,
        repo_path: PathBuf,
    ) -> Result<(Job, PipelineResult)> {
        let job_id = job.id;
        let start_time = Instant::now();

        info!(
            "Starting job {} for repo {} (snapshot: {})",
            job_id, job.repo_id, job.snapshot_id
        );

        // Print execution plan
        let plan = self.dag.execution_plan();
        info!("Execution plan:\n{}", plan);

        // Transition: QUEUED → RUNNING
        let mut state_machine = JobStateMachine::new(job);
        state_machine.start(self.worker_id.clone(), StageId::L1_IR)?;
        job = state_machine.into_job();

        // Get completed stages (for resume)
        let completed = self.checkpoint_mgr.completed_stages(job_id).await?;
        if !completed.is_empty() {
            info!(
                "Resuming from checkpoint - {} stages already completed: {:?}",
                completed.len(),
                completed
            );
        }

        // Execute DAG phases
        let result = self
            .run_dag(
                job_id,
                &job.repo_id,
                &job.snapshot_id,
                &completed,
                repo_path,
                &job,
            )
            .await;

        let elapsed = start_time.elapsed();

        // Update final state
        let final_job = match result {
            Ok(mut pipeline_result) => {
                pipeline_result.duration_ms = elapsed.as_millis() as u64;

                info!(
                    "Job {} completed successfully - processed {} files, created {} nodes, {} chunks in {}ms",
                    job_id,
                    pipeline_result.files_processed,
                    pipeline_result.nodes_created,
                    pipeline_result.chunks_created,
                    pipeline_result.duration_ms
                );

                let mut sm = JobStateMachine::new(job);
                sm.complete(pipeline_result.files_processed)?;
                let completed_job = sm.into_job();

                // Cleanup checkpoints on success
                self.checkpoint_mgr.delete_job_checkpoints(job_id).await?;

                (completed_job, pipeline_result)
            }
            Err(e) => {
                error!("Job {} failed: {}", job_id, e);

                // Convert to anyhow::Error for classification
                let anyhow_err: anyhow::Error = e.into();
                let error_category = self.classify_error(&anyhow_err);
                let failed_stage = self.get_current_stage_from_error(&anyhow_err);

                let mut sm = JobStateMachine::new(job);
                let retry_count = match &sm.job().state {
                    JobState::Failed { retry_count, .. } => *retry_count + 1,
                    _ => 0,
                };

                sm.fail(
                    anyhow_err.to_string(),
                    error_category,
                    failed_stage,
                    retry_count,
                )?;
                let failed_job = sm.into_job();

                let empty_result = PipelineResult {
                    duration_ms: elapsed.as_millis() as u64,
                    ..Default::default()
                };

                return Ok((failed_job, empty_result));
            }
        };

        Ok(final_job)
    }

    /// Execute DAG with parallel phases (like ParallelIndexingOrchestrator)
    async fn run_dag(
        &self,
        job_id: Uuid,
        repo_id: &str,
        snapshot_id: &str,
        completed: &HashSet<StageId>,
        repo_path: PathBuf,
        job: &Job,
    ) -> Result<PipelineResult> {
        let ctx = StageContext {
            job_id,
            repo_id: repo_id.to_string(),
            snapshot_id: snapshot_id.to_string(),
            cache_keys: CacheKeyManager::new(repo_id.to_string(), snapshot_id.to_string()),
            checkpoint_mgr: self.checkpoint_mgr.clone(),
            changed_files: job.changed_files.clone(),
            previous_snapshot_id: job.previous_snapshot_id.clone(),
        };

        // Log incremental mode
        if job.is_incremental() {
            info!(
                "Job {}: INCREMENTAL mode - {} changed files, previous snapshot: {}",
                job_id,
                job.changed_files.as_ref().unwrap().len(),
                job.previous_snapshot_id.as_ref().unwrap()
            );
        } else {
            info!("Job {}: FULL rebuild mode", job_id);
        }

        let mut overall_result = PipelineResult::default();

        // Execute each phase in order
        for (phase_idx, parallel_group) in self.dag.execution_order().iter().enumerate() {
            info!(
                "Job {}: Phase {} - {} stages{}",
                job_id,
                phase_idx + 1,
                parallel_group.len(),
                if parallel_group.len() > 1 {
                    " (parallel)"
                } else {
                    ""
                }
            );

            // Skip completed stages
            let to_execute: Vec<_> = parallel_group
                .iter()
                .filter(|id| !completed.contains(id))
                .copied()
                .collect();

            if to_execute.is_empty() {
                info!(
                    "Job {}: Phase {} already completed, skipping",
                    job_id,
                    phase_idx + 1
                );
                continue;
            }

            // Execute stages in parallel using tokio::spawn
            let mut tasks = Vec::new();
            for stage_id in &to_execute {
                let stage = self
                    .dag
                    .get_stage(*stage_id)
                    .ok_or_else(|| OrchestratorError::StageNotFound(format!("{:?}", stage_id)))?;

                let handler = self
                    .stage_handlers
                    .get(stage_id)
                    .ok_or_else(|| {
                        OrchestratorError::Config(format!(
                            "No handler registered for stage {:?}",
                            stage_id
                        ))
                    })?
                    .clone();

                let stage_ctx = ctx.clone();
                let stage_node = stage.clone();
                let repo_path_clone = repo_path.clone();

                tasks.push(tokio::spawn(async move {
                    Self::execute_stage(handler, stage_node, stage_ctx, repo_path_clone).await
                }));
            }

            // Wait for all parallel tasks (like asyncio.gather)
            let results = futures::future::join_all(tasks).await;

            // Check for failures (early exit like semantica-task-engine)
            for (i, task_result) in results.into_iter().enumerate() {
                let stage_id = to_execute[i];

                match task_result {
                    Ok(Ok(output)) => {
                        // Save checkpoint
                        let cache_key = ctx.cache_keys.key_for_stage(stage_id);
                        let checkpoint =
                            Checkpoint::new(job_id, stage_id, cache_key, output.cache_data.clone());

                        self.checkpoint_mgr.save_checkpoint(checkpoint).await?;

                        // Merge metrics
                        overall_result.merge_metrics(&output.metrics);

                        info!(
                            "Job {}: Stage {:?} completed - {} files, {} nodes in {}ms",
                            job_id,
                            stage_id,
                            output.metrics.files_processed,
                            output.metrics.nodes_created,
                            output.metrics.duration_ms
                        );
                    }
                    Ok(Err(e)) => {
                        error!("Job {}: Stage {:?} failed: {}", job_id, stage_id, e);
                        return Err(OrchestratorError::StageExecutionFailed(format!(
                            "Stage {:?}: {}",
                            stage_id, e
                        ))
                        .into());
                    }
                    Err(join_err) => {
                        error!(
                            "Job {}: Stage {:?} panicked: {}",
                            job_id, stage_id, join_err
                        );
                        return Err(OrchestratorError::StageExecutionFailed(format!(
                            "Stage {:?} panicked: {}",
                            stage_id, join_err
                        ))
                        .into());
                    }
                }
            }
        }

        Ok(overall_result)
    }

    /// Execute a single stage
    async fn execute_stage(
        handler: Arc<dyn StageHandler>,
        stage_node: StageNode,
        mut ctx: StageContext,
        repo_path: PathBuf,
    ) -> Result<StageOutput> {
        let stage_id = stage_node.id;
        info!("Executing stage: {} ({:?})", stage_node.name, stage_id);

        // Check if can skip
        if handler.can_skip(&ctx).await {
            info!("Stage {:?} skipped (cache hit)", stage_id);
            return Ok(StageOutput {
                cache_data: vec![],
                metrics: Default::default(),
            });
        }

        // Load dependency cache data
        let mut cache = HashMap::new();
        for dep_id in &stage_node.dependencies {
            let cache_key = ctx.cache_keys.key_for_stage(*dep_id);
            if let Some(data) = ctx.checkpoint_mgr.load_checkpoint(&cache_key).await? {
                cache.insert(cache_key.clone(), data);
                info!(
                    "Loaded dependency cache for {:?} ({} bytes)",
                    dep_id,
                    cache[&cache_key].len()
                );
            } else {
                warn!(
                    "Missing required cache: {} (dependency {:?})",
                    cache_key, dep_id
                );
                return Err(OrchestratorError::MissingDependency(format!(
                    "Cache not found for dependency {:?}: {}",
                    dep_id, cache_key
                ))
                .into());
            }
        }

        // Enumerate files (TODO: make this configurable)
        let files = Self::enumerate_files(&repo_path)?;
        info!("Found {} files to process", files.len());

        // Build input
        let input = StageInput {
            files,
            cache,
            config: StageConfig::default(),
            incremental: ctx.changed_files.is_some(),
            changed_files: ctx.changed_files.clone(),
        };

        // Execute with timeout
        let timeout = tokio::time::Duration::from_millis(stage_node.timeout_ms);
        let result = tokio::time::timeout(timeout, handler.execute(input, &mut ctx)).await;

        match result {
            Ok(Ok(output)) => Ok(output),
            Ok(Err(e)) => Err(e),
            Err(_) => Err(OrchestratorError::Timeout(format!(
                "Stage {:?} timed out after {}ms",
                stage_id, stage_node.timeout_ms
            ))
            .into()),
        }
    }

    /// Enumerate files in repository (simple implementation)
    fn enumerate_files(repo_path: &PathBuf) -> Result<Vec<PathBuf>> {
        let mut files = Vec::new();

        if !repo_path.exists() {
            return Err(OrchestratorError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("Repository path not found: {}", repo_path.display()),
            ))
            .into());
        }

        // Simple recursive file enumeration (TODO: use gitignore, file filters)
        fn visit_dirs(dir: &PathBuf, files: &mut Vec<PathBuf>) -> std::io::Result<()> {
            if dir.is_dir() {
                for entry in std::fs::read_dir(dir)? {
                    let entry = entry?;
                    let path = entry.path();

                    if path.is_dir() {
                        // Skip hidden directories
                        if let Some(name) = path.file_name() {
                            if name.to_string_lossy().starts_with('.') {
                                continue;
                            }
                        }
                        visit_dirs(&path, files)?;
                    } else if path.extension().map_or(false, |ext| ext == "py") {
                        files.push(path);
                    }
                }
            }
            Ok(())
        }

        visit_dirs(repo_path, &mut files)?;
        files.sort();
        Ok(files)
    }

    /// Classify error for retry logic (from semantica-task-engine)
    fn classify_error(&self, error: &anyhow::Error) -> ErrorCategory {
        let error_str = error.to_string();

        if error_str.contains("timeout") || error_str.contains("connection") {
            ErrorCategory::Transient
        } else if error_str.contains("OOM") || error_str.contains("out of memory") {
            ErrorCategory::Infrastructure
        } else if error_str.contains("parse error") || error_str.contains("invalid") {
            ErrorCategory::Permanent
        } else {
            ErrorCategory::Transient // Default to retry
        }
    }

    /// Get current stage from error message
    fn get_current_stage_from_error(&self, error: &anyhow::Error) -> StageId {
        let error_str = error.to_string();

        // Try to extract stage from error message
        if error_str.contains("L1_IR") || error_str.contains("IR") {
            StageId::L1_IR
        } else if error_str.contains("L2_Chunk") || error_str.contains("Chunk") {
            StageId::L2_Chunk
        } else if error_str.contains("L3_Lexical") || error_str.contains("Lexical") {
            StageId::L3_Lexical
        } else if error_str.contains("L4_Vector") || error_str.contains("Vector") {
            StageId::L4_Vector
        } else {
            StageId::L1_IR // Default
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipeline::StageMetrics;
    use async_trait::async_trait;

    // Mock stage handler for testing
    struct MockHandler {
        id: StageId,
        should_fail: bool,
    }

    #[async_trait]
    impl StageHandler for MockHandler {
        fn stage_id(&self) -> StageId {
            self.id
        }

        async fn execute(&self, input: StageInput, _ctx: &mut StageContext) -> Result<StageOutput> {
            if self.should_fail {
                return Err(
                    OrchestratorError::StageExecutionFailed("Mock failure".to_string()).into(),
                );
            }

            // Simulate processing
            tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;

            Ok(StageOutput {
                cache_data: bincode::serialize(&input.files).unwrap(),
                metrics: StageMetrics {
                    files_processed: input.files.len(),
                    nodes_created: input.files.len() * 10,
                    chunks_created: input.files.len() * 5,
                    duration_ms: 10,
                    errors: vec![],
                },
            })
        }

        fn output_cache_key(&self, ctx: &StageContext) -> String {
            ctx.cache_keys.key_for_stage(self.id)
        }
    }

    #[test]
    fn test_orchestrator_creation() {
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let orch = PipelineOrchestrator::new(checkpoint_mgr);
        assert!(orch.is_ok());
    }

    #[test]
    fn test_error_classification() {
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let orch = PipelineOrchestrator::new(checkpoint_mgr).unwrap();

        let timeout_err = anyhow::anyhow!("timeout occurred");
        assert_eq!(orch.classify_error(&timeout_err), ErrorCategory::Transient);

        let oom_err = anyhow::anyhow!("OOM: out of memory");
        assert_eq!(orch.classify_error(&oom_err), ErrorCategory::Infrastructure);

        let parse_err = anyhow::anyhow!("parse error: invalid syntax");
        assert_eq!(orch.classify_error(&parse_err), ErrorCategory::Permanent);
    }

    #[tokio::test]
    async fn test_execute_stage_success() {
        let handler = Arc::new(MockHandler {
            id: StageId::L1_IR,
            should_fail: false,
        });

        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "test".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("test".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let stage_node = StageNode::new(StageId::L1_IR, "Test", vec![], false, 5000);

        let repo_path = std::env::temp_dir().join("test_repo");
        std::fs::create_dir_all(&repo_path).unwrap();

        let result =
            PipelineOrchestrator::execute_stage(handler, stage_node, ctx, repo_path.clone()).await;

        std::fs::remove_dir_all(&repo_path).ok();

        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_pipeline_result_merge() {
        let mut result = PipelineResult::default();

        let metrics = StageMetrics {
            files_processed: 10,
            nodes_created: 100,
            chunks_created: 50,
            duration_ms: 1000,
            errors: vec!["error1".to_string()],
        };

        result.merge_metrics(&metrics);

        assert_eq!(result.files_processed, 10);
        assert_eq!(result.nodes_created, 100);
        assert_eq!(result.chunks_created, 50);
        assert_eq!(result.duration_ms, 1000);
        assert_eq!(result.errors.len(), 1);
    }
}
