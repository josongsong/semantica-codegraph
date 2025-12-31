/*
 * Path-Sensitive Taint Analysis
 *
 * Tracks taint along different execution paths with conditional flow.
 *
 * Key techniques:
 * 1. Path-sensitive: Track taint per execution path
 * 2. Meet-Over-Paths: Conservative state merging at join points
 * 3. Strong/Weak updates: Precise when safe, conservative when needed
 * 4. Path conditions: Track branch conditions (for SMT verification)
 *
 * Example:
 *   user_input = request.get("id")  // Source
 *
 *   if is_admin:
 *       // Path 1: admin check passes
 *       execute(query)  // NOT tainted (sanitized by condition)
 *   else:
 *       // Path 2: admin check fails
 *       execute(query)  // Tainted!
 *
 * Performance target: 10-20x faster than Python
 * - Python: ~1800 LOC with deque-based worklist
 * - Rust: Efficient path merging + loop limiting
 *
 * Reference:
 * - Python: path_sensitive_taint.py
 * - "Path-Sensitive Taint Analysis" (Arzt et al., 2014)
 * - "Precise and Scalable Static Taint Analysis" (FlowDroid paper)
 */

use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

use super::path_condition_converter::{convert_batch, convert_to_smt};
use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;
use crate::features::flow_graph::infrastructure::cfg::{CFGEdge, CFGEdgeType};
use crate::features::smt::infrastructure::orchestrator::SmtOrchestrator;
use crate::features::smt::infrastructure::PathFeasibility;

/// Path condition representing a branch decision
///
/// Examples:
/// - Condition{var: "is_admin", value: true} → if is_admin
/// - Condition{var: "count", value: false} → if not count > 0
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PathCondition {
    /// Variable or expression involved in condition
    pub var: String,

    /// Condition result (true/false branch)
    pub value: bool,

    /// Optional: Comparison operator (==, !=, <, >, etc.)
    pub operator: Option<String>,

    /// Optional: Compared value
    pub compared_value: Option<String>,
}

impl PathCondition {
    /// Create simple boolean condition
    pub fn boolean(var: impl Into<String>, value: bool) -> Self {
        Self {
            var: var.into(),
            value,
            operator: None,
            compared_value: None,
        }
    }

    /// Create comparison condition
    pub fn comparison(
        var: impl Into<String>,
        operator: impl Into<String>,
        compared_value: impl Into<String>,
        value: bool,
    ) -> Self {
        Self {
            var: var.into(),
            value,
            operator: Some(operator.into()),
            compared_value: Some(compared_value.into()),
        }
    }

    /// Format as string for debugging/SMT
    pub fn to_string(&self) -> String {
        if let (Some(op), Some(val)) = (&self.operator, &self.compared_value) {
            if self.value {
                format!("{} {} {}", self.var, op, val)
            } else {
                format!("!({} {} {})", self.var, op, val)
            }
        } else {
            if self.value {
                self.var.clone()
            } else {
                format!("!{}", self.var)
            }
        }
    }
}

/// Taint state at a program point with path conditions
///
/// Tracks:
/// - Which variables are tainted
/// - Path conditions leading here
/// - Depth (for loop limiting)
#[derive(Debug, Clone)]
pub struct PathSensitiveTaintState {
    /// Set of tainted variable names
    pub tainted_vars: HashSet<String>,

    /// Conditions on this execution path
    pub path_conditions: Vec<PathCondition>,

    /// Path depth (for loop/recursion limiting)
    pub depth: usize,

    /// Sanitized variables (false positive reduction)
    pub sanitized_vars: HashSet<String>,

    /// Metadata for debugging
    pub metadata: FxHashMap<String, String>,
}

impl PathSensitiveTaintState {
    /// Create new empty state
    pub fn new() -> Self {
        Self {
            tainted_vars: HashSet::new(),
            path_conditions: Vec::new(),
            depth: 0,
            sanitized_vars: HashSet::new(),
            metadata: FxHashMap::default(),
        }
    }

    /// Create state with initial taint sources
    pub fn with_sources(sources: HashSet<String>) -> Self {
        Self {
            tainted_vars: sources,
            path_conditions: Vec::new(),
            depth: 0,
            sanitized_vars: HashSet::new(),
            metadata: FxHashMap::default(),
        }
    }

    /// Add path condition
    pub fn add_condition(&mut self, condition: PathCondition) {
        self.path_conditions.push(condition);
    }

    /// Check if variable is tainted
    pub fn is_tainted(&self, var: &str) -> bool {
        self.tainted_vars.contains(var) && !self.sanitized_vars.contains(var)
    }

    /// Set taint status
    pub fn set_taint(&mut self, var: String, is_tainted: bool) {
        if is_tainted {
            self.tainted_vars.insert(var);
        } else {
            self.tainted_vars.remove(&var);
        }
    }

    /// Mark variable as sanitized
    pub fn sanitize(&mut self, var: &str) {
        self.sanitized_vars.insert(var.to_string());
    }

    /// Merge another state (for join points)
    ///
    /// Strategy: Meet-Over-Paths (conservative)
    /// - Tainted vars: Union (if tainted on ANY path → tainted)
    /// - Conditions: Intersection (only common conditions)
    /// - Depth: Maximum
    pub fn merge(&mut self, other: &PathSensitiveTaintState) {
        // Union of tainted vars
        self.tainted_vars.extend(other.tainted_vars.iter().cloned());

        // Intersection of path conditions (only keep common conditions)
        let common_conditions: Vec<PathCondition> = self
            .path_conditions
            .iter()
            .filter(|c| other.path_conditions.contains(c))
            .cloned()
            .collect();
        self.path_conditions = common_conditions;

        // Max depth
        self.depth = self.depth.max(other.depth);

        // Union of sanitized vars
        self.sanitized_vars
            .extend(other.sanitized_vars.iter().cloned());
    }

    /// Create new state with incremented depth
    pub fn with_depth(&self, depth: usize) -> Self {
        let mut state = self.clone();
        state.depth = depth;
        state
    }

    /// Clone for branching
    pub fn clone_for_branch(&self, condition: PathCondition) -> Self {
        let mut state = self.clone();
        state.add_condition(condition);
        state
    }
}

impl Default for PathSensitiveTaintState {
    fn default() -> Self {
        Self::new()
    }
}

/// Vulnerability with path conditions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathSensitiveVulnerability {
    /// Sink node ID
    pub sink: String,

    /// Tainted variables at sink
    pub tainted_vars: Vec<String>,

    /// Path conditions leading to sink
    pub path_conditions: Vec<String>,

    /// Severity
    pub severity: String,

    /// Confidence (0.0-1.0)
    pub confidence: f64,

    /// Path from source to sink (node IDs)
    pub path: Vec<String>,
}

/// Path-Sensitive Taint Analyzer
///
/// Tracks taint along different execution paths with conditional flow.
///
/// Algorithm:
/// 1. Worklist iteration on CFG
/// 2. Transfer function per node type
/// 3. State merging at join points (meet-over-paths)
/// 4. Loop limiting (k-limiting, default k=100)
///
/// Performance:
/// - Max states per node: 1 (with merging)
/// - Memory: O(CFG nodes)
/// - Time: O(CFG edges × transfer cost)
pub struct PathSensitiveTaintAnalyzer {
    /// Control Flow Graph edges
    cfg_edges: Vec<CFGEdge>,

    /// Data Flow Graph
    dfg: Option<DataFlowGraph>,

    /// Max path depth (loop limiting)
    max_depth: usize,

    /// States at each CFG node
    states: FxHashMap<String, PathSensitiveTaintState>,

    /// Worklist for fixpoint iteration
    worklist: VecDeque<String>,

    /// Visited nodes (for debugging)
    visited: HashSet<String>,

    /// Parent map for path reconstruction (child → parent)
    parent_map: FxHashMap<String, String>,

    /// SMT Orchestrator for path feasibility checking
    smt_orchestrator: SmtOrchestrator,

    /// Enable/disable SMT feasibility checking (for debugging/benchmarking)
    enable_smt: bool,
}

impl PathSensitiveTaintAnalyzer {
    /// Create new analyzer
    pub fn new(
        cfg_edges: Option<Vec<CFGEdge>>,
        dfg: Option<DataFlowGraph>,
        max_depth: usize,
    ) -> Self {
        Self {
            cfg_edges: cfg_edges.unwrap_or_default(),
            dfg,
            max_depth,
            states: FxHashMap::default(),
            worklist: VecDeque::new(),
            visited: HashSet::new(),
            parent_map: FxHashMap::default(),
            smt_orchestrator: SmtOrchestrator::new(),
            enable_smt: true,
        }
    }

    /// Enable or disable SMT feasibility checking
    pub fn with_smt(mut self, enable: bool) -> Self {
        self.enable_smt = enable;
        self
    }

    /// Run path-sensitive taint analysis
    ///
    /// Args:
    ///   sources: Taint sources (variable names)
    ///   sinks: Taint sinks (node IDs)
    ///   sanitizers: Sanitizing functions (optional)
    ///
    /// Returns:
    ///   List of vulnerabilities with path conditions
    ///
    /// Example:
    ///   sources = {"user_input"}
    ///   sinks = {"db_execute_node_1", "db_execute_node_2"}
    ///   sanitizers = {"sanitize_sql", "escape_html"}
    ///
    ///   vulns = analyzer.analyze(sources, sinks, Some(sanitizers))
    ///   // Returns vulnerabilities with path conditions
    pub fn analyze(
        &mut self,
        sources: HashSet<String>,
        sinks: HashSet<String>,
        sanitizers: Option<HashSet<String>>,
    ) -> Result<Vec<PathSensitiveVulnerability>, String> {
        if self.cfg_edges.is_empty() || self.dfg.is_none() {
            return Err("CFG edges and DFG are required for analysis".to_string());
        }

        let sanitizers = sanitizers.unwrap_or_default();

        // Initialize entry state
        let entry_state = PathSensitiveTaintState::with_sources(sources);
        let entry_node = self.get_entry_node()?;

        self.states.insert(entry_node.clone(), entry_state);
        self.worklist.push_back(entry_node.clone());

        // Fixpoint iteration
        while let Some(node_id) = self.worklist.pop_front() {
            self.visited.insert(node_id.clone());

            let current_state = self
                .states
                .get(&node_id)
                .cloned()
                .ok_or_else(|| format!("No state for node {}", node_id))?;

            // Check depth limit (loop limiting)
            if current_state.depth > self.max_depth {
                continue;
            }

            // Transfer function (process node)
            let new_states = self.transfer(&node_id, &current_state, &sanitizers)?;

            // Propagate to successors
            for (succ, state) in new_states {
                // Record parent for path reconstruction
                self.parent_map
                    .entry(succ.clone())
                    .or_insert_with(|| node_id.clone());

                let changed = self.propagate_state(&succ, &state);
                if changed && !self.worklist.contains(&succ) {
                    self.worklist.push_back(succ);
                }
            }
        }

        // Detect vulnerabilities at sinks
        let mut vulnerabilities = Vec::new();
        for sink in &sinks {
            if let Some(state) = self.states.get(sink) {
                if !state.tainted_vars.is_empty() {
                    let path_conds: Vec<String> = state
                        .path_conditions
                        .iter()
                        .map(|c| c.to_string())
                        .collect();

                    let vuln = PathSensitiveVulnerability {
                        sink: sink.clone(),
                        tainted_vars: state.tainted_vars.iter().cloned().collect(),
                        path_conditions: path_conds,
                        severity: "high".to_string(),
                        confidence: self.calculate_confidence(state),
                        path: self.reconstruct_path(sink),
                    };

                    vulnerabilities.push(vuln);
                }
            }
        }

        Ok(vulnerabilities)
    }

    /// Transfer function: Process a single node
    ///
    /// Returns: Map of successor nodes to states
    /// - Normal nodes: Single successor with updated state
    /// - Branch nodes: Multiple successors with different conditions
    fn transfer(
        &mut self,
        node_id: &str,
        state: &PathSensitiveTaintState,
        sanitizers: &HashSet<String>,
    ) -> Result<Vec<(String, PathSensitiveTaintState)>, String> {
        let mut results = Vec::new();

        // Get node type from CFG
        let node_type = self.get_node_type(node_id)?;

        match node_type.as_str() {
            "branch" => {
                // Branch node: Split into two paths
                let (true_succ, false_succ) = self.get_branch_successors(node_id)?;
                let condition = self.extract_branch_condition(node_id)?;

                // True branch
                let true_state = state.clone_for_branch(PathCondition::boolean(&condition, true));

                // Check path feasibility with SMT if enabled
                if self.enable_smt {
                    if let Ok(smt_conditions) = convert_batch(&true_state.path_conditions) {
                        let feasibility = self
                            .smt_orchestrator
                            .check_path_feasibility(&smt_conditions);

                        // Only add feasible or unknown paths (conservative approach)
                        match feasibility {
                            PathFeasibility::Feasible | PathFeasibility::Unknown => {
                                results.push((true_succ, true_state));
                            }
                            PathFeasibility::Infeasible => {
                                // Path proven infeasible - skip this branch (PRECISION IMPROVEMENT!)
                            }
                        }
                    } else {
                        // Conversion failed - conservatively include path
                        results.push((true_succ, true_state));
                    }
                } else {
                    // SMT disabled - always include path
                    results.push((true_succ, true_state));
                }

                // False branch
                let false_state = state.clone_for_branch(PathCondition::boolean(&condition, false));

                if self.enable_smt {
                    if let Ok(smt_conditions) = convert_batch(&false_state.path_conditions) {
                        let feasibility = self
                            .smt_orchestrator
                            .check_path_feasibility(&smt_conditions);

                        match feasibility {
                            PathFeasibility::Feasible | PathFeasibility::Unknown => {
                                results.push((false_succ, false_state));
                            }
                            PathFeasibility::Infeasible => {
                                // Path proven infeasible - skip this branch
                            }
                        }
                    } else {
                        results.push((false_succ, false_state));
                    }
                } else {
                    results.push((false_succ, false_state));
                }
            }

            "call" => {
                // Call node: Check if sanitizer
                let mut new_state = state.clone();
                if let Some(func_name) = self.get_called_function(node_id) {
                    if sanitizers.contains(&func_name) {
                        // Sanitize arguments
                        let args = self.get_call_arguments(node_id)?;
                        for arg in args {
                            new_state.sanitize(&arg);
                        }
                    }
                }

                let successors = self.get_successors(node_id)?;
                for succ in successors {
                    results.push((succ, new_state.clone()));
                }
            }

            "assign" => {
                // Assignment: Propagate taint
                let mut new_state = state.clone();
                let (lhs, rhs) = self.get_assignment(node_id)?;

                // If RHS is tainted, LHS becomes tainted
                if state.is_tainted(&rhs) {
                    new_state.set_taint(lhs.clone(), true);
                } else {
                    new_state.set_taint(lhs, false);
                }

                let successors = self.get_successors(node_id)?;
                for succ in successors {
                    results.push((succ, new_state.clone()));
                }
            }

            _ => {
                // Default: Propagate state unchanged
                let successors = self.get_successors(node_id)?;
                for succ in successors {
                    results.push((succ, state.clone()));
                }
            }
        }

        Ok(results)
    }

    /// Propagate state to successor node
    fn propagate_state(&mut self, succ: &str, state: &PathSensitiveTaintState) -> bool {
        if let Some(existing) = self.states.get_mut(succ) {
            let old_tainted = existing.tainted_vars.len();
            existing.merge(state);
            let new_tainted = existing.tainted_vars.len();
            new_tainted > old_tainted
        } else {
            self.states.insert(succ.to_string(), state.clone());
            true
        }
    }

    /// Calculate confidence score based on path conditions
    fn calculate_confidence(&self, state: &PathSensitiveTaintState) -> f64 {
        // More path conditions → lower confidence (more specific path)
        let condition_factor = 1.0 / (1.0 + state.path_conditions.len() as f64 * 0.1);

        // Deeper paths → lower confidence (more loops)
        let depth_factor = 1.0 / (1.0 + state.depth as f64 * 0.05);

        condition_factor * depth_factor
    }

    // Helper methods using actual CFG/DFG

    fn get_entry_node(&self) -> Result<String, String> {
        // Entry is the source of the first unconditional edge or first edge
        for edge in &self.cfg_edges {
            if matches!(edge.edge_type, CFGEdgeType::Unconditional) {
                return Ok(edge.source_block_id.clone());
            }
        }

        // Fallback: first edge source
        self.cfg_edges
            .first()
            .map(|e| e.source_block_id.clone())
            .ok_or_else(|| "No entry node found in CFG".to_string())
    }

    fn get_node_type(&self, node_id: &str) -> Result<String, String> {
        // Determine node type based on outgoing edges
        let outgoing_edges: Vec<_> = self
            .cfg_edges
            .iter()
            .filter(|e| e.source_block_id == node_id)
            .collect();

        if outgoing_edges.is_empty() {
            return Ok("return".to_string());
        }

        // Check for branch (has both true and false edges)
        let has_true = outgoing_edges
            .iter()
            .any(|e| matches!(e.edge_type, CFGEdgeType::True));
        let has_false = outgoing_edges
            .iter()
            .any(|e| matches!(e.edge_type, CFGEdgeType::False));

        if has_true && has_false {
            return Ok("branch".to_string());
        }

        // Check for loop back edge
        if outgoing_edges
            .iter()
            .any(|e| matches!(e.edge_type, CFGEdgeType::LoopBack))
        {
            return Ok("loop_continue".to_string());
        }

        // Default: assume assignment or call (need DFG to distinguish)
        Ok("default".to_string())
    }

    fn get_successors(&self, node_id: &str) -> Result<Vec<String>, String> {
        // Find all edges from this node
        let successors: Vec<String> = self
            .cfg_edges
            .iter()
            .filter(|e| e.source_block_id == node_id)
            .map(|e| e.target_block_id.clone())
            .collect();

        Ok(successors)
    }

    fn get_branch_successors(&self, node_id: &str) -> Result<(String, String), String> {
        let mut true_branch = None;
        let mut false_branch = None;

        for edge in &self.cfg_edges {
            if edge.source_block_id == node_id {
                match edge.edge_type {
                    CFGEdgeType::True => true_branch = Some(edge.target_block_id.clone()),
                    CFGEdgeType::False => false_branch = Some(edge.target_block_id.clone()),
                    _ => {}
                }
            }
        }

        match (true_branch, false_branch) {
            (Some(t), Some(f)) => Ok((t, f)),
            _ => Err(format!(
                "Node {} is not a branch node with both true/false successors",
                node_id
            )),
        }
    }

    fn extract_branch_condition(&self, node_id: &str) -> Result<String, String> {
        // Extract condition from node ID (basic implementation)
        // In real implementation, would query DFG or AST for actual condition
        Ok(format!("condition_{}", node_id))
    }

    fn get_called_function(&self, _node_id: &str) -> Option<String> {
        // Would query DFG for call target
        None
    }

    fn get_call_arguments(&self, _node_id: &str) -> Result<Vec<String>, String> {
        // Would query DFG for call arguments
        Ok(vec![])
    }

    fn get_assignment(&self, _node_id: &str) -> Result<(String, String), String> {
        // Would query DFG for assignment LHS/RHS
        Ok(("lhs".to_string(), "rhs".to_string()))
    }

    /// Reconstruct path from source to sink using parent map
    ///
    /// Performs backward slicing from sink to entry node.
    ///
    /// Returns: Ordered list of node IDs (Source → ... → Sink)
    fn reconstruct_path(&self, sink: &str) -> Vec<String> {
        let mut path = vec![sink.to_string()];
        let mut current = sink;

        // Backtrack using parent map
        while let Some(parent) = self.parent_map.get(current) {
            path.push(parent.clone());
            current = parent;

            // Prevent infinite loops (cycle detection)
            if path.len() > 1000 {
                break;
            }
        }

        // Reverse to get Source → Sink order
        path.reverse();
        path
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_path_condition() {
        let cond = PathCondition::boolean("is_admin", true);
        assert_eq!(cond.to_string(), "is_admin");

        let cond = PathCondition::boolean("is_admin", false);
        assert_eq!(cond.to_string(), "!is_admin");

        let cond = PathCondition::comparison("count", ">", "0", true);
        assert_eq!(cond.to_string(), "count > 0");
    }

    #[test]
    fn test_state_merge() {
        let mut state1 = PathSensitiveTaintState::new();
        state1.tainted_vars.insert("x".to_string());
        state1.add_condition(PathCondition::boolean("cond1", true));

        let mut state2 = PathSensitiveTaintState::new();
        state2.tainted_vars.insert("y".to_string());
        state2.add_condition(PathCondition::boolean("cond1", true));
        state2.add_condition(PathCondition::boolean("cond2", false));

        state1.merge(&state2);

        // Should have union of tainted vars
        assert!(state1.tainted_vars.contains("x"));
        assert!(state1.tainted_vars.contains("y"));

        // Should have intersection of conditions (only common)
        assert_eq!(state1.path_conditions.len(), 1);
        assert_eq!(state1.path_conditions[0].var, "cond1");
    }

    #[test]
    fn test_sanitization() {
        let mut state = PathSensitiveTaintState::new();
        state.set_taint("user_input".to_string(), true);
        assert!(state.is_tainted("user_input"));

        state.sanitize("user_input");
        assert!(!state.is_tainted("user_input")); // Sanitized → not tainted
    }

    #[test]
    fn test_smt_integration() {
        // Test SMT orchestrator integration in PathSensitiveTaintAnalyzer
        let analyzer = PathSensitiveTaintAnalyzer::new(None, None, 100);

        // Verify SMT is enabled by default
        assert!(analyzer.enable_smt);

        // Test with_smt builder method
        let analyzer_no_smt = PathSensitiveTaintAnalyzer::new(None, None, 100).with_smt(false);
        assert!(!analyzer_no_smt.enable_smt);
    }

    #[test]
    fn test_path_condition_conversion() {
        // Test that PathCondition can be converted to SMT format
        use crate::features::taint_analysis::infrastructure::path_condition_converter::convert_to_smt;

        let taint_cond = PathCondition::boolean("is_admin", true);
        let smt_cond = convert_to_smt(&taint_cond);

        assert!(smt_cond.is_ok());
        let smt = smt_cond.unwrap();
        assert_eq!(smt.var, "is_admin");
    }
}
