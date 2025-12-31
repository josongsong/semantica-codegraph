use crate::error::{ErrorCategory, OrchestratorError, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Stage identifier
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StageId {
    L1_IR,
    L2_Chunk,
    L3_Lexical,
    L4_Vector,
}

impl StageId {
    pub fn as_str(&self) -> &'static str {
        match self {
            StageId::L1_IR => "L1_IR",
            StageId::L2_Chunk => "L2_Chunk",
            StageId::L3_Lexical => "L3_Lexical",
            StageId::L4_Vector => "L4_Vector",
        }
    }

    pub fn from_str(s: &str) -> Result<Self> {
        match s {
            "L1_IR" => Ok(StageId::L1_IR),
            "L2_Chunk" => Ok(StageId::L2_Chunk),
            "L3_Lexical" => Ok(StageId::L3_Lexical),
            "L4_Vector" => Ok(StageId::L4_Vector),
            _ => Err(OrchestratorError::parse(format!("Invalid stage ID: {}", s))),
        }
    }
}

impl std::fmt::Display for StageId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Job state enum (inspired by semantica-task-engine JobState)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum JobState {
    Queued {
        queued_at: DateTime<Utc>,
        priority: i32,
    },
    Running {
        started_at: DateTime<Utc>,
        worker_id: String,
        current_stage: StageId,
        checkpoint_id: Option<Uuid>,
    },
    Completed {
        started_at: DateTime<Utc>,
        completed_at: DateTime<Utc>,
        duration_ms: u64,
        files_processed: usize,
    },
    Failed {
        started_at: DateTime<Utc>,
        failed_at: DateTime<Utc>,
        error: String,
        error_category: ErrorCategory,
        failed_stage: StageId,
        retry_count: u32,
        next_retry_at: Option<DateTime<Utc>>,
    },
    Cancelled {
        cancelled_at: DateTime<Utc>,
        reason: String,
    },
}

impl JobState {
    pub fn state_name(&self) -> &'static str {
        match self {
            JobState::Queued { .. } => "queued",
            JobState::Running { .. } => "running",
            JobState::Completed { .. } => "completed",
            JobState::Failed { .. } => "failed",
            JobState::Cancelled { .. } => "cancelled",
        }
    }

    pub fn is_terminal(&self) -> bool {
        matches!(
            self,
            JobState::Completed { .. } | JobState::Failed { .. } | JobState::Cancelled { .. }
        )
    }
}

/// Job model
#[derive(Debug, Clone)]
pub struct Job {
    pub id: Uuid,
    pub repo_id: String,
    pub snapshot_id: String,
    pub state: JobState,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,

    // Incremental update metadata
    pub changed_files: Option<std::collections::HashSet<std::path::PathBuf>>,
    pub previous_snapshot_id: Option<String>,
}

impl Job {
    /// Create a new queued job (full rebuild)
    pub fn new_queued(repo_id: String, snapshot_id: String, priority: i32) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            repo_id,
            snapshot_id,
            state: JobState::Queued {
                queued_at: now,
                priority,
            },
            created_at: now,
            updated_at: now,
            changed_files: None,
            previous_snapshot_id: None,
        }
    }

    /// Create a new queued job with incremental update metadata
    pub fn new_incremental(
        repo_id: String,
        snapshot_id: String,
        priority: i32,
        changed_files: std::collections::HashSet<std::path::PathBuf>,
        previous_snapshot_id: String,
    ) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            repo_id,
            snapshot_id,
            state: JobState::Queued {
                queued_at: now,
                priority,
            },
            created_at: now,
            updated_at: now,
            changed_files: Some(changed_files),
            previous_snapshot_id: Some(previous_snapshot_id),
        }
    }

    /// Check if this is an incremental job
    pub fn is_incremental(&self) -> bool {
        self.changed_files.is_some() && self.previous_snapshot_id.is_some()
    }
}

/// Job state machine for transitions
pub struct JobStateMachine {
    job: Job,
}

impl JobStateMachine {
    pub fn new(job: Job) -> Self {
        Self { job }
    }

    pub fn job(&self) -> &Job {
        &self.job
    }

    pub fn into_job(self) -> Job {
        self.job
    }

    /// Transition: QUEUED → RUNNING
    pub fn start(&mut self, worker_id: String, current_stage: StageId) -> Result<()> {
        match &self.job.state {
            JobState::Queued { .. } => {
                let now = Utc::now();
                self.job.state = JobState::Running {
                    started_at: now,
                    worker_id,
                    current_stage,
                    checkpoint_id: None,
                };
                self.job.updated_at = now;
                Ok(())
            }
            _ => Err(OrchestratorError::InvalidStateTransition {
                from: self.job.state.state_name().to_string(),
                to: "running".to_string(),
            }),
        }
    }

    /// Transition: RUNNING → COMPLETED
    pub fn complete(&mut self, files_processed: usize) -> Result<()> {
        match &self.job.state {
            JobState::Running { started_at, .. } => {
                let now = Utc::now();
                let duration_ms = (now - *started_at).num_milliseconds() as u64;

                self.job.state = JobState::Completed {
                    started_at: *started_at,
                    completed_at: now,
                    duration_ms,
                    files_processed,
                };
                self.job.updated_at = now;
                Ok(())
            }
            _ => Err(OrchestratorError::InvalidStateTransition {
                from: self.job.state.state_name().to_string(),
                to: "completed".to_string(),
            }),
        }
    }

    /// Transition: RUNNING → FAILED
    pub fn fail(
        &mut self,
        error: String,
        error_category: ErrorCategory,
        failed_stage: StageId,
        retry_count: u32,
    ) -> Result<()> {
        match &self.job.state {
            JobState::Running { started_at, .. } | JobState::Failed { started_at, .. } => {
                let now = Utc::now();

                // Calculate exponential backoff (2s, 4s, 8s)
                let next_retry_at = if retry_count < 3 && error_category == ErrorCategory::Transient
                {
                    let backoff_secs = 2u64.pow(retry_count);
                    Some(now + chrono::Duration::seconds(backoff_secs as i64))
                } else {
                    None
                };

                self.job.state = JobState::Failed {
                    started_at: *started_at,
                    failed_at: now,
                    error,
                    error_category,
                    failed_stage,
                    retry_count,
                    next_retry_at,
                };
                self.job.updated_at = now;
                Ok(())
            }
            _ => Err(OrchestratorError::InvalidStateTransition {
                from: self.job.state.state_name().to_string(),
                to: "failed".to_string(),
            }),
        }
    }

    /// Transition: FAILED → QUEUED (retry)
    pub fn retry(&mut self) -> Result<()> {
        match &self.job.state {
            JobState::Failed {
                retry_count,
                next_retry_at,
                ..
            } => {
                if next_retry_at.is_none() {
                    return Err(OrchestratorError::Config(
                        "No retry scheduled (max retries exceeded)".to_string(),
                    ));
                }

                let now = Utc::now();
                self.job.state = JobState::Queued {
                    queued_at: now,
                    priority: *retry_count as i32, // Higher priority for retries
                };
                self.job.updated_at = now;
                Ok(())
            }
            _ => Err(OrchestratorError::InvalidStateTransition {
                from: self.job.state.state_name().to_string(),
                to: "queued (retry)".to_string(),
            }),
        }
    }

    /// Transition: * → CANCELLED
    pub fn cancel(&mut self, reason: String) -> Result<()> {
        if self.job.state.is_terminal() {
            return Err(OrchestratorError::InvalidStateTransition {
                from: self.job.state.state_name().to_string(),
                to: "cancelled".to_string(),
            });
        }

        let now = Utc::now();
        self.job.state = JobState::Cancelled {
            cancelled_at: now,
            reason,
        };
        self.job.updated_at = now;
        Ok(())
    }

    /// Update current stage (for running jobs)
    pub fn update_stage(&mut self, stage: StageId) -> Result<()> {
        match &mut self.job.state {
            JobState::Running { current_stage, .. } => {
                *current_stage = stage;
                self.job.updated_at = Utc::now();
                Ok(())
            }
            _ => Err(OrchestratorError::InvalidStateTransition {
                from: self.job.state.state_name().to_string(),
                to: "update_stage".to_string(),
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stage_id_roundtrip() {
        for stage in &[
            StageId::L1_IR,
            StageId::L2_Chunk,
            StageId::L3_Lexical,
            StageId::L4_Vector,
        ] {
            let s = stage.as_str();
            let parsed = StageId::from_str(s).unwrap();
            assert_eq!(*stage, parsed);
        }
    }

    #[test]
    fn test_job_state_transition_queued_to_running() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.start("worker-1".to_string(), StageId::L1_IR).unwrap();

        assert!(matches!(sm.job().state, JobState::Running { .. }));
    }

    #[test]
    fn test_job_state_transition_running_to_completed() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.start("worker-1".to_string(), StageId::L1_IR).unwrap();
        sm.complete(100).unwrap();

        match &sm.job().state {
            JobState::Completed {
                files_processed, ..
            } => {
                assert_eq!(*files_processed, 100);
            }
            _ => panic!("Expected Completed state"),
        }
    }

    #[test]
    fn test_job_state_transition_running_to_failed() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.start("worker-1".to_string(), StageId::L1_IR).unwrap();
        sm.fail(
            "test error".to_string(),
            ErrorCategory::Transient,
            StageId::L1_IR,
            0,
        )
        .unwrap();

        match &sm.job().state {
            JobState::Failed {
                error,
                retry_count,
                next_retry_at,
                ..
            } => {
                assert_eq!(error, "test error");
                assert_eq!(*retry_count, 0);
                assert!(next_retry_at.is_some()); // Transient error should have retry
            }
            _ => panic!("Expected Failed state"),
        }
    }

    #[test]
    fn test_job_retry_increments_priority() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.start("worker-1".to_string(), StageId::L1_IR).unwrap();
        sm.fail(
            "test error".to_string(),
            ErrorCategory::Transient,
            StageId::L1_IR,
            1,
        )
        .unwrap();
        sm.retry().unwrap();

        match &sm.job().state {
            JobState::Queued { priority, .. } => {
                assert_eq!(*priority, 1); // Priority = retry_count
            }
            _ => panic!("Expected Queued state"),
        }
    }

    #[test]
    fn test_job_no_retry_for_permanent_error() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.start("worker-1".to_string(), StageId::L1_IR).unwrap();
        sm.fail(
            "parse error".to_string(),
            ErrorCategory::Permanent,
            StageId::L1_IR,
            0,
        )
        .unwrap();

        match &sm.job().state {
            JobState::Failed { next_retry_at, .. } => {
                assert!(next_retry_at.is_none()); // Permanent error should not retry
            }
            _ => panic!("Expected Failed state"),
        }
    }

    #[test]
    fn test_job_cancel_from_queued() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.cancel("user requested".to_string()).unwrap();

        match &sm.job().state {
            JobState::Cancelled { reason, .. } => {
                assert_eq!(reason, "user requested");
            }
            _ => panic!("Expected Cancelled state"),
        }
    }

    #[test]
    fn test_cannot_cancel_completed_job() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.start("worker-1".to_string(), StageId::L1_IR).unwrap();
        sm.complete(100).unwrap();

        let result = sm.cancel("too late".to_string());
        assert!(result.is_err());
    }

    #[test]
    fn test_update_stage_for_running_job() {
        let job = Job::new_queued("repo-1".to_string(), "snap-1".to_string(), 0);
        let mut sm = JobStateMachine::new(job);

        sm.start("worker-1".to_string(), StageId::L1_IR).unwrap();
        sm.update_stage(StageId::L2_Chunk).unwrap();

        match &sm.job().state {
            JobState::Running { current_stage, .. } => {
                assert_eq!(*current_stage, StageId::L2_Chunk);
            }
            _ => panic!("Expected Running state"),
        }
    }
}
