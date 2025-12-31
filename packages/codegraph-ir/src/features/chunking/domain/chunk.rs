//! Chunk Data Model
//!
//! Symbol-first hierarchical chunking for RAG.
//!
//! Hierarchy:
//!     Repo → Project → Module → File → Class → Function

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use super::ChunkKind;

/// A chunk represents a hierarchical unit of code for RAG
///
/// # Hierarchy levels
/// - `repo`: Top-level repository
/// - `project`: Sub-project within a monorepo
/// - `module`: Directory/package structure
/// - `file`: Source file
/// - `class`: Class/interface/struct
/// - `function`: Function/method (leaf chunks)
///
/// # ID format
/// `chunk:{repo_id}:{kind}:{fqn}`
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Chunk {
    pub chunk_id: String,
    pub repo_id: String,
    pub snapshot_id: String, // Git commit hash or timestamp
    pub project_id: Option<String>,
    pub module_path: Option<String>,
    pub file_path: Option<String>,

    pub kind: ChunkKind,
    pub fqn: String, // Fully qualified dotted name

    // Line range (current snapshot)
    pub start_line: Option<u32>,
    pub end_line: Option<u32>,

    // Original line range (for span drift detection)
    pub original_start_line: Option<u32>,
    pub original_end_line: Option<u32>,

    pub content_hash: Option<String>, // Hash of code text

    pub parent_id: Option<String>,
    pub children: Vec<String>,

    pub language: Option<String>, // "python", "typescript", etc.
    pub symbol_visibility: Option<String>, // "public" | "internal" | "private"

    pub symbol_id: Option<String>,       // Symbol this chunk represents
    pub symbol_owner_id: Option<String>, // Actual definition symbol (for re-exports/wrappers)

    pub summary: Option<String>,
    pub importance: Option<f32>,
    pub attrs: HashMap<String, String>,

    // Versioning (for incremental updates)
    pub version: i32,
    pub last_indexed_commit: Option<String>,
    pub is_deleted: bool,

    // RFC-RUST-ENGINE Phase 1: Ordering tie-breaker
    // Ensures deterministic total ordering for accurate caching
    pub local_seq: u32,

    // P1: Test detection (M1)
    pub is_test: Option<bool>, // True if this is a test function/class

    // P2: Overlay support (IDE integration)
    pub is_overlay: bool, // True if this is an overlay chunk (unsaved IDE changes)
    pub overlay_session_id: Option<String>, // IDE session ID for overlay chunks
    pub base_chunk_id: Option<String>, // Original base chunk ID that this overlay shadows
}

impl Default for Chunk {
    fn default() -> Self {
        Self {
            chunk_id: String::new(),
            repo_id: String::new(),
            snapshot_id: "default".to_string(),
            project_id: None,
            module_path: None,
            file_path: None,
            kind: ChunkKind::File,
            fqn: String::new(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: None,
            children: Vec::new(),
            language: None,
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }
    }
}

impl Chunk {
    /// Create a new Chunk with required fields
    pub fn new(
        chunk_id: String,
        repo_id: String,
        snapshot_id: String,
        kind: ChunkKind,
        fqn: String,
    ) -> Self {
        Self {
            chunk_id,
            repo_id,
            snapshot_id,
            kind,
            fqn,
            ..Default::default()
        }
    }

    /// Check if chunk has line range
    pub fn has_line_range(&self) -> bool {
        self.start_line.is_some() && self.end_line.is_some()
    }

    /// Get line count
    pub fn line_count(&self) -> Option<u32> {
        match (self.start_line, self.end_line) {
            (Some(start), Some(end)) => Some(end.saturating_sub(start) + 1),
            _ => None,
        }
    }

    /// Check if chunk is structural (repo, project, module, file)
    pub fn is_structural(&self) -> bool {
        matches!(
            self.kind,
            ChunkKind::Repo | ChunkKind::Project | ChunkKind::Module | ChunkKind::File
        )
    }

    /// Check if chunk is symbol (class, function)
    pub fn is_symbol(&self) -> bool {
        matches!(self.kind, ChunkKind::Class | ChunkKind::Function)
    }

    /// Add a child chunk ID
    pub fn add_child(&mut self, child_id: String) {
        if !self.children.contains(&child_id) {
            self.children.push(child_id);
        }
    }

    /// Set as overlay chunk
    pub fn set_overlay(&mut self, session_id: String, base_chunk_id: Option<String>) {
        self.is_overlay = true;
        self.overlay_session_id = Some(session_id);
        self.base_chunk_id = base_chunk_id;
    }
}

/// Type aliases for mappings
pub type ChunkId = String;
pub type GraphNodeId = String;
pub type IRNodeId = String;

pub type ChunkToGraph = HashMap<ChunkId, Vec<GraphNodeId>>;
pub type ChunkToIR = HashMap<ChunkId, Vec<IRNodeId>>;
pub type ChunkHierarchy = HashMap<ChunkId, Vec<ChunkId>>; // parent -> children

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chunk_creation() {
        let chunk = Chunk::new(
            "chunk:repo:func:foo".to_string(),
            "repo".to_string(),
            "abc123".to_string(),
            ChunkKind::Function,
            "foo".to_string(),
        );

        assert_eq!(chunk.chunk_id, "chunk:repo:func:foo");
        assert_eq!(chunk.repo_id, "repo");
        assert_eq!(chunk.snapshot_id, "abc123");
        assert_eq!(chunk.kind, ChunkKind::Function);
        assert_eq!(chunk.fqn, "foo");
        assert_eq!(chunk.version, 1);
        assert!(!chunk.is_overlay);
    }

    #[test]
    fn test_line_range() {
        let mut chunk = Chunk::default();
        assert!(!chunk.has_line_range());
        assert_eq!(chunk.line_count(), None);

        chunk.start_line = Some(10);
        chunk.end_line = Some(20);
        assert!(chunk.has_line_range());
        assert_eq!(chunk.line_count(), Some(11)); // 20 - 10 + 1
    }

    #[test]
    fn test_is_structural() {
        assert!(
            Chunk::new("".into(), "".into(), "".into(), ChunkKind::Repo, "".into()).is_structural()
        );
        assert!(Chunk::new(
            "".into(),
            "".into(),
            "".into(),
            ChunkKind::Project,
            "".into()
        )
        .is_structural());
        assert!(Chunk::new(
            "".into(),
            "".into(),
            "".into(),
            ChunkKind::Module,
            "".into()
        )
        .is_structural());
        assert!(
            Chunk::new("".into(), "".into(), "".into(), ChunkKind::File, "".into()).is_structural()
        );
        assert!(
            !Chunk::new("".into(), "".into(), "".into(), ChunkKind::Class, "".into())
                .is_structural()
        );
        assert!(!Chunk::new(
            "".into(),
            "".into(),
            "".into(),
            ChunkKind::Function,
            "".into()
        )
        .is_structural());
    }

    #[test]
    fn test_is_symbol() {
        assert!(
            Chunk::new("".into(), "".into(), "".into(), ChunkKind::Class, "".into()).is_symbol()
        );
        assert!(Chunk::new(
            "".into(),
            "".into(),
            "".into(),
            ChunkKind::Function,
            "".into()
        )
        .is_symbol());
        assert!(
            !Chunk::new("".into(), "".into(), "".into(), ChunkKind::File, "".into()).is_symbol()
        );
    }

    #[test]
    fn test_add_child() {
        let mut chunk = Chunk::default();
        chunk.add_child("child1".to_string());
        chunk.add_child("child2".to_string());
        chunk.add_child("child1".to_string()); // Duplicate

        assert_eq!(chunk.children.len(), 2);
        assert_eq!(chunk.children, vec!["child1", "child2"]);
    }

    #[test]
    fn test_overlay() {
        let mut chunk = Chunk::default();
        chunk.set_overlay("session123".to_string(), Some("base_chunk".to_string()));

        assert!(chunk.is_overlay);
        assert_eq!(chunk.overlay_session_id, Some("session123".to_string()));
        assert_eq!(chunk.base_chunk_id, Some("base_chunk".to_string()));
    }
}
