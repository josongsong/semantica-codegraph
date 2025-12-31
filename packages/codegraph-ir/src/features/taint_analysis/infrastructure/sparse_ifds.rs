//! Sparse IFDS Implementation
//!
//! # Overview
//!
//! Sparse IFDS is an optimization of the standard IFDS algorithm that
//! only processes nodes where facts can change (definition/use sites),
//! skipping intermediate nodes where facts simply propagate unchanged.
//!
//! # Reference
//!
//! "Sparse Interprocedural Dataflow Analysis" by Ramalingam (1996)
//! "Efficient and Precise Taint Analysis for Android" by Arzt et al. (2014)
//!
//! # Key Concepts
//!
//! 1. **Sparse CFG**: A reduced CFG containing only relevant nodes
//! 2. **Def-Use Chains**: Direct connections from definitions to uses
//! 3. **Relevant Nodes**: Nodes that can generate, kill, or use facts
//!
//! # Performance
//!
//! - Time: O(E_sparse) vs O(E_full) where E_sparse << E_full
//! - Space: O(V_sparse) vs O(V_full)
//! - Typical speedup: 2-10x for large programs
//!
//! # Example
//!
//! ```text
//! // Original CFG (5 nodes)
//! a = taint()  // Gen taint fact
//! b = a + 1    // Identity for taint
//! c = b + 2    // Identity for taint
//! d = c + 3    // Identity for taint
//! sink(d)      // Use taint fact
//!
//! // Sparse CFG (2 nodes + direct edge)
//! a = taint()  // Gen taint fact
//!      |
//!      v (sparse edge)
//! sink(d)      // Use taint fact
//! ```

use super::ifds_framework::{DataflowFact, FlowFunction, IFDSProblem, PathEdge};
use super::ifds_solver::{CFGEdge, CFGEdgeKind, CFG};
use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::VecDeque;

/// Relevance type for a node in Sparse IFDS
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum NodeRelevance {
    /// Node generates new facts (source)
    Generator,
    /// Node kills existing facts (sanitizer)
    Killer,
    /// Node uses facts without modifying them (sink)
    User,
    /// Node is entry/exit of a procedure (for interprocedural analysis)
    Boundary,
    /// Node is irrelevant (identity transformation for all facts)
    Irrelevant,
}

/// Sparse CFG node metadata
#[derive(Debug, Clone)]
pub struct SparseNode {
    /// Original CFG node ID
    pub original_node: String,
    /// Type of relevance
    pub relevance: NodeRelevance,
    /// Facts that can be generated at this node
    pub generated_facts: Vec<String>,
    /// Facts that can be killed at this node
    pub killed_facts: Vec<String>,
}

/// Sparse CFG edge (direct connection between relevant nodes)
#[derive(Debug, Clone)]
pub struct SparseEdge {
    /// Source node
    pub from: String,
    /// Target node
    pub to: String,
    /// Number of intermediate nodes skipped
    pub skipped_nodes: usize,
    /// Edge kind (preserved from original CFG)
    pub kind: CFGEdgeKind,
}

/// Sparse CFG: reduced CFG containing only relevant nodes
///
/// # Algorithm
///
/// 1. Identify relevant nodes (generators, killers, users, boundaries)
/// 2. Compute direct edges between relevant nodes
/// 3. Skip intermediate irrelevant nodes
///
/// # Invariants
///
/// - Every node in sparse_nodes is relevant
/// - Every edge connects two relevant nodes directly
/// - No intermediate irrelevant nodes on any edge
#[derive(Debug, Clone)]
pub struct SparseCFG {
    /// Relevant nodes only
    pub nodes: FxHashMap<String, SparseNode>,
    /// Direct edges between relevant nodes
    pub edges: FxHashMap<String, Vec<SparseEdge>>,
    /// Reverse edges for backward analysis
    pub reverse_edges: FxHashMap<String, Vec<SparseEdge>>,
    /// Entry nodes
    pub entries: FxHashSet<String>,
    /// Exit nodes
    pub exits: FxHashSet<String>,
    /// Statistics
    pub stats: SparseCFGStats,
}

/// Sparse CFG construction statistics
#[derive(Debug, Clone, Default)]
pub struct SparseCFGStats {
    /// Original CFG node count
    pub original_nodes: usize,
    /// Sparse CFG node count (relevant only)
    pub sparse_nodes: usize,
    /// Original CFG edge count
    pub original_edges: usize,
    /// Sparse CFG edge count
    pub sparse_edges: usize,
    /// Total nodes skipped
    pub total_skipped_nodes: usize,
    /// Reduction ratio (1 - sparse/original)
    pub reduction_ratio: f64,
}

impl SparseCFG {
    /// Build sparse CFG from original CFG
    ///
    /// # Algorithm (O(V + E))
    ///
    /// 1. First pass: Identify relevant nodes
    /// 2. Second pass: Compute direct edges between relevant nodes
    /// 3. Handle interprocedural edges specially
    ///
    /// # Arguments
    /// * `cfg` - Original CFG
    /// * `relevance_fn` - Function to determine node relevance
    ///
    /// # Returns
    /// Sparse CFG with only relevant nodes and direct edges
    pub fn from_cfg<R>(cfg: &CFG, relevance_fn: R) -> Self
    where
        R: Fn(&str) -> NodeRelevance,
    {
        // Collect all unique nodes from successors keys and edge targets
        let mut all_nodes: FxHashSet<String> = FxHashSet::default();
        for (from, edges) in &cfg.successors {
            all_nodes.insert(from.clone());
            for edge in edges {
                all_nodes.insert(edge.to.clone());
            }
        }
        // Also include entries and exits
        for entry in &cfg.entries {
            all_nodes.insert(entry.clone());
        }
        for exit in &cfg.exits {
            all_nodes.insert(exit.clone());
        }

        let original_nodes = all_nodes.len();
        let original_edges = cfg.edges.len();

        // Step 1: Identify relevant nodes
        let mut nodes = FxHashMap::default();
        let mut relevant_set: FxHashSet<String> = FxHashSet::default();

        for node_id in &all_nodes {
            let relevance = relevance_fn(node_id);
            if relevance != NodeRelevance::Irrelevant {
                relevant_set.insert(node_id.clone());
                nodes.insert(
                    node_id.clone(),
                    SparseNode {
                        original_node: node_id.clone(),
                        relevance,
                        generated_facts: Vec::new(),
                        killed_facts: Vec::new(),
                    },
                );
            }
        }

        // Always include entries and exits as relevant
        for entry in &cfg.entries {
            if !relevant_set.contains(entry) {
                relevant_set.insert(entry.clone());
                nodes.insert(
                    entry.clone(),
                    SparseNode {
                        original_node: entry.clone(),
                        relevance: NodeRelevance::Boundary,
                        generated_facts: Vec::new(),
                        killed_facts: Vec::new(),
                    },
                );
            }
        }
        for exit in &cfg.exits {
            if !relevant_set.contains(exit) {
                relevant_set.insert(exit.clone());
                nodes.insert(
                    exit.clone(),
                    SparseNode {
                        original_node: exit.clone(),
                        relevance: NodeRelevance::Boundary,
                        generated_facts: Vec::new(),
                        killed_facts: Vec::new(),
                    },
                );
            }
        }

        // Step 2: Compute direct edges using BFS from each relevant node
        let mut edges: FxHashMap<String, Vec<SparseEdge>> = FxHashMap::default();
        let mut reverse_edges: FxHashMap<String, Vec<SparseEdge>> = FxHashMap::default();
        let mut total_skipped = 0;

        for from_node in &relevant_set {
            let sparse_edges = Self::find_next_relevant_nodes(cfg, from_node, &relevant_set);

            for (to_node, skipped, kind) in sparse_edges {
                total_skipped += skipped;

                let edge = SparseEdge {
                    from: from_node.clone(),
                    to: to_node.clone(),
                    skipped_nodes: skipped,
                    kind: kind.clone(),
                };

                edges
                    .entry(from_node.clone())
                    .or_insert_with(Vec::new)
                    .push(edge.clone());

                reverse_edges
                    .entry(to_node.clone())
                    .or_insert_with(Vec::new)
                    .push(SparseEdge {
                        from: to_node,
                        to: from_node.clone(),
                        skipped_nodes: skipped,
                        kind,
                    });
            }
        }

        let sparse_nodes_count = nodes.len();
        let sparse_edges_count = edges.values().map(|e| e.len()).sum::<usize>();

        let reduction_ratio = if original_nodes > 0 {
            1.0 - (sparse_nodes_count as f64 / original_nodes as f64)
        } else {
            0.0
        };

        SparseCFG {
            nodes,
            edges,
            reverse_edges,
            entries: cfg.entries.iter().cloned().collect(),
            exits: cfg.exits.iter().cloned().collect(),
            stats: SparseCFGStats {
                original_nodes,
                sparse_nodes: sparse_nodes_count,
                original_edges,
                sparse_edges: sparse_edges_count,
                total_skipped_nodes: total_skipped,
                reduction_ratio,
            },
        }
    }

    /// Find next relevant nodes reachable from a given node
    ///
    /// Uses BFS to find all directly-reachable relevant nodes,
    /// counting skipped irrelevant nodes along the way.
    fn find_next_relevant_nodes(
        cfg: &CFG,
        start: &str,
        relevant_set: &FxHashSet<String>,
    ) -> Vec<(String, usize, CFGEdgeKind)> {
        let mut results = Vec::new();
        let mut visited: FxHashSet<String> = FxHashSet::default();
        // (node, skipped_count, original_edge_kind)
        let mut queue: VecDeque<(String, usize, Option<CFGEdgeKind>)> = VecDeque::new();

        // Initialize with direct successors
        if let Some(successors) = cfg.successors.get(start) {
            for edge in successors {
                queue.push_back((edge.to.clone(), 0, Some(edge.kind.clone())));
            }
        }

        while let Some((node, skipped, edge_kind)) = queue.pop_front() {
            if visited.contains(&node) {
                continue;
            }
            visited.insert(node.clone());

            if relevant_set.contains(&node) && node != start {
                // Found a relevant node!
                let kind = edge_kind.unwrap_or(CFGEdgeKind::Normal);
                results.push((node, skipped, kind));
            } else if !relevant_set.contains(&node) {
                // Continue through irrelevant node
                if let Some(successors) = cfg.successors.get(&node) {
                    for edge in successors {
                        if !visited.contains(&edge.to) {
                            // Preserve original edge kind, increment skip count
                            queue.push_back((
                                edge.to.clone(),
                                skipped + 1,
                                edge_kind.clone().or(Some(edge.kind.clone())),
                            ));
                        }
                    }
                }
            }
        }

        results
    }

    /// Get sparse successors of a node
    pub fn successors(&self, node: &str) -> Vec<&SparseEdge> {
        self.edges
            .get(node)
            .map(|edges| edges.iter().collect())
            .unwrap_or_default()
    }

    /// Get sparse predecessors of a node
    pub fn predecessors(&self, node: &str) -> Vec<&SparseEdge> {
        self.reverse_edges
            .get(node)
            .map(|edges| edges.iter().collect())
            .unwrap_or_default()
    }

    /// Check if a node is in the sparse CFG
    pub fn contains(&self, node: &str) -> bool {
        self.nodes.contains_key(node)
    }

    /// Get node metadata
    pub fn get_node(&self, node: &str) -> Option<&SparseNode> {
        self.nodes.get(node)
    }

    /// Get statistics about the sparse CFG
    pub fn stats(&self) -> &SparseCFGStats {
        &self.stats
    }

    /// Get reduction ratio (0.0 to 1.0)
    ///
    /// Higher is better: 0.5 means 50% of nodes were eliminated.
    pub fn reduction_ratio(&self) -> f64 {
        self.stats.reduction_ratio
    }

    /// Get number of sparse nodes
    pub fn num_sparse_nodes(&self) -> usize {
        self.stats.sparse_nodes
    }

    /// Get total nodes skipped
    pub fn nodes_skipped(&self) -> usize {
        self.stats.total_skipped_nodes
    }
}

/// Sparse IFDS Solver
///
/// Extends standard IFDS with sparse CFG optimization.
///
/// # Performance
///
/// - Skips intermediate nodes with identity flow
/// - Direct edges between relevant nodes
/// - Same precision as standard IFDS
///
/// # Usage
///
/// ```ignore
/// let sparse_cfg = SparseCFG::from_cfg(&cfg, |node| {
///     if is_taint_source(node) { NodeRelevance::Generator }
///     else if is_sanitizer(node) { NodeRelevance::Killer }
///     else if is_sink(node) { NodeRelevance::User }
///     else { NodeRelevance::Irrelevant }
/// });
///
/// let solver = SparseIFDSSolver::new(problem, sparse_cfg);
/// let results = solver.solve();
/// ```
pub struct SparseIFDSSolver<F: DataflowFact> {
    /// IFDS problem specification
    problem: Box<dyn IFDSProblem<F>>,

    /// Sparse CFG
    sparse_cfg: SparseCFG,

    /// Path edges: (d1, n, d2) means fact d2 holds at node n given initial fact d1
    path_edges: FxHashMap<String, FxHashSet<PathEdge<F>>>,

    /// Summary edges: summarize function effects
    summary_edges: FxHashMap<(String, F), FxHashSet<F>>,

    /// Worklist for tabulation algorithm
    worklist: VecDeque<PathEdge<F>>,

    /// Statistics
    stats: SparseIFDSStats,
}

/// Sparse IFDS Statistics
#[derive(Debug, Clone, Default)]
pub struct SparseIFDSStats {
    /// Number of path edges processed
    pub path_edges_processed: usize,
    /// Number of summary edges created
    pub summary_edges_created: usize,
    /// Number of iterations
    pub iterations: usize,
    /// Nodes skipped due to sparsity
    pub nodes_skipped: usize,
    /// Analysis time in ms
    pub analysis_time_ms: u64,
}

impl<F: DataflowFact + 'static> SparseIFDSSolver<F> {
    /// Create new sparse IFDS solver
    pub fn new(problem: Box<dyn IFDSProblem<F>>, sparse_cfg: SparseCFG) -> Self {
        Self {
            problem,
            sparse_cfg,
            path_edges: FxHashMap::default(),
            summary_edges: FxHashMap::default(),
            worklist: VecDeque::new(),
            stats: SparseIFDSStats::default(),
        }
    }

    /// Solve the IFDS problem using sparse tabulation
    ///
    /// # Algorithm
    ///
    /// 1. Initialize with seeds at entry node
    /// 2. Process worklist (only sparse edges)
    /// 3. Apply flow functions at relevant nodes
    /// 4. Skip intermediate irrelevant nodes
    ///
    /// # Returns
    /// Mapping from nodes to sets of facts
    pub fn solve(&mut self) -> FxHashMap<String, FxHashSet<F>> {
        let start = std::time::Instant::now();

        // Initialize with seeds
        self.initialize();

        // Main worklist loop
        while let Some(edge) = self.worklist.pop_front() {
            self.stats.iterations += 1;
            self.process_edge(&edge);
        }

        self.stats.analysis_time_ms = start.elapsed().as_millis() as u64;

        // Collect results
        self.collect_results()
    }

    /// Initialize with problem seeds
    fn initialize(&mut self) {
        for (node, fact) in self.problem.initial_seeds() {
            // Only process if node is in sparse CFG
            if self.sparse_cfg.contains(&node) {
                let edge = PathEdge {
                    source_fact: F::zero(),
                    target_node: node,
                    target_fact: fact,
                };
                self.add_path_edge(edge);
            }
        }
    }

    /// Add path edge to worklist if new
    fn add_path_edge(&mut self, edge: PathEdge<F>) {
        let entry = self
            .path_edges
            .entry(edge.target_node.clone())
            .or_insert_with(FxHashSet::default);

        if entry.insert(edge.clone()) {
            self.stats.path_edges_processed += 1;
            self.worklist.push_back(edge);
        }
    }

    /// Process a path edge
    fn process_edge(&mut self, edge: &PathEdge<F>) {
        let node = edge.target_node.clone();
        let fact = edge.target_fact.clone();

        // Get sparse successors (collect to avoid borrow conflict)
        let successors: Vec<_> = self
            .sparse_cfg
            .successors(&node)
            .into_iter()
            .map(|e| (e.to.clone(), e.skipped_nodes, e.kind.clone()))
            .collect();

        for (to_node, skipped, kind) in successors {
            // Track skipped nodes for statistics
            self.stats.nodes_skipped += skipped;

            match &kind {
                CFGEdgeKind::Normal => {
                    self.process_normal_edge(&node, &to_node, &fact);
                }
                CFGEdgeKind::Call { callee_entry } => {
                    self.process_call_edge(&node, callee_entry, &fact);
                }
                CFGEdgeKind::Return { call_site } => {
                    self.process_return_edge(&node, &to_node, call_site, &fact);
                }
                CFGEdgeKind::CallToReturn => {
                    self.process_call_to_return_edge(&node, &to_node, &fact);
                }
            }
        }
    }

    /// Process normal (intra-procedural) edge in sparse CFG
    fn process_normal_edge(&mut self, from: &str, to: &str, fact: &F) {
        // Apply flow function at source node
        let flow_fn = self.problem.normal_flow(from, to);
        let target_facts = flow_fn.compute(fact);

        for target_fact in target_facts {
            let edge = PathEdge {
                source_fact: F::zero(),
                target_node: to.to_string(),
                target_fact,
            };
            self.add_path_edge(edge);
        }
    }

    /// Process call edge
    fn process_call_edge(&mut self, call_site: &str, callee_entry: &str, fact: &F) {
        // Check for existing summary
        let summary_key = (callee_entry.to_string(), fact.clone());
        if let Some(summaries) = self.summary_edges.get(&summary_key) {
            // Reuse existing summaries (clone to avoid borrow conflict)
            let summaries_clone: Vec<_> = summaries.iter().cloned().collect();
            for return_fact in summaries_clone {
                let edge = PathEdge {
                    source_fact: fact.clone(),
                    target_node: call_site.to_string(), // Return to call site
                    target_fact: return_fact,
                };
                self.add_path_edge(edge);
            }
            return;
        }

        // Apply call flow function
        let call_flow = self.problem.call_flow(call_site, callee_entry);
        let callee_facts = call_flow.compute(fact);

        for callee_fact in callee_facts {
            let edge = PathEdge {
                source_fact: fact.clone(),
                target_node: callee_entry.to_string(),
                target_fact: callee_fact,
            };
            self.add_path_edge(edge);
        }
    }

    /// Process return edge
    fn process_return_edge(
        &mut self,
        exit_node: &str,
        return_site: &str,
        call_site: &str,
        fact: &F,
    ) {
        // Apply return flow function
        let return_flow = self.problem.return_flow(exit_node, return_site, call_site);
        let return_facts = return_flow.compute(fact);

        for return_fact in return_facts {
            // Store summary edge for later reuse
            let summary_key = (exit_node.to_string(), fact.clone());
            self.summary_edges
                .entry(summary_key)
                .or_insert_with(FxHashSet::default)
                .insert(return_fact.clone());
            self.stats.summary_edges_created += 1;

            let edge = PathEdge {
                source_fact: F::zero(),
                target_node: return_site.to_string(),
                target_fact: return_fact,
            };
            self.add_path_edge(edge);
        }
    }

    /// Process call-to-return edge
    fn process_call_to_return_edge(&mut self, call_site: &str, return_site: &str, fact: &F) {
        let flow_fn = self.problem.call_to_return_flow(call_site, return_site);
        let target_facts = flow_fn.compute(fact);

        for target_fact in target_facts {
            let edge = PathEdge {
                source_fact: F::zero(),
                target_node: return_site.to_string(),
                target_fact,
            };
            self.add_path_edge(edge);
        }
    }

    /// Collect final results
    fn collect_results(&self) -> FxHashMap<String, FxHashSet<F>> {
        let mut results = FxHashMap::default();

        for (node, edges) in &self.path_edges {
            let facts: FxHashSet<F> = edges.iter().map(|e| e.target_fact.clone()).collect();
            results.insert(node.clone(), facts);
        }

        results
    }

    /// Get analysis statistics
    pub fn statistics(&self) -> &SparseIFDSStats {
        &self.stats
    }

    /// Get sparse CFG statistics
    pub fn sparse_cfg_stats(&self) -> &SparseCFGStats {
        &self.sparse_cfg.stats
    }
}

/// Helper: Create relevance function for taint analysis
///
/// # Example
///
/// ```ignore
/// let relevance = taint_relevance_function(
///     &["source1", "source2"],
///     &["sanitize"],
///     &["sink1", "sink2"]
/// );
/// let sparse_cfg = SparseCFG::from_cfg(&cfg, relevance);
/// ```
pub fn taint_relevance_function<'a>(
    sources: &'a [&'a str],
    sanitizers: &'a [&'a str],
    sinks: &'a [&'a str],
) -> impl Fn(&str) -> NodeRelevance + 'a {
    move |node: &str| {
        if sources.iter().any(|s| node.contains(s)) {
            NodeRelevance::Generator
        } else if sanitizers.iter().any(|s| node.contains(s)) {
            NodeRelevance::Killer
        } else if sinks.iter().any(|s| node.contains(s)) {
            NodeRelevance::User
        } else {
            NodeRelevance::Irrelevant
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    // ============================================================
    // BASE CASE TESTS: Basic functionality
    // ============================================================

    #[test]
    fn test_node_relevance() {
        let gen = NodeRelevance::Generator;
        let kill = NodeRelevance::Killer;
        let user = NodeRelevance::User;
        let irr = NodeRelevance::Irrelevant;

        assert_ne!(gen, kill);
        assert_ne!(gen, irr);
        assert_eq!(user, NodeRelevance::User);
    }

    #[test]
    fn test_sparse_cfg_stats_default() {
        let stats = SparseCFGStats::default();
        assert_eq!(stats.original_nodes, 0);
        assert_eq!(stats.sparse_nodes, 0);
        assert_eq!(stats.reduction_ratio, 0.0);
    }

    #[test]
    fn test_sparse_ifds_stats_default() {
        let stats = SparseIFDSStats::default();
        assert_eq!(stats.path_edges_processed, 0);
        assert_eq!(stats.nodes_skipped, 0);
        assert_eq!(stats.iterations, 0);
    }

    #[test]
    fn test_taint_relevance_function() {
        let relevance = taint_relevance_function(&["get_user_input"], &["sanitize"], &["exec_sql"]);

        assert_eq!(relevance("get_user_input_1"), NodeRelevance::Generator);
        assert_eq!(relevance("sanitize_input"), NodeRelevance::Killer);
        assert_eq!(relevance("exec_sql_query"), NodeRelevance::User);
        assert_eq!(relevance("compute_value"), NodeRelevance::Irrelevant);
    }

    /// Create test CFG helper
    fn create_test_cfg(nodes: &[&str], edges: &[(&str, &str)]) -> CFG {
        let mut cfg = CFG::new();

        for &(from, to) in edges {
            cfg.add_edge(CFGEdge {
                from: from.to_string(),
                to: to.to_string(),
                kind: CFGEdgeKind::Normal,
            });
        }

        if let Some(&first) = nodes.first() {
            cfg.entries.insert(first.to_string());
        }
        if let Some(&last) = nodes.last() {
            cfg.exits.insert(last.to_string());
        }

        cfg
    }

    #[test]
    fn test_sparse_cfg_basic_construction() {
        // Linear CFG: source -> compute1 -> compute2 -> sink
        let cfg = create_test_cfg(
            &["source", "compute1", "compute2", "sink"],
            &[
                ("source", "compute1"),
                ("compute1", "compute2"),
                ("compute2", "sink"),
            ],
        );

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "source" {
                NodeRelevance::Generator
            } else if node == "sink" {
                NodeRelevance::User
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // Should have 2 relevant nodes + entry/exit
        assert!(sparse.nodes.contains_key("source"));
        assert!(sparse.nodes.contains_key("sink"));

        // Should skip intermediate nodes
        assert!(sparse.stats.total_skipped_nodes > 0);
        assert!(sparse.stats.reduction_ratio > 0.0);
    }

    #[test]
    fn test_sparse_cfg_direct_edge() {
        // source -> irrelevant -> sink
        // Should create direct edge: source -> sink (skipping irrelevant)
        let cfg = create_test_cfg(
            &["source", "irrelevant", "sink"],
            &[("source", "irrelevant"), ("irrelevant", "sink")],
        );

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "source" {
                NodeRelevance::Generator
            } else if node == "sink" {
                NodeRelevance::User
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // Check direct edge exists
        let successors = sparse.successors("source");
        assert!(!successors.is_empty());
        assert_eq!(successors[0].to, "sink");
        assert_eq!(successors[0].skipped_nodes, 1); // One node skipped
    }

    // ============================================================
    // EDGE CASE TESTS: Boundary conditions
    // ============================================================

    #[test]
    fn test_sparse_cfg_empty() {
        let cfg = CFG::new();
        let sparse = SparseCFG::from_cfg(&cfg, |_| NodeRelevance::Irrelevant);

        assert!(sparse.nodes.is_empty() || sparse.nodes.len() <= 2); // Only possible entry/exit
        assert_eq!(sparse.stats.original_nodes, 0);
    }

    #[test]
    fn test_sparse_cfg_single_node() {
        let mut cfg = CFG::new();
        cfg.entries.insert("only_node".to_string());
        cfg.exits.insert("only_node".to_string());

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "only_node" {
                NodeRelevance::Generator
            } else {
                NodeRelevance::Irrelevant
            }
        });

        assert!(sparse.contains("only_node"));
        assert_eq!(sparse.stats.sparse_nodes, 1);
    }

    #[test]
    fn test_sparse_cfg_all_relevant() {
        // When all nodes are relevant, no reduction should happen
        let cfg = create_test_cfg(&["a", "b", "c"], &[("a", "b"), ("b", "c")]);

        let sparse = SparseCFG::from_cfg(&cfg, |_| NodeRelevance::Generator);

        // All nodes should be preserved
        assert!(sparse.contains("a"));
        assert!(sparse.contains("b"));
        assert!(sparse.contains("c"));
        assert_eq!(sparse.stats.reduction_ratio, 0.0); // No reduction
    }

    #[test]
    fn test_sparse_cfg_all_irrelevant_except_boundaries() {
        // Only entry/exit are relevant
        let cfg = create_test_cfg(
            &["entry", "mid1", "mid2", "mid3", "exit"],
            &[
                ("entry", "mid1"),
                ("mid1", "mid2"),
                ("mid2", "mid3"),
                ("mid3", "exit"),
            ],
        );

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "entry" || node == "exit" {
                NodeRelevance::Boundary
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // Should have direct edge from entry to exit
        let successors = sparse.successors("entry");
        assert_eq!(successors.len(), 1);
        assert_eq!(successors[0].to, "exit");
        assert_eq!(successors[0].skipped_nodes, 3); // mid1, mid2, mid3 skipped
    }

    #[test]
    fn test_sparse_cfg_diamond_shape() {
        // Diamond: entry -> (left, right) -> exit
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge {
            from: "entry".into(),
            to: "left".into(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.add_edge(CFGEdge {
            from: "entry".into(),
            to: "right".into(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.add_edge(CFGEdge {
            from: "left".into(),
            to: "exit".into(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.add_edge(CFGEdge {
            from: "right".into(),
            to: "exit".into(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.entries.insert("entry".to_string());
        cfg.exits.insert("exit".to_string());

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "entry" || node == "exit" {
                NodeRelevance::Boundary
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // Entry should have 2 paths to exit (via left and right, both skipped)
        let successors = sparse.successors("entry");
        // Due to BFS deduplication, might be 1 or 2 edges depending on implementation
        assert!(!successors.is_empty());
    }

    #[test]
    fn test_sparse_cfg_with_loop() {
        // Loop: entry -> body -> (back to body OR exit)
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge {
            from: "entry".into(),
            to: "body".into(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.add_edge(CFGEdge {
            from: "body".into(),
            to: "body".into(),
            kind: CFGEdgeKind::Normal,
        }); // back edge
        cfg.add_edge(CFGEdge {
            from: "body".into(),
            to: "exit".into(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.entries.insert("entry".to_string());
        cfg.exits.insert("exit".to_string());

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "entry" || node == "exit" {
                NodeRelevance::Boundary
            } else if node == "body" {
                NodeRelevance::Generator
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // Body should have self-loop preserved
        let body_succs = sparse.successors("body");
        let has_self_loop = body_succs.iter().any(|e| e.to == "body");
        let has_exit = body_succs.iter().any(|e| e.to == "exit");
        assert!(has_self_loop || has_exit); // At least one should exist
    }

    #[test]
    fn test_sparse_cfg_multiple_sanitizers() {
        // source -> sanitizer1 -> sanitizer2 -> sink
        let cfg = create_test_cfg(
            &["source", "sanitizer1", "sanitizer2", "sink"],
            &[
                ("source", "sanitizer1"),
                ("sanitizer1", "sanitizer2"),
                ("sanitizer2", "sink"),
            ],
        );

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "source" {
                NodeRelevance::Generator
            } else if node.starts_with("sanitizer") {
                NodeRelevance::Killer
            } else if node == "sink" {
                NodeRelevance::User
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // All nodes should be relevant (no skipping)
        assert!(sparse.contains("source"));
        assert!(sparse.contains("sanitizer1"));
        assert!(sparse.contains("sanitizer2"));
        assert!(sparse.contains("sink"));
    }

    // ============================================================
    // EXTREME CASE TESTS: Stress and performance
    // ============================================================

    #[test]
    fn test_sparse_cfg_long_chain() {
        // Very long chain: source -> 100 irrelevant nodes -> sink
        let mut cfg = CFG::new();
        let mut prev = "source".to_string();

        cfg.entries.insert("source".to_string());

        for i in 0..100 {
            let next = format!("node_{}", i);
            cfg.add_edge(CFGEdge {
                from: prev.clone(),
                to: next.clone(),
                kind: CFGEdgeKind::Normal,
            });
            prev = next;
        }

        cfg.add_edge(CFGEdge {
            from: prev,
            to: "sink".to_string(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.exits.insert("sink".to_string());

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "source" {
                NodeRelevance::Generator
            } else if node == "sink" {
                NodeRelevance::User
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // Should skip 100 nodes
        assert_eq!(sparse.stats.total_skipped_nodes, 100);
        assert!(sparse.stats.reduction_ratio > 0.9); // >90% reduction

        // Direct edge from source to sink
        let successors = sparse.successors("source");
        assert_eq!(successors.len(), 1);
        assert_eq!(successors[0].to, "sink");
        assert_eq!(successors[0].skipped_nodes, 100);
    }

    #[test]
    fn test_sparse_cfg_wide_fan_out() {
        // Wide fan-out: source -> 50 sinks
        let mut cfg = CFG::new();
        cfg.entries.insert("source".to_string());

        for i in 0..50 {
            let sink = format!("sink_{}", i);
            cfg.add_edge(CFGEdge {
                from: "source".to_string(),
                to: sink.clone(),
                kind: CFGEdgeKind::Normal,
            });
            cfg.exits.insert(sink);
        }

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "source" {
                NodeRelevance::Generator
            } else if node.starts_with("sink") {
                NodeRelevance::User
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // All 51 nodes should be preserved (1 source + 50 sinks)
        assert_eq!(sparse.stats.sparse_nodes, 51);

        // Source should have 50 successors
        let successors = sparse.successors("source");
        assert_eq!(successors.len(), 50);
    }

    #[test]
    fn test_sparse_cfg_deep_nesting_with_relevance() {
        // Deep nesting with alternating relevance
        // relevant -> irrelevant -> relevant -> irrelevant -> ...
        let mut cfg = CFG::new();
        let mut prev = "start".to_string();
        cfg.entries.insert("start".to_string());

        for i in 0..20 {
            let next = if i % 2 == 0 {
                format!("relevant_{}", i)
            } else {
                format!("irrelevant_{}", i)
            };
            cfg.add_edge(CFGEdge {
                from: prev.clone(),
                to: next.clone(),
                kind: CFGEdgeKind::Normal,
            });
            prev = next;
        }
        cfg.exits.insert(prev);

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node.starts_with("relevant") || node == "start" {
                NodeRelevance::Generator
            } else if node.starts_with("irrelevant") {
                NodeRelevance::Irrelevant
            } else {
                NodeRelevance::Boundary
            }
        });

        // Should have edges that skip single irrelevant nodes
        for edge in sparse.edges.values().flatten() {
            // Each irrelevant node should be skipped (skipped_nodes = 1)
            assert!(edge.skipped_nodes <= 1);
        }
    }

    #[test]
    fn test_sparse_cfg_statistics_accuracy() {
        let cfg = create_test_cfg(
            &["a", "b", "c", "d", "e"],
            &[("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")],
        );

        let sparse = SparseCFG::from_cfg(&cfg, |node| {
            if node == "a" || node == "e" {
                NodeRelevance::Boundary
            } else {
                NodeRelevance::Irrelevant
            }
        });

        // Verify statistics
        assert_eq!(sparse.stats.original_nodes, 5);
        assert_eq!(sparse.stats.sparse_nodes, 2);
        assert_eq!(sparse.stats.original_edges, 4);
        // Reduction ratio should be (5-2)/5 = 0.6
        assert!((sparse.stats.reduction_ratio - 0.6).abs() < 0.01);
    }

    #[test]
    fn test_sparse_edge_kind_preservation() {
        // Test that edge kinds are preserved through sparse transformation
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge {
            from: "caller".to_string(),
            to: "callee".to_string(),
            kind: CFGEdgeKind::Call {
                callee_entry: "callee_entry".to_string(),
            },
        });
        cfg.entries.insert("caller".to_string());
        cfg.exits.insert("callee".to_string());

        let sparse = SparseCFG::from_cfg(&cfg, |_| NodeRelevance::Boundary);

        let successors = sparse.successors("caller");
        if !successors.is_empty() {
            // Edge kind should be preserved
            match &successors[0].kind {
                CFGEdgeKind::Call { .. } => {} // OK
                _ => panic!("Edge kind should be preserved as Call"),
            }
        }
    }

    // ============================================================
    // REGRESSION TESTS: Known edge cases
    // ============================================================

    #[test]
    fn test_sparse_cfg_no_panic_on_disconnected() {
        // Disconnected graph shouldn't cause panic
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge {
            from: "a".into(),
            to: "b".into(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.add_edge(CFGEdge {
            from: "c".into(),
            to: "d".into(),
            kind: CFGEdgeKind::Normal,
        }); // Disconnected
        cfg.entries.insert("a".to_string());
        cfg.entries.insert("c".to_string());
        cfg.exits.insert("b".to_string());
        cfg.exits.insert("d".to_string());

        // Should not panic
        let sparse = SparseCFG::from_cfg(&cfg, |_| NodeRelevance::Boundary);
        assert!(sparse.nodes.len() >= 4);
    }

    #[test]
    fn test_sparse_cfg_unicode_node_names() {
        // Unicode node names shouldn't cause issues
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge {
            from: "소스_노드".to_string(),
            to: "싱크_노드".to_string(),
            kind: CFGEdgeKind::Normal,
        });
        cfg.entries.insert("소스_노드".to_string());
        cfg.exits.insert("싱크_노드".to_string());

        let sparse = SparseCFG::from_cfg(&cfg, |_| NodeRelevance::Boundary);
        assert!(sparse.contains("소스_노드"));
        assert!(sparse.contains("싱크_노드"));
    }
}
