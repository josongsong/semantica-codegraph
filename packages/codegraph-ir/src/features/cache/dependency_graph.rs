//! Dependency graph for incremental updates

use crate::features::cache::{CacheError, CacheResult, FileId, Fingerprint};
use dashmap::DashMap;
use petgraph::algo::toposort;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::Direction;
use std::collections::{HashSet, VecDeque};

/// File node in dependency graph
#[derive(Debug, Clone)]
pub struct FileNode {
    pub file_id: FileId,
    pub fingerprint: Fingerprint,
    pub last_modified_ns: u64,
}

/// Dependency graph for incremental builds
///
/// Tracks file dependencies and computes affected files on changes.
pub struct DependencyGraph {
    /// Graph (file nodes + import edges)
    graph: DiGraph<FileNode, ()>,

    /// File ID → Node index mapping
    file_to_node: DashMap<FileId, NodeIndex>,
}

impl DependencyGraph {
    /// Create new dependency graph
    pub fn new() -> Self {
        Self {
            graph: DiGraph::new(),
            file_to_node: DashMap::new(),
        }
    }

    /// Register file with dependencies
    ///
    /// # Arguments
    /// * `file_id` - File identifier
    /// * `fingerprint` - Content fingerprint
    /// * `dependencies` - Files this file depends on (imports)
    pub fn register_file(
        &mut self,
        file_id: FileId,
        fingerprint: Fingerprint,
        dependencies: &[FileId],
    ) {
        // Get or create node index (releases entry lock immediately with *)
        let node_idx = *self.file_to_node.entry(file_id.clone()).or_insert_with(|| {
            self.graph.add_node(FileNode {
                file_id: file_id.clone(),
                fingerprint,
                last_modified_ns: unix_now_ns(),
            })
        });

        // Update node
        if let Some(node) = self.graph.node_weight_mut(node_idx) {
            node.fingerprint = fingerprint;
            node.last_modified_ns = unix_now_ns();
        }

        // Add dependency edges
        for dep_id in dependencies {
            // Skip self-references to avoid deadlock on DashMap entry
            if dep_id == &file_id {
                continue;
            }

            let dep_node = *self.file_to_node.entry(dep_id.clone()).or_insert_with(|| {
                // Create placeholder node
                self.graph.add_node(FileNode {
                    file_id: dep_id.clone(),
                    fingerprint: Fingerprint::zero(),
                    last_modified_ns: 0,
                })
            });

            // Add edge: file → dependency
            self.graph.add_edge(node_idx, dep_node, ());
        }
    }

    /// Get affected files (BFS from changed files)
    ///
    /// Returns all files that need to be rebuilt due to changes.
    pub fn get_affected_files(&self, changed: &[FileId]) -> Vec<FileId> {
        let mut affected = HashSet::new();
        let mut queue = VecDeque::new();

        // Start from changed files
        for file_id in changed {
            if let Some(node_idx) = self.file_to_node.get(file_id) {
                affected.insert(file_id.clone());
                queue.push_back(*node_idx);
            }
        }

        // BFS traversal (find dependents)
        while let Some(node_idx) = queue.pop_front() {
            // Find files that depend on this file (incoming edges)
            for neighbor in self.graph.neighbors_directed(node_idx, Direction::Incoming) {
                if let Some(node) = self.graph.node_weight(neighbor) {
                    if affected.insert(node.file_id.clone()) {
                        queue.push_back(neighbor);
                    }
                }
            }
        }

        affected.into_iter().collect()
    }

    /// Get topological build order
    ///
    /// Returns files in dependency order: dependencies first, dependents last.
    /// E.g., if A imports B, result is [B, A] so B is built before A.
    pub fn build_order(&self) -> CacheResult<Vec<FileId>> {
        let sorted = toposort(&self.graph, None).map_err(|_| CacheError::DependencyCycle)?;

        // Reverse because toposort returns [source, sink] order,
        // but build order needs dependencies (sinks) first
        Ok(sorted
            .into_iter()
            .rev()
            .filter_map(|idx| self.graph.node_weight(idx))
            .map(|node| node.file_id.clone())
            .collect())
    }

    /// Clear all entries
    pub fn clear(&mut self) {
        self.graph.clear();
        self.file_to_node.clear();
    }
}

impl Default for DependencyGraph {
    fn default() -> Self {
        Self::new()
    }
}

fn unix_now_ns() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::cache::Language;

    #[test]
    fn test_dependency_graph_basic() {
        let mut graph = DependencyGraph::new();

        let file_a = FileId::from_path_str("a.py", Language::Python);
        let file_b = FileId::from_path_str("b.py", Language::Python);
        let file_c = FileId::from_path_str("c.py", Language::Python);

        // a.py imports b.py
        // b.py imports c.py
        graph.register_file(
            file_a.clone(),
            Fingerprint::compute(b"a"),
            &[file_b.clone()],
        );
        graph.register_file(
            file_b.clone(),
            Fingerprint::compute(b"b"),
            &[file_c.clone()],
        );
        graph.register_file(file_c.clone(), Fingerprint::compute(b"c"), &[]);

        // If c.py changes, both b.py and a.py are affected
        let affected = graph.get_affected_files(&[file_c.clone()]);

        assert_eq!(affected.len(), 3);
        assert!(affected.contains(&file_a));
        assert!(affected.contains(&file_b));
        assert!(affected.contains(&file_c));
    }

    #[test]
    fn test_dependency_graph_no_dependencies() {
        let mut graph = DependencyGraph::new();

        let file_a = FileId::from_path_str("a.py", Language::Python);
        graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[]);

        let affected = graph.get_affected_files(&[file_a.clone()]);

        assert_eq!(affected.len(), 1);
        assert!(affected.contains(&file_a));
    }

    #[test]
    fn test_dependency_graph_build_order() {
        let mut graph = DependencyGraph::new();

        let file_a = FileId::from_path_str("a.py", Language::Python);
        let file_b = FileId::from_path_str("b.py", Language::Python);

        graph.register_file(
            file_a.clone(),
            Fingerprint::compute(b"a"),
            &[file_b.clone()],
        );
        graph.register_file(file_b.clone(), Fingerprint::compute(b"b"), &[]);

        let order = graph.build_order().unwrap();

        // b should come before a (topological order)
        let a_pos = order.iter().position(|f| f == &file_a).unwrap();
        let b_pos = order.iter().position(|f| f == &file_b).unwrap();

        assert!(b_pos < a_pos);
    }
}
