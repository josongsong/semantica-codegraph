use crate::error::{OrchestratorError, Result};
use crate::job::StageId;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use uuid::Uuid;

/// Checkpoint data (placeholder for now, will be populated with actual stage data)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Checkpoint {
    pub id: Uuid,
    pub job_id: Uuid,
    pub stage: StageId,
    pub cache_key: String,
    pub cache_data: Vec<u8>, // Serialized stage output (bincode)
}

impl Checkpoint {
    pub fn new(job_id: Uuid, stage: StageId, cache_key: String, cache_data: Vec<u8>) -> Self {
        Self {
            id: Uuid::new_v4(),
            job_id,
            stage,
            cache_key,
            cache_data,
        }
    }
}

/// Checkpoint manager (SQLite-backed, but interface-first for testing)
pub struct CheckpointManager {
    // Will be replaced with sqlx::SqlitePool
    checkpoints: std::sync::Arc<parking_lot::Mutex<Vec<Checkpoint>>>,
}

impl CheckpointManager {
    pub fn new_in_memory() -> Self {
        Self {
            checkpoints: std::sync::Arc::new(parking_lot::Mutex::new(Vec::new())),
        }
    }

    /// Save checkpoint
    pub async fn save_checkpoint(&self, checkpoint: Checkpoint) -> Result<()> {
        let mut checkpoints = self.checkpoints.lock();

        // Remove existing checkpoint for same job+stage
        checkpoints.retain(|cp| !(cp.job_id == checkpoint.job_id && cp.stage == checkpoint.stage));

        checkpoints.push(checkpoint);
        Ok(())
    }

    /// Load checkpoint by cache key
    pub async fn load_checkpoint(&self, cache_key: &str) -> Result<Option<Vec<u8>>> {
        let checkpoints = self.checkpoints.lock();

        Ok(checkpoints
            .iter()
            .find(|cp| cp.cache_key == cache_key)
            .map(|cp| cp.cache_data.clone()))
    }

    /// Get completed stages for a job
    pub async fn completed_stages(&self, job_id: Uuid) -> Result<HashSet<StageId>> {
        let checkpoints = self.checkpoints.lock();

        Ok(checkpoints
            .iter()
            .filter(|cp| cp.job_id == job_id)
            .map(|cp| cp.stage)
            .collect())
    }

    /// Delete checkpoints for a job (cleanup after completion)
    pub async fn delete_job_checkpoints(&self, job_id: Uuid) -> Result<()> {
        let mut checkpoints = self.checkpoints.lock();
        checkpoints.retain(|cp| cp.job_id != job_id);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_save_and_load_checkpoint() {
        let mgr = CheckpointManager::new_in_memory();
        let job_id = Uuid::new_v4();

        let cp = Checkpoint::new(
            job_id,
            StageId::L1_IR,
            "ir:repo1:snap1".to_string(),
            vec![1, 2, 3, 4],
        );

        mgr.save_checkpoint(cp).await.unwrap();

        let loaded = mgr.load_checkpoint("ir:repo1:snap1").await.unwrap();
        assert_eq!(loaded, Some(vec![1, 2, 3, 4]));
    }

    #[tokio::test]
    async fn test_save_checkpoint_replaces_existing() {
        let mgr = CheckpointManager::new_in_memory();
        let job_id = Uuid::new_v4();

        // Save first checkpoint
        let cp1 = Checkpoint::new(
            job_id,
            StageId::L1_IR,
            "ir:repo1:snap1".to_string(),
            vec![1, 2, 3],
        );
        mgr.save_checkpoint(cp1).await.unwrap();

        // Save second checkpoint for same job+stage
        let cp2 = Checkpoint::new(
            job_id,
            StageId::L1_IR,
            "ir:repo1:snap1".to_string(),
            vec![4, 5, 6],
        );
        mgr.save_checkpoint(cp2).await.unwrap();

        // Should have latest data
        let loaded = mgr.load_checkpoint("ir:repo1:snap1").await.unwrap();
        assert_eq!(loaded, Some(vec![4, 5, 6]));
    }

    #[tokio::test]
    async fn test_completed_stages() {
        let mgr = CheckpointManager::new_in_memory();
        let job_id = Uuid::new_v4();

        // Save checkpoints for L1 and L2
        let cp1 = Checkpoint::new(
            job_id,
            StageId::L1_IR,
            "ir:repo1:snap1".to_string(),
            vec![1, 2, 3],
        );
        let cp2 = Checkpoint::new(
            job_id,
            StageId::L2_Chunk,
            "chunks:repo1:snap1".to_string(),
            vec![4, 5, 6],
        );

        mgr.save_checkpoint(cp1).await.unwrap();
        mgr.save_checkpoint(cp2).await.unwrap();

        let completed = mgr.completed_stages(job_id).await.unwrap();
        assert_eq!(completed.len(), 2);
        assert!(completed.contains(&StageId::L1_IR));
        assert!(completed.contains(&StageId::L2_Chunk));
    }

    #[tokio::test]
    async fn test_delete_job_checkpoints() {
        let mgr = CheckpointManager::new_in_memory();
        let job_id = Uuid::new_v4();

        let cp = Checkpoint::new(
            job_id,
            StageId::L1_IR,
            "ir:repo1:snap1".to_string(),
            vec![1, 2, 3],
        );
        mgr.save_checkpoint(cp).await.unwrap();

        mgr.delete_job_checkpoints(job_id).await.unwrap();

        let completed = mgr.completed_stages(job_id).await.unwrap();
        assert_eq!(completed.len(), 0);
    }

    #[tokio::test]
    async fn test_load_nonexistent_checkpoint() {
        let mgr = CheckpointManager::new_in_memory();

        let loaded = mgr.load_checkpoint("nonexistent").await.unwrap();
        assert_eq!(loaded, None);
    }
}
