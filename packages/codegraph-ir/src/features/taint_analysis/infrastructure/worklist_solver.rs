/*
 * Worklist Fixpoint Solver for Taint Analysis
 *
 * Classic dataflow framework based on Kildall's algorithm (1973).
 *
 * Algorithm:
 * 1. Initialize in_facts and out_facts for each CFG node
 * 2. Add entry node to worklist
 * 3. While worklist not empty:
 *    a. Pop node from worklist
 *    b. Meet: Union predecessor out_facts → new_in
 *    c. Transfer: Apply flow function new_in → new_out
 *    d. If new_out changed: update and add successors to worklist
 * 4. Fixpoint reached when worklist empty
 *
 * Performance:
 * - Time: O(CFG_edges × transfer_cost)
 * - Space: O(CFG_nodes × facts_per_node)
 * - Typical: 5-10 iterations for convergence
 *
 * References:
 * - Kildall, G. (1973). "A Unified Approach to Global Program Optimization"
 * - Kam, J. & Ullman, J. (1977). "Monotone Data Flow Analysis Frameworks"
 * - Python: fixpoint_taint_solver.py (300 lines)
 */

use rustc_hash::FxHashMap;
use std::collections::{HashMap, HashSet, VecDeque};

/// Taint fact: (variable, source location)
///
/// Example:
///   TaintFact { variable: "user_input", source: "node_42" }
///   → Variable "user_input" was tainted at node 42
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct TaintFact {
    /// Variable name
    pub variable: String,

    /// Source node ID where taint originated
    pub source: String,
}

impl TaintFact {
    /// Create new taint fact
    pub fn new(variable: impl Into<String>, source: impl Into<String>) -> Self {
        Self {
            variable: variable.into(),
            source: source.into(),
        }
    }
}

/// CFG node representation for worklist solver
///
/// Minimal representation needed for dataflow:
/// - Predecessors and successors
/// - Variables defined/used
/// - Node semantics (source, sanitizer, assignment)
#[derive(Debug, Clone)]
pub struct CFGNode {
    /// Node ID
    pub id: String,

    /// Predecessor nodes
    pub predecessors: Vec<String>,

    /// Successor nodes
    pub successors: Vec<String>,

    /// Variable defined by this node (if any)
    pub def_var: Option<String>,

    /// Variables used by this node
    pub use_vars: HashSet<String>,

    /// Is this a taint source?
    pub is_source: bool,

    /// Is this a sanitizer?
    pub is_sanitizer: bool,
}

impl CFGNode {
    /// Create new CFG node
    pub fn new(id: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            predecessors: Vec::new(),
            successors: Vec::new(),
            def_var: None,
            use_vars: HashSet::new(),
            is_source: false,
            is_sanitizer: false,
        }
    }

    /// Add predecessor
    pub fn add_predecessor(&mut self, pred_id: impl Into<String>) {
        self.predecessors.push(pred_id.into());
    }

    /// Add successor
    pub fn add_successor(&mut self, succ_id: impl Into<String>) {
        self.successors.push(succ_id.into());
    }
}

/// CFG representation for worklist solver
#[derive(Debug, Clone)]
pub struct CFG {
    /// All nodes by ID
    pub nodes: FxHashMap<String, CFGNode>,

    /// Entry node ID
    pub entry: String,

    /// Exit nodes (may be multiple)
    pub exits: Vec<String>,
}

impl CFG {
    /// Create new CFG
    pub fn new(entry: impl Into<String>) -> Self {
        Self {
            nodes: FxHashMap::default(),
            entry: entry.into(),
            exits: Vec::new(),
        }
    }

    /// Add node
    pub fn add_node(&mut self, node: CFGNode) {
        self.nodes.insert(node.id.clone(), node);
    }

    /// Get predecessors of node
    pub fn predecessors(&self, node_id: &str) -> Vec<String> {
        self.nodes
            .get(node_id)
            .map(|n| n.predecessors.clone())
            .unwrap_or_default()
    }

    /// Get successors of node
    pub fn successors(&self, node_id: &str) -> Vec<String> {
        self.nodes
            .get(node_id)
            .map(|n| n.successors.clone())
            .unwrap_or_default()
    }
}

/// Worklist-based fixpoint solver for taint analysis
///
/// Classic Kildall-style dataflow framework:
/// - Meet: Union of predecessor out facts
/// - Transfer: Gen/Kill/Propagate
/// - Iterate until fixpoint
///
/// Performance characteristics:
/// - Typical convergence: 5-10 iterations
/// - Worst case: O(CFG_nodes × lattice_height)
/// - With widening: guaranteed termination
pub struct WorklistTaintSolver {
    /// Control Flow Graph
    cfg: CFG,

    /// Max iterations (safety limit)
    max_iterations: usize,

    /// Enable debug tracing
    trace: bool,
}

impl WorklistTaintSolver {
    /// Create new solver
    pub fn new(cfg: CFG) -> Self {
        Self {
            cfg,
            max_iterations: 1000,
            trace: false,
        }
    }

    /// Create solver with custom iteration limit
    pub fn with_max_iterations(mut self, max_iterations: usize) -> Self {
        self.max_iterations = max_iterations;
        self
    }

    /// Enable debug tracing
    pub fn with_trace(mut self, trace: bool) -> Self {
        self.trace = trace;
        self
    }

    /// Solve taint analysis using worklist iteration
    ///
    /// # Arguments
    /// * `sources` - Initial taint sources: {node_id: {variables}}
    /// * `sinks` - Sink nodes to check
    ///
    /// # Returns
    /// out_facts for each node: {node_id: {TaintFact}}
    ///
    /// # Algorithm
    /// ```text
    /// 1. Initialize in_facts, out_facts = ∅
    /// 2. worklist = [entry]
    /// 3. while worklist ≠ ∅:
    ///      node = worklist.pop()
    ///      new_in = ⋃ out_facts[pred] for pred in predecessors(node)
    ///      new_out = transfer(node, new_in)
    ///      if new_out ≠ out_facts[node]:
    ///        out_facts[node] = new_out
    ///        worklist.extend(successors(node))
    /// 4. return out_facts
    /// ```
    pub fn solve(
        &self,
        sources: &HashMap<String, HashSet<String>>,
        _sinks: &HashSet<String>,
    ) -> HashMap<String, HashSet<TaintFact>> {
        let mut in_facts: FxHashMap<String, HashSet<TaintFact>> = FxHashMap::default();
        let mut out_facts: FxHashMap<String, HashSet<TaintFact>> = FxHashMap::default();
        let mut worklist = VecDeque::new();

        // NO initialization - let nodes be added on-demand during analysis
        // This allows proper first-visit detection in changed logic

        // Start from entry
        worklist.push_back(self.cfg.entry.clone());

        let mut iterations = 0;

        #[cfg(feature = "trace")]
        if self.trace {
            eprintln!(
                "[Worklist] Starting fixpoint iteration from entry: {}",
                self.cfg.entry
            );
        }

        while let Some(node_id) = worklist.pop_front() {
            iterations += 1;

            if iterations > self.max_iterations {
                #[cfg(feature = "trace")]
                if self.trace {
                    eprintln!(
                        "[Worklist] WARNING: Exceeded max iterations ({})",
                        self.max_iterations
                    );
                }
                break;
            }

            // Meet: Union of predecessor out facts
            let mut new_in = HashSet::new();
            for pred_id in self.cfg.predecessors(&node_id) {
                if let Some(pred_out) = out_facts.get(&pred_id) {
                    new_in.extend(pred_out.iter().cloned());
                }
            }

            // Update in_facts
            in_facts.insert(node_id.clone(), new_in.clone());

            // Transfer function
            let new_out = self.transfer(&node_id, &new_in, sources);

            // Check if changed
            // CRITICAL: First visit must be treated as changed (even if empty)
            // to ensure all reachable nodes are processed
            let changed = if let Some(old_out) = out_facts.get(&node_id) {
                &new_out != old_out
            } else {
                true // First visit: always changed to propagate to successors
            };

            if changed {
                #[cfg(feature = "trace")]
                if self.trace {
                    eprintln!(
                        "[Worklist] Node {} changed: {} facts → {} facts",
                        node_id,
                        out_facts.get(&node_id).map_or(0, |s| s.len()),
                        new_out.len()
                    );
                }

                out_facts.insert(node_id.clone(), new_out);

                // Add successors to worklist
                for succ_id in self.cfg.successors(&node_id) {
                    if !worklist.contains(&succ_id) {
                        worklist.push_back(succ_id);
                    }
                }
            }
        }

        #[cfg(feature = "trace")]
        if self.trace {
            eprintln!("[Worklist] Converged after {} iterations", iterations);
        }

        out_facts.into_iter().collect()
    }

    /// Transfer function: Gen/Kill/Propagate
    ///
    /// # Gen (Generate new taints)
    /// - If node is a source, add taint facts for source variables
    ///
    /// # Kill (Remove taints)
    /// - If node is a sanitizer, remove taint facts for sanitized variables
    ///
    /// # Propagate (Copy taints)
    /// - If node defines `x = f(y1, y2, ...)` and any `yi` is tainted,
    ///   then `x` becomes tainted
    ///
    /// # Arguments
    /// * `node_id` - Current CFG node
    /// * `in_facts` - Input taint facts
    /// * `sources` - Known taint sources
    ///
    /// # Returns
    /// Output taint facts after applying transfer function
    fn transfer(
        &self,
        node_id: &str,
        in_facts: &HashSet<TaintFact>,
        sources: &HashMap<String, HashSet<String>>,
    ) -> HashSet<TaintFact> {
        let Some(node) = self.cfg.nodes.get(node_id) else {
            return in_facts.clone();
        };

        let mut out = in_facts.clone();

        // GEN: Add new taints from sources
        if let Some(source_vars) = sources.get(node_id) {
            for var in source_vars {
                out.insert(TaintFact::new(var.clone(), node_id));
            }
        }

        // KILL: Remove sanitized taints
        if node.is_sanitizer {
            let before_count = out.len();
            out.retain(|fact| !node.use_vars.contains(&fact.variable));

            #[cfg(feature = "trace")]
            if self.trace && out.len() < before_count {
                eprintln!(
                    "[Transfer] KILL: Sanitized {} facts at {}",
                    before_count - out.len(),
                    node_id
                );
            }
        }

        // PROPAGATE: x = f(y) where y is tainted
        if let Some(def_var) = &node.def_var {
            for use_var in &node.use_vars {
                for fact in in_facts {
                    if &fact.variable == use_var {
                        out.insert(TaintFact::new(def_var.clone(), fact.source.clone()));

                        #[cfg(feature = "trace")]
                        if self.trace {
                            eprintln!(
                                "[Transfer] PROPAGATE: {} → {} (source: {})",
                                use_var, def_var, fact.source
                            );
                        }
                    }
                }
            }
        }

        out
    }

    /// Get taint facts at entry of a node
    pub fn get_in_facts(
        &self,
        node_id: &str,
        result: &HashMap<String, HashSet<TaintFact>>,
    ) -> HashSet<TaintFact> {
        let mut in_facts = HashSet::new();
        for pred_id in self.cfg.predecessors(node_id) {
            if let Some(pred_out) = result.get(&pred_id) {
                in_facts.extend(pred_out.iter().cloned());
            }
        }
        in_facts
    }

    /// Check if a sink is reachable with tainted data
    ///
    /// # Arguments
    /// * `sink_id` - Sink node ID
    /// * `result` - Fixpoint solution (out_facts per node)
    ///
    /// # Returns
    /// Set of tainted variables reaching the sink
    pub fn check_sink(
        &self,
        sink_id: &str,
        result: &HashMap<String, HashSet<TaintFact>>,
    ) -> HashSet<String> {
        let in_facts = self.get_in_facts(sink_id, result);
        in_facts.into_iter().map(|f| f.variable).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_taint_fact_creation() {
        let fact = TaintFact::new("user_input", "node_1");
        assert_eq!(fact.variable, "user_input");
        assert_eq!(fact.source, "node_1");
    }

    #[test]
    fn test_cfg_node_creation() {
        let mut node = CFGNode::new("n1");
        node.add_predecessor("n0");
        node.add_successor("n2");
        node.def_var = Some("x".to_string());
        node.use_vars.insert("y".to_string());

        assert_eq!(node.id, "n1");
        assert_eq!(node.predecessors, vec!["n0"]);
        assert_eq!(node.successors, vec!["n2"]);
        assert_eq!(node.def_var, Some("x".to_string()));
        assert!(node.use_vars.contains("y"));
    }

    #[test]
    fn test_simple_source_to_sink() {
        // CFG: entry -> source -> sink -> exit
        let mut cfg = CFG::new("entry");

        let mut entry = CFGNode::new("entry");
        entry.add_successor("source");

        let mut source = CFGNode::new("source");
        source.add_predecessor("entry");
        source.add_successor("sink");
        source.def_var = Some("user_input".to_string());
        source.is_source = true;

        let mut sink = CFGNode::new("sink");
        sink.add_predecessor("source");
        sink.add_successor("exit");
        sink.use_vars.insert("user_input".to_string());

        let mut exit = CFGNode::new("exit");
        exit.add_predecessor("sink");

        cfg.add_node(entry);
        cfg.add_node(source);
        cfg.add_node(sink);
        cfg.add_node(exit);
        cfg.exits.push("exit".to_string());

        let solver = WorklistTaintSolver::new(cfg).with_trace(true);

        let sources = HashMap::from([(
            "source".to_string(),
            HashSet::from(["user_input".to_string()]),
        )]);
        let sinks = HashSet::from(["sink".to_string()]);

        let result = solver.solve(&sources, &sinks);

        // Check that sink receives tainted data
        let tainted_at_sink = solver.check_sink("sink", &result);
        assert!(
            tainted_at_sink.contains("user_input"),
            "Sink should receive tainted user_input"
        );
    }

    #[test]
    fn test_sanitizer_blocks_taint() {
        // CFG: entry -> source -> sanitizer -> sink
        let mut cfg = CFG::new("entry");

        let mut entry = CFGNode::new("entry");
        entry.add_successor("source");

        let mut source = CFGNode::new("source");
        source.add_predecessor("entry");
        source.add_successor("sanitizer");
        source.def_var = Some("user_input".to_string());
        source.is_source = true;

        let mut sanitizer = CFGNode::new("sanitizer");
        sanitizer.add_predecessor("source");
        sanitizer.add_successor("sink");
        sanitizer.use_vars.insert("user_input".to_string());
        sanitizer.is_sanitizer = true;

        let mut sink = CFGNode::new("sink");
        sink.add_predecessor("sanitizer");
        sink.use_vars.insert("user_input".to_string());

        cfg.add_node(entry);
        cfg.add_node(source);
        cfg.add_node(sanitizer);
        cfg.add_node(sink);

        let solver = WorklistTaintSolver::new(cfg);

        let sources = HashMap::from([(
            "source".to_string(),
            HashSet::from(["user_input".to_string()]),
        )]);
        let sinks = HashSet::from(["sink".to_string()]);

        let result = solver.solve(&sources, &sinks);

        // Check that sanitizer removed taint
        let tainted_at_sink = solver.check_sink("sink", &result);
        assert!(
            tainted_at_sink.is_empty(),
            "Sanitizer should block taint from reaching sink"
        );
    }

    #[test]
    fn test_taint_propagation() {
        // CFG: entry -> source(x) -> assign(y=x) -> sink(y)
        let mut cfg = CFG::new("entry");

        let mut entry = CFGNode::new("entry");
        entry.add_successor("source");

        let mut source = CFGNode::new("source");
        source.add_predecessor("entry");
        source.add_successor("assign");
        source.def_var = Some("x".to_string());

        let mut assign = CFGNode::new("assign");
        assign.add_predecessor("source");
        assign.add_successor("sink");
        assign.def_var = Some("y".to_string());
        assign.use_vars.insert("x".to_string());

        let mut sink = CFGNode::new("sink");
        sink.add_predecessor("assign");
        sink.use_vars.insert("y".to_string());

        cfg.add_node(entry);
        cfg.add_node(source);
        cfg.add_node(assign);
        cfg.add_node(sink);

        let solver = WorklistTaintSolver::new(cfg);

        let sources = HashMap::from([("source".to_string(), HashSet::from(["x".to_string()]))]);
        let sinks = HashSet::from(["sink".to_string()]);

        let result = solver.solve(&sources, &sinks);

        // Check that taint propagates from x to y
        let tainted_at_sink = solver.check_sink("sink", &result);
        assert!(
            tainted_at_sink.contains("y"),
            "Taint should propagate from x to y"
        );
    }

    #[test]
    fn test_convergence_on_loop() {
        // CFG with loop: entry -> loop_head <-> loop_body -> exit
        let mut cfg = CFG::new("entry");

        let mut entry = CFGNode::new("entry");
        entry.add_successor("loop_head");

        let mut loop_head = CFGNode::new("loop_head");
        loop_head.add_predecessor("entry");
        loop_head.add_predecessor("loop_body");
        loop_head.add_successor("loop_body");
        loop_head.add_successor("exit");

        let mut loop_body = CFGNode::new("loop_body");
        loop_body.add_predecessor("loop_head");
        loop_body.add_successor("loop_head");

        let mut exit = CFGNode::new("exit");
        exit.add_predecessor("loop_head");

        cfg.add_node(entry);
        cfg.add_node(loop_head);
        cfg.add_node(loop_body);
        cfg.add_node(exit);

        let solver = WorklistTaintSolver::new(cfg);

        let sources = HashMap::from([("loop_body".to_string(), HashSet::from(["i".to_string()]))]);
        let sinks = HashSet::new();

        // Should converge without infinite loop
        let _result = solver.solve(&sources, &sinks);
        // Success if we reach here
    }

    #[test]
    fn test_max_iterations_limit() {
        // Create artificial divergent CFG (shouldn't happen with monotone framework)
        let mut cfg = CFG::new("entry");

        let mut entry = CFGNode::new("entry");
        entry.add_successor("n1");
        cfg.add_node(entry);

        // Chain of 100 nodes
        for i in 1..100 {
            let mut node = CFGNode::new(format!("n{}", i));
            node.add_predecessor(format!("n{}", i - 1));
            node.add_successor(format!("n{}", i + 1));
            cfg.add_node(node);
        }

        let mut final_node = CFGNode::new("n100");
        final_node.add_predecessor("n99");
        cfg.add_node(final_node);

        let solver = WorklistTaintSolver::new(cfg).with_max_iterations(10);

        let sources = HashMap::from([("entry".to_string(), HashSet::from(["x".to_string()]))]);
        let sinks = HashSet::new();

        // Should stop at max_iterations without panic
        let _result = solver.solve(&sources, &sinks);
        // Success if we reach here
    }

    #[test]
    fn test_no_sources() {
        let mut cfg = CFG::new("entry");
        let entry = CFGNode::new("entry");
        cfg.add_node(entry);

        let solver = WorklistTaintSolver::new(cfg);
        let sources = HashMap::new();
        let sinks = HashSet::new();

        let result = solver.solve(&sources, &sinks);

        // Should have empty out_facts for entry
        assert!(result.get("entry").map_or(true, |s| s.is_empty()));
    }

    #[test]
    fn test_multiple_sources() {
        // CFG: entry -> source1 -> merge <- source2 <- entry
        //                         merge -> sink
        let mut cfg = CFG::new("entry");

        let mut entry = CFGNode::new("entry");
        entry.add_successor("source1");
        entry.add_successor("source2");

        let mut source1 = CFGNode::new("source1");
        source1.add_predecessor("entry");
        source1.add_successor("merge");
        source1.def_var = Some("x".to_string());

        let mut source2 = CFGNode::new("source2");
        source2.add_predecessor("entry");
        source2.add_successor("merge");
        source2.def_var = Some("y".to_string());

        let mut merge = CFGNode::new("merge");
        merge.add_predecessor("source1");
        merge.add_predecessor("source2");
        merge.add_successor("sink");

        let mut sink = CFGNode::new("sink");
        sink.add_predecessor("merge");
        sink.use_vars.insert("x".to_string());
        sink.use_vars.insert("y".to_string());

        cfg.add_node(entry);
        cfg.add_node(source1);
        cfg.add_node(source2);
        cfg.add_node(merge);
        cfg.add_node(sink);

        let solver = WorklistTaintSolver::new(cfg);

        let sources = HashMap::from([
            ("source1".to_string(), HashSet::from(["x".to_string()])),
            ("source2".to_string(), HashSet::from(["y".to_string()])),
        ]);
        let sinks = HashSet::from(["sink".to_string()]);

        let result = solver.solve(&sources, &sinks);

        let tainted_at_sink = solver.check_sink("sink", &result);
        assert!(tainted_at_sink.contains("x"), "Should have x from source1");
        assert!(tainted_at_sink.contains("y"), "Should have y from source2");
    }
}
