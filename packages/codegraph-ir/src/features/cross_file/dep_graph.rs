//! Dependency Graph with petgraph (RFC-062)
//!
//! File dependency graph using petgraph.
//! Supports Tarjan SCC for cycle detection, topological sort, and PageRank.

use petgraph::algo::tarjan_scc;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::visit::EdgeRef;
use petgraph::Direction;
use std::collections::{HashMap, HashSet, VecDeque};

use super::types::ResolvedImport;

/// PageRank configuration
#[derive(Debug, Clone)]
pub struct PageRankConfig {
    /// Damping factor (typically 0.85)
    pub damping: f64,

    /// Maximum iterations
    pub max_iterations: usize,

    /// Convergence threshold
    pub tolerance: f64,
}

impl Default for PageRankConfig {
    fn default() -> Self {
        Self {
            damping: 0.85,
            max_iterations: 100,
            tolerance: 1e-6,
        }
    }
}

/// File dependency graph
///
/// Directed graph where:
/// - Nodes are file paths
/// - Edges represent dependencies (A → B means A depends on B)
pub struct DependencyGraph {
    /// Directed graph: file → files it depends on
    graph: DiGraph<String, ()>,

    /// Path → Node index mapping
    path_to_node: HashMap<String, NodeIndex>,

    /// Strongly connected components (cycles)
    cycles: Vec<Vec<String>>,

    /// Cached topological order
    topo_order: Vec<String>,
}

impl DependencyGraph {
    /// Create empty dependency graph
    pub fn new() -> Self {
        Self {
            graph: DiGraph::new(),
            path_to_node: HashMap::new(),
            cycles: Vec::new(),
            topo_order: Vec::new(),
        }
    }

    /// Build dependency graph from resolved imports
    pub fn build(resolved_imports: &HashMap<String, Vec<ResolvedImport>>) -> Self {
        let mut graph = DiGraph::new();
        let mut path_to_node = HashMap::new();

        // Collect all file paths
        let mut all_files: HashSet<String> = resolved_imports.keys().cloned().collect();
        for imports in resolved_imports.values() {
            for import in imports {
                if let Some(ref source_file) = import.source_file {
                    all_files.insert(source_file.clone());
                }
            }
        }

        // Add all files as nodes
        for file_path in &all_files {
            let idx = graph.add_node(file_path.clone());
            path_to_node.insert(file_path.clone(), idx);
        }

        // Add dependency edges
        for (from_path, imports) in resolved_imports {
            let from_idx = match path_to_node.get(from_path) {
                Some(idx) => *idx,
                None => continue,
            };

            for import in imports {
                if let Some(ref source_file) = import.source_file {
                    // Don't add self-loops
                    if source_file == from_path {
                        continue;
                    }

                    if let Some(&to_idx) = path_to_node.get(source_file) {
                        // Add edge: from_path depends on source_file
                        graph.add_edge(from_idx, to_idx, ());
                    }
                }
            }
        }

        // Compute SCCs for cycle detection
        let sccs = tarjan_scc(&graph);
        let cycles: Vec<Vec<String>> = sccs
            .into_iter()
            .filter(|scc| scc.len() > 1) // Only cycles
            .map(|scc| scc.into_iter().map(|idx| graph[idx].clone()).collect())
            .collect();

        // Compute topological order using Kahn's algorithm
        let topo_order = Self::compute_topological_order(&graph, &path_to_node);

        Self {
            graph,
            path_to_node,
            cycles,
            topo_order,
        }
    }

    /// Compute topological order using Kahn's algorithm
    fn compute_topological_order(
        graph: &DiGraph<String, ()>,
        _path_to_node: &HashMap<String, NodeIndex>,
    ) -> Vec<String> {
        let mut in_degree: HashMap<NodeIndex, usize> = HashMap::new();

        // Initialize in-degree for all nodes
        for idx in graph.node_indices() {
            in_degree.insert(idx, 0);
        }

        // Calculate in-degree (count incoming edges)
        for edge in graph.edge_references() {
            *in_degree.entry(edge.target()).or_insert(0) += 1;
        }

        // Start with nodes that have no dependencies (in-degree 0)
        let mut queue: VecDeque<NodeIndex> = in_degree
            .iter()
            .filter(|(_, &degree)| degree == 0)
            .map(|(&idx, _)| idx)
            .collect();

        let mut order = Vec::new();

        while let Some(idx) = queue.pop_front() {
            order.push(graph[idx].clone());

            // Reduce in-degree for neighbors
            for neighbor in graph.neighbors(idx) {
                if let Some(degree) = in_degree.get_mut(&neighbor) {
                    *degree -= 1;
                    if *degree == 0 {
                        queue.push_back(neighbor);
                    }
                }
            }
        }

        // Reverse to get dependencies-first order (base modules first)
        order.reverse();
        order
    }

    /// Get files that depend on this file (reverse lookup)
    pub fn get_dependents(&self, file_path: &str) -> Vec<String> {
        if let Some(&idx) = self.path_to_node.get(file_path) {
            self.graph
                .neighbors_directed(idx, Direction::Incoming)
                .map(|idx| self.graph[idx].clone())
                .collect()
        } else {
            Vec::new()
        }
    }

    /// Get files that this file depends on
    pub fn get_dependencies(&self, file_path: &str) -> Vec<String> {
        if let Some(&idx) = self.path_to_node.get(file_path) {
            self.graph
                .neighbors_directed(idx, Direction::Outgoing)
                .map(|idx| self.graph[idx].clone())
                .collect()
        } else {
            Vec::new()
        }
    }

    /// Get all dependencies as HashMap
    pub fn get_all_dependencies(&self) -> HashMap<String, Vec<String>> {
        self.path_to_node
            .keys()
            .map(|path| (path.clone(), self.get_dependencies(path)))
            .collect()
    }

    /// Get all dependents as HashMap
    pub fn get_all_dependents(&self) -> HashMap<String, Vec<String>> {
        self.path_to_node
            .keys()
            .map(|path| (path.clone(), self.get_dependents(path)))
            .collect()
    }

    /// Get topological order (base modules first)
    pub fn topological_order(&self) -> Vec<String> {
        self.topo_order.clone()
    }

    /// Get detected cycles
    pub fn cycles(&self) -> &[Vec<String>] {
        &self.cycles
    }

    /// Has cycles?
    pub fn has_cycles(&self) -> bool {
        !self.cycles.is_empty()
    }

    /// Get edge count (number of dependencies)
    pub fn edge_count(&self) -> usize {
        self.graph.edge_count()
    }

    /// Get node count (number of files)
    pub fn node_count(&self) -> usize {
        self.graph.node_count()
    }

    /// Get transitive dependents (files that depend on this file, transitively)
    pub fn get_transitive_dependents(&self, file_path: &str) -> Vec<String> {
        let mut visited = HashSet::new();
        let mut queue = VecDeque::new();

        if let Some(&idx) = self.path_to_node.get(file_path) {
            queue.push_back(idx);
        }

        while let Some(idx) = queue.pop_front() {
            for neighbor in self.graph.neighbors_directed(idx, Direction::Incoming) {
                let neighbor_path = &self.graph[neighbor];
                if visited.insert(neighbor_path.clone()) {
                    queue.push_back(neighbor);
                }
            }
        }

        visited.into_iter().collect()
    }

    /// Get transitive dependencies (files that this file depends on, transitively)
    pub fn get_transitive_dependencies(&self, file_path: &str) -> Vec<String> {
        let mut visited = HashSet::new();
        let mut queue = VecDeque::new();

        if let Some(&idx) = self.path_to_node.get(file_path) {
            queue.push_back(idx);
        }

        while let Some(idx) = queue.pop_front() {
            for neighbor in self.graph.neighbors_directed(idx, Direction::Outgoing) {
                let neighbor_path = &self.graph[neighbor];
                if visited.insert(neighbor_path.clone()) {
                    queue.push_back(neighbor);
                }
            }
        }

        visited.into_iter().collect()
    }

    /// Compute PageRank scores for all files
    ///
    /// PageRank measures the importance of each file based on the dependency graph structure.
    /// Files that are depended upon by many other important files get higher scores.
    ///
    /// # Algorithm
    ///
    /// Classic PageRank (Page & Brin, 1998):
    /// ```text
    /// PR(A) = (1-d)/N + d * Σ(PR(T_i) / C(T_i))
    /// ```
    /// where:
    /// - d = damping factor (0.85)
    /// - N = total number of nodes
    /// - T_i = nodes pointing to A
    /// - C(T_i) = out-degree of T_i
    ///
    /// # Returns
    ///
    /// HashMap mapping file paths to importance scores (0.0-1.0+)
    ///
    /// # Example
    ///
    /// ```ignore
    /// let graph = DependencyGraph::build(&imports);
    /// let scores = graph.compute_pagerank(None);
    ///
    /// // Find most critical files
    /// for (file, score) in scores.iter().take(10) {
    ///     println!("{}: {:.4}", file, score);
    /// }
    /// ```
    pub fn compute_pagerank(&self, config: Option<PageRankConfig>) -> HashMap<String, f64> {
        let config = config.unwrap_or_default();

        if self.graph.node_count() == 0 {
            return HashMap::new();
        }

        // Initialize PageRank scores (uniform distribution)
        let n = self.graph.node_count() as f64;
        let mut scores: HashMap<NodeIndex, f64> = HashMap::new();
        let initial_score = 1.0 / n;

        for idx in self.graph.node_indices() {
            scores.insert(idx, initial_score);
        }

        // Pre-compute out-degrees for dangling node handling
        let out_degrees: HashMap<NodeIndex, usize> = self
            .graph
            .node_indices()
            .map(|idx| {
                (
                    idx,
                    self.graph
                        .neighbors_directed(idx, Direction::Outgoing)
                        .count(),
                )
            })
            .collect();

        // Power iteration
        for _iteration in 0..config.max_iterations {
            let mut new_scores: HashMap<NodeIndex, f64> = HashMap::new();
            let mut max_diff: f64 = 0.0;

            // Calculate dangling node contribution (nodes with no outgoing edges)
            let dangling_sum: f64 = self
                .graph
                .node_indices()
                .filter(|idx| out_degrees[idx] == 0)
                .map(|idx| scores[&idx])
                .sum();

            for idx in self.graph.node_indices() {
                // Base score (teleportation) + dangling redistribution
                let mut score = (1.0 - config.damping) / n + config.damping * dangling_sum / n;

                // Add contributions from incoming edges
                for incoming_idx in self.graph.neighbors_directed(idx, Direction::Incoming) {
                    let incoming_score = scores[&incoming_idx];
                    let out_degree = out_degrees[&incoming_idx] as f64;

                    if out_degree > 0.0 {
                        score += config.damping * (incoming_score / out_degree);
                    }
                }

                // Track convergence
                let old_score = scores[&idx];
                let diff = (score - old_score).abs();
                max_diff = max_diff.max(diff);

                new_scores.insert(idx, score);
            }

            scores = new_scores;

            // Check convergence
            if max_diff < config.tolerance {
                break;
            }
        }

        // Convert NodeIndex -> file path
        scores
            .into_iter()
            .map(|(idx, score)| (self.graph[idx].clone(), score))
            .collect()
    }

    /// Get top-K most important files by PageRank
    ///
    /// # Arguments
    ///
    /// * `k` - Number of top files to return
    /// * `config` - Optional PageRank configuration
    ///
    /// # Returns
    ///
    /// Vec of (file_path, score) tuples, sorted by descending score
    ///
    /// # Example
    ///
    /// ```ignore
    /// let critical = graph.get_critical_files(10, None);
    /// for (file, score) in critical {
    ///     println!("Critical file: {} (importance: {:.4})", file, score);
    /// }
    /// ```
    pub fn get_critical_files(
        &self,
        k: usize,
        config: Option<PageRankConfig>,
    ) -> Vec<(String, f64)> {
        let scores = self.compute_pagerank(config);

        let mut ranked: Vec<(String, f64)> = scores.into_iter().collect();
        // Stable sort: by score descending, then by filename for tie-breaking
        ranked.sort_by(|a, b| {
            b.1.partial_cmp(&a.1)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| a.0.cmp(&b.0))
        });

        ranked.into_iter().take(k).collect()
    }

    /// Get PageRank score for a specific file
    ///
    /// Returns None if file not found in graph.
    pub fn get_file_importance(
        &self,
        file_path: &str,
        config: Option<PageRankConfig>,
    ) -> Option<f64> {
        let scores = self.compute_pagerank(config);
        scores.get(file_path).copied()
    }

    /// Get files ranked by importance (PageRank), with optional filtering
    ///
    /// # Arguments
    ///
    /// * `min_score` - Minimum PageRank score to include
    /// * `config` - Optional PageRank configuration
    ///
    /// # Returns
    ///
    /// Vec of (file_path, score) tuples, sorted by descending score
    pub fn get_important_files(
        &self,
        min_score: f64,
        config: Option<PageRankConfig>,
    ) -> Vec<(String, f64)> {
        let scores = self.compute_pagerank(config);

        let mut ranked: Vec<(String, f64)> = scores
            .into_iter()
            .filter(|(_, score)| *score >= min_score)
            .collect();

        ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        ranked
    }
}

impl Default for DependencyGraph {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::cross_file::types::ResolutionMethod;

    fn make_resolved_import(import_fqn: &str, source_file: Option<&str>) -> ResolvedImport {
        if let Some(file) = source_file {
            ResolvedImport::resolved(
                import_fqn.to_string(),
                import_fqn.to_string(),
                file.to_string(),
                "node123".to_string(),
                ResolutionMethod::ExactMatch,
            )
        } else {
            ResolvedImport::unresolved(import_fqn.to_string())
        }
    }

    #[test]
    fn test_empty_graph() {
        let graph = DependencyGraph::build(&HashMap::new());
        assert_eq!(graph.node_count(), 0);
        assert_eq!(graph.edge_count(), 0);
        assert!(!graph.has_cycles());
    }

    #[test]
    fn test_simple_dependency() {
        let mut imports = HashMap::new();

        // main.py depends on utils.py
        imports.insert(
            "src/main.py".to_string(),
            vec![make_resolved_import("utils.helper", Some("src/utils.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        assert_eq!(graph.node_count(), 2);
        assert_eq!(graph.edge_count(), 1);

        let deps = graph.get_dependencies("src/main.py");
        assert_eq!(deps, vec!["src/utils.py".to_string()]);

        let dependents = graph.get_dependents("src/utils.py");
        assert_eq!(dependents, vec!["src/main.py".to_string()]);
    }

    #[test]
    fn test_topological_order() {
        let mut imports = HashMap::new();

        // a.py depends on b.py
        // b.py depends on c.py
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "b.py".to_string(),
            vec![make_resolved_import("c", Some("c.py"))],
        );

        let graph = DependencyGraph::build(&imports);
        let order = graph.topological_order();

        // c.py should come before b.py, which should come before a.py
        let pos_c = order.iter().position(|x| x == "c.py").unwrap();
        let pos_b = order.iter().position(|x| x == "b.py").unwrap();
        let pos_a = order.iter().position(|x| x == "a.py").unwrap();

        assert!(pos_c < pos_b);
        assert!(pos_b < pos_a);
    }

    #[test]
    fn test_cycle_detection() {
        let mut imports = HashMap::new();

        // a.py depends on b.py
        // b.py depends on a.py (cycle!)
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "b.py".to_string(),
            vec![make_resolved_import("a", Some("a.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        assert!(graph.has_cycles());
        assert_eq!(graph.cycles().len(), 1);
        assert_eq!(graph.cycles()[0].len(), 2);
    }

    #[test]
    fn test_transitive_dependents() {
        let mut imports = HashMap::new();

        // a.py depends on b.py
        // b.py depends on c.py
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "b.py".to_string(),
            vec![make_resolved_import("c", Some("c.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Transitive dependents of c.py should include both a.py and b.py
        let trans_deps = graph.get_transitive_dependents("c.py");
        assert!(trans_deps.contains(&"a.py".to_string()));
        assert!(trans_deps.contains(&"b.py".to_string()));
    }

    #[test]
    fn test_external_imports_ignored() {
        let mut imports = HashMap::new();

        // main.py depends on numpy (external)
        imports.insert(
            "src/main.py".to_string(),
            vec![make_resolved_import("numpy", None)],
        );

        let graph = DependencyGraph::build(&imports);

        // Only main.py should be in the graph
        assert_eq!(graph.node_count(), 1);
        assert_eq!(graph.edge_count(), 0);
    }

    #[test]
    fn test_pagerank_simple() {
        let mut imports = HashMap::new();

        // a.py depends on b.py
        // c.py depends on b.py
        // b.py is a "hub" - should have highest PageRank
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "c.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // b.py should have highest score (depended on by both a.py and c.py)
        let score_b = scores.get("b.py").unwrap();
        let score_a = scores.get("a.py").unwrap();
        let score_c = scores.get("c.py").unwrap();

        assert!(*score_b > *score_a);
        assert!(*score_b > *score_c);

        // Scores should sum to approximately 1.0
        let total: f64 = scores.values().sum();
        assert!((total - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_pagerank_get_critical_files() {
        let mut imports = HashMap::new();

        // Create a star topology: all files depend on core.py
        for i in 1..=5 {
            imports.insert(
                format!("file{}.py", i),
                vec![make_resolved_import("core", Some("core.py"))],
            );
        }

        let graph = DependencyGraph::build(&imports);
        let critical = graph.get_critical_files(3, None);

        // core.py should be #1
        assert_eq!(critical[0].0, "core.py");

        // Should return exactly 3 files
        assert_eq!(critical.len(), 3);

        // Scores should be descending
        assert!(critical[0].1 >= critical[1].1);
        assert!(critical[1].1 >= critical[2].1);
    }

    #[test]
    fn test_pagerank_empty_graph() {
        let graph = DependencyGraph::build(&HashMap::new());
        let scores = graph.compute_pagerank(None);

        assert_eq!(scores.len(), 0);

        let critical = graph.get_critical_files(10, None);
        assert_eq!(critical.len(), 0);
    }

    #[test]
    fn test_pagerank_custom_config() {
        let mut imports = HashMap::new();

        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Test with custom damping factor
        let config = PageRankConfig {
            damping: 0.95,
            max_iterations: 50,
            tolerance: 1e-8,
        };

        let scores = graph.compute_pagerank(Some(config));

        // Should still return valid scores
        assert_eq!(scores.len(), 2);

        let total: f64 = scores.values().sum();
        assert!((total - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_get_file_importance() {
        let mut imports = HashMap::new();

        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "c.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Get importance for existing file
        let importance = graph.get_file_importance("b.py", None);
        assert!(importance.is_some());
        assert!(importance.unwrap() > 0.0);

        // Get importance for non-existent file
        let importance = graph.get_file_importance("nonexistent.py", None);
        assert!(importance.is_none());
    }

    #[test]
    fn test_get_important_files_with_threshold() {
        let mut imports = HashMap::new();

        // Create varying degrees of importance
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("core", Some("core.py"))],
        );
        imports.insert(
            "b.py".to_string(),
            vec![make_resolved_import("core", Some("core.py"))],
        );
        imports.insert(
            "c.py".to_string(),
            vec![make_resolved_import("a", Some("a.py"))],
        );

        let graph = DependencyGraph::build(&imports);
        let all_scores = graph.compute_pagerank(None);

        // Get average score
        let avg_score: f64 = all_scores.values().sum::<f64>() / all_scores.len() as f64;

        // Filter by above-average importance
        let important = graph.get_important_files(avg_score, None);

        // Should have fewer files than total
        assert!(important.len() < all_scores.len());

        // All returned files should have score >= threshold
        for (_, score) in &important {
            assert!(*score >= avg_score);
        }
    }

    // =====================================================================
    // EDGE CASES & CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_pagerank_single_node() {
        let mut imports = HashMap::new();

        // Single file with no dependencies
        imports.insert("lonely.py".to_string(), vec![]);

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // Should have score = 1.0 (only node)
        assert_eq!(scores.len(), 1);
        let score = scores.get("lonely.py").unwrap();
        assert!((score - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_pagerank_two_nodes_bidirectional() {
        let mut imports = HashMap::new();

        // a.py ↔ b.py (mutual dependency - cycle)
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "b.py".to_string(),
            vec![make_resolved_import("a", Some("a.py"))],
        );

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // Both should have equal scores (symmetric)
        let score_a = scores.get("a.py").unwrap();
        let score_b = scores.get("b.py").unwrap();

        assert!((score_a - score_b).abs() < 1e-6);
        assert!((score_a - 0.5).abs() < 0.1); // Each ~0.5
    }

    #[test]
    fn test_pagerank_chain_topology() {
        let mut imports = HashMap::new();

        // Linear chain: a → b → c → d → e
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "b.py".to_string(),
            vec![make_resolved_import("c", Some("c.py"))],
        );
        imports.insert(
            "c.py".to_string(),
            vec![make_resolved_import("d", Some("d.py"))],
        );
        imports.insert(
            "d.py".to_string(),
            vec![make_resolved_import("e", Some("e.py"))],
        );

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // e should have highest score (end of chain - no outgoing edges)
        let score_e = scores.get("e.py").unwrap();
        let score_a = scores.get("a.py").unwrap();

        assert!(*score_e > *score_a);

        // Scores should form a gradient: a < b < c < d < e
        assert!(scores.get("a.py").unwrap() < scores.get("b.py").unwrap());
        assert!(scores.get("b.py").unwrap() < scores.get("c.py").unwrap());
        assert!(scores.get("c.py").unwrap() < scores.get("d.py").unwrap());
        assert!(scores.get("d.py").unwrap() < scores.get("e.py").unwrap());
    }

    #[test]
    fn test_pagerank_star_vs_chain() {
        // Star topology vs chain - star center should dominate
        let mut star_imports = HashMap::new();
        for i in 1..=10 {
            star_imports.insert(
                format!("spoke{}.py", i),
                vec![make_resolved_import("hub", Some("hub.py"))],
            );
        }

        let mut chain_imports = HashMap::new();
        chain_imports.insert(
            "c1.py".to_string(),
            vec![make_resolved_import("c2", Some("c2.py"))],
        );
        for i in 2..=10 {
            chain_imports.insert(
                format!("c{}.py", i),
                vec![make_resolved_import(
                    &format!("c{}", i + 1),
                    Some(&format!("c{}.py", i + 1)),
                )],
            );
        }
        chain_imports.insert("c11.py".to_string(), vec![]);

        let star_graph = DependencyGraph::build(&star_imports);
        let chain_graph = DependencyGraph::build(&chain_imports);

        let star_scores = star_graph.compute_pagerank(None);
        let chain_scores = chain_graph.compute_pagerank(None);

        let hub_score = star_scores.get("hub.py").unwrap();
        let chain_max = chain_scores.values().copied().fold(0.0f64, f64::max);

        // Hub should have significantly higher score than any chain node
        assert!(*hub_score > chain_max * 2.0);
    }

    #[test]
    fn test_pagerank_isolated_components() {
        let mut imports = HashMap::new();

        // Component 1: a → b
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        // Component 2: c → d (isolated)
        imports.insert(
            "c.py".to_string(),
            vec![make_resolved_import("d", Some("d.py"))],
        );

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // Each component should have scores summing to ~0.5
        let component1_sum = scores.get("a.py").unwrap() + scores.get("b.py").unwrap();
        let component2_sum = scores.get("c.py").unwrap() + scores.get("d.py").unwrap();

        assert!((component1_sum - 0.5).abs() < 0.1);
        assert!((component2_sum - 0.5).abs() < 0.1);
    }

    #[test]
    fn test_pagerank_large_cycle() {
        let mut imports = HashMap::new();

        // Circular dependency: 1 → 2 → 3 → ... → 20 → 1
        for i in 1..=20 {
            let next = if i == 20 { 1 } else { i + 1 };
            imports.insert(
                format!("file{}.py", i),
                vec![make_resolved_import(
                    &format!("f{}", next),
                    Some(&format!("file{}.py", next)),
                )],
            );
        }

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // All nodes in cycle should have equal scores
        let first_score = scores.get("file1.py").unwrap();
        for i in 2..=20 {
            let score = scores.get(&format!("file{}.py", i)).unwrap();
            assert!((score - first_score).abs() < 1e-4);
        }

        // Each should be ~1/20
        assert!((first_score - 0.05).abs() < 0.01);
    }

    #[test]
    fn test_pagerank_convergence_early_exit() {
        let mut imports = HashMap::new();

        // Simple case that converges quickly
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Low tolerance should converge fast
        let config = PageRankConfig {
            damping: 0.85,
            max_iterations: 1000,
            tolerance: 1e-10,
        };

        let scores = graph.compute_pagerank(Some(config));

        // Should still get valid results
        assert_eq!(scores.len(), 2);
        let total: f64 = scores.values().sum();
        assert!((total - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_pagerank_max_iterations_limit() {
        let mut imports = HashMap::new();

        // Complex cyclic graph
        for i in 1..=10 {
            for j in 1..=10 {
                if i != j {
                    imports
                        .entry(format!("f{}.py", i))
                        .or_insert_with(Vec::new)
                        .push(make_resolved_import(
                            &format!("x{}", j),
                            Some(&format!("f{}.py", j)),
                        ));
                }
            }
        }

        let graph = DependencyGraph::build(&imports);

        // Very few iterations
        let config = PageRankConfig {
            damping: 0.85,
            max_iterations: 3,
            tolerance: 1e-12,
        };

        let scores = graph.compute_pagerank(Some(config));

        // Should stop after 3 iterations
        assert_eq!(scores.len(), 10);

        // Scores may not be perfectly converged, but should be valid
        let total: f64 = scores.values().sum();
        assert!((total - 1.0).abs() < 0.1); // Loose tolerance
    }

    #[test]
    fn test_pagerank_extreme_damping() {
        let mut imports = HashMap::new();

        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );
        imports.insert(
            "c.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Very low damping (mostly teleportation)
        let config_low = PageRankConfig {
            damping: 0.1,
            max_iterations: 100,
            tolerance: 1e-6,
        };

        // Very high damping (mostly follow links)
        let config_high = PageRankConfig {
            damping: 0.99,
            max_iterations: 100,
            tolerance: 1e-6,
        };

        let scores_low = graph.compute_pagerank(Some(config_low));
        let scores_high = graph.compute_pagerank(Some(config_high));

        // Low damping: scores should be more uniform
        let low_max = scores_low.values().copied().fold(0.0f64, f64::max);
        let low_min = scores_low.values().copied().fold(1.0f64, f64::min);

        // High damping: scores should be more differentiated
        let high_max = scores_high.values().copied().fold(0.0f64, f64::max);
        let high_min = scores_high.values().copied().fold(1.0f64, f64::min);

        // High damping should create larger spread
        assert!((high_max - high_min) > (low_max - low_min));
    }

    #[test]
    fn test_pagerank_dangling_nodes() {
        let mut imports = HashMap::new();

        // a, b, c all depend on d, but d has no dependencies (dangling node)
        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("d", Some("d.py"))],
        );
        imports.insert(
            "b.py".to_string(),
            vec![make_resolved_import("d", Some("d.py"))],
        );
        imports.insert(
            "c.py".to_string(),
            vec![make_resolved_import("d", Some("d.py"))],
        );

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // d should have very high score (3 incoming, 0 outgoing)
        let score_d = scores.get("d.py").unwrap();

        // d should have at least 50% of total importance
        assert!(*score_d > 0.5);
    }

    #[test]
    fn test_get_critical_files_k_larger_than_graph() {
        let mut imports = HashMap::new();

        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Ask for more files than exist
        let critical = graph.get_critical_files(100, None);

        // Should return all files (capped at graph size)
        assert_eq!(critical.len(), 2);
    }

    #[test]
    fn test_get_critical_files_k_zero() {
        let mut imports = HashMap::new();

        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Ask for 0 files
        let critical = graph.get_critical_files(0, None);

        assert_eq!(critical.len(), 0);
    }

    #[test]
    fn test_get_important_files_threshold_too_high() {
        let mut imports = HashMap::new();

        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Threshold higher than any score
        let important = graph.get_important_files(10.0, None);

        assert_eq!(important.len(), 0);
    }

    #[test]
    fn test_get_important_files_threshold_zero() {
        let mut imports = HashMap::new();

        imports.insert(
            "a.py".to_string(),
            vec![make_resolved_import("b", Some("b.py"))],
        );

        let graph = DependencyGraph::build(&imports);

        // Threshold 0.0 should return all files
        let important = graph.get_important_files(0.0, None);

        assert_eq!(important.len(), 2);
    }

    #[test]
    fn test_pagerank_self_loop_ignored() {
        let mut imports = HashMap::new();

        // File that imports itself (should be ignored by graph builder)
        imports.insert(
            "recursive.py".to_string(),
            vec![
                make_resolved_import("recursive", Some("recursive.py")),
                make_resolved_import("other", Some("other.py")),
            ],
        );

        let graph = DependencyGraph::build(&imports);

        // Should have 2 nodes, 1 edge (self-loop ignored)
        assert_eq!(graph.node_count(), 2);
        assert_eq!(graph.edge_count(), 1);

        let scores = graph.compute_pagerank(None);
        assert_eq!(scores.len(), 2);
    }

    #[test]
    fn test_pagerank_determinism() {
        let mut imports = HashMap::new();

        // Random-ish graph
        for i in 0..10 {
            imports.insert(
                format!("f{}.py", i),
                vec![
                    make_resolved_import("x", Some(&format!("f{}.py", (i + 1) % 10))),
                    make_resolved_import("y", Some(&format!("f{}.py", (i + 3) % 10))),
                ],
            );
        }

        let graph = DependencyGraph::build(&imports);

        // Run PageRank multiple times
        let scores1 = graph.compute_pagerank(None);
        let scores2 = graph.compute_pagerank(None);
        let scores3 = graph.compute_pagerank(None);

        // Results should be identical (deterministic)
        for key in scores1.keys() {
            assert!((scores1[key] - scores2[key]).abs() < 1e-10);
            assert!((scores1[key] - scores3[key]).abs() < 1e-10);
        }
    }

    #[test]
    fn test_pagerank_numerical_stability_large_graph() {
        let mut imports = HashMap::new();

        // Large graph (100 nodes)
        for i in 0..100 {
            imports.insert(
                format!("f{}.py", i),
                vec![
                    make_resolved_import("x", Some(&format!("f{}.py", (i + 1) % 100))),
                    make_resolved_import("y", Some(&format!("f{}.py", (i + 7) % 100))),
                    make_resolved_import("z", Some(&format!("f{}.py", (i + 13) % 100))),
                ],
            );
        }

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // Check numerical stability
        assert_eq!(scores.len(), 100);

        // All scores should be positive
        for score in scores.values() {
            assert!(*score > 0.0);
            assert!(score.is_finite());
        }

        // Sum should be 1.0 within tolerance
        let total: f64 = scores.values().sum();
        assert!((total - 1.0).abs() < 1e-4);

        // No score should be NaN or infinite
        for score in scores.values() {
            assert!(!score.is_nan());
            assert!(!score.is_infinite());
        }
    }

    #[test]
    fn test_pagerank_sorted_output_stability() {
        let mut imports = HashMap::new();

        // Create graph with very similar scores
        for i in 0..5 {
            imports.insert(
                format!("f{}.py", i),
                vec![make_resolved_import("hub", Some("hub.py"))],
            );
        }

        let graph = DependencyGraph::build(&imports);

        // Get critical files multiple times
        let critical1 = graph.get_critical_files(6, None);
        let critical2 = graph.get_critical_files(6, None);

        // Results should be identical (stable sorting)
        assert_eq!(critical1.len(), critical2.len());
        for i in 0..critical1.len() {
            assert_eq!(critical1[i].0, critical2[i].0);
            assert!((critical1[i].1 - critical2[i].1).abs() < 1e-10);
        }
    }

    #[test]
    fn test_pagerank_perfect_bipartite_graph() {
        let mut imports = HashMap::new();

        // Bipartite: Group A (a1, a2) → Group B (b1, b2)
        // Every A depends on every B
        for a in 1..=2 {
            for b in 1..=2 {
                imports
                    .entry(format!("a{}.py", a))
                    .or_insert_with(Vec::new)
                    .push(make_resolved_import(
                        &format!("b{}", b),
                        Some(&format!("b{}.py", b)),
                    ));
            }
        }

        let graph = DependencyGraph::build(&imports);
        let scores = graph.compute_pagerank(None);

        // All B nodes should have equal high scores
        let score_b1 = scores.get("b1.py").unwrap();
        let score_b2 = scores.get("b2.py").unwrap();
        assert!((score_b1 - score_b2).abs() < 1e-6);

        // All A nodes should have equal low scores
        let score_a1 = scores.get("a1.py").unwrap();
        let score_a2 = scores.get("a2.py").unwrap();
        assert!((score_a1 - score_a2).abs() < 1e-6);

        // B scores should be higher than A scores
        assert!(*score_b1 > *score_a1);
    }
}
