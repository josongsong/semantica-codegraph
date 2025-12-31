/*
 * IFDS Framework (Interprocedural Finite Distributive Subset Problems)
 *
 * NEW SOTA Implementation - No Python equivalent
 *
 * Key Features:
 * - Exploded supergraph construction
 * - Tabulation algorithm (Reps, Horwitz, Sagiv, 1995)
 * - Flow functions for taint propagation
 * - Distributive dataflow analysis
 * - O(ED³) complexity (E=edges, D=dataflow facts)
 *
 * Algorithm:
 * 1. Build exploded supergraph (CFG × dataflow facts)
 * 2. Compute summary edges via worklist
 * 3. Propagate dataflow facts interprocedurally
 * 4. Extract results from reachable nodes
 *
 * Performance Target: Handle 10k+ functions, 100k+ facts
 *
 * References:
 * - Reps, Horwitz, Sagiv (1995): "Precise Interprocedural Dataflow Analysis via Graph Reachability"
 * - Naeem, Lhoták, Rodriguez (2010): "Practical Extensions to the IFDS Algorithm"
 * - Bodden et al. (2012): "Inter-procedural Data-flow Analysis with IFDS/IDE and Soot"
 */

use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::fmt::Debug;
use std::hash::Hash;

/// Dataflow fact (abstract domain element)
///
/// Example:
///   - Taint analysis: TaintFact { variable: "x", source: "user_input" }
///   - Reaching definitions: DefFact { variable: "x", def_site: "line_42" }
///   - Null pointer: NullFact { variable: "p", may_be_null: true }
pub trait DataflowFact: Clone + Eq + Hash + Debug {
    /// Check if this is the special ZERO fact (universal identity)
    fn is_zero(&self) -> bool;

    /// Create the ZERO fact (top of lattice, represents "no information")
    fn zero() -> Self;
}

/// Node in the exploded supergraph
///
/// Each node is a pair (CFG node, dataflow fact).
/// The exploded supergraph has |CFG| × |Facts| nodes.
///
/// Example:
///   CFG node: "line_10" (statement x = y)
///   Fact: TaintFact { variable: "y", source: "input" }
///   → Exploded node: ("line_10", TaintFact{y, input})
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ExplodedNode<F: DataflowFact> {
    /// CFG node (statement/basic block)
    pub cfg_node: String,

    /// Dataflow fact at this node
    pub fact: F,
}

impl<F: DataflowFact> ExplodedNode<F> {
    pub fn new(cfg_node: String, fact: F) -> Self {
        Self { cfg_node, fact }
    }
}

/// Edge in the exploded supergraph
///
/// Types:
/// - Normal: Intra-procedural flow (within function)
/// - Call: Call site to callee entry
/// - Return: Callee exit to return site
/// - Summary: Call site to return site (computed by tabulation)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ExplodedEdgeKind {
    /// Normal intra-procedural edge
    Normal,

    /// Call edge: call site → callee entry
    Call,

    /// Return edge: callee exit → return site
    Return,

    /// Summary edge: call site → return site (computed)
    Summary,
}

#[derive(Debug, Clone)]
pub struct ExplodedEdge<F: DataflowFact> {
    pub from: ExplodedNode<F>,
    pub to: ExplodedNode<F>,
    pub kind: ExplodedEdgeKind,
}

/// Flow function: D → 2^D (maps one fact to set of facts)
///
/// Represents the effect of a statement on dataflow facts.
///
/// Example (taint propagation):
///   Statement: x = y
///   Input fact: Tainted(y)
///   Output facts: {Tainted(x), Tainted(y)}  (x becomes tainted, y stays tainted)
pub trait FlowFunction<F: DataflowFact> {
    /// Compute output facts given input fact
    ///
    /// # Arguments
    /// * `input` - Input dataflow fact
    ///
    /// # Returns
    /// Set of output dataflow facts
    fn compute(&self, input: &F) -> HashSet<F>;

    /// Check if this flow function is identity (f(d) = {d})
    fn is_identity(&self) -> bool {
        false
    }
}

/// Identity flow function: f(d) = {d}
pub struct IdentityFlowFunction;

impl<F: DataflowFact> FlowFunction<F> for IdentityFlowFunction {
    fn compute(&self, input: &F) -> HashSet<F> {
        HashSet::from([input.clone()])
    }

    fn is_identity(&self) -> bool {
        true
    }
}

/// Kill flow function: f(d) = ∅ (kills all facts)
pub struct KillFlowFunction;

impl<F: DataflowFact> FlowFunction<F> for KillFlowFunction {
    fn compute(&self, _input: &F) -> HashSet<F> {
        HashSet::new()
    }
}

/// Gen flow function: f(d) = {d} ∪ {gen_fact}
pub struct GenFlowFunction<F: DataflowFact> {
    pub gen_fact: F,
}

impl<F: DataflowFact> FlowFunction<F> for GenFlowFunction<F> {
    fn compute(&self, input: &F) -> HashSet<F> {
        let mut result = HashSet::new();
        result.insert(input.clone());
        result.insert(self.gen_fact.clone());
        result
    }
}

/// Exploded supergraph
///
/// The core data structure for IFDS analysis.
/// Represents CFG × Facts as an explicit graph.
pub struct ExplodedSupergraph<F: DataflowFact> {
    /// All nodes in exploded supergraph
    pub nodes: HashSet<ExplodedNode<F>>,

    /// All edges (including computed summary edges)
    pub edges: Vec<ExplodedEdge<F>>,

    /// Adjacency list for efficient traversal
    /// node → set of successor nodes
    pub successors: FxHashMap<ExplodedNode<F>, HashSet<ExplodedNode<F>>>,

    /// Reverse adjacency list (for backward analysis)
    /// node → set of predecessor nodes
    pub predecessors: FxHashMap<ExplodedNode<F>, HashSet<ExplodedNode<F>>>,
}

impl<F: DataflowFact> ExplodedSupergraph<F> {
    pub fn new() -> Self {
        Self {
            nodes: HashSet::new(),
            edges: Vec::new(),
            successors: FxHashMap::default(),
            predecessors: FxHashMap::default(),
        }
    }

    /// Add node to exploded supergraph
    pub fn add_node(&mut self, node: ExplodedNode<F>) {
        self.nodes.insert(node.clone());
        self.successors
            .entry(node.clone())
            .or_insert_with(HashSet::new);
        self.predecessors.entry(node).or_insert_with(HashSet::new);
    }

    /// Add edge to exploded supergraph
    pub fn add_edge(&mut self, edge: ExplodedEdge<F>) {
        // Add nodes if not exists
        self.add_node(edge.from.clone());
        self.add_node(edge.to.clone());

        // Add edge
        self.successors
            .entry(edge.from.clone())
            .or_insert_with(HashSet::new)
            .insert(edge.to.clone());

        self.predecessors
            .entry(edge.to.clone())
            .or_insert_with(HashSet::new)
            .insert(edge.from.clone());

        self.edges.push(edge);
    }

    /// Get successors of a node
    pub fn get_successors(&self, node: &ExplodedNode<F>) -> Option<&HashSet<ExplodedNode<F>>> {
        self.successors.get(node)
    }

    /// Get predecessors of a node
    pub fn get_predecessors(&self, node: &ExplodedNode<F>) -> Option<&HashSet<ExplodedNode<F>>> {
        self.predecessors.get(node)
    }

    /// Check if edge exists
    pub fn has_edge(&self, from: &ExplodedNode<F>, to: &ExplodedNode<F>) -> bool {
        self.successors
            .get(from)
            .map_or(false, |succs| succs.contains(to))
    }

    /// Get number of nodes
    pub fn num_nodes(&self) -> usize {
        self.nodes.len()
    }

    /// Get number of edges
    pub fn num_edges(&self) -> usize {
        self.edges.len()
    }
}

impl<F: DataflowFact> Default for ExplodedSupergraph<F> {
    fn default() -> Self {
        Self::new()
    }
}

/// Path edge: (d1, n, d2)
///
/// Represents that fact d2 is reachable at node n when d1 holds at the start.
///
/// Example:
///   PathEdge(Tainted(input), line_10, Tainted(x))
///   → "If input is tainted at entry, then x is tainted at line_10"
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PathEdge<F: DataflowFact> {
    /// Source fact (at procedure entry)
    pub source_fact: F,

    /// Target CFG node
    pub target_node: String,

    /// Target fact (at target_node)
    pub target_fact: F,
}

impl<F: DataflowFact> PathEdge<F> {
    pub fn new(source_fact: F, target_node: String, target_fact: F) -> Self {
        Self {
            source_fact,
            target_node,
            target_fact,
        }
    }
}

/// Summary edge: (call_site, d1, return_site, d2)
///
/// Represents the effect of a procedure call.
///
/// Example:
///   SummaryEdge(line_5, Tainted(arg), line_6, Tainted(ret))
///   → "Calling function at line_5 with tainted arg results in tainted ret at line_6"
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct SummaryEdge<F: DataflowFact> {
    /// Call site
    pub call_site: String,

    /// Fact at call site
    pub call_fact: F,

    /// Return site
    pub return_site: String,

    /// Fact at return site
    pub return_fact: F,
}

impl<F: DataflowFact> SummaryEdge<F> {
    pub fn new(call_site: String, call_fact: F, return_site: String, return_fact: F) -> Self {
        Self {
            call_site,
            call_fact,
            return_site,
            return_fact,
        }
    }
}

/// IFDS Problem specification
///
/// Defines the dataflow problem to be solved:
/// - Initial facts (seeds)
/// - Flow functions for each edge type
/// - Meet operator (typically union)
pub trait IFDSProblem<F: DataflowFact> {
    /// Get initial facts (entry points)
    ///
    /// Example (taint analysis):
    ///   Initial facts at main(): {Tainted(argv)}
    fn initial_seeds(&self) -> Vec<(String, F)>;

    /// Get normal flow function (intra-procedural)
    ///
    /// # Arguments
    /// * `from_node` - Source CFG node
    /// * `to_node` - Target CFG node
    ///
    /// # Returns
    /// Flow function for this edge
    fn normal_flow(&self, from_node: &str, to_node: &str) -> Box<dyn FlowFunction<F>>;

    /// Get call flow function
    ///
    /// # Arguments
    /// * `call_site` - Call site node
    /// * `callee_entry` - Callee entry node
    ///
    /// # Returns
    /// Flow function for call edge
    fn call_flow(&self, call_site: &str, callee_entry: &str) -> Box<dyn FlowFunction<F>>;

    /// Get return flow function
    ///
    /// # Arguments
    /// * `callee_exit` - Callee exit node
    /// * `return_site` - Return site node
    /// * `call_site` - Corresponding call site
    ///
    /// # Returns
    /// Flow function for return edge
    fn return_flow(
        &self,
        callee_exit: &str,
        return_site: &str,
        call_site: &str,
    ) -> Box<dyn FlowFunction<F>>;

    /// Get call-to-return flow function (pass-through)
    ///
    /// Handles facts that flow directly from call site to return site
    /// without going through the callee (e.g., local variables).
    ///
    /// # Arguments
    /// * `call_site` - Call site node
    /// * `return_site` - Return site node
    ///
    /// # Returns
    /// Flow function for pass-through edge
    fn call_to_return_flow(&self, call_site: &str, return_site: &str) -> Box<dyn FlowFunction<F>>;
}

/// IFDS Analysis Statistics
#[derive(Debug, Clone, Default)]
pub struct IFDSStatistics {
    /// Number of nodes in exploded supergraph
    pub num_exploded_nodes: usize,

    /// Number of edges in exploded supergraph
    pub num_exploded_edges: usize,

    /// Number of path edges computed
    pub num_path_edges: usize,

    /// Number of summary edges computed
    pub num_summary_edges: usize,

    /// Number of summary edge reuses (optimization metric)
    /// Higher is better - indicates callee re-analysis was avoided
    pub num_summary_reuses: usize,

    /// Number of worklist iterations
    pub num_iterations: usize,

    /// Analysis time (milliseconds)
    pub analysis_time_ms: u64,
}

#[cfg(test)]
mod tests {
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

    #[test]
    fn test_exploded_node_creation() {
        let node = ExplodedNode::new("line_10".to_string(), TestFact::Tainted("x".to_string()));

        assert_eq!(node.cfg_node, "line_10");
        assert_eq!(node.fact, TestFact::Tainted("x".to_string()));
    }

    #[test]
    fn test_exploded_supergraph_add_node() {
        let mut graph: ExplodedSupergraph<TestFact> = ExplodedSupergraph::new();

        let node1 = ExplodedNode::new("line_10".to_string(), TestFact::Tainted("x".to_string()));
        let node2 = ExplodedNode::new("line_11".to_string(), TestFact::Tainted("y".to_string()));

        graph.add_node(node1.clone());
        graph.add_node(node2.clone());

        assert_eq!(graph.num_nodes(), 2);
        assert!(graph.nodes.contains(&node1));
        assert!(graph.nodes.contains(&node2));
    }

    #[test]
    fn test_exploded_supergraph_add_edge() {
        let mut graph: ExplodedSupergraph<TestFact> = ExplodedSupergraph::new();

        let node1 = ExplodedNode::new("line_10".to_string(), TestFact::Tainted("x".to_string()));
        let node2 = ExplodedNode::new("line_11".to_string(), TestFact::Tainted("y".to_string()));

        let edge = ExplodedEdge {
            from: node1.clone(),
            to: node2.clone(),
            kind: ExplodedEdgeKind::Normal,
        };

        graph.add_edge(edge);

        assert_eq!(graph.num_nodes(), 2);
        assert_eq!(graph.num_edges(), 1);
        assert!(graph.has_edge(&node1, &node2));
    }

    #[test]
    fn test_exploded_supergraph_successors() {
        let mut graph: ExplodedSupergraph<TestFact> = ExplodedSupergraph::new();

        let node1 = ExplodedNode::new("line_10".to_string(), TestFact::Tainted("x".to_string()));
        let node2 = ExplodedNode::new("line_11".to_string(), TestFact::Tainted("y".to_string()));
        let node3 = ExplodedNode::new("line_12".to_string(), TestFact::Tainted("z".to_string()));

        graph.add_edge(ExplodedEdge {
            from: node1.clone(),
            to: node2.clone(),
            kind: ExplodedEdgeKind::Normal,
        });

        graph.add_edge(ExplodedEdge {
            from: node1.clone(),
            to: node3.clone(),
            kind: ExplodedEdgeKind::Normal,
        });

        let succs = graph.get_successors(&node1).unwrap();
        assert_eq!(succs.len(), 2);
        assert!(succs.contains(&node2));
        assert!(succs.contains(&node3));
    }

    #[test]
    fn test_exploded_supergraph_predecessors() {
        let mut graph: ExplodedSupergraph<TestFact> = ExplodedSupergraph::new();

        let node1 = ExplodedNode::new("line_10".to_string(), TestFact::Tainted("x".to_string()));
        let node2 = ExplodedNode::new("line_11".to_string(), TestFact::Tainted("y".to_string()));
        let node3 = ExplodedNode::new("line_12".to_string(), TestFact::Tainted("z".to_string()));

        graph.add_edge(ExplodedEdge {
            from: node1.clone(),
            to: node3.clone(),
            kind: ExplodedEdgeKind::Normal,
        });

        graph.add_edge(ExplodedEdge {
            from: node2.clone(),
            to: node3.clone(),
            kind: ExplodedEdgeKind::Normal,
        });

        let preds = graph.get_predecessors(&node3).unwrap();
        assert_eq!(preds.len(), 2);
        assert!(preds.contains(&node1));
        assert!(preds.contains(&node2));
    }

    #[test]
    fn test_identity_flow_function() {
        let flow = IdentityFlowFunction;
        let input = TestFact::Tainted("x".to_string());

        let output = flow.compute(&input);

        assert_eq!(output.len(), 1);
        assert!(output.contains(&TestFact::Tainted("x".to_string())));
        assert!(FlowFunction::<TestFact>::is_identity(&flow));
    }

    #[test]
    fn test_kill_flow_function() {
        let flow = KillFlowFunction;
        let input = TestFact::Tainted("x".to_string());

        let output = flow.compute(&input);

        assert_eq!(output.len(), 0);
    }

    #[test]
    fn test_gen_flow_function() {
        let flow = GenFlowFunction {
            gen_fact: TestFact::Tainted("y".to_string()),
        };
        let input = TestFact::Tainted("x".to_string());

        let output = flow.compute(&input);

        assert_eq!(output.len(), 2);
        assert!(output.contains(&TestFact::Tainted("x".to_string())));
        assert!(output.contains(&TestFact::Tainted("y".to_string())));
    }

    #[test]
    fn test_path_edge_creation() {
        let edge = PathEdge::new(
            TestFact::Tainted("input".to_string()),
            "line_10".to_string(),
            TestFact::Tainted("x".to_string()),
        );

        assert_eq!(edge.source_fact, TestFact::Tainted("input".to_string()));
        assert_eq!(edge.target_node, "line_10");
        assert_eq!(edge.target_fact, TestFact::Tainted("x".to_string()));
    }

    #[test]
    fn test_summary_edge_creation() {
        let edge = SummaryEdge::new(
            "line_5".to_string(),
            TestFact::Tainted("arg".to_string()),
            "line_6".to_string(),
            TestFact::Tainted("ret".to_string()),
        );

        assert_eq!(edge.call_site, "line_5");
        assert_eq!(edge.call_fact, TestFact::Tainted("arg".to_string()));
        assert_eq!(edge.return_site, "line_6");
        assert_eq!(edge.return_fact, TestFact::Tainted("ret".to_string()));
    }

    #[test]
    fn test_zero_fact() {
        let zero = TestFact::zero();
        assert!(zero.is_zero());
        assert_eq!(zero, TestFact::Zero);
    }
}
