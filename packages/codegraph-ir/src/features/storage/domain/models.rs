//! Storage Domain Models
//!
//! SOTA Design based on RFC-074:
//! - Content-Addressable Storage (Bazel CAS, Nix)
//! - Multi-Repository (Sourcegraph)
//! - Multi-Snapshot (Git-like versioning)
//! - Soft Delete (safe incremental updates)

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::shared::models::Value;

/// Chunk ID format: `"<repo_id>:<file_path>:<symbol_name>:<start_line>-<end_line>"`
///
/// Examples:
/// - `"backend-api:src/auth.py:login:10-25"`
/// - `"frontend:components/Button.tsx:Button:5-15"`
pub type ChunkId = String;

/// Repository ID (unique identifier)
pub type RepoId = String;

/// Snapshot ID format: `"<repo_id>:<branch_name>"` or `"<repo_id>:<commit_hash>"`
pub type SnapshotId = String;

/// Repository Entity
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Repository {
    /// Repository ID (primary key)
    pub repo_id: RepoId,

    /// Repository name
    pub name: String,

    /// Remote URL (e.g., "https://github.com/user/repo")
    pub remote_url: Option<String>,

    /// Local file system path
    pub local_path: Option<String>,

    /// Default branch (e.g., "main", "develop")
    pub default_branch: String,

    /// Creation timestamp
    pub created_at: DateTime<Utc>,

    /// Last update timestamp
    pub updated_at: DateTime<Utc>,
}

/// Snapshot Entity (Branch or Commit)
///
/// Supports both branch tracking ("main", "develop") and
/// commit tracking ("abc123def") for version control
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snapshot {
    /// Snapshot ID (primary key)
    /// Format: "repo-id:branch-name" or "repo-id:commit-hash"
    pub snapshot_id: SnapshotId,

    /// Repository ID (foreign key)
    pub repo_id: RepoId,

    /// Git commit hash (optional)
    pub commit_hash: Option<String>,

    /// Git branch name (optional)
    pub branch_name: Option<String>,

    /// Creation timestamp
    pub created_at: DateTime<Utc>,
}

/// Chunk Entity (Core searchable unit)
///
/// SOTA Features:
/// - Content-Addressable: `content_hash` for incremental updates
/// - Soft Delete: `is_deleted` flag for safe updates
/// - Multi-Repo: `repo_id` + `snapshot_id` isolation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chunk {
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Identity (Content-Addressable)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Chunk ID (primary key)
    /// Format: "repo:path:symbol:start-end"
    pub chunk_id: ChunkId,

    /// Repository ID (foreign key)
    pub repo_id: RepoId,

    /// Snapshot ID (foreign key)
    pub snapshot_id: SnapshotId,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Location
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// File path (relative to repo root)
    pub file_path: String,

    /// Start line number
    pub start_line: u32,

    /// End line number
    pub end_line: u32,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Semantics
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Chunk kind (e.g., "function", "class", "module")
    pub kind: String,

    /// Fully Qualified Name (e.g., "myapp.auth.login")
    pub fqn: Option<String>,

    /// Programming language
    pub language: String,

    /// Symbol visibility ("public", "private", "internal")
    pub symbol_visibility: Option<String>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Content (CRITICAL: Actual source code)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Actual source code content
    pub content: String,

    /// SHA256 hash of content (for change detection)
    pub content_hash: String,

    /// AI-generated summary (optional)
    pub summary: Option<String>,

    /// Importance score (PageRank: 0.0-1.0)
    pub importance: f32,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Soft Delete (Safe Incremental Updates)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Soft delete flag (default: false)
    /// - Never hard DELETE chunks
    /// - UPSERT can revive deleted chunks
    pub is_deleted: bool,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Metadata (Language-specific attributes)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Flexible JSON attributes
    pub attrs: HashMap<String, Value>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Timestamps
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Creation timestamp
    pub created_at: DateTime<Utc>,

    /// Last update timestamp
    pub updated_at: DateTime<Utc>,
}

/// Dependency Entity (Cross-Chunk Relationships)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Dependency {
    /// Dependency ID (primary key)
    pub id: String,

    /// Source chunk ID
    pub from_chunk_id: ChunkId,

    /// Target chunk ID
    pub to_chunk_id: ChunkId,

    /// Relationship type (e.g., "CALLS", "IMPORTS", "EXTENDS")
    pub relationship: DependencyType,

    /// Confidence score (0.0-1.0, for fuzzy matching)
    pub confidence: f32,

    /// Creation timestamp
    pub created_at: DateTime<Utc>,
}

/// Dependency Type (Cross-Chunk Relationship)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DependencyType {
    /// Function/method call
    Calls,

    /// Import/include
    Imports,

    /// Class inheritance
    Extends,

    /// Interface implementation
    Implements,

    /// Data flow (variable assignment)
    Flows,

    /// Type annotation
    TypedBy,
}

/// Chunk Kind (Semantic classification)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ChunkKind {
    Function,
    Class,
    Method,
    Module,
    Variable,
    Constant,
    Interface,
    Type,
    Enum,
    Struct,
}

/// Symbol Visibility
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SymbolVisibility {
    Public,
    Private,
    Protected,
    Internal,
}

impl Chunk {
    /// Generate chunk ID from components
    ///
    /// Format: `"<repo_id>:<file_path>:<symbol_name>:<start_line>-<end_line>"`
    pub fn generate_id(
        repo_id: &str,
        file_path: &str,
        symbol_name: &str,
        start_line: u32,
        end_line: u32,
    ) -> ChunkId {
        format!(
            "{}:{}:{}:{}-{}",
            repo_id, file_path, symbol_name, start_line, end_line
        )
    }

    /// Compute SHA256 hash of content
    pub fn compute_content_hash(content: &str) -> String {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(content.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    /// Create a new chunk with default values
    pub fn new(
        repo_id: String,
        snapshot_id: String,
        file_path: String,
        start_line: u32,
        end_line: u32,
        kind: String,
        content: String,
    ) -> Self {
        let content_hash = Self::compute_content_hash(&content);
        let chunk_id = Self::generate_id(&repo_id, &file_path, "unknown", start_line, end_line);

        Self {
            chunk_id,
            repo_id,
            snapshot_id,
            file_path,
            start_line,
            end_line,
            kind,
            fqn: None,
            language: "unknown".to_string(),
            symbol_visibility: None,
            content,
            content_hash,
            summary: None,
            importance: 0.5,
            is_deleted: false,
            attrs: HashMap::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        }
    }

    /// Check if this chunk has been modified (compare content hashes)
    pub fn is_modified(&self, other_hash: &str) -> bool {
        self.content_hash != other_hash
    }
}

impl Snapshot {
    /// Create snapshot ID from repo and branch/commit
    pub fn generate_id(repo_id: &str, branch_or_commit: &str) -> SnapshotId {
        format!("{}:{}", repo_id, branch_or_commit)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chunk_id_generation() {
        let id = Chunk::generate_id("my-repo", "src/main.rs", "main", 1, 10);
        assert_eq!(id, "my-repo:src/main.rs:main:1-10");
    }

    #[test]
    fn test_content_hash() {
        let hash1 = Chunk::compute_content_hash("fn main() {}");
        let hash2 = Chunk::compute_content_hash("fn main() {}");
        let hash3 = Chunk::compute_content_hash("fn main() { println!(\"changed\"); }");

        assert_eq!(hash1, hash2);
        assert_ne!(hash1, hash3);
    }

    #[test]
    fn test_chunk_is_modified() {
        let chunk = Chunk::new(
            "repo".into(),
            "main".into(),
            "test.rs".into(),
            1,
            10,
            "function".into(),
            "fn test() {}".into(),
        );

        let same_hash = Chunk::compute_content_hash("fn test() {}");
        let different_hash = Chunk::compute_content_hash("fn test() { changed }");

        assert!(!chunk.is_modified(&same_hash));
        assert!(chunk.is_modified(&different_hash));
    }
}
