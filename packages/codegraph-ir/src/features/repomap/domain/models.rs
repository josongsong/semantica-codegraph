//! Core Domain Models

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Type of node in the RepoMap tree
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NodeKind {
    /// Repository root
    Repository,
    /// Directory
    Directory,
    /// File
    File,
    /// Class/Module
    Class,
    /// Function/Method
    Function,
}

/// Node in the RepoMap tree hierarchy
///
/// Represents a single unit in the repository structure, from repository
/// root down to individual functions.
///
/// # Invariants
///
/// 1. `parent_id` is None only for Repository root
/// 2. `children_ids` are valid node IDs within the same snapshot
/// 3. `depth` matches actual tree depth (root = 0)
/// 4. `file_path` is None for non-File nodes
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepoMapNode {
    /// Unique identifier (format: "repo:path:kind:name")
    pub id: String,

    /// Node type
    pub kind: NodeKind,

    /// Node name (e.g., "MyClass", "my_function")
    pub name: String,

    /// Full path (for File nodes) or relative path (for directories)
    pub path: String,

    /// Parent node ID (None for repository root)
    pub parent_id: Option<String>,

    /// Child node IDs
    pub children_ids: Vec<String>,

    /// Tree depth (root = 0)
    pub depth: usize,

    /// Metrics (LOC, complexity, importance, etc.)
    pub metrics: super::RepoMapMetrics,

    /// File path (for File/Class/Function nodes)
    pub file_path: Option<String>,

    /// Symbol ID (references chunk or IR node)
    pub symbol_id: Option<String>,

    /// Repository ID
    pub repo_id: String,

    /// Snapshot ID
    pub snapshot_id: String,
}

impl RepoMapNode {
    /// Create a new RepoMap node
    pub fn new(
        id: String,
        kind: NodeKind,
        name: String,
        path: String,
        repo_id: String,
        snapshot_id: String,
    ) -> Self {
        Self {
            id,
            kind,
            name,
            path,
            parent_id: None,
            children_ids: Vec::new(),
            depth: 0,
            metrics: super::RepoMapMetrics::default(),
            file_path: None,
            symbol_id: None,
            repo_id,
            snapshot_id,
        }
    }

    /// Set parent (empty string is treated as None)
    pub fn with_parent(mut self, parent_id: String) -> Self {
        self.parent_id = if parent_id.is_empty() {
            None
        } else {
            Some(parent_id)
        };
        self
    }

    /// Set depth
    pub fn with_depth(mut self, depth: usize) -> Self {
        self.depth = depth;
        self
    }

    /// Set file path
    pub fn with_file_path(mut self, file_path: String) -> Self {
        self.file_path = Some(file_path);
        self
    }

    /// Set symbol ID
    pub fn with_symbol_id(mut self, symbol_id: String) -> Self {
        self.symbol_id = Some(symbol_id);
        self
    }

    /// Add child
    pub fn add_child(&mut self, child_id: String) {
        if !self.children_ids.contains(&child_id) {
            self.children_ids.push(child_id);
        }
    }

    /// Check if this is a leaf node
    pub fn is_leaf(&self) -> bool {
        self.children_ids.is_empty()
    }

    /// Check if this is the root node
    pub fn is_root(&self) -> bool {
        self.parent_id.is_none() && self.kind == NodeKind::Repository
    }
}

/// RepoMap Snapshot - versioned state of repository structure
///
/// Immutable snapshot of the entire RepoMap tree at a specific point in time.
///
/// # Invariants
///
/// 1. Exactly one root node (NodeKind::Repository)
/// 2. All parent_id references are valid
/// 3. No cycles in the tree
/// 4. All nodes belong to the same repo_id and snapshot_id
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepoMapSnapshot {
    /// Repository ID
    pub repo_id: String,

    /// Snapshot ID (e.g., "v1", git commit hash)
    pub snapshot_id: String,

    /// All nodes (indexed by node ID)
    pub nodes: HashMap<String, RepoMapNode>,

    /// Root node ID
    pub root_id: String,

    /// Snapshot creation timestamp (Unix epoch)
    pub created_at: u64,

    /// Total metrics (aggregated from all nodes)
    pub total_metrics: super::RepoMapMetrics,
}

impl RepoMapSnapshot {
    /// Create a new snapshot
    pub fn new(repo_id: String, snapshot_id: String, nodes: Vec<RepoMapNode>) -> Self {
        // Find root node
        let root = nodes
            .iter()
            .find(|n| n.is_root())
            .expect("RepoMapSnapshot must have exactly one root node");
        let root_id = root.id.clone();

        // Build node index
        let node_map: HashMap<String, RepoMapNode> =
            nodes.into_iter().map(|n| (n.id.clone(), n)).collect();

        // Aggregate total metrics
        let total_metrics = Self::aggregate_metrics(&node_map);

        Self {
            repo_id,
            snapshot_id,
            nodes: node_map,
            root_id,
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            total_metrics,
        }
    }

    /// Get root node
    pub fn root(&self) -> &RepoMapNode {
        self.nodes.get(&self.root_id).expect("Root node must exist")
    }

    /// Get node by ID
    pub fn get_node(&self, id: &str) -> Option<&RepoMapNode> {
        self.nodes.get(id)
    }

    /// Get all children of a node
    pub fn get_children(&self, node_id: &str) -> Vec<&RepoMapNode> {
        if let Some(node) = self.get_node(node_id) {
            node.children_ids
                .iter()
                .filter_map(|child_id| self.get_node(child_id))
                .collect()
        } else {
            Vec::new()
        }
    }

    /// Aggregate metrics from all nodes
    fn aggregate_metrics(nodes: &HashMap<String, RepoMapNode>) -> super::RepoMapMetrics {
        let mut total = super::RepoMapMetrics::default();

        for node in nodes.values() {
            total.loc += node.metrics.loc;
            total.symbol_count += node.metrics.symbol_count;
            total.complexity += node.metrics.complexity;
        }

        total
    }

    /// Validate snapshot integrity
    ///
    /// Returns errors if:
    /// - No root node
    /// - Multiple root nodes
    /// - Invalid parent references
    /// - Cycles detected
    pub fn validate(&self) -> Result<(), Vec<String>> {
        let mut errors = Vec::new();

        // Check root exists
        if !self.nodes.contains_key(&self.root_id) {
            errors.push(format!("Root node {} not found", self.root_id));
        }

        // Check for multiple roots
        let root_count = self.nodes.values().filter(|n| n.is_root()).count();
        if root_count != 1 {
            errors.push(format!("Expected 1 root, found {}", root_count));
        }

        // Check parent references
        for node in self.nodes.values() {
            if let Some(parent_id) = &node.parent_id {
                if !self.nodes.contains_key(parent_id) {
                    errors.push(format!(
                        "Node {} references non-existent parent {}",
                        node.id, parent_id
                    ));
                }
            }
        }

        // Check for cycles (DFS)
        if let Err(cycle_err) = self.check_cycles() {
            errors.push(cycle_err);
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }

    /// Check for cycles using DFS
    fn check_cycles(&self) -> Result<(), String> {
        use std::collections::HashSet;

        let mut visited = HashSet::new();
        let mut path = HashSet::new();

        fn dfs(
            node_id: &str,
            snapshot: &RepoMapSnapshot,
            visited: &mut HashSet<String>,
            path: &mut HashSet<String>,
        ) -> Result<(), String> {
            if path.contains(node_id) {
                return Err(format!("Cycle detected at node {}", node_id));
            }

            if visited.contains(node_id) {
                return Ok(());
            }

            path.insert(node_id.to_string());
            visited.insert(node_id.to_string());

            if let Some(node) = snapshot.get_node(node_id) {
                for child_id in &node.children_ids {
                    dfs(child_id, snapshot, visited, path)?;
                }
            }

            path.remove(node_id);
            Ok(())
        }

        dfs(&self.root_id, self, &mut visited, &mut path)
    }
}
