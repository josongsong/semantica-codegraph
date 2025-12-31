//! Pipeline Execution State
//!
//! Tracks the progress and results of pipeline execution.

use crate::pipeline::dag::{PipelineDAG, StageId};
use super::memory::GraphContext;
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

/// Pipeline execution state
pub struct PipelineState {
    /// Current DAG (if pipeline is running)
    pub dag: Option<PipelineDAG>,

    /// Completed stages
    pub completed_stages: HashSet<StageId>,

    /// Stage results (cached for query/incremental updates)
    pub stage_results: HashMap<StageId, Arc<StageResultData>>,

    /// Repository metadata
    pub repo_root: PathBuf,
    pub repo_name: String,

    /// Main context (Arc-wrapped)
    pub context: Arc<GraphContext>,

    /// Indexing statistics
    pub stats: IndexingStats,

    /// Pipeline status
    pub status: PipelineStatus,
}

impl PipelineState {
    pub fn new(repo_root: PathBuf, repo_name: String) -> Self {
        let context = GraphContext::new(repo_name.clone(), repo_root.to_string_lossy().to_string());

        Self {
            dag: None,
            completed_stages: HashSet::new(),
            stage_results: HashMap::new(),
            repo_root: repo_root.clone(),
            repo_name: repo_name.clone(),
            context: Arc::new(context),
            stats: IndexingStats::new(),
            status: PipelineStatus::NotStarted,
        }
    }

    /// Check if stage is completed
    pub fn is_stage_completed(&self, stage_id: StageId) -> bool {
        self.completed_stages.contains(&stage_id)
    }

    /// Mark stage as completed
    pub fn mark_completed(&mut self, stage_id: StageId, result: Arc<StageResultData>) {
        self.completed_stages.insert(stage_id);
        self.stage_results.insert(stage_id, result);
    }

    /// Get stage result
    pub fn get_stage_result(&self, stage_id: StageId) -> Option<&Arc<StageResultData>> {
        self.stage_results.get(&stage_id)
    }

    /// Update context (replace with new Arc)
    pub fn update_context(&mut self, new_context: GraphContext) {
        self.context = Arc::new(new_context);
    }

    /// Get context handle (Arc clone)
    pub fn get_context(&self) -> Arc<GraphContext> {
        Arc::clone(&self.context)
    }
}

/// Pipeline execution status
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PipelineStatus {
    NotStarted,
    Running,
    Completed,
    Failed,
    PartiallyCompleted,
}

/// Indexing statistics
#[derive(Debug, Clone)]
pub struct IndexingStats {
    pub total_files: usize,
    pub total_nodes: usize,
    pub total_edges: usize,
    pub total_chunks: usize,
    pub total_symbols: usize,

    pub total_duration: Duration,
    pub l1_duration: Duration,

    pub stages_completed: usize,
    pub stages_failed: usize,

    pub files_processed: usize,
    pub files_failed: usize,

    pub loc_processed: usize,
}

impl IndexingStats {
    pub fn new() -> Self {
        Self {
            total_files: 0,
            total_nodes: 0,
            total_edges: 0,
            total_chunks: 0,
            total_symbols: 0,
            total_duration: Duration::from_secs(0),
            l1_duration: Duration::from_secs(0),
            stages_completed: 0,
            stages_failed: 0,
            files_processed: 0,
            files_failed: 0,
            loc_processed: 0,
        }
    }

    /// Calculate throughput (nodes/sec)
    pub fn throughput(&self) -> f64 {
        if self.total_duration.as_secs_f64() > 0.0 {
            self.total_nodes as f64 / self.total_duration.as_secs_f64()
        } else {
            0.0
        }
    }

    /// Calculate LOC/sec
    pub fn loc_per_second(&self) -> f64 {
        if self.total_duration.as_secs_f64() > 0.0 {
            self.loc_processed as f64 / self.total_duration.as_secs_f64()
        } else {
            0.0
        }
    }
}

/// Stage execution result data
///
/// Each stage can store its specific results here.
/// Using Arc<dyn Any> for type-safe downcasting.
pub struct StageResultData {
    /// Stage ID
    pub stage_id: StageId,

    /// Execution duration
    pub duration: Duration,

    /// Success status
    pub success: bool,

    /// Error message (if failed)
    pub error: Option<String>,

    /// Stage-specific data (type-erased, use downcast)
    pub data: Option<Arc<dyn std::any::Any + Send + Sync>>,
}

impl StageResultData {
    pub fn success(stage_id: StageId, duration: Duration) -> Self {
        Self {
            stage_id,
            duration,
            success: true,
            error: None,
            data: None,
        }
    }

    pub fn success_with_data<T: 'static + Send + Sync>(
        stage_id: StageId,
        duration: Duration,
        data: T,
    ) -> Self {
        Self {
            stage_id,
            duration,
            success: true,
            error: None,
            data: Some(Arc::new(data)),
        }
    }

    pub fn failure(stage_id: StageId, duration: Duration, error: String) -> Self {
        Self {
            stage_id,
            duration,
            success: false,
            error: Some(error),
            data: None,
        }
    }

    /// Get typed data
    pub fn get_data<T: 'static + Send + Sync>(&self) -> Option<Arc<T>> {
        self.data.as_ref()?
            .clone()
            .downcast::<T>()
            .ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pipeline_state() {
        let state = PipelineState::new(
            PathBuf::from("/test"),
            "test-repo".to_string(),
        );

        assert_eq!(state.status, PipelineStatus::NotStarted);
        assert_eq!(state.completed_stages.len(), 0);
    }

    #[test]
    fn test_indexing_stats() {
        let mut stats = IndexingStats::new();
        stats.total_nodes = 1000;
        stats.total_duration = Duration::from_secs(10);

        assert_eq!(stats.throughput(), 100.0); // 1000 nodes / 10 sec
    }

    #[test]
    fn test_stage_result_data() {
        #[derive(Debug, Clone, PartialEq)]
        struct ChunkingResult {
            chunks_created: usize,
        }

        let result = StageResultData::success_with_data(
            StageId::L2Chunking,
            Duration::from_secs(5),
            ChunkingResult { chunks_created: 100 },
        );

        assert!(result.success);
        assert_eq!(result.duration, Duration::from_secs(5));

        let data = result.get_data::<ChunkingResult>().unwrap();
        assert_eq!(data.chunks_created, 100);
    }
}
