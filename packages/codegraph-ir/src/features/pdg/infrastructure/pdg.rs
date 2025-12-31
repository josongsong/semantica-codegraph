/*
 * PDG (Program Dependence Graph) Module
 *
 * PDG = CFG (Control Flow) + DFG (Data Flow)
 *
 * PRODUCTION GRADE:
 * - petgraph for efficient graph operations
 * - Control + Data dependency edges
 * - Backward/Forward slicing support
 *
 * Performance Target:
 * - PDG construction: 5-10x faster than Python
 * - Slicing: 10-20x faster (petgraph traversal)
 */

use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;
use crate::features::flow_graph::infrastructure::cfg::{CFGEdge, CFGEdgeType};
use crate::shared::models::Span;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::Direction;
use std::collections::{HashMap, HashSet, VecDeque};

/// Dependency type in PDG
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum DependencyType {
    Control, // Control flow dependency (from CFG)
    Data,    // Data flow dependency (from DFG)
}

impl DependencyType {
    pub fn as_str(&self) -> &'static str {
        match self {
            DependencyType::Control => "CONTROL",
            DependencyType::Data => "DATA",
        }
    }
}

/// PDG Node
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PDGNode {
    pub node_id: String,
    pub statement: String,
    pub line_number: u32,
    pub span: Span,
    pub defined_vars: Vec<String>,
    pub used_vars: Vec<String>,
    pub is_entry: bool,
    pub is_exit: bool,
    pub file_path: Option<String>,
}

impl PDGNode {
    pub fn new(node_id: String, statement: String, line_number: u32, span: Span) -> Self {
        PDGNode {
            node_id,
            statement,
            line_number,
            span,
            defined_vars: Vec::new(),
            used_vars: Vec::new(),
            is_entry: false,
            is_exit: false,
            file_path: None,
        }
    }

    pub fn with_vars(mut self, defined: Vec<String>, used: Vec<String>) -> Self {
        self.defined_vars = defined;
        self.used_vars = used;
        self
    }

    pub fn with_entry_exit(mut self, is_entry: bool, is_exit: bool) -> Self {
        self.is_entry = is_entry;
        self.is_exit = is_exit;
        self
    }
}

/// PDG Edge
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PDGEdge {
    pub from_node: String,
    pub to_node: String,
    pub dependency_type: DependencyType,
    pub label: Option<String>, // Variable name for data, condition for control
}

/// Serializable DTO for ProgramDependenceGraph
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PDGDto {
    pub function_id: String,
    pub nodes: Vec<PDGNode>,
    pub edges: Vec<PDGEdge>,
}

/// Program Dependence Graph
///
/// Uses petgraph for efficient graph operations:
/// - O(1) node/edge lookup
/// - O(V+E) traversal for slicing
#[derive(Debug)]
pub struct ProgramDependenceGraph {
    /// petgraph directed graph
    graph: DiGraph<PDGNode, PDGEdge>,
    /// Node ID to petgraph NodeIndex mapping
    node_map: HashMap<String, NodeIndex>,
    /// Function ID this PDG belongs to
    pub function_id: String,
}

// Custom serde implementation via DTO
impl serde::Serialize for ProgramDependenceGraph {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let dto = PDGDto {
            function_id: self.function_id.clone(),
            nodes: self.graph.node_weights().cloned().collect(),
            edges: self.graph.edge_weights().cloned().collect(),
        };
        dto.serialize(serializer)
    }
}

impl<'de> serde::Deserialize<'de> for ProgramDependenceGraph {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let dto = PDGDto::deserialize(deserializer)?;
        let mut pdg = ProgramDependenceGraph::new(dto.function_id);

        for node in dto.nodes {
            pdg.add_node(node);
        }

        for edge in dto.edges {
            pdg.add_edge(edge);
        }

        Ok(pdg)
    }
}

impl ProgramDependenceGraph {
    /// Create new empty PDG
    pub fn new(function_id: String) -> Self {
        ProgramDependenceGraph {
            graph: DiGraph::new(),
            node_map: HashMap::new(),
            function_id,
        }
    }

    /// Add node to PDG
    pub fn add_node(&mut self, node: PDGNode) -> NodeIndex {
        let node_id = node.node_id.clone();
        let idx = self.graph.add_node(node);
        self.node_map.insert(node_id, idx);
        idx
    }

    /// Add edge to PDG
    pub fn add_edge(&mut self, edge: PDGEdge) {
        let from_idx = self.node_map.get(&edge.from_node);
        let to_idx = self.node_map.get(&edge.to_node);

        if let (Some(&from), Some(&to)) = (from_idx, to_idx) {
            self.graph.add_edge(from, to, edge);
        }
    }

    /// Get node by ID
    pub fn get_node(&self, node_id: &str) -> Option<&PDGNode> {
        self.node_map
            .get(node_id)
            .and_then(|&idx| self.graph.node_weight(idx))
    }

    /// Get all incoming edges (dependencies) for a node
    pub fn get_dependencies(&self, node_id: &str) -> Vec<&PDGEdge> {
        let Some(&idx) = self.node_map.get(node_id) else {
            return Vec::new();
        };

        self.graph
            .edges_directed(idx, Direction::Incoming)
            .map(|e| e.weight())
            .collect()
    }

    /// Get all outgoing edges (dependents) for a node
    pub fn get_dependents(&self, node_id: &str) -> Vec<&PDGEdge> {
        let Some(&idx) = self.node_map.get(node_id) else {
            return Vec::new();
        };

        self.graph
            .edges_directed(idx, Direction::Outgoing)
            .map(|e| e.weight())
            .collect()
    }

    /// Backward slice: all nodes that affect target_node
    ///
    /// Implements Weiser's algorithm using BFS
    ///
    /// # Performance
    /// O(V + E) where V = nodes, E = edges
    pub fn backward_slice(&self, target_node: &str, max_depth: Option<usize>) -> HashSet<String> {
        self.backward_slice_filtered(target_node, max_depth, true, true)
    }

    /// Backward slice with dependency type filtering (Thin Slicing support)
    ///
    /// # Arguments
    /// * `target_node` - Starting node for backward traversal
    /// * `max_depth` - Maximum traversal depth (None = unlimited)
    /// * `include_control` - Include control dependencies (false = Thin Slice)
    /// * `include_data` - Include data dependencies
    ///
    /// # Thin Slicing
    /// Set `include_control=false` to get a thin slice (data dependencies only).
    /// Thin slices are typically 30-50% smaller than full slices.
    ///
    /// Reference: Sridharan et al., "Thin Slicing", PLDI 2007
    pub fn backward_slice_filtered(
        &self,
        target_node: &str,
        max_depth: Option<usize>,
        include_control: bool,
        include_data: bool,
    ) -> HashSet<String> {
        let max_depth = max_depth.unwrap_or(usize::MAX);
        let mut slice_nodes = HashSet::new();
        let mut visited = HashSet::new();
        let mut worklist: VecDeque<(String, usize)> = VecDeque::new();

        worklist.push_back((target_node.to_string(), 0));

        while let Some((current, depth)) = worklist.pop_front() {
            if depth > max_depth {
                continue;
            }

            if visited.contains(&current) {
                continue;
            }

            if !self.node_map.contains_key(&current) {
                continue;
            }

            visited.insert(current.clone());
            slice_nodes.insert(current.clone());

            // Get dependencies with type filtering
            for edge in self.get_dependencies(&current) {
                let should_follow = match edge.dependency_type {
                    DependencyType::Control => include_control,
                    DependencyType::Data => include_data,
                };

                if should_follow && !visited.contains(&edge.from_node) {
                    worklist.push_back((edge.from_node.clone(), depth + 1));
                }
            }
        }

        slice_nodes
    }

    /// Thin slice: backward slice with data dependencies only
    ///
    /// "Why does this variable have this value?" (ignoring control flow)
    ///
    /// Thin slices are smaller and more focused on direct data flow,
    /// useful for understanding value propagation without control context.
    ///
    /// Reference: Sridharan et al., "Thin Slicing", PLDI 2007
    pub fn thin_slice(&self, target_node: &str, max_depth: Option<usize>) -> HashSet<String> {
        self.backward_slice_filtered(target_node, max_depth, false, true)
    }

    /// Forward slice: all nodes affected by source_node
    ///
    /// # Performance
    /// O(V + E)
    pub fn forward_slice(&self, source_node: &str, max_depth: Option<usize>) -> HashSet<String> {
        self.forward_slice_filtered(source_node, max_depth, true, true)
    }

    /// Forward slice with dependency type filtering
    ///
    /// # Arguments
    /// * `source_node` - Starting node for forward traversal
    /// * `max_depth` - Maximum traversal depth (None = unlimited)
    /// * `include_control` - Include control dependencies
    /// * `include_data` - Include data dependencies
    pub fn forward_slice_filtered(
        &self,
        source_node: &str,
        max_depth: Option<usize>,
        include_control: bool,
        include_data: bool,
    ) -> HashSet<String> {
        let max_depth = max_depth.unwrap_or(usize::MAX);
        let mut slice_nodes = HashSet::new();
        let mut visited = HashSet::new();
        let mut worklist: VecDeque<(String, usize)> = VecDeque::new();

        worklist.push_back((source_node.to_string(), 0));

        while let Some((current, depth)) = worklist.pop_front() {
            if depth > max_depth {
                continue;
            }

            if visited.contains(&current) {
                continue;
            }

            if !self.node_map.contains_key(&current) {
                continue;
            }

            visited.insert(current.clone());
            slice_nodes.insert(current.clone());

            // Get dependents with type filtering
            for edge in self.get_dependents(&current) {
                let should_follow = match edge.dependency_type {
                    DependencyType::Control => include_control,
                    DependencyType::Data => include_data,
                };

                if should_follow && !visited.contains(&edge.to_node) {
                    worklist.push_back((edge.to_node.clone(), depth + 1));
                }
            }
        }

        slice_nodes
    }

    /// Hybrid slice: backward + forward union
    pub fn hybrid_slice(&self, focus_node: &str, max_depth: Option<usize>) -> HashSet<String> {
        let backward = self.backward_slice(focus_node, max_depth);
        let forward = self.forward_slice(focus_node, max_depth);

        backward.union(&forward).cloned().collect()
    }

    /// Chop: statements on paths from source to target
    ///
    /// `Chop(source, target) = backward_slice(target) ∩ forward_slice(source)`
    ///
    /// "What code connects source to target?"
    ///
    /// Useful for understanding:
    /// - How a value flows from definition to use
    /// - Impact analysis between two specific points
    ///
    /// Reference: Jackson & Rollins, "Chopping", FSE 1994
    pub fn chop(
        &self,
        source_node: &str,
        target_node: &str,
        max_depth: Option<usize>,
    ) -> HashSet<String> {
        let backward = self.backward_slice(target_node, max_depth);
        let forward = self.forward_slice(source_node, max_depth);

        backward.intersection(&forward).cloned().collect()
    }

    /// Chop with dependency type filtering
    pub fn chop_filtered(
        &self,
        source_node: &str,
        target_node: &str,
        max_depth: Option<usize>,
        include_control: bool,
        include_data: bool,
    ) -> HashSet<String> {
        let backward =
            self.backward_slice_filtered(target_node, max_depth, include_control, include_data);
        let forward =
            self.forward_slice_filtered(source_node, max_depth, include_control, include_data);

        backward.intersection(&forward).cloned().collect()
    }

    /// Get statistics
    pub fn get_stats(&self) -> PDGStats {
        let mut control_edges = 0;
        let mut data_edges = 0;

        for edge in self.graph.edge_weights() {
            match edge.dependency_type {
                DependencyType::Control => control_edges += 1,
                DependencyType::Data => data_edges += 1,
            }
        }

        PDGStats {
            node_count: self.graph.node_count(),
            edge_count: self.graph.edge_count(),
            control_edges,
            data_edges,
        }
    }

    /// Check if node exists
    pub fn contains_node(&self, node_id: &str) -> bool {
        self.node_map.contains_key(node_id)
    }

    /// Get all node IDs
    pub fn node_ids(&self) -> Vec<String> {
        self.node_map.keys().cloned().collect()
    }
}

/// PDG Statistics
#[derive(Debug, Clone)]
pub struct PDGStats {
    pub node_count: usize,
    pub edge_count: usize,
    pub control_edges: usize,
    pub data_edges: usize,
}

/// PDG Builder
///
/// Combines CFG and DFG into PDG
pub struct PDGBuilder {
    nodes: Vec<PDGNode>,
    cfg_edges: Vec<CFGEdge>,
    dfg_edges: Vec<(String, String, String)>, // (from, to, variable)
}

impl PDGBuilder {
    pub fn new() -> Self {
        PDGBuilder {
            nodes: Vec::new(),
            cfg_edges: Vec::new(),
            dfg_edges: Vec::new(),
        }
    }

    /// Add PDG node
    pub fn add_node(&mut self, node: PDGNode) {
        self.nodes.push(node);
    }

    /// Add CFG edges (control dependencies)
    pub fn add_cfg_edges(&mut self, edges: Vec<CFGEdge>) {
        self.cfg_edges.extend(edges);
    }

    /// Add DFG edges (data dependencies) from DataFlowGraph
    pub fn add_dfg(&mut self, dfg: &DataFlowGraph) {
        for &(def_idx, use_idx) in &dfg.def_use_edges {
            if let (Some(def_node), Some(_use_node)) =
                (dfg.nodes.get(def_idx), dfg.nodes.get(use_idx))
            {
                self.dfg_edges.push((
                    format!("{}_{}", dfg.function_id, def_idx),
                    format!("{}_{}", dfg.function_id, use_idx),
                    def_node.variable_name.clone(),
                ));
            }
        }
    }

    /// Build PDG from collected nodes and edges
    pub fn build(self, function_id: String) -> ProgramDependenceGraph {
        let mut pdg = ProgramDependenceGraph::new(function_id);

        // Add all nodes
        for node in self.nodes {
            pdg.add_node(node);
        }

        // Add control dependency edges (from CFG)
        for cfg_edge in self.cfg_edges {
            let label = match cfg_edge.edge_type {
                CFGEdgeType::True => Some("True".to_string()),
                CFGEdgeType::False => Some("False".to_string()),
                _ => None,
            };

            pdg.add_edge(PDGEdge {
                from_node: cfg_edge.source_block_id,
                to_node: cfg_edge.target_block_id,
                dependency_type: DependencyType::Control,
                label,
            });
        }

        // Add data dependency edges (from DFG)
        for (from, to, var) in self.dfg_edges {
            pdg.add_edge(PDGEdge {
                from_node: from,
                to_node: to,
                dependency_type: DependencyType::Data,
                label: Some(var),
            });
        }

        pdg
    }
}

impl Default for PDGBuilder {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_simple_pdg() -> ProgramDependenceGraph {
        let mut pdg = ProgramDependenceGraph::new("test_func".to_string());

        // Add nodes
        pdg.add_node(
            PDGNode::new(
                "n1".to_string(),
                "x = 1".to_string(),
                1,
                Span::new(1, 0, 1, 5),
            )
            .with_vars(vec!["x".to_string()], vec![]),
        );

        pdg.add_node(
            PDGNode::new(
                "n2".to_string(),
                "y = x + 1".to_string(),
                2,
                Span::new(2, 0, 2, 9),
            )
            .with_vars(vec!["y".to_string()], vec!["x".to_string()]),
        );

        pdg.add_node(
            PDGNode::new(
                "n3".to_string(),
                "z = y * 2".to_string(),
                3,
                Span::new(3, 0, 3, 9),
            )
            .with_vars(vec!["z".to_string()], vec!["y".to_string()]),
        );

        // Add data dependency edges
        pdg.add_edge(PDGEdge {
            from_node: "n1".to_string(),
            to_node: "n2".to_string(),
            dependency_type: DependencyType::Data,
            label: Some("x".to_string()),
        });

        pdg.add_edge(PDGEdge {
            from_node: "n2".to_string(),
            to_node: "n3".to_string(),
            dependency_type: DependencyType::Data,
            label: Some("y".to_string()),
        });

        // Add control edges
        pdg.add_edge(PDGEdge {
            from_node: "n1".to_string(),
            to_node: "n2".to_string(),
            dependency_type: DependencyType::Control,
            label: None,
        });

        pdg.add_edge(PDGEdge {
            from_node: "n2".to_string(),
            to_node: "n3".to_string(),
            dependency_type: DependencyType::Control,
            label: None,
        });

        pdg
    }

    #[test]
    fn test_pdg_creation() {
        let pdg = create_simple_pdg();
        let stats = pdg.get_stats();

        assert_eq!(stats.node_count, 3);
        assert_eq!(stats.edge_count, 4); // 2 data + 2 control
        assert_eq!(stats.data_edges, 2);
        assert_eq!(stats.control_edges, 2);
    }

    #[test]
    fn test_backward_slice() {
        let pdg = create_simple_pdg();

        // Backward slice from n3 should include n1, n2, n3
        let slice = pdg.backward_slice("n3", None);

        assert_eq!(slice.len(), 3);
        assert!(slice.contains("n1"));
        assert!(slice.contains("n2"));
        assert!(slice.contains("n3"));
    }

    #[test]
    fn test_backward_slice_with_depth() {
        let pdg = create_simple_pdg();

        // Backward slice from n3 with depth 1 should only include n2, n3
        let slice = pdg.backward_slice("n3", Some(1));

        assert_eq!(slice.len(), 2);
        assert!(slice.contains("n2"));
        assert!(slice.contains("n3"));
        assert!(!slice.contains("n1"));
    }

    #[test]
    fn test_forward_slice() {
        let pdg = create_simple_pdg();

        // Forward slice from n1 should include n1, n2, n3
        let slice = pdg.forward_slice("n1", None);

        assert_eq!(slice.len(), 3);
        assert!(slice.contains("n1"));
        assert!(slice.contains("n2"));
        assert!(slice.contains("n3"));
    }

    #[test]
    fn test_forward_slice_with_depth() {
        let pdg = create_simple_pdg();

        // Forward slice from n1 with depth 1 should only include n1, n2
        let slice = pdg.forward_slice("n1", Some(1));

        assert_eq!(slice.len(), 2);
        assert!(slice.contains("n1"));
        assert!(slice.contains("n2"));
        assert!(!slice.contains("n3"));
    }

    #[test]
    fn test_hybrid_slice() {
        let pdg = create_simple_pdg();

        // Hybrid slice from n2 should include all nodes
        let slice = pdg.hybrid_slice("n2", None);

        assert_eq!(slice.len(), 3);
    }

    #[test]
    fn test_get_dependencies() {
        let pdg = create_simple_pdg();

        let deps = pdg.get_dependencies("n3");
        assert_eq!(deps.len(), 2); // 1 data + 1 control from n2
    }

    #[test]
    fn test_get_dependents() {
        let pdg = create_simple_pdg();

        let deps = pdg.get_dependents("n1");
        assert_eq!(deps.len(), 2); // 1 data + 1 control to n2
    }

    #[test]
    fn test_empty_pdg() {
        let pdg = ProgramDependenceGraph::new("empty".to_string());
        let stats = pdg.get_stats();

        assert_eq!(stats.node_count, 0);
        assert_eq!(stats.edge_count, 0);
    }

    #[test]
    fn test_nonexistent_node_slice() {
        let pdg = create_simple_pdg();

        // Slice on nonexistent node should return empty set
        let slice = pdg.backward_slice("nonexistent", None);
        assert!(slice.is_empty());
    }

    #[test]
    fn test_pdg_builder() {
        let mut builder = PDGBuilder::new();

        builder.add_node(PDGNode::new(
            "b1".to_string(),
            "a = 1".to_string(),
            1,
            Span::new(1, 0, 1, 5),
        ));

        builder.add_node(PDGNode::new(
            "b2".to_string(),
            "b = a".to_string(),
            2,
            Span::new(2, 0, 2, 5),
        ));

        let pdg = builder.build("builder_test".to_string());

        assert_eq!(pdg.get_stats().node_count, 2);
    }

    // Large scale test
    #[test]
    fn test_large_scale_pdg() {
        let mut pdg = ProgramDependenceGraph::new("large".to_string());

        // Add 1000 nodes
        for i in 0..1000 {
            pdg.add_node(PDGNode::new(
                format!("n{}", i),
                format!("stmt_{}", i),
                i as u32,
                Span::new(i as u32, 0, i as u32, 10),
            ));
        }

        // Add chain of edges
        for i in 0..999 {
            pdg.add_edge(PDGEdge {
                from_node: format!("n{}", i),
                to_node: format!("n{}", i + 1),
                dependency_type: DependencyType::Data,
                label: Some(format!("v{}", i)),
            });
        }

        let stats = pdg.get_stats();
        assert_eq!(stats.node_count, 1000);
        assert_eq!(stats.edge_count, 999);

        // Backward slice from last node should include all
        let slice = pdg.backward_slice("n999", None);
        assert_eq!(slice.len(), 1000);

        // Forward slice from first node should include all
        let slice = pdg.forward_slice("n0", None);
        assert_eq!(slice.len(), 1000);
    }

    // ============================================================
    // NEW: Thin Slicing & Chop Tests
    // ============================================================

    #[test]
    fn test_thin_slice_data_only() {
        let pdg = create_simple_pdg();

        // Thin slice = data dependencies only
        // create_simple_pdg has both data and control edges from n1→n2→n3
        let thin = pdg.thin_slice("n3", None);
        let full = pdg.backward_slice("n3", None);

        // Both should include all nodes in this simple chain
        // (since data edges alone form a complete path)
        assert_eq!(thin.len(), 3);
        assert_eq!(full.len(), 3);
    }

    #[test]
    fn test_backward_slice_control_only() {
        let pdg = create_simple_pdg();

        // Control dependencies only (no data)
        let control_only = pdg.backward_slice_filtered("n3", None, true, false);

        // Should still include n1, n2, n3 via control edges
        assert_eq!(control_only.len(), 3);
    }

    #[test]
    fn test_backward_slice_data_only() {
        let pdg = create_simple_pdg();

        // Data dependencies only (no control) = thin slice
        let data_only = pdg.backward_slice_filtered("n3", None, false, true);

        // Should still include n1, n2, n3 via data edges
        assert_eq!(data_only.len(), 3);
    }

    #[test]
    fn test_thin_slice_smaller_than_full() {
        // Create PDG where control edges connect more nodes than data edges
        let mut pdg = ProgramDependenceGraph::new("control_heavy".to_string());

        // n1 → n2 → n3 (data chain)
        // n4 → n2 (control only, no data)
        pdg.add_node(PDGNode::new(
            "n1".to_string(),
            "x = 1".to_string(),
            1,
            Span::new(1, 0, 1, 5),
        ));
        pdg.add_node(PDGNode::new(
            "n2".to_string(),
            "y = x".to_string(),
            2,
            Span::new(2, 0, 2, 5),
        ));
        pdg.add_node(PDGNode::new(
            "n3".to_string(),
            "z = y".to_string(),
            3,
            Span::new(3, 0, 3, 5),
        ));
        pdg.add_node(PDGNode::new(
            "n4".to_string(),
            "if cond".to_string(),
            4,
            Span::new(4, 0, 4, 7),
        ));

        // Data edges: n1 → n2 → n3
        pdg.add_edge(PDGEdge {
            from_node: "n1".to_string(),
            to_node: "n2".to_string(),
            dependency_type: DependencyType::Data,
            label: Some("x".to_string()),
        });
        pdg.add_edge(PDGEdge {
            from_node: "n2".to_string(),
            to_node: "n3".to_string(),
            dependency_type: DependencyType::Data,
            label: Some("y".to_string()),
        });

        // Control edge: n4 → n2 (n2 is control-dependent on n4)
        pdg.add_edge(PDGEdge {
            from_node: "n4".to_string(),
            to_node: "n2".to_string(),
            dependency_type: DependencyType::Control,
            label: Some("True".to_string()),
        });

        // Full backward slice from n3: should include n1, n2, n3, n4
        let full = pdg.backward_slice("n3", None);
        assert_eq!(full.len(), 4);
        assert!(full.contains("n4")); // Control dependency included

        // Thin slice from n3: should only include n1, n2, n3
        let thin = pdg.thin_slice("n3", None);
        assert_eq!(thin.len(), 3);
        assert!(!thin.contains("n4")); // Control dependency excluded!

        // Thin slice is smaller!
        assert!(thin.len() < full.len());
    }

    #[test]
    fn test_chop_basic() {
        let pdg = create_simple_pdg();

        // Chop(n1, n3) = forward(n1) ∩ backward(n3)
        // Both should include all nodes, so chop = all nodes
        let chop = pdg.chop("n1", "n3", None);

        assert_eq!(chop.len(), 3);
        assert!(chop.contains("n1"));
        assert!(chop.contains("n2"));
        assert!(chop.contains("n3"));
    }

    #[test]
    fn test_chop_middle_node() {
        let pdg = create_simple_pdg();

        // Chop(n1, n2) should only include n1, n2
        let chop = pdg.chop("n1", "n2", None);

        assert_eq!(chop.len(), 2);
        assert!(chop.contains("n1"));
        assert!(chop.contains("n2"));
        assert!(!chop.contains("n3")); // n3 is after n2
    }

    #[test]
    fn test_chop_disjoint() {
        // Test chop with no path between source and target
        let mut pdg = ProgramDependenceGraph::new("disjoint".to_string());

        pdg.add_node(PDGNode::new(
            "a".to_string(),
            "x = 1".to_string(),
            1,
            Span::new(1, 0, 1, 5),
        ));
        pdg.add_node(PDGNode::new(
            "b".to_string(),
            "y = 2".to_string(),
            2,
            Span::new(2, 0, 2, 5),
        ));

        // No edges between a and b
        let chop = pdg.chop("a", "b", None);

        // Chop should be empty (no path from a to b)
        assert!(chop.is_empty());
    }

    #[test]
    fn test_chop_same_node() {
        let pdg = create_simple_pdg();

        // Chop(n2, n2) should only include n2
        let chop = pdg.chop("n2", "n2", None);

        assert_eq!(chop.len(), 1);
        assert!(chop.contains("n2"));
    }

    #[test]
    fn test_forward_slice_filtered() {
        let mut pdg = ProgramDependenceGraph::new("forward_filter".to_string());

        pdg.add_node(PDGNode::new(
            "n1".to_string(),
            "x = 1".to_string(),
            1,
            Span::new(1, 0, 1, 5),
        ));
        pdg.add_node(PDGNode::new(
            "n2".to_string(),
            "y = x".to_string(),
            2,
            Span::new(2, 0, 2, 5),
        ));
        pdg.add_node(PDGNode::new(
            "n3".to_string(),
            "z = 3".to_string(),
            3,
            Span::new(3, 0, 3, 5),
        ));

        // Data edge: n1 → n2
        pdg.add_edge(PDGEdge {
            from_node: "n1".to_string(),
            to_node: "n2".to_string(),
            dependency_type: DependencyType::Data,
            label: Some("x".to_string()),
        });

        // Control edge: n1 → n3
        pdg.add_edge(PDGEdge {
            from_node: "n1".to_string(),
            to_node: "n3".to_string(),
            dependency_type: DependencyType::Control,
            label: None,
        });

        // Data-only forward slice from n1
        let data_only = pdg.forward_slice_filtered("n1", None, false, true);
        assert_eq!(data_only.len(), 2); // n1, n2
        assert!(!data_only.contains("n3"));

        // Control-only forward slice from n1
        let control_only = pdg.forward_slice_filtered("n1", None, true, false);
        assert_eq!(control_only.len(), 2); // n1, n3
        assert!(!control_only.contains("n2"));

        // Full forward slice
        let full = pdg.forward_slice("n1", None);
        assert_eq!(full.len(), 3); // n1, n2, n3
    }

    #[test]
    fn test_chop_filtered() {
        let pdg = create_simple_pdg();

        // Chop with data-only should still work
        let chop = pdg.chop_filtered("n1", "n3", None, false, true);
        assert_eq!(chop.len(), 3);
    }

    // ============================================================
    // EDGE CASES: L11 SOTA Coverage
    // ============================================================

    /// Edge case: Both include_control and include_data are false
    /// Should return only the starting node (no traversal)
    #[test]
    fn test_slice_both_flags_false() {
        let pdg = create_simple_pdg();

        // Backward slice with no dependencies followed
        let result = pdg.backward_slice_filtered("n3", None, false, false);
        assert_eq!(result.len(), 1);
        assert!(result.contains("n3")); // Only starting node

        // Forward slice with no dependencies followed
        let result = pdg.forward_slice_filtered("n1", None, false, false);
        assert_eq!(result.len(), 1);
        assert!(result.contains("n1")); // Only starting node
    }

    /// Edge case: max_depth = 0 should return only starting node
    #[test]
    fn test_slice_max_depth_zero() {
        let pdg = create_simple_pdg();

        let result = pdg.backward_slice("n3", Some(0));
        assert_eq!(result.len(), 1);
        assert!(result.contains("n3"));

        let result = pdg.forward_slice("n1", Some(0));
        assert_eq!(result.len(), 1);
        assert!(result.contains("n1"));

        let result = pdg.thin_slice("n3", Some(0));
        assert_eq!(result.len(), 1);
        assert!(result.contains("n3"));
    }

    /// Edge case: Self-loop (node depends on itself)
    #[test]
    fn test_self_loop() {
        let mut pdg = ProgramDependenceGraph::new("selfloop".to_string());

        pdg.add_node(PDGNode::new(
            "loop".to_string(),
            "x = x + 1".to_string(),
            1,
            Span::new(1, 0, 1, 9),
        ));

        // Self-referencing edge
        pdg.add_edge(PDGEdge {
            from_node: "loop".to_string(),
            to_node: "loop".to_string(),
            dependency_type: DependencyType::Data,
            label: Some("x".to_string()),
        });

        // Should not infinite loop, should return just the node
        let result = pdg.backward_slice("loop", None);
        assert_eq!(result.len(), 1);
        assert!(result.contains("loop"));

        let result = pdg.forward_slice("loop", None);
        assert_eq!(result.len(), 1);
        assert!(result.contains("loop"));

        let result = pdg.thin_slice("loop", None);
        assert_eq!(result.len(), 1);
    }

    /// Edge case: Cyclic graph (A → B → C → A)
    #[test]
    fn test_cyclic_graph() {
        let mut pdg = ProgramDependenceGraph::new("cycle".to_string());

        pdg.add_node(PDGNode::new(
            "a".to_string(),
            "a".to_string(),
            1,
            Span::new(1, 0, 1, 1),
        ));
        pdg.add_node(PDGNode::new(
            "b".to_string(),
            "b".to_string(),
            2,
            Span::new(2, 0, 2, 1),
        ));
        pdg.add_node(PDGNode::new(
            "c".to_string(),
            "c".to_string(),
            3,
            Span::new(3, 0, 3, 1),
        ));

        // Cycle: a → b → c → a
        pdg.add_edge(PDGEdge {
            from_node: "a".to_string(),
            to_node: "b".to_string(),
            dependency_type: DependencyType::Data,
            label: None,
        });
        pdg.add_edge(PDGEdge {
            from_node: "b".to_string(),
            to_node: "c".to_string(),
            dependency_type: DependencyType::Data,
            label: None,
        });
        pdg.add_edge(PDGEdge {
            from_node: "c".to_string(),
            to_node: "a".to_string(),
            dependency_type: DependencyType::Data,
            label: None,
        });

        // Should not infinite loop, should return all nodes
        let result = pdg.backward_slice("a", None);
        assert_eq!(result.len(), 3);

        let result = pdg.forward_slice("a", None);
        assert_eq!(result.len(), 3);

        // Chop in cycle should include all
        let result = pdg.chop("a", "c", None);
        assert_eq!(result.len(), 3);
    }

    /// Edge case: Empty PDG operations
    #[test]
    fn test_empty_pdg_thin_slice() {
        let pdg = ProgramDependenceGraph::new("empty".to_string());

        // thin_slice on empty PDG
        let result = pdg.thin_slice("nonexistent", None);
        assert!(result.is_empty());
    }

    /// Edge case: Empty PDG chop
    #[test]
    fn test_empty_pdg_chop() {
        let pdg = ProgramDependenceGraph::new("empty".to_string());

        let result = pdg.chop("a", "b", None);
        assert!(result.is_empty());
    }

    /// Edge case: Chop with reversed direction (target before source in graph)
    #[test]
    fn test_chop_reversed() {
        let pdg = create_simple_pdg(); // n1 → n2 → n3

        // Chop(n3, n1) - n3 is after n1, so forward(n3) ∩ backward(n1) = empty
        let result = pdg.chop("n3", "n1", None);
        assert!(result.is_empty());
    }

    /// Extreme case: Wide graph (high fan-out)
    #[test]
    fn test_wide_graph() {
        let mut pdg = ProgramDependenceGraph::new("wide".to_string());

        // Root node with 100 children
        pdg.add_node(PDGNode::new(
            "root".to_string(),
            "root".to_string(),
            0,
            Span::new(0, 0, 0, 4),
        ));

        for i in 0..100 {
            let child = format!("child_{}", i);
            pdg.add_node(PDGNode::new(
                child.clone(),
                child.clone(),
                (i + 1) as u32,
                Span::new((i + 1) as u32, 0, (i + 1) as u32, 10),
            ));
            pdg.add_edge(PDGEdge {
                from_node: "root".to_string(),
                to_node: child,
                dependency_type: DependencyType::Data,
                label: None,
            });
        }

        // Forward slice from root should include all 101 nodes
        let result = pdg.forward_slice("root", None);
        assert_eq!(result.len(), 101);

        // Backward slice from any child should include root + that child
        let result = pdg.backward_slice("child_50", None);
        assert_eq!(result.len(), 2);
        assert!(result.contains("root"));
        assert!(result.contains("child_50"));
    }

    /// Extreme case: Deep graph (long chain)
    #[test]
    fn test_deep_graph_with_depth_limit() {
        let mut pdg = ProgramDependenceGraph::new("deep".to_string());

        // Chain of 100 nodes: n0 → n1 → ... → n99
        for i in 0..100 {
            pdg.add_node(PDGNode::new(
                format!("n{}", i),
                format!("n{}", i),
                i as u32,
                Span::new(i as u32, 0, i as u32, 2),
            ));
            if i > 0 {
                pdg.add_edge(PDGEdge {
                    from_node: format!("n{}", i - 1),
                    to_node: format!("n{}", i),
                    dependency_type: DependencyType::Data,
                    label: None,
                });
            }
        }

        // Backward slice with depth limit
        let result = pdg.backward_slice("n99", Some(10));
        assert_eq!(result.len(), 11); // n89 to n99

        // Forward slice with depth limit
        let result = pdg.forward_slice("n0", Some(5));
        assert_eq!(result.len(), 6); // n0 to n5

        // Thin slice with depth limit
        let result = pdg.thin_slice("n50", Some(3));
        assert_eq!(result.len(), 4); // n47, n48, n49, n50
    }

    /// Mixed dependency types with filtering
    #[test]
    fn test_mixed_dependencies_complex() {
        let mut pdg = ProgramDependenceGraph::new("mixed".to_string());

        // Graph:
        //   n1 --data--> n2 --control--> n3
        //        \--control--> n4 --data--> n3
        pdg.add_node(PDGNode::new(
            "n1".to_string(),
            "n1".to_string(),
            1,
            Span::new(1, 0, 1, 2),
        ));
        pdg.add_node(PDGNode::new(
            "n2".to_string(),
            "n2".to_string(),
            2,
            Span::new(2, 0, 2, 2),
        ));
        pdg.add_node(PDGNode::new(
            "n3".to_string(),
            "n3".to_string(),
            3,
            Span::new(3, 0, 3, 2),
        ));
        pdg.add_node(PDGNode::new(
            "n4".to_string(),
            "n4".to_string(),
            4,
            Span::new(4, 0, 4, 2),
        ));

        pdg.add_edge(PDGEdge {
            from_node: "n1".to_string(),
            to_node: "n2".to_string(),
            dependency_type: DependencyType::Data,
            label: None,
        });
        pdg.add_edge(PDGEdge {
            from_node: "n2".to_string(),
            to_node: "n3".to_string(),
            dependency_type: DependencyType::Control,
            label: None,
        });
        pdg.add_edge(PDGEdge {
            from_node: "n1".to_string(),
            to_node: "n4".to_string(),
            dependency_type: DependencyType::Control,
            label: None,
        });
        pdg.add_edge(PDGEdge {
            from_node: "n4".to_string(),
            to_node: "n3".to_string(),
            dependency_type: DependencyType::Data,
            label: None,
        });

        // Full backward slice from n3: all 4 nodes
        let full = pdg.backward_slice("n3", None);
        assert_eq!(full.len(), 4);

        // Data-only backward slice from n3: n3, n4, n1 (via n1→n4 is control, so n1 not included via n4)
        // Path: n3 ←data← n4, but n4 ←control← n1, so n1 not included
        let data_only = pdg.backward_slice_filtered("n3", None, false, true);
        assert_eq!(data_only.len(), 2); // n3, n4 (n1 requires control edge to reach n4)
        assert!(data_only.contains("n3"));
        assert!(data_only.contains("n4"));
        assert!(!data_only.contains("n1")); // n1→n4 is control, excluded

        // Control-only: n3 ←control← n2 ←?← n1
        // n2 ←data← n1, so n1 not included via control-only
        let control_only = pdg.backward_slice_filtered("n3", None, true, false);
        assert_eq!(control_only.len(), 2); // n3, n2
        assert!(!control_only.contains("n1")); // n1→n2 is data, excluded
    }
}
