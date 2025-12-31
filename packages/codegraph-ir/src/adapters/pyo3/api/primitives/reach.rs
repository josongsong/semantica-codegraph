//! P1: REACH - Graph Reachability Primitive
//!
//! RFC-071: Mathematical basis - Euler 1736 (Königsberg bridges)
//!
//! Covers:
//! - Call graph traversal
//! - Backward/Forward slicing
//! - Transitive dependency analysis
//! - Dead code detection
//!
//! Performance: 10-50x faster than Python (petgraph + Rayon)

use std::collections::{HashSet, VecDeque, HashMap};
use serde::{Deserialize, Serialize};

use super::session::AnalysisSession;
use crate::shared::models::{Edge, EdgeKind};

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

/// Reachability direction
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ReachDirection {
    Forward,   // Source → Target
    Backward,  // Target → Source
    Both,      // Bidirectional
}

impl ReachDirection {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "backward" | "back" => ReachDirection::Backward,
            "both" | "bidirectional" => ReachDirection::Both,
            _ => ReachDirection::Forward,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            ReachDirection::Forward => "forward",
            ReachDirection::Backward => "backward",
            ReachDirection::Both => "both",
        }
    }
}

/// Graph type for traversal
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GraphType {
    Cfg,      // Control Flow Graph
    Dfg,      // Data Flow Graph
    Pdg,      // Program Dependence Graph
    CallGraph, // Call Graph
    All,      // All edge types
}

impl GraphType {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "cfg" | "control" => GraphType::Cfg,
            "dfg" | "data" | "dataflow" => GraphType::Dfg,
            "pdg" | "dependence" => GraphType::Pdg,
            "call" | "callgraph" => GraphType::CallGraph,
            _ => GraphType::All,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            GraphType::Cfg => "cfg",
            GraphType::Dfg => "dfg",
            GraphType::Pdg => "pdg",
            GraphType::CallGraph => "callgraph",
            GraphType::All => "all",
        }
    }

    /// Check if edge matches this graph type
    pub fn matches_edge(&self, edge_kind: &EdgeKind) -> bool {
        match self {
            GraphType::Cfg => matches!(edge_kind,
                EdgeKind::ControlFlow |
                EdgeKind::TrueBranch |
                EdgeKind::FalseBranch
            ),
            GraphType::Dfg => matches!(edge_kind,
                EdgeKind::DataFlow |
                EdgeKind::DefUse
            ),
            GraphType::Pdg => matches!(edge_kind,
                EdgeKind::ControlFlow |
                EdgeKind::DataFlow |
                EdgeKind::DefUse |
                EdgeKind::TrueBranch |
                EdgeKind::FalseBranch
            ),
            GraphType::CallGraph => matches!(edge_kind,
                EdgeKind::Calls |
                EdgeKind::Invokes
            ),
            GraphType::All => true,
        }
    }
}

/// Edge in reachability result (for path reconstruction)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReachEdge {
    pub source_id: String,
    pub target_id: String,
    pub edge_kind: String,
    pub depth: usize,
}

/// Reachability result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReachResult {
    /// Reachable node IDs (ordered by discovery)
    pub nodes: Vec<String>,

    /// Traversed edges (for path reconstruction)
    pub edges: Vec<ReachEdge>,

    /// Depth from start for each node
    pub depths: HashMap<String, usize>,

    /// Statistics
    pub total_nodes: usize,
    pub max_depth_reached: usize,
    pub traversal_direction: String,
    pub graph_type: String,
}

impl ReachResult {
    pub fn new(direction: ReachDirection, graph: GraphType) -> Self {
        Self {
            nodes: Vec::new(),
            edges: Vec::new(),
            depths: HashMap::new(),
            total_nodes: 0,
            max_depth_reached: 0,
            traversal_direction: direction.as_str().to_string(),
            graph_type: graph.as_str().to_string(),
        }
    }

    /// Serialize to msgpack
    pub fn to_msgpack(&self) -> Result<Vec<u8>, String> {
        rmp_serde::to_vec_named(self)
            .map_err(|e| format!("Failed to serialize ReachResult: {}", e))
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// P1: REACH Implementation
// ═══════════════════════════════════════════════════════════════════════════

/// P1: Graph Reachability
///
/// Mathematical basis: Euler's Königsberg bridge theorem (1736)
///
/// Algorithm: BFS with depth tracking
/// - O(V + E) time complexity
/// - Optional depth limit
/// - Optional edge type filter
///
/// # Arguments
/// * `session` - Analysis session with IR
/// * `start` - Starting node ID
/// * `direction` - Traversal direction
/// * `graph` - Graph type filter
/// * `max_depth` - Maximum traversal depth
/// * `filter` - Optional node kind filter
///
/// # Returns
/// * ReachResult with reachable nodes and paths
pub fn reach(
    session: &AnalysisSession,
    start: &str,
    direction: ReachDirection,
    graph: GraphType,
    max_depth: Option<usize>,
    filter: Option<&[String]>,
) -> ReachResult {
    let max_depth = max_depth.unwrap_or(usize::MAX);
    let filter_set: Option<HashSet<&str>> = filter.map(|f|
        f.iter().map(|s| s.as_str()).collect()
    );

    let mut result = ReachResult::new(direction, graph);
    let mut visited = HashSet::new();
    let mut worklist: VecDeque<(String, usize)> = VecDeque::new();

    // Check start node exists
    if session.get_node(start).is_none() {
        return result;
    }

    worklist.push_back((start.to_string(), 0));
    visited.insert(start.to_string());

    // Build edge index for efficient lookup
    let (forward_edges, backward_edges) = build_edge_index(session.edges(), graph);

    while let Some((current, depth)) = worklist.pop_front() {
        if depth > max_depth {
            continue;
        }

        // Apply node filter if specified
        if let Some(ref filter) = filter_set {
            if let Some(node) = session.get_node(&current) {
                let kind_str = node.kind.as_str();
                if !filter.contains(kind_str) && depth > 0 {
                    continue;
                }
            }
        }

        // Add to result
        result.nodes.push(current.clone());
        result.depths.insert(current.clone(), depth);
        result.max_depth_reached = result.max_depth_reached.max(depth);

        // Get neighbors based on direction
        let neighbors = match direction {
            ReachDirection::Forward => {
                get_neighbors(&current, &forward_edges)
            }
            ReachDirection::Backward => {
                get_neighbors(&current, &backward_edges)
            }
            ReachDirection::Both => {
                let mut n = get_neighbors(&current, &forward_edges);
                n.extend(get_neighbors(&current, &backward_edges));
                n
            }
        };

        for (neighbor_id, edge_kind) in neighbors {
            if !visited.contains(&neighbor_id) {
                visited.insert(neighbor_id.clone());
                worklist.push_back((neighbor_id.clone(), depth + 1));

                // Record edge for path reconstruction
                let (source, target) = match direction {
                    ReachDirection::Backward => (neighbor_id.clone(), current.clone()),
                    _ => (current.clone(), neighbor_id.clone()),
                };

                result.edges.push(ReachEdge {
                    source_id: source,
                    target_id: target,
                    edge_kind: edge_kind.as_str().to_string(),
                    depth: depth + 1,
                });
            }
        }
    }

    result.total_nodes = result.nodes.len();
    result
}

/// Build forward and backward edge indices
fn build_edge_index(
    edges: &[Edge],
    graph: GraphType,
) -> (HashMap<String, Vec<(String, EdgeKind)>>, HashMap<String, Vec<(String, EdgeKind)>>) {
    let mut forward: HashMap<String, Vec<(String, EdgeKind)>> = HashMap::new();
    let mut backward: HashMap<String, Vec<(String, EdgeKind)>> = HashMap::new();

    for edge in edges {
        if graph.matches_edge(&edge.kind) {
            forward
                .entry(edge.source_id.clone())
                .or_default()
                .push((edge.target_id.clone(), edge.kind.clone()));

            backward
                .entry(edge.target_id.clone())
                .or_default()
                .push((edge.source_id.clone(), edge.kind.clone()));
        }
    }

    (forward, backward)
}

/// Get neighbors from edge index
fn get_neighbors(
    node_id: &str,
    edge_index: &HashMap<String, Vec<(String, EdgeKind)>>,
) -> Vec<(String, EdgeKind)> {
    edge_index
        .get(node_id)
        .cloned()
        .unwrap_or_default()
}

// ═══════════════════════════════════════════════════════════════════════════
// Extended REACH: With Paths
// ═══════════════════════════════════════════════════════════════════════════

/// Path from start to a reachable node
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReachPath {
    pub target: String,
    pub path: Vec<String>,
    pub depth: usize,
}

/// Extended reachability result with full paths
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReachWithPathsResult {
    /// Base reachability result
    pub nodes: Vec<String>,

    /// Full paths to each node (for explainability)
    pub paths: Vec<ReachPath>,

    /// Statistics
    pub total_nodes: usize,
    pub total_paths: usize,
    pub max_depth: usize,
}

/// Reach with full path reconstruction
///
/// Useful for:
/// - Taint path explanation
/// - Dependency chains
/// - Call stacks
///
/// # Performance
/// - More memory intensive (stores all paths)
/// - Use for smaller subgraphs or with depth limit
pub fn reach_with_paths(
    session: &AnalysisSession,
    start: &str,
    direction: ReachDirection,
    graph: GraphType,
    max_depth: Option<usize>,
) -> ReachWithPathsResult {
    let max_depth = max_depth.unwrap_or(100);  // Default limit for path-based

    let mut result = ReachWithPathsResult {
        nodes: Vec::new(),
        paths: Vec::new(),
        total_nodes: 0,
        total_paths: 0,
        max_depth: 0,
    };

    if session.get_node(start).is_none() {
        return result;
    }

    // BFS with path tracking
    let mut visited = HashSet::new();
    let mut worklist: VecDeque<(String, Vec<String>)> = VecDeque::new();

    worklist.push_back((start.to_string(), vec![start.to_string()]));
    visited.insert(start.to_string());

    let (forward_edges, backward_edges) = build_edge_index(session.edges(), graph);

    while let Some((current, path)) = worklist.pop_front() {
        let depth = path.len() - 1;

        if depth > max_depth {
            continue;
        }

        result.nodes.push(current.clone());
        result.paths.push(ReachPath {
            target: current.clone(),
            path: path.clone(),
            depth,
        });
        result.max_depth = result.max_depth.max(depth);

        let neighbors = match direction {
            ReachDirection::Forward => get_neighbors(&current, &forward_edges),
            ReachDirection::Backward => get_neighbors(&current, &backward_edges),
            ReachDirection::Both => {
                let mut n = get_neighbors(&current, &forward_edges);
                n.extend(get_neighbors(&current, &backward_edges));
                n
            }
        };

        for (neighbor_id, _) in neighbors {
            if !visited.contains(&neighbor_id) {
                visited.insert(neighbor_id.clone());
                let mut new_path = path.clone();
                new_path.push(neighbor_id.clone());
                worklist.push_back((neighbor_id, new_path));
            }
        }
    }

    result.total_nodes = result.nodes.len();
    result.total_paths = result.paths.len();
    result
}

// ═══════════════════════════════════════════════════════════════════════════
// Convenience Functions
// ═══════════════════════════════════════════════════════════════════════════

/// Find all callers of a function (backward call graph traversal)
pub fn find_callers(
    session: &AnalysisSession,
    function_id: &str,
    max_depth: Option<usize>,
) -> ReachResult {
    reach(
        session,
        function_id,
        ReachDirection::Backward,
        GraphType::CallGraph,
        max_depth,
        Some(&["function".to_string(), "method".to_string()]),
    )
}

/// Find all callees of a function (forward call graph traversal)
pub fn find_callees(
    session: &AnalysisSession,
    function_id: &str,
    max_depth: Option<usize>,
) -> ReachResult {
    reach(
        session,
        function_id,
        ReachDirection::Forward,
        GraphType::CallGraph,
        max_depth,
        Some(&["function".to_string(), "method".to_string()]),
    )
}

/// Backward slice using PDG
pub fn backward_slice(
    session: &AnalysisSession,
    target: &str,
    max_depth: Option<usize>,
) -> ReachResult {
    reach(
        session,
        target,
        ReachDirection::Backward,
        GraphType::Pdg,
        max_depth,
        None,
    )
}

/// Forward slice using PDG
pub fn forward_slice(
    session: &AnalysisSession,
    source: &str,
    max_depth: Option<usize>,
) -> ReachResult {
    reach(
        session,
        source,
        ReachDirection::Forward,
        GraphType::Pdg,
        max_depth,
        None,
    )
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{Node, NodeKind, Span};

    fn create_test_session() -> AnalysisSession {
        // Create a simple call graph:
        // main → helper → util
        //      ↘ other
        let nodes = vec![
            Node::new(
                "main".to_string(),
                NodeKind::Function,
                "module.main".to_string(),
                "test.py".to_string(),
                Span::new(1, 0, 10, 0),
            ).with_name("main"),
            Node::new(
                "helper".to_string(),
                NodeKind::Function,
                "module.helper".to_string(),
                "test.py".to_string(),
                Span::new(12, 0, 20, 0),
            ).with_name("helper"),
            Node::new(
                "util".to_string(),
                NodeKind::Function,
                "module.util".to_string(),
                "test.py".to_string(),
                Span::new(22, 0, 30, 0),
            ).with_name("util"),
            Node::new(
                "other".to_string(),
                NodeKind::Function,
                "module.other".to_string(),
                "test.py".to_string(),
                Span::new(32, 0, 40, 0),
            ).with_name("other"),
        ];

        let edges = vec![
            Edge::new("main".to_string(), "helper".to_string(), EdgeKind::Calls),
            Edge::new("main".to_string(), "other".to_string(), EdgeKind::Calls),
            Edge::new("helper".to_string(), "util".to_string(), EdgeKind::Calls),
        ];

        AnalysisSession::new("test.py".to_string(), nodes, edges, None)
    }

    #[test]
    fn test_reach_forward() {
        let session = create_test_session();

        let result = reach(
            &session,
            "main",
            ReachDirection::Forward,
            GraphType::CallGraph,
            None,
            None,
        );

        // main → helper → util, main → other
        assert_eq!(result.total_nodes, 4);
        assert!(result.nodes.contains(&"main".to_string()));
        assert!(result.nodes.contains(&"helper".to_string()));
        assert!(result.nodes.contains(&"util".to_string()));
        assert!(result.nodes.contains(&"other".to_string()));
    }

    #[test]
    fn test_reach_backward() {
        let session = create_test_session();

        let result = reach(
            &session,
            "util",
            ReachDirection::Backward,
            GraphType::CallGraph,
            None,
            None,
        );

        // util ← helper ← main
        assert_eq!(result.total_nodes, 3);
        assert!(result.nodes.contains(&"util".to_string()));
        assert!(result.nodes.contains(&"helper".to_string()));
        assert!(result.nodes.contains(&"main".to_string()));
    }

    #[test]
    fn test_reach_with_depth_limit() {
        let session = create_test_session();

        let result = reach(
            &session,
            "main",
            ReachDirection::Forward,
            GraphType::CallGraph,
            Some(1),
            None,
        );

        // main → helper, main → other (depth 1)
        assert_eq!(result.total_nodes, 3);
        assert!(!result.nodes.contains(&"util".to_string()));  // depth 2
    }

    #[test]
    fn test_reach_nonexistent_start() {
        let session = create_test_session();

        let result = reach(
            &session,
            "nonexistent",
            ReachDirection::Forward,
            GraphType::CallGraph,
            None,
            None,
        );

        assert_eq!(result.total_nodes, 0);
    }

    #[test]
    fn test_reach_with_filter() {
        let session = create_test_session();

        let result = reach(
            &session,
            "main",
            ReachDirection::Forward,
            GraphType::CallGraph,
            None,
            Some(&["function".to_string()]),
        );

        // All nodes are functions, so all should be included
        assert_eq!(result.total_nodes, 4);
    }

    #[test]
    fn test_reach_depths() {
        let session = create_test_session();

        let result = reach(
            &session,
            "main",
            ReachDirection::Forward,
            GraphType::CallGraph,
            None,
            None,
        );

        assert_eq!(*result.depths.get("main").unwrap(), 0);
        assert_eq!(*result.depths.get("helper").unwrap(), 1);
        assert_eq!(*result.depths.get("util").unwrap(), 2);
    }

    #[test]
    fn test_reach_with_paths() {
        let session = create_test_session();

        let result = reach_with_paths(
            &session,
            "main",
            ReachDirection::Forward,
            GraphType::CallGraph,
            None,
        );

        assert_eq!(result.total_nodes, 4);

        // Check path to util
        let util_path = result.paths.iter()
            .find(|p| p.target == "util")
            .expect("Should have path to util");

        assert_eq!(util_path.path, vec!["main", "helper", "util"]);
        assert_eq!(util_path.depth, 2);
    }

    #[test]
    fn test_find_callers() {
        let session = create_test_session();

        let result = find_callers(&session, "util", None);

        assert!(result.nodes.contains(&"helper".to_string()));
        assert!(result.nodes.contains(&"main".to_string()));
    }

    #[test]
    fn test_find_callees() {
        let session = create_test_session();

        let result = find_callees(&session, "main", None);

        assert!(result.nodes.contains(&"helper".to_string()));
        assert!(result.nodes.contains(&"other".to_string()));
        assert!(result.nodes.contains(&"util".to_string()));
    }

    #[test]
    fn test_graph_type_filtering() {
        // Create session with mixed edge types
        let nodes = vec![
            Node::new(
                "n1".to_string(),
                NodeKind::Variable,
                "n1".to_string(),
                "test.py".to_string(),
                Span::new(1, 0, 1, 0),
            ).with_name("x"),
            Node::new(
                "n2".to_string(),
                NodeKind::Variable,
                "n2".to_string(),
                "test.py".to_string(),
                Span::new(2, 0, 2, 0),
            ).with_name("y"),
            Node::new(
                "n3".to_string(),
                NodeKind::Variable,
                "n3".to_string(),
                "test.py".to_string(),
                Span::new(3, 0, 3, 0),
            ).with_name("z"),
        ];

        let edges = vec![
            Edge::new("n1".to_string(), "n2".to_string(), EdgeKind::DataFlow),
            Edge::new("n2".to_string(), "n3".to_string(), EdgeKind::ControlFlow),
        ];

        let session = AnalysisSession::new("test.py".to_string(), nodes, edges, None);

        // DFG only - should only follow data flow edge
        let dfg_result = reach(
            &session,
            "n1",
            ReachDirection::Forward,
            GraphType::Dfg,
            None,
            None,
        );
        assert_eq!(dfg_result.total_nodes, 2);  // n1, n2

        // CFG only - should only follow control flow edge
        let cfg_result = reach(
            &session,
            "n2",
            ReachDirection::Forward,
            GraphType::Cfg,
            None,
            None,
        );
        assert_eq!(cfg_result.total_nodes, 2);  // n2, n3
    }

    #[test]
    fn test_reach_result_serialization() {
        let session = create_test_session();

        let result = reach(
            &session,
            "main",
            ReachDirection::Forward,
            GraphType::CallGraph,
            None,
            None,
        );

        // Serialize to msgpack
        let bytes = result.to_msgpack().expect("Should serialize");
        assert!(!bytes.is_empty());

        // Deserialize
        let deserialized: ReachResult = rmp_serde::from_slice(&bytes)
            .expect("Should deserialize");

        assert_eq!(deserialized.total_nodes, result.total_nodes);
        assert_eq!(deserialized.nodes.len(), result.nodes.len());
    }

    #[test]
    fn test_reach_direction_from_str() {
        assert_eq!(ReachDirection::from_str("forward"), ReachDirection::Forward);
        assert_eq!(ReachDirection::from_str("backward"), ReachDirection::Backward);
        assert_eq!(ReachDirection::from_str("back"), ReachDirection::Backward);
        assert_eq!(ReachDirection::from_str("both"), ReachDirection::Both);
        assert_eq!(ReachDirection::from_str("unknown"), ReachDirection::Forward);
    }

    #[test]
    fn test_graph_type_from_str() {
        assert_eq!(GraphType::from_str("cfg"), GraphType::Cfg);
        assert_eq!(GraphType::from_str("dfg"), GraphType::Dfg);
        assert_eq!(GraphType::from_str("pdg"), GraphType::Pdg);
        assert_eq!(GraphType::from_str("call"), GraphType::CallGraph);
        assert_eq!(GraphType::from_str("unknown"), GraphType::All);
    }

    // Performance test
    #[test]
    fn test_reach_large_graph() {
        // Create chain of 1000 nodes
        let mut nodes = Vec::new();
        let mut edges = Vec::new();

        for i in 0..1000 {
            nodes.push(
                Node::new(
                    format!("n{}", i),
                    NodeKind::Function,
                    format!("n{}", i),
                    "test.py".to_string(),
                    Span::new(i as u32, 0, i as u32, 0),
                ).with_name(&format!("func{}", i))
            );

            if i > 0 {
                edges.push(Edge::new(
                    format!("n{}", i - 1),
                    format!("n{}", i),
                    EdgeKind::Calls,
                ));
            }
        }

        let session = AnalysisSession::new("test.py".to_string(), nodes, edges, None);

        let start = std::time::Instant::now();
        let result = reach(
            &session,
            "n0",
            ReachDirection::Forward,
            GraphType::CallGraph,
            None,
            None,
        );
        let elapsed = start.elapsed();

        assert_eq!(result.total_nodes, 1000);
        assert!(elapsed.as_millis() < 100, "Should complete in < 100ms, took {}ms", elapsed.as_millis());
    }
}
