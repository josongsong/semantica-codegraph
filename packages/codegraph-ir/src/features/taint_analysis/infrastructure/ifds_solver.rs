/*
 * IFDS Tabulation Algorithm (Solver)
 *
 * NEW SOTA Implementation - No Python equivalent
 *
 * Implements the worklist-based tabulation algorithm from:
 * Reps, Horwitz, Sagiv (1995): "Precise Interprocedural Dataflow Analysis via Graph Reachability"
 *
 * Key Features:
 * - Worklist-based fixpoint iteration
 * - Exploded supergraph construction
 * - Summary edge computation
 * - Path edge propagation
 * - O(ED³) complexity (E=edges, D=dataflow facts)
 *
 * Algorithm Overview:
 * 1. Initialize worklist with seed facts
 * 2. Pop path edge (d1, n, d2) from worklist
 * 3. For each CFG successor m of n:
 *    - Apply flow function: flow(d2) = {d3, d4, ...}
 *    - For each d3 in flow(d2):
 *      - Add path edge (d1, m, d3) to worklist (if new)
 * 4. Handle calls specially:
 *    - Call edges: propagate to callee entry
 *    - Return edges: use summary edges
 *    - Call-to-return: pass-through local facts
 * 5. Repeat until worklist empty (fixpoint)
 *
 * Performance Target: Handle 10k+ functions, 100k+ facts
 *
 * References:
 * - Reps, Horwitz, Sagiv (1995): Original IFDS paper
 * - Naeem, Lhoták, Rodriguez (2010): Practical extensions
 * - Bodden et al. (2012): IFDS/IDE with Soot
 */

use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::{HashMap, HashSet, VecDeque};
use std::fmt::Debug;
use std::hash::Hash;
use std::time::Instant;

use super::ifds_framework::{
    DataflowFact, ExplodedEdge, ExplodedEdgeKind, ExplodedNode, ExplodedSupergraph, FlowFunction,
    IFDSProblem, IFDSStatistics, PathEdge, SummaryEdge,
};

/// CFG Edge (for control flow graph)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CFGEdge {
    pub from: String,
    pub to: String,
    pub kind: CFGEdgeKind,
}

/// CFG Edge Kind
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum CFGEdgeKind {
    /// Normal intra-procedural edge
    Normal,

    /// Call edge: call site → callee entry
    Call { callee_entry: String },

    /// Return edge: callee exit → return site
    Return { call_site: String },

    /// Call-to-return edge: call site → return site (pass-through)
    CallToReturn,
}

impl CFGEdge {
    pub fn normal(from: impl Into<String>, to: impl Into<String>) -> Self {
        Self {
            from: from.into(),
            to: to.into(),
            kind: CFGEdgeKind::Normal,
        }
    }

    pub fn call(call_site: impl Into<String>, callee_entry: impl Into<String>) -> Self {
        let callee_entry_str = callee_entry.into();
        Self {
            from: call_site.into(),
            to: callee_entry_str.clone(),
            kind: CFGEdgeKind::Call {
                callee_entry: callee_entry_str,
            },
        }
    }

    pub fn ret(
        callee_exit: impl Into<String>,
        return_site: impl Into<String>,
        call_site: impl Into<String>,
    ) -> Self {
        Self {
            from: callee_exit.into(),
            to: return_site.into(),
            kind: CFGEdgeKind::Return {
                call_site: call_site.into(),
            },
        }
    }

    pub fn call_to_return(call_site: impl Into<String>, return_site: impl Into<String>) -> Self {
        Self {
            from: call_site.into(),
            to: return_site.into(),
            kind: CFGEdgeKind::CallToReturn,
        }
    }
}

/// CFG (Control Flow Graph)
#[derive(Debug, Clone)]
pub struct CFG {
    /// All edges in the CFG
    pub edges: Vec<CFGEdge>,

    /// Adjacency list: node → successors
    pub successors: FxHashMap<String, Vec<CFGEdge>>,

    /// Entry nodes (procedure entries)
    pub entries: HashSet<String>,

    /// Exit nodes (procedure exits)
    pub exits: HashSet<String>,
}

impl CFG {
    pub fn new() -> Self {
        Self {
            edges: Vec::new(),
            successors: FxHashMap::default(),
            entries: HashSet::new(),
            exits: HashSet::new(),
        }
    }

    /// Add edge to CFG
    pub fn add_edge(&mut self, edge: CFGEdge) {
        self.successors
            .entry(edge.from.clone())
            .or_insert_with(Vec::new)
            .push(edge.clone());

        self.edges.push(edge);
    }

    /// Add entry node
    pub fn add_entry(&mut self, node: impl Into<String>) {
        self.entries.insert(node.into());
    }

    /// Add exit node
    pub fn add_exit(&mut self, node: impl Into<String>) {
        self.exits.insert(node.into());
    }

    /// Get successors of a node
    pub fn get_successors(&self, node: &str) -> Option<&[CFGEdge]> {
        self.successors.get(node).map(|v| v.as_slice())
    }
}

impl Default for CFG {
    fn default() -> Self {
        Self::new()
    }
}

/// IFDS Tabulation Solver
///
/// Implements the worklist-based tabulation algorithm.
///
/// Usage:
/// ```text
/// let mut solver = IFDSSolver::new(problem, cfg);
/// let result = solver.solve();
/// ```
pub struct IFDSSolver<F: DataflowFact> {
    /// IFDS problem specification
    problem: Box<dyn IFDSProblem<F>>,

    /// Control flow graph
    cfg: CFG,

    /// Exploded supergraph (CFG × Facts)
    supergraph: ExplodedSupergraph<F>,

    /// Path edges: (d1, n) → {d2, d3, ...}
    /// "If d1 holds at entry, then {d2, d3, ...} hold at n"
    path_edges: FxHashMap<(F, String), HashSet<F>>,

    /// Summary edges: (call_site, d1, return_site) → {d2, d3, ...}
    /// "Calling with d1 at call_site results in {d2, d3, ...} at return_site"
    summary_edges: FxHashMap<(String, F, String), HashSet<F>>,

    /// Worklist of path edges to process
    worklist: VecDeque<PathEdge<F>>,

    /// Statistics
    stats: IFDSStatistics,
}

impl<F: DataflowFact + 'static> IFDSSolver<F> {
    /// Create new IFDS solver
    ///
    /// # Arguments
    /// * `problem` - IFDS problem specification
    /// * `cfg` - Control flow graph
    pub fn new(problem: Box<dyn IFDSProblem<F>>, cfg: CFG) -> Self {
        Self {
            problem,
            cfg,
            supergraph: ExplodedSupergraph::new(),
            path_edges: FxHashMap::default(),
            summary_edges: FxHashMap::default(),
            worklist: VecDeque::new(),
            stats: IFDSStatistics::default(),
        }
    }

    /// Solve the IFDS problem
    ///
    /// Returns the exploded supergraph with all reachable facts.
    pub fn solve(mut self) -> IFDSSolverResult<F> {
        let start_time = Instant::now();

        // Initialize worklist with seed facts
        self.initialize_worklist();

        // Main tabulation loop
        while let Some(path_edge) = self.worklist.pop_front() {
            self.stats.num_iterations += 1;
            self.process_path_edge(path_edge);
        }

        // Compute statistics
        self.stats.num_exploded_nodes = self.supergraph.num_nodes();
        self.stats.num_exploded_edges = self.supergraph.num_edges();
        self.stats.num_path_edges = self.path_edges.values().map(|s| s.len()).sum();
        self.stats.num_summary_edges = self.summary_edges.values().map(|s| s.len()).sum();
        self.stats.analysis_time_ms = start_time.elapsed().as_millis() as u64;

        IFDSSolverResult {
            supergraph: self.supergraph,
            path_edges: self.path_edges,
            summary_edges: self.summary_edges,
            stats: self.stats,
        }
    }

    /// Solve with configurable limits
    ///
    /// # Arguments
    /// * `max_iterations` - Maximum number of iterations
    /// * `max_path_edges` - Maximum number of path edges
    ///
    /// # Returns
    /// Solver result (may be partial if limits exceeded)
    pub fn solve_with_limits(
        mut self,
        max_iterations: usize,
        max_path_edges: usize,
    ) -> IFDSSolverResult<F> {
        let start_time = Instant::now();

        // Initialize worklist with seed facts
        self.initialize_worklist();

        // Main tabulation loop with limits
        while let Some(path_edge) = self.worklist.pop_front() {
            // Check iteration limit
            if self.stats.num_iterations >= max_iterations {
                break;
            }

            // Check path edge limit
            let current_path_edges: usize = self.path_edges.values().map(|s| s.len()).sum();
            if current_path_edges >= max_path_edges {
                break;
            }

            self.stats.num_iterations += 1;
            self.process_path_edge(path_edge);
        }

        // Compute statistics
        self.stats.num_exploded_nodes = self.supergraph.num_nodes();
        self.stats.num_exploded_edges = self.supergraph.num_edges();
        self.stats.num_path_edges = self.path_edges.values().map(|s| s.len()).sum();
        self.stats.num_summary_edges = self.summary_edges.values().map(|s| s.len()).sum();
        self.stats.analysis_time_ms = start_time.elapsed().as_millis() as u64;

        IFDSSolverResult {
            supergraph: self.supergraph,
            path_edges: self.path_edges,
            summary_edges: self.summary_edges,
            stats: self.stats,
        }
    }

    /// Initialize worklist with seed facts
    fn initialize_worklist(&mut self) {
        let seeds = self.problem.initial_seeds();

        for (entry_node, seed_fact) in seeds {
            // Add path edge: (ZERO, entry, seed_fact)
            let zero = F::zero();
            let path_edge = PathEdge::new(zero.clone(), entry_node.clone(), seed_fact.clone());

            self.add_path_edge(path_edge);
        }
    }

    /// Process a path edge: (d1, n, d2)
    ///
    /// Propagates d2 to all successors of n.
    fn process_path_edge(&mut self, path_edge: PathEdge<F>) {
        let PathEdge {
            source_fact: d1,
            target_node: n,
            target_fact: d2,
        } = path_edge;

        // Get successors of n in CFG (clone to avoid borrow issues)
        let successors = match self.cfg.get_successors(&n) {
            Some(succs) => succs.to_vec(), // Clone the vec
            None => return,                // No successors
        };

        // Process each successor edge
        for edge in successors {
            match &edge.kind {
                CFGEdgeKind::Normal => {
                    // Normal intra-procedural edge
                    self.process_normal_edge(&d1, &n, &d2, &edge.to);
                }
                CFGEdgeKind::Call { callee_entry } => {
                    // Call edge: call site → callee entry
                    self.process_call_edge(&d1, &n, &d2, callee_entry);
                }
                CFGEdgeKind::Return { call_site } => {
                    // Return edge: callee exit → return site
                    self.process_return_edge(&d1, &n, &d2, &edge.to, call_site);
                }
                CFGEdgeKind::CallToReturn => {
                    // Call-to-return edge: pass-through local facts
                    self.process_call_to_return_edge(&d1, &n, &d2, &edge.to);
                }
            }
        }
    }

    /// Process normal intra-procedural edge: n → m
    fn process_normal_edge(
        &mut self,
        d1: &F,  // Source fact at entry
        n: &str, // Current node
        d2: &F,  // Fact at n
        m: &str, // Successor node
    ) {
        // Get flow function: n → m
        let flow = self.problem.normal_flow(n, m);

        // Apply flow function: d2 → {d3, d4, ...}
        let output_facts = flow.compute(d2);

        // Add path edges: (d1, m, d3) for each d3
        for d3 in output_facts {
            let path_edge = PathEdge::new(
                d1.clone(),
                m.to_string(),
                d3.clone(), // Clone d3 so we can use it below
            );
            self.add_path_edge(path_edge);

            // Add edge to supergraph
            self.add_supergraph_edge(
                n,
                d2,
                m,
                &d3, // Use d3 instead of path_edge.target_fact
                ExplodedEdgeKind::Normal,
            );
        }
    }

    /// Process call edge: call_site → callee_entry
    ///
    /// IFDS Call Edge Semantics with Summary Reuse (Reps et al. 1995):
    /// 1. Apply call_flow to propagate facts into callee
    /// 2. Check for existing summary edges to reuse
    fn process_call_edge(
        &mut self,
        d1: &F, // Source fact at entry
        call_site: &str,
        d2: &F, // Fact at call site
        callee_entry: &str,
    ) {
        // Get call flow function
        let flow = self.problem.call_flow(call_site, callee_entry);

        // Apply flow function: d2 → {d3, d4, ...}
        let output_facts = flow.compute(d2);

        // Find return site for this call (needed for summary edge lookup)
        let return_site = self.find_return_site_for_call(call_site);

        // Add path edges: (d3, callee_entry, d3) for each d3
        // (Each callee starts with its own source fact)
        for d3 in output_facts {
            let path_edge = PathEdge::new(
                d3.clone(), // Source fact = target fact at entry
                callee_entry.to_string(),
                d3.clone(),
            );
            self.add_path_edge(path_edge);

            // Add edge to supergraph
            self.add_supergraph_edge(call_site, d2, callee_entry, &d3, ExplodedEdgeKind::Call);

            // OPTIMIZATION: Reuse existing summary edges
            // If we already have a summary for (call_site, d3) -> (return_site, d_return),
            // we can immediately propagate to return_site without re-analyzing callee.
            if let Some(ref ret_site) = return_site {
                let summary_key = (call_site.to_string(), d3.clone(), ret_site.clone());
                if let Some(return_facts) = self.summary_edges.get(&summary_key).cloned() {
                    self.stats.num_summary_reuses += 1;
                    for d_return in return_facts {
                        // Add path edge directly to return site using summary
                        let summary_path_edge =
                            PathEdge::new(d1.clone(), ret_site.clone(), d_return.clone());
                        self.add_path_edge(summary_path_edge);

                        // Add edge to supergraph (summary edge application)
                        self.add_supergraph_edge(
                            call_site,
                            &d3,
                            ret_site,
                            &d_return,
                            ExplodedEdgeKind::Summary,
                        );
                    }
                }
            }
        }
    }

    /// Find the return site for a given call site
    fn find_return_site_for_call(&self, call_site: &str) -> Option<String> {
        if let Some(successors) = self.cfg.get_successors(call_site) {
            for edge in successors {
                if let CFGEdgeKind::CallToReturn = &edge.kind {
                    return Some(edge.to.clone());
                }
            }
        }
        None
    }

    /// Process return edge: callee_exit → return_site
    ///
    /// IFDS Return Edge Semantics (Reps et al. 1995):
    /// For a return from callee_exit to return_site, we need to find all
    /// (d1, d3) pairs at call_site where call_flow(d3) produces d4.
    /// Then propagate (d1, return_site, d6) for each d6 in return_flow(d5).
    fn process_return_edge(
        &mut self,
        d4: &F, // Source fact at callee entry
        callee_exit: &str,
        d5: &F, // Fact at callee exit
        return_site: &str,
        call_site: &str,
    ) {
        // Get return flow function
        let flow = self
            .problem
            .return_flow(callee_exit, return_site, call_site);

        // Apply flow function: d5 → {d6, d7, ...}
        let output_facts = flow.compute(d5);

        // For each output fact d6:
        for d6 in output_facts {
            // IFDS return edge handling:
            // Find all source facts at call_site that could have produced d4 in callee
            // Since d4 is the source fact in callee (from call_flow), we need to find
            // the corresponding caller facts.

            // Look for all path edges at call_site (any source fact)
            let call_site_facts: Vec<(F, F)> = self
                .path_edges
                .iter()
                .filter(|((_, node), _)| node == call_site)
                .flat_map(|((src, _), facts)| {
                    facts.iter().map(move |fact| (src.clone(), fact.clone()))
                })
                .collect();

            // Get callee entry (needed to get call_flow)
            // We need to find the callee_entry that corresponds to this return
            let callee_entry = self.find_callee_entry_for_return(callee_exit, call_site);

            for (d1, d3) in call_site_facts {
                // FIXED: Properly check if call_flow(d3) produces d4
                // This is the key IFDS invariant: we only connect returns when
                // the call_flow actually produced the callee's source fact.
                let call_flow_produces_d4 = if let Some(ref entry) = callee_entry {
                    let call_flow = self.problem.call_flow(call_site, entry);
                    let produced_facts = call_flow.compute(&d3);
                    produced_facts.contains(d4)
                } else {
                    // Fallback: if we can't find callee_entry, use conservative check
                    // Zero fact always flows through, or identity case
                    d4 == &d3 || d4.is_zero()
                };

                if call_flow_produces_d4 {
                    // Add path edge: (d1, return_site, d6)
                    let path_edge = PathEdge::new(d1.clone(), return_site.to_string(), d6.clone());
                    self.add_path_edge(path_edge);

                    // Add summary edge: (call_site, d3, return_site, d6)
                    self.add_summary_edge(call_site, d3.clone(), return_site, d6.clone());

                    // Add edge to supergraph
                    self.add_supergraph_edge(
                        callee_exit,
                        d5,
                        return_site,
                        &d6,
                        ExplodedEdgeKind::Return,
                    );
                }
            }
        }
    }

    /// Find the callee entry node for a given callee exit and call site
    fn find_callee_entry_for_return(&self, callee_exit: &str, call_site: &str) -> Option<String> {
        // Look through CFG to find the call edge from call_site
        if let Some(successors) = self.cfg.get_successors(call_site) {
            for edge in successors {
                if let CFGEdgeKind::Call { callee_entry } = &edge.kind {
                    // Heuristic: callee_entry and callee_exit should share a prefix
                    // (e.g., "foo_entry" and "foo_exit" both contain "foo")
                    let entry_base = callee_entry.trim_end_matches("_entry");
                    let exit_base = callee_exit.trim_end_matches("_exit");
                    if entry_base == exit_base
                        || callee_entry.starts_with(exit_base)
                        || exit_base.starts_with(entry_base)
                    {
                        return Some(callee_entry.clone());
                    }
                }
            }
            // If no match found, return the first callee entry (conservative)
            for edge in successors {
                if let CFGEdgeKind::Call { callee_entry } = &edge.kind {
                    return Some(callee_entry.clone());
                }
            }
        }
        None
    }

    /// Process call-to-return edge (pass-through for local facts)
    fn process_call_to_return_edge(
        &mut self,
        d1: &F, // Source fact at entry
        call_site: &str,
        d2: &F, // Fact at call site
        return_site: &str,
    ) {
        // Get call-to-return flow function
        let flow = self.problem.call_to_return_flow(call_site, return_site);

        // Apply flow function: d2 → {d3, d4, ...}
        let output_facts = flow.compute(d2);

        // Add path edges: (d1, return_site, d3) for each d3
        for d3 in output_facts {
            let path_edge = PathEdge::new(
                d1.clone(),
                return_site.to_string(),
                d3.clone(), // Clone d3 so we can use it below
            );
            self.add_path_edge(path_edge);

            // Add edge to supergraph
            self.add_supergraph_edge(
                call_site,
                d2,
                return_site,
                &d3, // Use d3 instead of path_edge.target_fact
                ExplodedEdgeKind::Normal,
            );
        }
    }

    /// Add path edge to worklist (if new)
    fn add_path_edge(&mut self, path_edge: PathEdge<F>) {
        let key = (path_edge.source_fact.clone(), path_edge.target_node.clone());

        let facts = self.path_edges.entry(key).or_insert_with(HashSet::new);

        // Only add if new
        if facts.insert(path_edge.target_fact.clone()) {
            self.worklist.push_back(path_edge);
        }
    }

    /// Add summary edge
    fn add_summary_edge(
        &mut self,
        call_site: &str,
        call_fact: F,
        return_site: &str,
        return_fact: F,
    ) {
        let key = (call_site.to_string(), call_fact, return_site.to_string());

        self.summary_edges
            .entry(key)
            .or_insert_with(HashSet::new)
            .insert(return_fact);
    }

    /// Add edge to exploded supergraph
    fn add_supergraph_edge(
        &mut self,
        from_node: &str,
        from_fact: &F,
        to_node: &str,
        to_fact: &F,
        kind: ExplodedEdgeKind,
    ) {
        let from = ExplodedNode::new(from_node.to_string(), from_fact.clone());
        let to = ExplodedNode::new(to_node.to_string(), to_fact.clone());

        let edge = ExplodedEdge { from, to, kind };
        self.supergraph.add_edge(edge);
    }
}

/// IFDS Solver Result
pub struct IFDSSolverResult<F: DataflowFact> {
    /// Exploded supergraph (CFG × Facts)
    pub supergraph: ExplodedSupergraph<F>,

    /// Path edges: (d1, n) → {d2, ...}
    pub path_edges: FxHashMap<(F, String), HashSet<F>>,

    /// Summary edges: (call_site, d1, return_site) → {d2, ...}
    pub summary_edges: FxHashMap<(String, F, String), HashSet<F>>,

    /// Statistics
    pub stats: IFDSStatistics,
}

impl<F: DataflowFact> IFDSSolverResult<F> {
    /// Get reachable facts at a node
    ///
    /// # Arguments
    /// * `node` - CFG node
    /// * `source_fact` - Source fact at entry (use ZERO for all facts)
    ///
    /// # Returns
    /// Set of reachable facts at node
    pub fn get_facts_at_node(&self, node: &str, source_fact: &F) -> HashSet<F> {
        let key = (source_fact.clone(), node.to_string());
        self.path_edges.get(&key).cloned().unwrap_or_default()
    }

    /// Check if a fact is reachable at a node (from specific source fact context)
    pub fn is_fact_reachable(&self, node: &str, source_fact: &F, target_fact: &F) -> bool {
        self.get_facts_at_node(node, source_fact)
            .contains(target_fact)
    }

    /// Check if a fact is reachable at a node (from any source fact context)
    ///
    /// This is useful when you want to check if a fact reaches a node regardless of
    /// the IFDS context (e.g., for inter-procedural analysis where callees start with
    /// new source facts).
    pub fn is_fact_at_node(&self, node: &str, target_fact: &F) -> bool {
        for ((_, n), facts) in &self.path_edges {
            if n == node && facts.contains(target_fact) {
                return true;
            }
        }
        false
    }

    /// Get all nodes where a fact is reachable
    pub fn get_nodes_with_fact(&self, fact: &F) -> HashSet<String> {
        let mut nodes = HashSet::new();

        for ((_, node), facts) in &self.path_edges {
            if facts.contains(fact) {
                nodes.insert(node.clone());
            }
        }

        nodes
    }

    /// Get all reachable facts at all nodes
    ///
    /// Groups facts by node (from any source fact context).
    ///
    /// # Returns
    /// Map from node → set of reachable facts
    pub fn get_reachable_facts_at_all_nodes(&self) -> FxHashMap<String, FxHashSet<F>> {
        let mut result: FxHashMap<String, FxHashSet<F>> = FxHashMap::default();

        for ((_, node), facts) in &self.path_edges {
            let entry = result.entry(node.clone()).or_default();
            for fact in facts {
                entry.insert(fact.clone());
            }
        }

        result
    }

    /// Get number of path edges
    pub fn path_edges_count(&self) -> usize {
        self.path_edges.values().map(|s| s.len()).sum()
    }

    /// Get number of summary edges
    pub fn summary_edges_count(&self) -> usize {
        self.summary_edges.values().map(|s| s.len()).sum()
    }

    /// Get analysis statistics
    pub fn statistics(&self) -> &IFDSStatistics {
        &self.stats
    }
}

#[cfg(test)]
mod tests {
    use super::super::ifds_framework::{GenFlowFunction, IdentityFlowFunction, KillFlowFunction};
    use super::*;

    /// Simple taint fact for testing
    #[derive(Debug, Clone, PartialEq, Eq, Hash)]
    enum TestFact {
        Zero,
        Tainted(String),
    }

    impl DataflowFact for TestFact {
        fn is_zero(&self) -> bool {
            matches!(self, TestFact::Zero)
        }

        fn zero() -> Self {
            TestFact::Zero
        }
    }

    /// Simple IFDS problem for testing
    struct SimpleTaintProblem;

    impl IFDSProblem<TestFact> for SimpleTaintProblem {
        fn initial_seeds(&self) -> Vec<(String, TestFact)> {
            vec![("entry".to_string(), TestFact::Tainted("input".to_string()))]
        }

        fn normal_flow(&self, _from: &str, _to: &str) -> Box<dyn FlowFunction<TestFact>> {
            Box::new(IdentityFlowFunction)
        }

        fn call_flow(
            &self,
            _call_site: &str,
            _callee_entry: &str,
        ) -> Box<dyn FlowFunction<TestFact>> {
            Box::new(IdentityFlowFunction)
        }

        fn return_flow(
            &self,
            _callee_exit: &str,
            _return_site: &str,
            _call_site: &str,
        ) -> Box<dyn FlowFunction<TestFact>> {
            Box::new(IdentityFlowFunction)
        }

        fn call_to_return_flow(
            &self,
            _call_site: &str,
            _return_site: &str,
        ) -> Box<dyn FlowFunction<TestFact>> {
            Box::new(IdentityFlowFunction)
        }
    }

    #[test]
    fn test_cfg_creation() {
        let mut cfg = CFG::new();

        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_edge(CFGEdge::normal("n2", "n3"));
        cfg.add_entry("n1");
        cfg.add_exit("n3");

        assert_eq!(cfg.edges.len(), 2);
        assert!(cfg.entries.contains("n1"));
        assert!(cfg.exits.contains("n3"));
    }

    #[test]
    fn test_cfg_successors() {
        let mut cfg = CFG::new();

        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_edge(CFGEdge::normal("n1", "n3"));

        let succs = cfg.get_successors("n1").unwrap();
        assert_eq!(succs.len(), 2);
    }

    #[test]
    fn test_simple_linear_flow() {
        // CFG: entry → n1 → n2 → exit
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_edge(CFGEdge::normal("n2", "exit"));
        cfg.add_entry("entry");
        cfg.add_exit("exit");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        // Check that taint propagates to all nodes
        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        assert!(result.is_fact_reachable("entry", &zero, &tainted));
        assert!(result.is_fact_reachable("n1", &zero, &tainted));
        assert!(result.is_fact_reachable("n2", &zero, &tainted));
        assert!(result.is_fact_reachable("exit", &zero, &tainted));
    }

    #[test]
    fn test_branching_flow() {
        // CFG: entry → n1 → n2
        //                 → n3
        //      n2, n3 → exit
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_edge(CFGEdge::normal("n1", "n3"));
        cfg.add_edge(CFGEdge::normal("n2", "exit"));
        cfg.add_edge(CFGEdge::normal("n3", "exit"));
        cfg.add_entry("entry");
        cfg.add_exit("exit");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        // Taint should reach both branches
        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        assert!(result.is_fact_reachable("n2", &zero, &tainted));
        assert!(result.is_fact_reachable("n3", &zero, &tainted));
        assert!(result.is_fact_reachable("exit", &zero, &tainted));
    }

    #[test]
    fn test_get_facts_at_node() {
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let facts = result.get_facts_at_node("entry", &zero);

        assert!(facts.contains(&TestFact::Tainted("input".to_string())));
    }

    #[test]
    fn test_get_nodes_with_fact() {
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let tainted = TestFact::Tainted("input".to_string());
        let nodes = result.get_nodes_with_fact(&tainted);

        assert!(nodes.contains("entry"));
        assert!(nodes.contains("n1"));
        assert!(nodes.contains("n2"));
    }

    #[test]
    fn test_statistics() {
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        assert!(result.stats.num_exploded_nodes > 0);
        assert!(result.stats.num_exploded_edges > 0);
        assert!(result.stats.num_path_edges > 0);
        assert!(result.stats.num_iterations > 0);
    }

    #[test]
    fn test_empty_cfg() {
        let cfg = CFG::new();
        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        // Should handle empty CFG gracefully
        assert_eq!(result.stats.num_exploded_nodes, 0);
    }

    #[test]
    fn test_cfg_edge_kinds() {
        let edge1 = CFGEdge::normal("n1", "n2");
        assert!(matches!(edge1.kind, CFGEdgeKind::Normal));

        let edge2 = CFGEdge::call("call_site", "callee");
        assert!(matches!(edge2.kind, CFGEdgeKind::Call { .. }));

        let edge3 = CFGEdge::ret("exit", "return_site", "call_site");
        assert!(matches!(edge3.kind, CFGEdgeKind::Return { .. }));

        let edge4 = CFGEdge::call_to_return("call_site", "return_site");
        assert!(matches!(edge4.kind, CFGEdgeKind::CallToReturn));
    }

    // ========== Phase 3: Advanced SOTA-Level Tests ==========

    /// Test interprocedural analysis: taint flows through function call
    ///
    /// CFG:
    ///   entry → call_site → callee_entry
    ///   callee_entry → callee_exit
    ///   callee_exit → return_site → exit
    ///   call_site → return_site (call-to-return)
    #[test]
    fn test_interprocedural_call_return() {
        let mut cfg = CFG::new();

        // Main function (using "entry" to match SimpleTaintProblem's initial_seeds)
        cfg.add_edge(CFGEdge::normal("entry", "call_site"));
        cfg.add_edge(CFGEdge::call("call_site", "callee_entry"));
        cfg.add_edge(CFGEdge::call_to_return("call_site", "return_site"));
        cfg.add_edge(CFGEdge::ret("callee_exit", "return_site", "call_site"));
        cfg.add_edge(CFGEdge::normal("return_site", "exit"));

        // Callee function
        cfg.add_edge(CFGEdge::normal("callee_entry", "callee_body"));
        cfg.add_edge(CFGEdge::normal("callee_body", "callee_exit"));

        cfg.add_entry("entry");
        cfg.add_exit("exit");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // Taint should flow through call
        assert!(result.is_fact_reachable("entry", &zero, &tainted));
        assert!(result.is_fact_reachable("call_site", &zero, &tainted));
        // In callee, source fact changes (IFDS context switch)
        assert!(result.is_fact_at_node("callee_entry", &tainted));
        assert!(result.is_fact_at_node("callee_body", &tainted));
        assert!(result.is_fact_at_node("callee_exit", &tainted));
        // After return, back in main context
        assert!(result.is_fact_at_node("return_site", &tainted));
        assert!(result.is_fact_at_node("exit", &tainted));

        // Verify summary edge was computed
        assert!(result.stats.num_summary_edges > 0);
    }

    /// Test call-to-return edge: local variables unaffected by call
    #[test]
    fn test_call_to_return_local_passthrough() {
        // Problem that generates local fact at call_site
        struct LocalPassthroughProblem;

        impl IFDSProblem<TestFact> for LocalPassthroughProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact)> {
                vec![
                    ("entry".to_string(), TestFact::Tainted("local".to_string())),
                    ("entry".to_string(), TestFact::Tainted("arg".to_string())),
                ]
            }

            fn normal_flow(&self, _from: &str, _to: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }

            fn call_flow(
                &self,
                _call_site: &str,
                _callee_entry: &str,
            ) -> Box<dyn FlowFunction<TestFact>> {
                // Only arg flows into callee
                struct ArgOnlyFlow;
                impl FlowFunction<TestFact> for ArgOnlyFlow {
                    fn compute(&self, input: &TestFact) -> HashSet<TestFact> {
                        match input {
                            TestFact::Tainted(s) if s == "arg" => HashSet::from([input.clone()]),
                            _ => HashSet::new(),
                        }
                    }
                }
                Box::new(ArgOnlyFlow)
            }

            fn return_flow(
                &self,
                _callee_exit: &str,
                _return_site: &str,
                _call_site: &str,
            ) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }

            fn call_to_return_flow(
                &self,
                _call_site: &str,
                _return_site: &str,
            ) -> Box<dyn FlowFunction<TestFact>> {
                // Local variables pass through
                struct LocalPassthroughFlow;
                impl FlowFunction<TestFact> for LocalPassthroughFlow {
                    fn compute(&self, input: &TestFact) -> HashSet<TestFact> {
                        match input {
                            TestFact::Tainted(s) if s == "local" => HashSet::from([input.clone()]),
                            _ => HashSet::new(),
                        }
                    }
                }
                Box::new(LocalPassthroughFlow)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "call_site"));
        cfg.add_edge(CFGEdge::call("call_site", "callee_entry"));
        cfg.add_edge(CFGEdge::call_to_return("call_site", "return_site"));
        cfg.add_edge(CFGEdge::ret("callee_exit", "return_site", "call_site"));
        cfg.add_edge(CFGEdge::normal("callee_entry", "callee_exit"));
        cfg.add_edge(CFGEdge::normal("return_site", "exit"));
        cfg.add_entry("entry");

        let problem = Box::new(LocalPassthroughProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let local = TestFact::Tainted("local".to_string());
        let arg = TestFact::Tainted("arg".to_string());

        // Local should bypass callee (via call-to-return edge)
        assert!(result.is_fact_reachable("call_site", &zero, &local));
        assert!(!result.is_fact_at_node("callee_entry", &local)); // NOT in callee (local doesn't enter)
        assert!(result.is_fact_reachable("return_site", &zero, &local)); // Back at return
        assert!(result.is_fact_reachable("exit", &zero, &local));

        // Arg should go through callee
        // Note: In IFDS, when entering callee, a new context starts with the arg as source_fact
        assert!(result.is_fact_reachable("call_site", &zero, &arg));
        assert!(result.is_fact_at_node("callee_entry", &arg)); // arg reaches callee (in its own context)
        assert!(result.is_fact_at_node("callee_exit", &arg));
        assert!(result.is_fact_at_node("return_site", &arg));
    }

    /// Test CFG with cycles: loop should converge to fixpoint
    #[test]
    fn test_cfg_with_loop_convergence() {
        // CFG: entry → loop_header ⇄ loop_body → exit
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "loop_header"));
        cfg.add_edge(CFGEdge::normal("loop_header", "loop_body"));
        cfg.add_edge(CFGEdge::normal("loop_body", "loop_header")); // Back edge
        cfg.add_edge(CFGEdge::normal("loop_header", "exit"));
        cfg.add_entry("entry");
        cfg.add_exit("exit");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // Taint should reach all nodes despite cycle
        assert!(result.is_fact_reachable("entry", &zero, &tainted));
        assert!(result.is_fact_reachable("loop_header", &zero, &tainted));
        assert!(result.is_fact_reachable("loop_body", &zero, &tainted));
        assert!(result.is_fact_reachable("exit", &zero, &tainted));

        // Should have multiple iterations due to cycle
        assert!(result.stats.num_iterations > 3);
    }

    /// Test nested loops: multiple cycles
    #[test]
    fn test_nested_loops() {
        // CFG: entry → outer_header ⇄ inner_header ⇄ inner_body → exit
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "outer_header"));
        cfg.add_edge(CFGEdge::normal("outer_header", "inner_header"));
        cfg.add_edge(CFGEdge::normal("inner_header", "inner_body"));
        cfg.add_edge(CFGEdge::normal("inner_body", "inner_header")); // Inner back edge
        cfg.add_edge(CFGEdge::normal("inner_header", "outer_header")); // Outer back edge
        cfg.add_edge(CFGEdge::normal("outer_header", "exit"));
        cfg.add_entry("entry");
        cfg.add_exit("exit");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // All nodes should be reachable
        assert!(result.is_fact_reachable("outer_header", &zero, &tainted));
        assert!(result.is_fact_reachable("inner_header", &zero, &tainted));
        assert!(result.is_fact_reachable("inner_body", &zero, &tainted));
        assert!(result.is_fact_reachable("exit", &zero, &tainted));
    }

    /// Test complex FlowFunction: Gen + Kill combination
    #[test]
    fn test_gen_kill_flow_function() {
        struct GenKillProblem;

        impl IFDSProblem<TestFact> for GenKillProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact)> {
                vec![("entry".to_string(), TestFact::Tainted("x".to_string()))]
            }

            fn normal_flow(&self, _from: &str, to: &str) -> Box<dyn FlowFunction<TestFact>> {
                if to == "sanitize" {
                    // x = sanitize(y): Kill x, Gen y
                    struct SanitizeFlow;
                    impl FlowFunction<TestFact> for SanitizeFlow {
                        fn compute(&self, input: &TestFact) -> HashSet<TestFact> {
                            match input {
                                TestFact::Tainted(s) if s == "x" => {
                                    // Kill x, gen clean y
                                    HashSet::new()
                                }
                                other => HashSet::from([other.clone()]),
                            }
                        }
                    }
                    Box::new(SanitizeFlow)
                } else {
                    Box::new(IdentityFlowFunction)
                }
            }

            fn call_flow(&self, _: &str, _: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }

            fn return_flow(&self, _: &str, _: &str, _: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }

            fn call_to_return_flow(&self, _: &str, _: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "before_sanitize"));
        cfg.add_edge(CFGEdge::normal("before_sanitize", "sanitize"));
        cfg.add_edge(CFGEdge::normal("sanitize", "after_sanitize"));
        cfg.add_entry("entry");

        let problem = Box::new(GenKillProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let x = TestFact::Tainted("x".to_string());

        // x should exist before sanitize
        assert!(result.is_fact_reachable("before_sanitize", &zero, &x));

        // x should be killed after sanitize
        assert!(!result.is_fact_reachable("after_sanitize", &zero, &x));
    }

    /// Test multiple facts at same node
    #[test]
    fn test_multiple_facts_per_node() {
        struct MultiFact;

        impl IFDSProblem<TestFact> for MultiFact {
            fn initial_seeds(&self) -> Vec<(String, TestFact)> {
                vec![
                    ("entry".to_string(), TestFact::Tainted("x".to_string())),
                    ("entry".to_string(), TestFact::Tainted("y".to_string())),
                    ("entry".to_string(), TestFact::Tainted("z".to_string())),
                ]
            }

            fn normal_flow(&self, _: &str, _: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }

            fn call_flow(&self, _: &str, _: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }

            fn return_flow(&self, _: &str, _: &str, _: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }

            fn call_to_return_flow(&self, _: &str, _: &str) -> Box<dyn FlowFunction<TestFact>> {
                Box::new(IdentityFlowFunction)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_entry("entry");

        let problem = Box::new(MultiFact);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let x = TestFact::Tainted("x".to_string());
        let y = TestFact::Tainted("y".to_string());
        let z = TestFact::Tainted("z".to_string());

        // All three facts should coexist at n1
        let facts = result.get_facts_at_node("n1", &zero);
        assert!(facts.contains(&x));
        assert!(facts.contains(&y));
        assert!(facts.contains(&z));
        assert_eq!(facts.len(), 3);
    }

    /// Test multiple paths to same node with meet
    #[test]
    fn test_multiple_paths_convergence() {
        // CFG: entry → path1 → merge
        //           → path2 → merge
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "path1"));
        cfg.add_edge(CFGEdge::normal("entry", "path2"));
        cfg.add_edge(CFGEdge::normal("path1", "merge"));
        cfg.add_edge(CFGEdge::normal("path2", "merge"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // Taint from both paths should reach merge
        assert!(result.is_fact_reachable("path1", &zero, &tainted));
        assert!(result.is_fact_reachable("path2", &zero, &tainted));
        assert!(result.is_fact_reachable("merge", &zero, &tainted));
    }

    /// Test unreachable nodes
    #[test]
    fn test_unreachable_nodes() {
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        // orphan_node is not connected
        cfg.add_edge(CFGEdge::normal("orphan", "orphan2"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // Reachable nodes should have taint
        assert!(result.is_fact_reachable("entry", &zero, &tainted));
        assert!(result.is_fact_reachable("n1", &zero, &tainted));
        assert!(result.is_fact_reachable("n2", &zero, &tainted));

        // Orphan nodes should NOT have taint
        assert!(!result.is_fact_reachable("orphan", &zero, &tainted));
        assert!(!result.is_fact_reachable("orphan2", &zero, &tainted));
    }

    /// Test large CFG performance (100 nodes)
    #[test]
    fn test_large_cfg_performance() {
        let mut cfg = CFG::new();

        // Create linear chain of 100 nodes, starting from "entry" to match SimpleTaintProblem
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_entry("entry");
        for i in 1..99 {
            let from = format!("n{}", i);
            let to = format!("n{}", i + 1);
            cfg.add_edge(CFGEdge::normal(&from, &to));
        }
        cfg.add_exit("n99");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);

        let start = std::time::Instant::now();
        let result = solver.solve();
        let elapsed = start.elapsed();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // Should reach all nodes
        assert!(result.is_fact_reachable("entry", &zero, &tainted));
        assert!(result.is_fact_reachable("n50", &zero, &tainted));
        assert!(result.is_fact_reachable("n99", &zero, &tainted));

        // Should complete in reasonable time (< 100ms for 100 nodes)
        assert!(elapsed.as_millis() < 100, "Took too long: {:?}", elapsed);

        // Statistics should be reasonable
        assert!(result.stats.num_exploded_nodes > 0);
        assert!(result.stats.num_iterations <= 102); // Linear should be ~100 iterations
    }

    /// Test diamond-shaped CFG (common pattern)
    #[test]
    fn test_diamond_cfg() {
        // CFG: entry → branch1 → merge
        //           → branch2 → merge
        //      merge → exit
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "branch1"));
        cfg.add_edge(CFGEdge::normal("entry", "branch2"));
        cfg.add_edge(CFGEdge::normal("branch1", "merge"));
        cfg.add_edge(CFGEdge::normal("branch2", "merge"));
        cfg.add_edge(CFGEdge::normal("merge", "exit"));
        cfg.add_entry("entry");
        cfg.add_exit("exit");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // All paths should propagate taint
        assert!(result.is_fact_reachable("branch1", &zero, &tainted));
        assert!(result.is_fact_reachable("branch2", &zero, &tainted));
        assert!(result.is_fact_reachable("merge", &zero, &tainted));
        assert!(result.is_fact_reachable("exit", &zero, &tainted));
    }

    /// Test summary edge reuse across multiple call sites
    #[test]
    fn test_summary_edge_reuse() {
        // CFG: main calls helper twice (using "entry" to match SimpleTaintProblem)
        let mut cfg = CFG::new();

        // First call
        cfg.add_edge(CFGEdge::normal("entry", "call1"));
        cfg.add_edge(CFGEdge::call("call1", "helper_entry"));
        cfg.add_edge(CFGEdge::call_to_return("call1", "return1"));
        cfg.add_edge(CFGEdge::ret("helper_exit", "return1", "call1"));

        // Second call
        cfg.add_edge(CFGEdge::normal("return1", "call2"));
        cfg.add_edge(CFGEdge::call("call2", "helper_entry"));
        cfg.add_edge(CFGEdge::call_to_return("call2", "return2"));
        cfg.add_edge(CFGEdge::ret("helper_exit", "return2", "call2"));

        // Helper function
        cfg.add_edge(CFGEdge::normal("helper_entry", "helper_body"));
        cfg.add_edge(CFGEdge::normal("helper_body", "helper_exit"));

        cfg.add_edge(CFGEdge::normal("return2", "exit"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintProblem);
        let solver = IFDSSolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let tainted = TestFact::Tainted("input".to_string());

        // Taint should flow through both calls
        assert!(result.is_fact_reachable("call1", &zero, &tainted));
        assert!(result.is_fact_at_node("return1", &tainted));
        assert!(result.is_fact_at_node("call2", &tainted));
        assert!(result.is_fact_at_node("return2", &tainted));
        assert!(result.is_fact_at_node("exit", &tainted));

        // Should have summary edges for both calls
        assert!(result.stats.num_summary_edges >= 2);
    }
}
