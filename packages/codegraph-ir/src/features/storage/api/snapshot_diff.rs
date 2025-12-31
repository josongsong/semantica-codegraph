//! Snapshot Diff Types
//!
//! Types for representing differences between code snapshots.

use crate::features::storage::domain::models::Chunk;

/// Semantic diff between two snapshots
///
/// Tracks added, modified, and deleted chunks at a semantic level
/// (based on FQN and content hash, not line numbers).
#[derive(Debug, Clone, Default)]
pub struct SnapshotDiff {
    /// Chunks added in new snapshot
    pub added: Vec<Chunk>,

    /// Chunks modified between snapshots (old, new)
    pub modified: Vec<(Chunk, Chunk)>,

    /// Chunks deleted from old snapshot
    pub deleted: Vec<Chunk>,
}

impl SnapshotDiff {
    /// Create empty diff
    pub fn new() -> Self {
        Self::default()
    }

    /// Total number of changes
    pub fn total_changes(&self) -> usize {
        self.added.len() + self.modified.len() + self.deleted.len()
    }

    /// Check if diff is empty
    pub fn is_empty(&self) -> bool {
        self.added.is_empty() && self.modified.is_empty() && self.deleted.is_empty()
    }

    /// Get summary statistics
    pub fn summary(&self) -> String {
        format!(
            "+{} ~{} -{} (total: {})",
            self.added.len(),
            self.modified.len(),
            self.deleted.len(),
            self.total_changes()
        )
    }
}

/// Statistics from snapshot creation
#[derive(Debug, Clone, Default)]
pub struct SnapshotStats {
    /// Total files checked for changes
    pub files_checked: usize,

    /// Files skipped (unchanged based on hash)
    pub files_skipped: usize,

    /// Files re-analyzed (changed)
    pub files_analyzed: usize,

    /// Total chunks created
    pub chunks_created: usize,

    /// Total dependencies created
    pub dependencies_created: usize,
}

impl SnapshotStats {
    /// Create empty stats
    pub fn new() -> Self {
        Self::default()
    }

    /// Get summary string
    pub fn summary(&self) -> String {
        format!(
            "Checked: {}, Skipped: {} ({}%), Analyzed: {}, Chunks: {}, Deps: {}",
            self.files_checked,
            self.files_skipped,
            if self.files_checked > 0 {
                (self.files_skipped * 100) / self.files_checked
            } else {
                0
            },
            self.files_analyzed,
            self.chunks_created,
            self.dependencies_created
        )
    }
}
