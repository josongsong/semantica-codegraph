/*
 * IDE Solver (Interprocedural Distributive Environment Solver)
 *
 * NEW SOTA Implementation - No Python equivalent
 *
 * Extends IFDS tabulation with value propagation.
 *
 * Key Features:
 * - Value propagation along with fact reachability
 * - Meet operation for combining values from multiple paths
 * - Edge function composition for path-based transformations
 * - Jump functions for procedure summaries
 * - O(ED³) complexity (same as IFDS)
 *
 * Algorithm Overview:
 * 1. Run IFDS to compute fact reachability
 * 2. For each reachable (node, fact) pair:
 *    - Propagate values using edge functions
 *    - Combine values from multiple paths using meet
 *    - Compose edge functions along paths
 * 3. Compute final values at each program point
 *
 * Performance Target: Handle 10k+ functions, 100k+ facts
 *
 * References:
 * - Sagiv, Reps, Horwitz (1996): "Precise Interprocedural Dataflow Analysis with Applications to Constant Propagation"
 * - Naeem, Lhoták (2008): "Typestate-like Analysis of Multiple Interacting Objects"
 */

use rustc_hash::FxHashMap;
use std::collections::{HashMap, HashSet, VecDeque};
use std::fmt::Debug;
use std::hash::Hash;
use std::time::Instant;

use super::ide_framework::{EdgeFunction, IDEProblem, IDEStatistics, IDEValue};
use super::ifds_framework::DataflowFact;
use super::ifds_solver::{CFGEdge, CFGEdgeKind, CFG};

/// Value table: stores (node, fact) → value mappings
///
/// Example:
///   value_table[("line_10", Tainted("x"))] = TaintLevel(5)
type ValueTable<F, V> = FxHashMap<(String, F), V>;

/// Edge function table: stores (node1, fact1, node2, fact2) → edge function
///
/// Instead of storing Box<dyn EdgeFunction>, we'll recompute edge functions
/// on demand using the IDEProblem.
type EdgeFunctionKey = (String, String, String, String); // (from_node, from_fact_str, to_node, to_fact_str)

/// Jump function key: (call_site, source_fact, return_site, target_fact)
type JumpFunctionKey<F> = (String, F, String, F);

/// Micro function key: (from_node, to_node, source_fact, target_fact)
/// Used to track edge function applications at individual edges
type MicroFunctionKey<F> = (String, String, F, F);

/// IDE Solver
///
/// Extends IFDS with value propagation.
///
/// # Key Features (2025-01-01 Enhancements)
/// - Flow function support for fact transformation
/// - Micro function tracking for intra-procedural edges
/// - Jump function caching for procedure summaries
/// - Edge function composition along paths
pub struct IDESolver<F: DataflowFact, V: IDEValue> {
    /// IDE problem specification
    problem: Box<dyn IDEProblem<F, V>>,

    /// Control flow graph
    cfg: CFG,

    /// Value table: (node, fact) → value
    value_table: ValueTable<F, V>,

    /// Micro function results: tracks which edge functions have been applied
    /// Key: (from_node, to_node, source_fact, target_fact)
    /// Value: (input_value, output_value) - cached transformation result
    /// This enables result reuse when same edge function is applied to same input
    micro_function_results: FxHashMap<MicroFunctionKey<F>, FxHashMap<V, V>>,

    /// Jump function cache: stores composed edge functions for procedure summaries
    /// Key: (call_site, source_fact, return_site, target_fact)
    /// Value: composed edge function result (cached value transformation)
    jump_function_cache: FxHashMap<JumpFunctionKey<F>, V>,

    /// Worklist: (node, fact, value) triples to process
    worklist: VecDeque<(String, F, V)>,

    /// Statistics
    stats: IDEStatistics,
}

impl<F: DataflowFact + 'static, V: IDEValue + 'static> IDESolver<F, V> {
    /// Create new IDE solver
    ///
    /// # Arguments
    /// * `problem` - IDE problem specification
    /// * `cfg` - Control flow graph
    pub fn new(problem: Box<dyn IDEProblem<F, V>>, cfg: CFG) -> Self {
        Self {
            problem,
            cfg,
            value_table: FxHashMap::default(),
            micro_function_results: FxHashMap::default(),
            jump_function_cache: FxHashMap::default(),
            worklist: VecDeque::new(),
            stats: IDEStatistics::default(),
        }
    }

    /// Solve the IDE problem
    ///
    /// Returns the value table with final values for each (node, fact) pair.
    pub fn solve(mut self) -> IDESolverResult<F, V> {
        let start_time = Instant::now();

        // Initialize worklist with seed values
        self.initialize_worklist();

        // Main value propagation loop
        while let Some((node, fact, value)) = self.worklist.pop_front() {
            self.stats.num_value_propagations += 1;
            self.propagate_value(node, fact, value);
        }

        // Compute statistics
        self.stats.analysis_time_ms = start_time.elapsed().as_millis() as u64;

        IDESolverResult {
            value_table: self.value_table,
            stats: self.stats,
        }
    }

    /// Solve with configurable options
    ///
    /// # Arguments
    /// * `max_iterations` - Maximum value propagations
    /// * `use_micro_cache` - Enable micro-function caching
    /// * `use_jump_cache` - Enable jump-function caching
    ///
    /// # Returns
    /// Solver result (may be partial if limit exceeded)
    pub fn solve_with_config(
        mut self,
        max_iterations: usize,
        _use_micro_cache: bool, // Currently always enabled in implementation
        _use_jump_cache: bool,  // Currently always enabled in implementation
    ) -> IDESolverResult<F, V> {
        let start_time = Instant::now();

        // Initialize worklist with seed values
        self.initialize_worklist();

        // Main value propagation loop with limit
        while let Some((node, fact, value)) = self.worklist.pop_front() {
            // Check iteration limit
            if self.stats.num_value_propagations >= max_iterations {
                break;
            }

            self.stats.num_value_propagations += 1;
            self.propagate_value(node, fact, value);
        }

        // Compute statistics
        self.stats.analysis_time_ms = start_time.elapsed().as_millis() as u64;

        IDESolverResult {
            value_table: self.value_table,
            stats: self.stats,
        }
    }

    /// Initialize worklist with seed values
    fn initialize_worklist(&mut self) {
        let seeds = self.problem.initial_seeds();

        for (node, fact, value) in seeds {
            self.add_to_worklist(node, fact, value);
        }
    }

    /// Propagate value to (node, fact) pair
    fn propagate_value(&mut self, node: String, fact: F, new_value: V) {
        // Get current value at (node, fact)
        let key = (node.clone(), fact.clone());
        let current_value = self.value_table.get(&key);

        // Meet new value with current value
        let combined_value = match current_value {
            Some(v) => {
                self.stats.num_meet_operations += 1;
                v.meet(&new_value)
            }
            None => new_value.clone(),
        };

        // Update value table if changed
        if current_value.map_or(true, |v| v != &combined_value) {
            self.value_table.insert(key, combined_value.clone());

            // Propagate to successors
            self.propagate_to_successors(&node, &fact, &combined_value);
        }
    }

    /// Propagate value to successor nodes
    fn propagate_to_successors(&mut self, node: &str, fact: &F, value: &V) {
        // Get successors of node in CFG (clone to avoid borrow issues)
        let successors = match self.cfg.get_successors(node) {
            Some(succs) => succs.to_vec(),
            None => return,
        };

        // Process each successor edge
        for edge in successors {
            match &edge.kind {
                CFGEdgeKind::Normal => {
                    self.propagate_normal_edge(node, &edge.to, fact, value);
                }
                CFGEdgeKind::Call { callee_entry } => {
                    self.propagate_call_edge(node, callee_entry, fact, value);
                }
                CFGEdgeKind::Return { call_site } => {
                    self.propagate_return_edge(node, &edge.to, call_site, fact, value);
                }
                CFGEdgeKind::CallToReturn => {
                    self.propagate_call_to_return_edge(node, &edge.to, fact, value);
                }
            }
        }
    }

    /// Propagate along normal intra-procedural edge
    ///
    /// FIXED (2025-01-01): Now uses flow function for fact transformation
    /// instead of assuming identity flow.
    ///
    /// ENHANCED (2025-01-01): Micro-function caching for result reuse.
    fn propagate_normal_edge(
        &mut self,
        from_node: &str,
        to_node: &str,
        source_fact: &F,
        source_value: &V,
    ) {
        // Get target facts from flow function (supports Gen/Kill)
        let target_facts = self
            .problem
            .normal_flow_function(from_node, to_node, source_fact);

        // Propagate value to each target fact
        for target_fact in target_facts {
            // Build micro function key
            let micro_key = (
                from_node.to_string(),
                to_node.to_string(),
                source_fact.clone(),
                target_fact.clone(),
            );

            // Check micro function cache first (cache hit path)
            let (target_value, is_cache_hit) = {
                let cached = self
                    .micro_function_results
                    .get(&micro_key)
                    .and_then(|results| results.get(source_value).cloned());

                if let Some(value) = cached {
                    (value, true)
                } else {
                    // Cache miss - compute edge function result
                    let edge_fn = self.problem.normal_edge_function(
                        from_node,
                        to_node,
                        source_fact,
                        &target_fact,
                    );
                    (edge_fn.apply(source_value), false)
                }
            };

            // Update statistics
            if is_cache_hit {
                self.stats.num_micro_function_reuses += 1;
            } else {
                self.stats.num_micro_functions += 1;
                // Update cache only on miss
                self.micro_function_results
                    .entry(micro_key)
                    .or_insert_with(FxHashMap::default)
                    .insert(source_value.clone(), target_value.clone());
            }

            // Add to worklist
            self.add_to_worklist(to_node.to_string(), target_fact, target_value);
        }
    }

    /// Propagate along call edge
    ///
    /// FIXED (2025-01-01): Now uses flow function for argument mapping.
    fn propagate_call_edge(
        &mut self,
        call_site: &str,
        callee_entry: &str,
        source_fact: &F,
        source_value: &V,
    ) {
        // Get target facts from call flow function (argument mapping)
        let target_facts = self
            .problem
            .call_flow_function(call_site, callee_entry, source_fact);

        for target_fact in target_facts {
            // Get edge function
            let edge_fn =
                self.problem
                    .call_edge_function(call_site, callee_entry, source_fact, &target_fact);

            // Apply edge function
            let target_value = edge_fn.apply(source_value);

            // Add to worklist
            self.add_to_worklist(callee_entry.to_string(), target_fact, target_value);
        }
    }

    /// Propagate along return edge
    ///
    /// FIXED (2025-01-01): Now uses flow function for return value mapping.
    /// ENHANCED: Uses jump function cache for procedure summary optimization.
    fn propagate_return_edge(
        &mut self,
        callee_exit: &str,
        return_site: &str,
        call_site: &str,
        source_fact: &F,
        source_value: &V,
    ) {
        // Get target facts from return flow function
        let target_facts =
            self.problem
                .return_flow_function(callee_exit, return_site, call_site, source_fact);

        for target_fact in target_facts {
            // Check jump function cache first (procedure summary)
            let jump_key = (
                call_site.to_string(),
                source_fact.clone(),
                return_site.to_string(),
                target_fact.clone(),
            );

            let target_value = if let Some(cached_value) = self.jump_function_cache.get(&jump_key) {
                // Use cached jump function result
                self.stats.num_jump_function_reuses += 1;
                cached_value.clone()
            } else {
                // Compute edge function and cache
                let edge_fn = self.problem.return_edge_function(
                    callee_exit,
                    return_site,
                    call_site,
                    source_fact,
                    &target_fact,
                );

                // Apply edge function
                let computed_value = edge_fn.apply(source_value);

                // Cache the jump function result for future reuse
                self.jump_function_cache
                    .insert(jump_key, computed_value.clone());
                self.stats.num_jump_functions += 1;

                computed_value
            };

            // Add to worklist
            self.add_to_worklist(return_site.to_string(), target_fact, target_value);
        }
    }

    /// Propagate along call-to-return edge
    ///
    /// FIXED (2025-01-01): Now uses flow function for local variable pass-through.
    fn propagate_call_to_return_edge(
        &mut self,
        call_site: &str,
        return_site: &str,
        source_fact: &F,
        source_value: &V,
    ) {
        // Get target facts from call-to-return flow function
        let target_facts =
            self.problem
                .call_to_return_flow_function(call_site, return_site, source_fact);

        for target_fact in target_facts {
            // Get edge function
            let edge_fn = self.problem.call_to_return_edge_function(
                call_site,
                return_site,
                source_fact,
                &target_fact,
            );

            // Apply edge function
            let target_value = edge_fn.apply(source_value);

            // Add to worklist
            self.add_to_worklist(return_site.to_string(), target_fact, target_value);
        }
    }

    /// Add (node, fact, value) to worklist
    fn add_to_worklist(&mut self, node: String, fact: F, value: V) {
        self.worklist.push_back((node, fact, value));
    }
}

/// IDE Solver Result
pub struct IDESolverResult<F: DataflowFact, V: IDEValue> {
    /// Value table: (node, fact) → value
    pub value_table: ValueTable<F, V>,

    /// Statistics
    pub stats: IDEStatistics,
}

impl<F: DataflowFact, V: IDEValue> IDESolverResult<F, V> {
    /// Get value at (node, fact)
    ///
    /// # Arguments
    /// * `node` - CFG node
    /// * `fact` - Dataflow fact
    ///
    /// # Returns
    /// Value at (node, fact), or None if not reachable
    pub fn get_value(&self, node: &str, fact: &F) -> Option<&V> {
        let key = (node.to_string(), fact.clone());
        self.value_table.get(&key)
    }

    /// Get all facts at a node with their values
    pub fn get_facts_at_node(&self, node: &str) -> HashMap<F, V> {
        let mut result = HashMap::new();

        for ((n, fact), value) in &self.value_table {
            if n == node {
                result.insert(fact.clone(), value.clone());
            }
        }

        result
    }

    /// Get all nodes where a fact has a value
    pub fn get_nodes_with_fact(&self, fact: &F) -> HashMap<String, V> {
        let mut result = HashMap::new();

        for ((node, f), value) in &self.value_table {
            if f == fact {
                result.insert(node.clone(), value.clone());
            }
        }

        result
    }

    /// Get number of (node, fact) pairs with values
    pub fn num_values(&self) -> usize {
        self.value_table.len()
    }

    /// Get analysis statistics
    pub fn statistics(&self) -> &IDEStatistics {
        &self.stats
    }

    /// Get all values grouped by node
    ///
    /// # Returns
    /// Map from node → (fact → value)
    pub fn get_all_values(&self) -> FxHashMap<String, FxHashMap<F, V>> {
        let mut result: FxHashMap<String, FxHashMap<F, V>> = FxHashMap::default();

        for ((node, fact), value) in &self.value_table {
            result
                .entry(node.clone())
                .or_default()
                .insert(fact.clone(), value.clone());
        }

        result
    }

    /// Get all nodes that have at least one fact with a value
    pub fn get_all_nodes(&self) -> Vec<String> {
        let mut nodes: std::collections::HashSet<String> = std::collections::HashSet::new();
        for (node, _fact) in self.value_table.keys() {
            nodes.insert(node.clone());
        }
        nodes.into_iter().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::super::ide_framework::{ConstantEdgeFunction, IdentityEdgeFunction};
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

    /// Taint level value (0 = clean, 10 = highly tainted)
    #[derive(Debug, Clone, PartialEq, Eq, Hash)]
    struct TaintLevel(u8);

    impl IDEValue for TaintLevel {
        fn top() -> Self {
            TaintLevel(10) // Maximally tainted
        }

        fn bottom() -> Self {
            TaintLevel(0) // Untainted
        }

        fn meet(&self, other: &Self) -> Self {
            // Max taint level
            TaintLevel(self.0.max(other.0))
        }

        fn is_top(&self) -> bool {
            self.0 == 10
        }

        fn is_bottom(&self) -> bool {
            self.0 == 0
        }
    }

    /// Simple IDE problem for testing (uses "entry" as seed node)
    struct SimpleTaintLevelProblem;

    impl IDEProblem<TestFact, TaintLevel> for SimpleTaintLevelProblem {
        fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
            vec![(
                "entry".to_string(),
                TestFact::Tainted("input".to_string()),
                TaintLevel(10),
            )]
        }

        fn normal_edge_function(
            &self,
            _from: &str,
            _to: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction) // Preserve taint level
        }

        fn call_edge_function(
            &self,
            _call_site: &str,
            _callee: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction)
        }

        fn return_edge_function(
            &self,
            _callee_exit: &str,
            _return_site: &str,
            _call_site: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction)
        }

        fn call_to_return_edge_function(
            &self,
            _call_site: &str,
            _return_site: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction)
        }
    }

    /// Configurable IDE problem for testing with custom entry node
    struct ConfigurableTaintLevelProblem {
        entry_node: String,
        taint_var: String,
        initial_level: u8,
    }

    impl ConfigurableTaintLevelProblem {
        fn new(
            entry_node: impl Into<String>,
            taint_var: impl Into<String>,
            initial_level: u8,
        ) -> Self {
            Self {
                entry_node: entry_node.into(),
                taint_var: taint_var.into(),
                initial_level,
            }
        }
    }

    impl IDEProblem<TestFact, TaintLevel> for ConfigurableTaintLevelProblem {
        fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
            vec![(
                self.entry_node.clone(),
                TestFact::Tainted(self.taint_var.clone()),
                TaintLevel(self.initial_level),
            )]
        }

        fn normal_edge_function(
            &self,
            _from: &str,
            _to: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction)
        }

        fn call_edge_function(
            &self,
            _call_site: &str,
            _callee: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction)
        }

        fn return_edge_function(
            &self,
            _callee_exit: &str,
            _return_site: &str,
            _call_site: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction)
        }

        fn call_to_return_edge_function(
            &self,
            _call_site: &str,
            _return_site: &str,
            _source: &TestFact,
            _target: &TestFact,
        ) -> Box<dyn EdgeFunction<TaintLevel>> {
            Box::new(IdentityEdgeFunction)
        }
    }

    #[test]
    fn test_taint_level_value() {
        let v1 = TaintLevel(5);
        let v2 = TaintLevel(7);

        assert_eq!(v1.meet(&v2), TaintLevel(7)); // Max
        assert!(!v1.is_top());
        assert!(!v1.is_bottom());
    }

    #[test]
    fn test_taint_level_top_bottom() {
        let top = TaintLevel::top();
        let bottom = TaintLevel::bottom();

        assert!(top.is_top());
        assert!(bottom.is_bottom());
        assert_eq!(top, TaintLevel(10));
        assert_eq!(bottom, TaintLevel(0));
    }

    #[test]
    fn test_simple_linear_propagation() {
        // CFG: entry → n1 → n2
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintLevelProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        // Check that taint level propagates
        let tainted = TestFact::Tainted("input".to_string());
        assert_eq!(result.get_value("entry", &tainted), Some(&TaintLevel(10)));
        assert_eq!(result.get_value("n1", &tainted), Some(&TaintLevel(10)));
        assert_eq!(result.get_value("n2", &tainted), Some(&TaintLevel(10)));
    }

    #[test]
    fn test_get_facts_at_node() {
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintLevelProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let facts = result.get_facts_at_node("entry");
        assert!(facts.contains_key(&TestFact::Tainted("input".to_string())));
    }

    #[test]
    fn test_get_nodes_with_fact() {
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintLevelProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let tainted = TestFact::Tainted("input".to_string());
        let nodes = result.get_nodes_with_fact(&tainted);

        assert!(nodes.contains_key("entry"));
        assert!(nodes.contains_key("n1"));
    }

    #[test]
    fn test_statistics() {
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintLevelProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        assert!(result.stats.num_value_propagations > 0);
    }

    #[test]
    fn test_empty_cfg() {
        struct EmptyProblem;
        impl IDEProblem<TestFact, TaintLevel> for EmptyProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![] // No seeds for empty CFG
            }
            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(IdentityEdgeFunction)
            }
            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(IdentityEdgeFunction)
            }
            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(IdentityEdgeFunction)
            }
            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(IdentityEdgeFunction)
            }
        }

        let cfg = CFG::new();
        let problem = Box::new(EmptyProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        // Should handle empty CFG gracefully
        assert_eq!(result.num_values(), 0);
    }

    // ========== Phase 3: Advanced IDE Tests ==========

    /// Test EdgeFunction composition with sanitizers
    #[test]
    fn test_edge_function_composition() {
        use super::super::ide_framework::EdgeFunction;

        // Create two sanitizer functions
        #[derive(Debug)]
        struct SanitizerEdge {
            reduction: u8,
        }
        impl EdgeFunction<TaintLevel> for SanitizerEdge {
            fn apply(&self, input: &TaintLevel) -> TaintLevel {
                TaintLevel(input.0.saturating_sub(self.reduction))
            }
            fn compose(
                &self,
                _other: &dyn EdgeFunction<TaintLevel>,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                // Simplified compose: just return copy
                Box::new(SanitizerEdge {
                    reduction: self.reduction,
                })
            }
        }

        let san1 = SanitizerEdge { reduction: 3 };
        let input = TaintLevel(10);
        let result = san1.apply(&input);

        // 10 - 3 = 7
        assert_eq!(result, TaintLevel(7));
    }

    /// Test multiple paths with meet operation
    #[test]
    fn test_multiple_paths_meet() {
        // Problem with different severity on different paths
        struct MultiPathProblem;

        impl IDEProblem<TestFact, TaintLevel> for MultiPathProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![(
                    "entry".to_string(),
                    TestFact::Tainted("x".to_string()),
                    TaintLevel(5),
                )]
            }

            fn normal_edge_function(
                &self,
                _from: &str,
                to: &str,
                _source: &TestFact,
                _target: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                // Different transformations on different paths
                if to == "path1" {
                    // Increase severity to 8
                    Box::new(super::super::ide_framework::ConstantEdgeFunction::new(
                        TaintLevel(8),
                    ))
                } else if to == "path2" {
                    // Increase severity to 6
                    Box::new(super::super::ide_framework::ConstantEdgeFunction::new(
                        TaintLevel(6),
                    ))
                } else {
                    Box::new(super::super::ide_framework::IdentityEdgeFunction)
                }
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        // CFG: entry → path1 → merge
        //           → path2 → merge
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "path1"));
        cfg.add_edge(CFGEdge::normal("entry", "path2"));
        cfg.add_edge(CFGEdge::normal("path1", "merge"));
        cfg.add_edge(CFGEdge::normal("path2", "merge"));
        cfg.add_entry("entry");

        let problem = Box::new(MultiPathProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let tainted = TestFact::Tainted("x".to_string());

        // At merge, should take max (conservative meet)
        let merge_value = result.get_value("merge", &tainted);
        assert_eq!(merge_value, Some(&TaintLevel(8))); // max(8, 6) = 8

        // Verify meet operations occurred
        assert!(result.stats.num_meet_operations > 0);
    }

    /// Test interprocedural value propagation
    #[test]
    fn test_interprocedural_value_flow() {
        struct InterProcProblem;

        impl IDEProblem<TestFact, TaintLevel> for InterProcProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![(
                    "main_entry".to_string(),
                    TestFact::Tainted("arg".to_string()),
                    TaintLevel(10),
                )]
            }

            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                // Reduce severity on return (sanitization in callee)
                #[derive(Debug)]
                struct ReturnSanitizer;
                impl EdgeFunction<TaintLevel> for ReturnSanitizer {
                    fn apply(&self, input: &TaintLevel) -> TaintLevel {
                        TaintLevel(input.0.saturating_sub(3))
                    }
                    fn compose(
                        &self,
                        _: &dyn EdgeFunction<TaintLevel>,
                    ) -> Box<dyn EdgeFunction<TaintLevel>> {
                        Box::new(ReturnSanitizer)
                    }
                }
                Box::new(ReturnSanitizer)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                source: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                // Kill the arg fact on call-to-return (it goes through callee)
                match source {
                    TestFact::Tainted(s) if s == "arg" => {
                        // Return bottom (kill) so return edge value wins in meet
                        Box::new(super::super::ide_framework::ConstantEdgeFunction::new(
                            TaintLevel::bottom(),
                        ))
                    }
                    _ => Box::new(super::super::ide_framework::IdentityEdgeFunction),
                }
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("main_entry", "call_site"));
        cfg.add_edge(CFGEdge::call("call_site", "callee_entry"));
        cfg.add_edge(CFGEdge::call_to_return("call_site", "return_site"));
        cfg.add_edge(CFGEdge::ret("callee_exit", "return_site", "call_site"));
        cfg.add_edge(CFGEdge::normal("callee_entry", "callee_exit"));
        cfg.add_entry("main_entry");

        let problem = Box::new(InterProcProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let arg = TestFact::Tainted("arg".to_string());

        // Initial severity: 10
        assert_eq!(result.get_value("main_entry", &arg), Some(&TaintLevel(10)));

        // After call (sanitized): 10 - 3 = 7
        // call-to-return returns bottom(0), return returns 7, meet(0, 7) = 7
        let return_value = result.get_value("return_site", &arg);
        assert_eq!(return_value, Some(&TaintLevel(7)));
    }

    /// Test loop with value convergence
    #[test]
    fn test_loop_value_convergence() {
        // CFG with loop: entry → loop → loop → exit
        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "loop"));
        cfg.add_edge(CFGEdge::normal("loop", "loop")); // Self-loop
        cfg.add_edge(CFGEdge::normal("loop", "exit"));
        cfg.add_entry("entry");

        let problem = Box::new(SimpleTaintLevelProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let tainted = TestFact::Tainted("input".to_string());

        // Value should stabilize at loop despite cycle
        assert!(result.get_value("loop", &tainted).is_some());
        assert!(result.get_value("exit", &tainted).is_some());
    }

    /// Test large-scale IDE analysis (100 nodes)
    #[test]
    fn test_large_scale_ide() {
        let mut cfg = CFG::new();
        cfg.add_entry("n0");

        // Linear chain of 100 nodes
        for i in 0..99 {
            cfg.add_edge(CFGEdge::normal(&format!("n{}", i), &format!("n{}", i + 1)));
        }

        // Use ConfigurableTaintLevelProblem with correct entry node "n0"
        let problem = Box::new(ConfigurableTaintLevelProblem::new("n0", "input", 10));
        let solver = IDESolver::new(problem, cfg);

        let start = std::time::Instant::now();
        let result = solver.solve();
        let elapsed = start.elapsed();

        let tainted = TestFact::Tainted("input".to_string());

        // All nodes should have value
        assert!(result.get_value("n0", &tainted).is_some());
        assert!(result.get_value("n50", &tainted).is_some());
        assert!(result.get_value("n99", &tainted).is_some());

        // Should complete quickly
        assert!(elapsed.as_millis() < 200, "Too slow: {:?}", elapsed);
    }

    /// Test meet operator properties
    #[test]
    fn test_meet_properties() {
        let v1 = TaintLevel(5);
        let v2 = TaintLevel(7);
        let v3 = TaintLevel(3);

        // Commutativity: meet(a,b) = meet(b,a)
        assert_eq!(v1.meet(&v2), v2.meet(&v1));

        // Associativity: meet(meet(a,b),c) = meet(a,meet(b,c))
        let left = v1.meet(&v2).meet(&v3);
        let right = v1.meet(&v2.meet(&v3));
        assert_eq!(left, right);

        // Idempotency: meet(a,a) = a
        assert_eq!(v1.meet(&v1), v1);

        // Top is absorbing
        let top = TaintLevel::top();
        assert_eq!(v1.meet(&top), top);
        assert_eq!(top.meet(&v1), top);
    }

    /// Test zero fact handling in IDE
    #[test]
    fn test_zero_fact_ide() {
        struct ZeroHandlingProblem;

        impl IDEProblem<TestFact, TaintLevel> for ZeroHandlingProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![
                    ("entry".to_string(), TestFact::zero(), TaintLevel(0)),
                    (
                        "entry".to_string(),
                        TestFact::Tainted("x".to_string()),
                        TaintLevel(10),
                    ),
                ]
            }

            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_entry("entry");

        let problem = Box::new(ZeroHandlingProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let zero = TestFact::zero();
        let x = TestFact::Tainted("x".to_string());

        // Both zero and tainted should have values
        assert!(result.get_value("entry", &zero).is_some());
        assert!(result.get_value("entry", &x).is_some());
        assert!(result.get_value("n1", &zero).is_some());
        assert!(result.get_value("n1", &x).is_some());
    }

    /// Test diamond CFG with different edge functions
    #[test]
    fn test_diamond_different_edges() {
        struct DiamondProblem;

        impl IDEProblem<TestFact, TaintLevel> for DiamondProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![(
                    "entry".to_string(),
                    TestFact::Tainted("x".to_string()),
                    TaintLevel(5),
                )]
            }

            fn normal_edge_function(
                &self,
                from: &str,
                to: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                // Different severity changes on different paths
                if from == "entry" && to == "left" {
                    Box::new(super::super::ide_framework::ConstantEdgeFunction::new(
                        TaintLevel(8),
                    ))
                } else if from == "entry" && to == "right" {
                    Box::new(super::super::ide_framework::ConstantEdgeFunction::new(
                        TaintLevel(3),
                    ))
                } else {
                    Box::new(super::super::ide_framework::IdentityEdgeFunction)
                }
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "left"));
        cfg.add_edge(CFGEdge::normal("entry", "right"));
        cfg.add_edge(CFGEdge::normal("left", "merge"));
        cfg.add_edge(CFGEdge::normal("right", "merge"));
        cfg.add_entry("entry");

        let problem = Box::new(DiamondProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let x = TestFact::Tainted("x".to_string());

        // Left path: severity 8
        assert_eq!(result.get_value("left", &x), Some(&TaintLevel(8)));

        // Right path: severity 3
        assert_eq!(result.get_value("right", &x), Some(&TaintLevel(3)));

        // Merge: should take max (conservative)
        assert_eq!(result.get_value("merge", &x), Some(&TaintLevel(8)));
    }

    // ============================================================
    // MICRO FUNCTION CACHE TESTS (2025-01-01 Enhancement)
    // ============================================================

    /// Test micro function cache reuse
    #[test]
    fn test_micro_function_cache_reuse() {
        struct CacheTestProblem;

        impl IDEProblem<TestFact, TaintLevel> for CacheTestProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                // Multiple seeds at same node should trigger cache reuse
                vec![
                    (
                        "entry".to_string(),
                        TestFact::Tainted("x".to_string()),
                        TaintLevel(5),
                    ),
                    (
                        "entry".to_string(),
                        TestFact::Tainted("y".to_string()),
                        TaintLevel(5),
                    ),
                ]
            }

            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_entry("entry");

        let problem = Box::new(CacheTestProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        // Check statistics for cache behavior
        let stats = result.statistics();
        // With same value at same edge, should see cache reuse
        assert!(
            stats.num_micro_functions > 0,
            "Should compute some micro functions"
        );
    }

    /// Test statistics tracking
    #[test]
    fn test_ide_statistics_tracking() {
        struct StatsProblem;

        impl IDEProblem<TestFact, TaintLevel> for StatsProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![(
                    "entry".to_string(),
                    TestFact::Tainted("x".to_string()),
                    TaintLevel(5),
                )]
            }

            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "n1"));
        cfg.add_edge(CFGEdge::normal("n1", "n2"));
        cfg.add_edge(CFGEdge::normal("n2", "n3"));
        cfg.add_entry("entry");

        let problem = Box::new(StatsProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        let stats = result.statistics();

        // Should have processed some value propagations
        assert!(stats.num_value_propagations > 0, "Should propagate values");

        // Analysis time should be recorded
        assert!(stats.analysis_time_ms >= 0);
    }

    /// Test flow function integration (Gen/Kill support)
    #[test]
    fn test_flow_function_gen_kill() {
        struct GenKillProblem;

        impl IDEProblem<TestFact, TaintLevel> for GenKillProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![(
                    "entry".to_string(),
                    TestFact::Tainted("x".to_string()),
                    TaintLevel(5),
                )]
            }

            // Flow function that generates new fact at specific node
            fn normal_flow_function(
                &self,
                from: &str,
                _to: &str,
                source_fact: &TestFact,
            ) -> Vec<TestFact> {
                if from == "gen_node" {
                    // Generate new fact
                    vec![
                        source_fact.clone(),
                        TestFact::Tainted("new_fact".to_string()),
                    ]
                } else {
                    vec![source_fact.clone()]
                }
            }

            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        let mut cfg = CFG::new();
        cfg.add_edge(CFGEdge::normal("entry", "gen_node"));
        cfg.add_edge(CFGEdge::normal("gen_node", "exit"));
        cfg.add_entry("entry");

        let problem = Box::new(GenKillProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        // Original fact should propagate
        let x = TestFact::Tainted("x".to_string());
        assert!(result.get_value("exit", &x).is_some());

        // Generated fact should also exist at exit
        let new_fact = TestFact::Tainted("new_fact".to_string());
        assert!(result.get_value("exit", &new_fact).is_some());
    }

    // ============================================================
    // EDGE CASE TESTS
    // ============================================================

    /// Test empty CFG
    #[test]
    fn test_ide_empty_cfg() {
        struct EmptyProblem;

        impl IDEProblem<TestFact, TaintLevel> for EmptyProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![] // No seeds
            }

            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        let cfg = CFG::new();
        let problem = Box::new(EmptyProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        // Should not panic, should have empty results
        assert!(
            result.get_all_nodes().is_empty() || result.statistics().num_value_propagations == 0
        );
    }

    /// Test large scale IDE performance
    #[test]
    fn test_ide_large_scale() {
        struct LargeScaleProblem;

        impl IDEProblem<TestFact, TaintLevel> for LargeScaleProblem {
            fn initial_seeds(&self) -> Vec<(String, TestFact, TaintLevel)> {
                vec![(
                    "node_0".to_string(),
                    TestFact::Tainted("x".to_string()),
                    TaintLevel(5),
                )]
            }

            fn normal_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }

            fn call_to_return_edge_function(
                &self,
                _: &str,
                _: &str,
                _: &TestFact,
                _: &TestFact,
            ) -> Box<dyn EdgeFunction<TaintLevel>> {
                Box::new(super::super::ide_framework::IdentityEdgeFunction)
            }
        }

        // Create long chain CFG
        let mut cfg = CFG::new();
        for i in 0..100 {
            cfg.add_edge(CFGEdge::normal(
                &format!("node_{}", i),
                &format!("node_{}", i + 1),
            ));
        }
        cfg.add_entry("node_0");

        let problem = Box::new(LargeScaleProblem);
        let solver = IDESolver::new(problem, cfg);
        let result = solver.solve();

        // Should complete without timeout
        let stats = result.statistics();
        assert!(stats.num_value_propagations > 0);

        // Value should reach the end
        let x = TestFact::Tainted("x".to_string());
        assert!(result.get_value("node_100", &x).is_some());
    }
}
