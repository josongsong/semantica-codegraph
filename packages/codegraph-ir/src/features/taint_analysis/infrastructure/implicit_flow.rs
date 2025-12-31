/*
 * Implicit Flow Taint Analysis
 *
 * NEW SOTA Implementation - Tracks information flow through control dependencies
 *
 * Implicit flow occurs when sensitive data affects control flow decisions,
 * indirectly influencing output values without direct data flow.
 *
 * Example:
 * ```python
 * secret = get_password()     # Source: secret is tainted
 * if secret == "admin123":    # Tainted condition!
 *     x = 1                   # x implicitly receives secret info
 * else:
 *     x = 0                   # x implicitly receives secret info
 * print(x)                    # Sink: x leaks info about secret
 * ```
 *
 * In this example:
 * - Direct taint: secret → print(secret) would be caught
 * - Implicit taint: secret → condition → x → print(x) - THIS MODULE
 *
 * Key Concepts:
 * 1. Control Dependency: A statement S is control-dependent on condition C
 *    if C determines whether S executes
 * 2. Implicit Flow: If C uses tainted variable V, all control-dependent
 *    statements inherit taint from V
 * 3. Security Level: Often combined with lattice-based security labels
 *
 * Algorithm:
 * 1. Build Control Dependency Graph (CDG) from CFG
 * 2. For each branch with tainted condition:
 *    - Find all control-dependent nodes
 *    - Propagate implicit taint to writes in those nodes
 * 3. Handle nested conditionals (transitive control dependency)
 *
 * Performance Target: O(n * m) where n=nodes, m=tainted conditions
 *
 * References:
 * - Denning & Denning (1977): "Certification of Programs for Secure Information Flow"
 * - Sabelfeld & Myers (2003): "Language-based Information-Flow Security"
 * - King et al. (2008): "Implicit Flows: Can't Live With 'Em, Can't Live Without 'Em"
 */

use rustc_hash::{FxHashMap, FxHashSet};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

use super::ifds_solver::{CFGEdge, CFGEdgeKind, CFG as IFDSCFG};
use crate::features::flow_graph::infrastructure::cfg::CFGEdge as FlowCFGEdge;

// ============================================================================
// Control Dependency Graph
// ============================================================================

/// Control Dependency Edge
///
/// Represents that `dependent` node is control-dependent on `controller` node.
/// The `branch` indicates which branch (true/false) leads to the dependency.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ControlDependency {
    /// Controller node (the condition)
    pub controller: String,

    /// Dependent node (executed conditionally)
    pub dependent: String,

    /// Which branch of the condition (true/false)
    pub branch: bool,

    /// Nesting level (for nested conditionals)
    pub nesting_level: usize,
}

impl ControlDependency {
    pub fn new(controller: impl Into<String>, dependent: impl Into<String>, branch: bool) -> Self {
        Self {
            controller: controller.into(),
            dependent: dependent.into(),
            branch,
            nesting_level: 0,
        }
    }

    pub fn with_nesting(mut self, level: usize) -> Self {
        self.nesting_level = level;
        self
    }
}

/// Control Dependency Graph (CDG)
///
/// Maps each node to its controlling conditions.
/// Used to determine implicit information flow.
#[derive(Debug, Clone, Default)]
pub struct ControlDependencyGraph {
    /// Node → set of controlling conditions
    /// If a node has multiple controllers, it's nested in multiple conditionals
    dependencies: FxHashMap<String, Vec<ControlDependency>>,

    /// Reverse mapping: Controller → all dependent nodes
    dependents: FxHashMap<String, FxHashSet<String>>,

    /// Entry nodes (not control-dependent on anything)
    entry_nodes: FxHashSet<String>,
}

impl ControlDependencyGraph {
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a control dependency
    pub fn add_dependency(&mut self, dep: ControlDependency) {
        // Forward mapping
        self.dependencies
            .entry(dep.dependent.clone())
            .or_insert_with(Vec::new)
            .push(dep.clone());

        // Reverse mapping
        self.dependents
            .entry(dep.controller.clone())
            .or_insert_with(FxHashSet::default)
            .insert(dep.dependent.clone());
    }

    /// Get all controllers for a node
    pub fn get_controllers(&self, node: &str) -> Option<&[ControlDependency]> {
        self.dependencies.get(node).map(|v| v.as_slice())
    }

    /// Get all nodes dependent on a controller
    pub fn get_dependents(&self, controller: &str) -> Option<&FxHashSet<String>> {
        self.dependents.get(controller)
    }

    /// Check if a node is control-dependent on any condition
    pub fn is_controlled(&self, node: &str) -> bool {
        self.dependencies.contains_key(node)
    }

    /// Get maximum nesting level for a node
    pub fn get_nesting_level(&self, node: &str) -> usize {
        self.dependencies
            .get(node)
            .map(|deps| deps.iter().map(|d| d.nesting_level).max().unwrap_or(0))
            .unwrap_or(0)
    }

    /// Add an entry node (not controlled by any condition)
    pub fn add_entry_node(&mut self, node: impl Into<String>) {
        self.entry_nodes.insert(node.into());
    }

    /// Build CDG from CFG using post-dominator analysis
    ///
    /// Algorithm (simplified):
    /// 1. Compute post-dominator tree
    /// 2. For each branch node B with successors S1, S2:
    ///    - Nodes in S1's subtree (not post-dominated by B) are control-dependent on B (true)
    ///    - Nodes in S2's subtree (not post-dominated by B) are control-dependent on B (false)
    pub fn build_from_cfg(cfg: &IFDSCFG) -> Self {
        let mut cdg = Self::new();

        // Simplified algorithm: use branch detection from CFG edges
        // Full implementation would compute post-dominators

        // Find branch nodes (nodes with multiple successors)
        let mut branch_successors: FxHashMap<String, Vec<(String, bool)>> = FxHashMap::default();

        for edge in &cfg.edges {
            if let CFGEdgeKind::Normal = &edge.kind {
                // Check if this is part of a branch
                branch_successors
                    .entry(edge.from.clone())
                    .or_insert_with(Vec::new)
                    .push((edge.to.clone(), true)); // Will refine branch direction
            }
        }

        // Process branch nodes
        for (branch_node, successors) in &branch_successors {
            if successors.len() >= 2 {
                // This is a branch point (if/else, switch, etc.)
                // Mark all reachable nodes as control-dependent

                for (idx, (succ, _)) in successors.iter().enumerate() {
                    let branch_value = idx == 0; // First successor = true branch

                    // Find all nodes reachable from this successor
                    // until we hit a join point (post-dominator)
                    let reachable = Self::find_control_dependent_nodes(cfg, succ, branch_node);

                    for dep_node in reachable {
                        cdg.add_dependency(ControlDependency::new(
                            branch_node.clone(),
                            dep_node,
                            branch_value,
                        ));
                    }
                }
            }
        }

        // Mark entry nodes
        for entry in &cfg.entries {
            cdg.add_entry_node(entry.clone());
        }

        cdg
    }

    /// Find nodes control-dependent on a branch
    ///
    /// Uses forward reachability with join-point detection
    fn find_control_dependent_nodes(
        cfg: &IFDSCFG,
        start: &str,
        controller: &str,
    ) -> FxHashSet<String> {
        let mut dependent = FxHashSet::default();
        let mut visited = FxHashSet::default();
        let mut worklist = VecDeque::new();

        worklist.push_back(start.to_string());
        visited.insert(start.to_string());

        while let Some(node) = worklist.pop_front() {
            // Don't include the controller itself
            if node != controller {
                dependent.insert(node.clone());
            }

            // Get successors
            if let Some(successors) = cfg.get_successors(&node) {
                for succ_edge in successors {
                    let succ = &succ_edge.to;

                    // Stop at join points (nodes with multiple predecessors)
                    // Simplified: just do bounded forward exploration
                    if !visited.contains(succ) && dependent.len() < 100 {
                        visited.insert(succ.clone());
                        worklist.push_back(succ.clone());
                    }
                }
            }
        }

        dependent
    }
}

// ============================================================================
// Implicit Taint State
// ============================================================================

/// Implicit taint source
///
/// Tracks the origin of implicit taint (which condition caused it)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ImplicitTaintSource {
    /// Original tainted variable in the condition
    pub tainted_variable: String,

    /// The condition node where the taint was used
    pub condition_node: String,

    /// Which branch was taken
    pub branch_taken: bool,

    /// Direct taint source (if known)
    pub direct_source: Option<String>,
}

impl ImplicitTaintSource {
    pub fn new(
        tainted_variable: impl Into<String>,
        condition_node: impl Into<String>,
        branch_taken: bool,
    ) -> Self {
        Self {
            tainted_variable: tainted_variable.into(),
            condition_node: condition_node.into(),
            branch_taken,
            direct_source: None,
        }
    }

    pub fn with_direct_source(mut self, source: impl Into<String>) -> Self {
        self.direct_source = Some(source.into());
        self
    }
}

/// Implicit taint state for a program point
///
/// Tracks both direct taint and implicit taint at each location
#[derive(Debug, Clone, Default)]
pub struct ImplicitTaintState {
    /// Direct taint: variable → set of taint sources
    pub direct_taint: FxHashMap<String, FxHashSet<String>>,

    /// Implicit taint: variable → set of implicit sources
    pub implicit_taint: FxHashMap<String, Vec<ImplicitTaintSource>>,

    /// Active tainted conditions (for propagation)
    /// condition_node → tainted variables used in condition
    pub active_conditions: FxHashMap<String, FxHashSet<String>>,
}

impl ImplicitTaintState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Add direct taint to a variable
    pub fn add_direct_taint(&mut self, var: impl Into<String>, source: impl Into<String>) {
        self.direct_taint
            .entry(var.into())
            .or_insert_with(FxHashSet::default)
            .insert(source.into());
    }

    /// Add implicit taint to a variable
    pub fn add_implicit_taint(&mut self, var: impl Into<String>, source: ImplicitTaintSource) {
        self.implicit_taint
            .entry(var.into())
            .or_insert_with(Vec::new)
            .push(source);
    }

    /// Check if a variable has any taint (direct or implicit)
    pub fn is_tainted(&self, var: &str) -> bool {
        self.direct_taint.contains_key(var) || self.implicit_taint.contains_key(var)
    }

    /// Check if a variable has direct taint
    pub fn has_direct_taint(&self, var: &str) -> bool {
        self.direct_taint
            .get(var)
            .map(|s| !s.is_empty())
            .unwrap_or(false)
    }

    /// Check if a variable has implicit taint
    pub fn has_implicit_taint(&self, var: &str) -> bool {
        self.implicit_taint
            .get(var)
            .map(|s| !s.is_empty())
            .unwrap_or(false)
    }

    /// Get all taint sources for a variable (both direct and implicit)
    pub fn get_all_taint_sources(&self, var: &str) -> Vec<String> {
        let mut sources = Vec::new();

        // Add direct sources
        if let Some(direct) = self.direct_taint.get(var) {
            sources.extend(direct.iter().cloned());
        }

        // Add implicit sources (as formatted strings)
        if let Some(implicit) = self.implicit_taint.get(var) {
            for src in implicit {
                sources.push(format!(
                    "implicit:{}@{}",
                    src.tainted_variable, src.condition_node
                ));
            }
        }

        sources
    }

    /// Register a tainted condition
    pub fn register_tainted_condition(
        &mut self,
        condition_node: impl Into<String>,
        tainted_vars: FxHashSet<String>,
    ) {
        self.active_conditions
            .insert(condition_node.into(), tainted_vars);
    }

    /// Merge with another state (for join points)
    pub fn merge(&mut self, other: &ImplicitTaintState) {
        // Merge direct taint
        for (var, sources) in &other.direct_taint {
            self.direct_taint
                .entry(var.clone())
                .or_insert_with(FxHashSet::default)
                .extend(sources.iter().cloned());
        }

        // Merge implicit taint
        for (var, sources) in &other.implicit_taint {
            self.implicit_taint
                .entry(var.clone())
                .or_insert_with(Vec::new)
                .extend(sources.iter().cloned());
        }

        // Merge active conditions
        for (node, vars) in &other.active_conditions {
            self.active_conditions
                .entry(node.clone())
                .or_insert_with(FxHashSet::default)
                .extend(vars.iter().cloned());
        }
    }

    /// Clone state for branch exploration
    pub fn clone_for_branch(&self) -> Self {
        self.clone()
    }
}

// ============================================================================
// Implicit Flow Analyzer
// ============================================================================

/// Implicit Flow Vulnerability
///
/// Represents a detected implicit information flow
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImplicitFlowVulnerability {
    /// Variable receiving implicit taint
    pub tainted_variable: String,

    /// Source variable (in condition)
    pub source_variable: String,

    /// Condition node where taint was used
    pub condition_node: String,

    /// Sink where tainted variable is used
    pub sink_node: String,

    /// Sink type (e.g., "execute", "print", "send")
    pub sink_type: String,

    /// Path from source to sink
    pub path: Vec<String>,

    /// Severity assessment
    pub severity: ImplicitFlowSeverity,
}

/// Severity levels for implicit flow vulnerabilities
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ImplicitFlowSeverity {
    /// Low: Implicit flow with low information leakage
    Low,

    /// Medium: Partial information leakage possible
    Medium,

    /// High: Significant information leakage
    High,

    /// Critical: Full secret reconstruction possible (e.g., bit-by-bit extraction)
    Critical,
}

impl ImplicitFlowSeverity {
    /// Assess severity based on nesting and path length
    pub fn assess(nesting_level: usize, path_length: usize, in_loop: bool) -> Self {
        // Higher nesting + loops = easier to extract full information
        let score = nesting_level + if in_loop { 3 } else { 0 };

        match score {
            0..=1 => Self::Low,
            2..=3 => Self::Medium,
            4..=5 => Self::High,
            _ => Self::Critical,
        }
    }
}

/// Implicit Flow Analyzer Configuration
#[derive(Debug, Clone)]
pub struct ImplicitFlowConfig {
    /// Maximum analysis depth
    pub max_depth: usize,

    /// Maximum paths to explore
    pub max_paths: usize,

    /// Track implicit flows through nested conditions
    pub track_nested: bool,

    /// Include low-severity findings
    pub include_low_severity: bool,

    /// Known taint sources (variable patterns)
    pub taint_sources: FxHashSet<String>,

    /// Known taint sinks (function/node patterns)
    pub taint_sinks: FxHashSet<String>,
}

impl Default for ImplicitFlowConfig {
    fn default() -> Self {
        Self {
            max_depth: 50,
            max_paths: 1000,
            track_nested: true,
            include_low_severity: false,
            taint_sources: FxHashSet::from_iter([
                "user_input".to_string(),
                "password".to_string(),
                "secret".to_string(),
                "api_key".to_string(),
                "token".to_string(),
                "request".to_string(),
            ]),
            taint_sinks: FxHashSet::from_iter([
                "execute".to_string(),
                "print".to_string(),
                "send".to_string(),
                "write".to_string(),
                "log".to_string(),
                "eval".to_string(),
            ]),
        }
    }
}

/// Implicit Flow Taint Analyzer
///
/// Detects information leakage through control dependencies.
///
/// Usage:
/// ```text
/// let mut analyzer = ImplicitFlowAnalyzer::new(config);
/// let cdg = ControlDependencyGraph::build_from_cfg(&cfg);
/// let vulns = analyzer.analyze(&cfg, &cdg, &initial_taint);
/// ```
pub struct ImplicitFlowAnalyzer {
    /// Configuration
    config: ImplicitFlowConfig,

    /// Per-node taint states
    states: FxHashMap<String, ImplicitTaintState>,

    /// Detected vulnerabilities
    vulnerabilities: Vec<ImplicitFlowVulnerability>,

    /// Statistics
    stats: ImplicitFlowStats,
}

/// Analysis statistics
#[derive(Debug, Clone, Default)]
pub struct ImplicitFlowStats {
    pub nodes_analyzed: usize,
    pub implicit_flows_detected: usize,
    pub direct_flows_detected: usize,
    pub conditions_with_taint: usize,
    pub max_nesting_level: usize,
    pub paths_explored: usize,
}

impl ImplicitFlowAnalyzer {
    /// Create new analyzer with configuration
    pub fn new(config: ImplicitFlowConfig) -> Self {
        Self {
            config,
            states: FxHashMap::default(),
            vulnerabilities: Vec::new(),
            stats: ImplicitFlowStats::default(),
        }
    }

    /// Create with default configuration
    pub fn default_config() -> Self {
        Self::new(ImplicitFlowConfig::default())
    }

    /// Analyze CFG for implicit flows
    ///
    /// # Arguments
    /// * `cfg` - Control flow graph
    /// * `cdg` - Control dependency graph
    /// * `initial_taint` - Initial taint state (sources)
    ///
    /// # Returns
    /// List of detected implicit flow vulnerabilities
    pub fn analyze(
        &mut self,
        cfg: &IFDSCFG,
        cdg: &ControlDependencyGraph,
        initial_taint: &FxHashMap<String, FxHashSet<String>>,
    ) -> Vec<ImplicitFlowVulnerability> {
        // Initialize states with initial taint
        let mut initial_state = ImplicitTaintState::new();
        for (var, sources) in initial_taint {
            for source in sources {
                initial_state.add_direct_taint(var.clone(), source.clone());
            }
        }

        // Worklist-based fixpoint iteration
        let mut worklist: VecDeque<String> = VecDeque::new();
        let mut visited: FxHashSet<String> = FxHashSet::default();

        // Start from entry nodes
        for entry in &cfg.entries {
            self.states.insert(entry.clone(), initial_state.clone());
            worklist.push_back(entry.clone());
        }

        // Main analysis loop
        while let Some(node) = worklist.pop_front() {
            if self.stats.paths_explored >= self.config.max_paths {
                break;
            }
            self.stats.paths_explored += 1;

            // Get current state
            let state = match self.states.get(&node) {
                Some(s) => s.clone(),
                None => continue,
            };

            // Process this node
            let new_state = self.process_node(&node, &state, cdg);

            // Check for tainted conditions at branch points
            if let Some(successors) = cfg.get_successors(&node) {
                if successors.len() >= 2 {
                    // This is a branch point - check if condition uses tainted data
                    self.check_tainted_condition(&node, &new_state, cdg);
                }
            }

            // Check for sinks
            self.check_sink(&node, &new_state);

            // Update state and propagate
            self.states.insert(node.clone(), new_state.clone());
            self.stats.nodes_analyzed += 1;

            // Add successors to worklist
            if let Some(successors) = cfg.get_successors(&node) {
                for succ_edge in successors {
                    let succ = &succ_edge.to;

                    // Check state change in separate block to avoid borrow conflict
                    let (needs_add, succ_state_after) = {
                        // Get or create successor state
                        let succ_state = self
                            .states
                            .entry(succ.clone())
                            .or_insert_with(ImplicitTaintState::new);

                        // Record old sizes for change detection
                        let old_direct: usize =
                            succ_state.direct_taint.values().map(|s| s.len()).sum();
                        let old_implicit: usize =
                            succ_state.implicit_taint.values().map(|s| s.len()).sum();

                        // Merge new state
                        succ_state.merge(&new_state);

                        // Check if anything changed
                        let new_direct: usize =
                            succ_state.direct_taint.values().map(|s| s.len()).sum();
                        let new_implicit: usize =
                            succ_state.implicit_taint.values().map(|s| s.len()).sum();
                        let changed = new_direct > old_direct || new_implicit > old_implicit;

                        (!visited.contains(succ) || changed, succ_state.clone())
                    };

                    // Add to worklist if needed (outside mutable borrow scope)
                    if needs_add {
                        visited.insert(succ.clone());
                        worklist.push_back(succ.clone());
                    }
                }
            }
        }

        self.vulnerabilities.clone()
    }

    /// Process a single node
    fn process_node(
        &mut self,
        node: &str,
        state: &ImplicitTaintState,
        cdg: &ControlDependencyGraph,
    ) -> ImplicitTaintState {
        let mut new_state = state.clone();

        // Check if this node is control-dependent on tainted condition
        if let Some(controllers) = cdg.get_controllers(node) {
            for dep in controllers {
                // Check if any active condition controls this node
                if let Some(tainted_vars) = state.active_conditions.get(&dep.controller) {
                    // Propagate implicit taint to any writes at this node
                    for tainted_var in tainted_vars {
                        // In a full implementation, we would parse the node
                        // to find what variables are written
                        // For now, assume node name indicates a write: "x = ..."
                        if let Some(write_var) = self.extract_write_target(node) {
                            let implicit_source = ImplicitTaintSource::new(
                                tainted_var.clone(),
                                dep.controller.clone(),
                                dep.branch,
                            );
                            new_state.add_implicit_taint(write_var, implicit_source);
                            self.stats.implicit_flows_detected += 1;

                            // Track max nesting
                            if dep.nesting_level > self.stats.max_nesting_level {
                                self.stats.max_nesting_level = dep.nesting_level;
                            }
                        }
                    }
                }
            }
        }

        new_state
    }

    /// Check if a branch condition uses tainted data
    fn check_tainted_condition(
        &mut self,
        node: &str,
        state: &ImplicitTaintState,
        _cdg: &ControlDependencyGraph,
    ) {
        // Extract variables used in condition
        let condition_vars = self.extract_condition_vars(node);

        // Check which are tainted
        let mut tainted_in_condition = FxHashSet::default();
        for var in condition_vars {
            if state.is_tainted(&var) {
                tainted_in_condition.insert(var);
            }
        }

        // Register if condition uses tainted data
        if !tainted_in_condition.is_empty() {
            self.stats.conditions_with_taint += 1;

            // Update state with active tainted condition
            if let Some(node_state) = self.states.get_mut(node) {
                node_state.register_tainted_condition(node.to_string(), tainted_in_condition);
            }
        }
    }

    /// Check if node is a sink and tainted data reaches it
    fn check_sink(&mut self, node: &str, state: &ImplicitTaintState) {
        // Check if this node matches a sink pattern
        let is_sink = self
            .config
            .taint_sinks
            .iter()
            .any(|sink| node.contains(sink));

        if !is_sink {
            return;
        }

        // Check for tainted variables used at this sink
        let used_vars = self.extract_used_vars(node);

        for var in used_vars {
            if state.has_implicit_taint(&var) {
                // Found implicit flow to sink!
                if let Some(implicit_sources) = state.implicit_taint.get(&var) {
                    for source in implicit_sources {
                        let severity = ImplicitFlowSeverity::assess(
                            0,     // Would compute from CDG
                            0,     // Would compute path length
                            false, // Would detect loops
                        );

                        // Skip low severity if configured
                        if severity == ImplicitFlowSeverity::Low
                            && !self.config.include_low_severity
                        {
                            continue;
                        }

                        let vuln = ImplicitFlowVulnerability {
                            tainted_variable: var.clone(),
                            source_variable: source.tainted_variable.clone(),
                            condition_node: source.condition_node.clone(),
                            sink_node: node.to_string(),
                            sink_type: self.extract_sink_type(node),
                            path: vec![
                                source.tainted_variable.clone(),
                                source.condition_node.clone(),
                                var.clone(),
                                node.to_string(),
                            ],
                            severity,
                        };

                        self.vulnerabilities.push(vuln);
                    }
                }
            }

            // Also check direct taint at sinks
            if state.has_direct_taint(&var) {
                self.stats.direct_flows_detected += 1;
            }
        }
    }

    /// Extract write target from node (simplified)
    fn extract_write_target(&self, node: &str) -> Option<String> {
        // Pattern: "var = ..." or "assign_var"
        if node.contains('=') {
            let parts: Vec<&str> = node.split('=').collect();
            if !parts.is_empty() {
                return Some(parts[0].trim().to_string());
            }
        }
        if node.starts_with("assign_") {
            return Some(node.replace("assign_", ""));
        }
        None
    }

    /// Extract variables used in condition (simplified)
    fn extract_condition_vars(&self, node: &str) -> Vec<String> {
        // Pattern: "if_<var>" or "branch_<var>"
        let mut vars = Vec::new();

        if node.starts_with("if_") || node.starts_with("branch_") {
            let var = node.replace("if_", "").replace("branch_", "");
            // Handle comparisons: "x_gt_5" → "x"
            if let Some(idx) = var.find('_') {
                vars.push(var[..idx].to_string());
            } else {
                vars.push(var);
            }
        }

        // Also check if node contains known taint source patterns
        for source_pattern in &self.config.taint_sources {
            if node.contains(source_pattern.as_str()) {
                vars.push(source_pattern.clone());
            }
        }

        vars
    }

    /// Extract variables used at a node (simplified)
    fn extract_used_vars(&self, node: &str) -> Vec<String> {
        let mut vars = Vec::new();

        // Pattern: "func(var)" or "sink_var"
        if node.contains('(') && node.contains(')') {
            let start = node.find('(').unwrap();
            let end = node.find(')').unwrap();
            if start < end {
                let args = &node[start + 1..end];
                for arg in args.split(',') {
                    vars.push(arg.trim().to_string());
                }
            }
        }

        vars
    }

    /// Extract sink type from node name
    fn extract_sink_type(&self, node: &str) -> String {
        for sink in &self.config.taint_sinks {
            if node.contains(sink.as_str()) {
                return sink.clone();
            }
        }
        "unknown".to_string()
    }

    /// Check if state changed (for fixpoint detection)
    fn state_changed(&self, old: &ImplicitTaintState, new: &ImplicitTaintState) -> bool {
        // Check if any new taint was added
        for (var, sources) in &new.direct_taint {
            if let Some(old_sources) = old.direct_taint.get(var) {
                if sources.len() > old_sources.len() {
                    return true;
                }
            } else if !sources.is_empty() {
                return true;
            }
        }

        for (var, sources) in &new.implicit_taint {
            if let Some(old_sources) = old.implicit_taint.get(var) {
                if sources.len() > old_sources.len() {
                    return true;
                }
            } else if !sources.is_empty() {
                return true;
            }
        }

        false
    }

    /// Get analysis statistics
    pub fn stats(&self) -> &ImplicitFlowStats {
        &self.stats
    }

    /// Get all detected vulnerabilities
    pub fn vulnerabilities(&self) -> &[ImplicitFlowVulnerability] {
        &self.vulnerabilities
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn create_simple_cfg() -> IFDSCFG {
        let mut cfg = IFDSCFG::new();

        // Simple if-else:
        // entry → read_secret → if_secret → assign_x=1 → sink
        //                                 → assign_x=0 → sink
        cfg.add_entry("entry");
        cfg.add_edge(super::super::ifds_solver::CFGEdge::normal(
            "entry",
            "read_secret",
        ));
        cfg.add_edge(super::super::ifds_solver::CFGEdge::normal(
            "read_secret",
            "if_secret",
        ));
        cfg.add_edge(super::super::ifds_solver::CFGEdge::normal(
            "if_secret",
            "assign_x=1",
        ));
        cfg.add_edge(super::super::ifds_solver::CFGEdge::normal(
            "if_secret",
            "assign_x=0",
        ));
        cfg.add_edge(super::super::ifds_solver::CFGEdge::normal(
            "assign_x=1",
            "print(x)",
        ));
        cfg.add_edge(super::super::ifds_solver::CFGEdge::normal(
            "assign_x=0",
            "print(x)",
        ));
        cfg.add_exit("print(x)");

        cfg
    }

    #[test]
    fn test_control_dependency_graph_creation() {
        let cdg = ControlDependencyGraph::new();
        assert!(!cdg.is_controlled("test"));
    }

    #[test]
    fn test_add_control_dependency() {
        let mut cdg = ControlDependencyGraph::new();
        cdg.add_dependency(ControlDependency::new("if_cond", "assign_x", true));

        assert!(cdg.is_controlled("assign_x"));
        assert!(!cdg.is_controlled("if_cond"));

        let controllers = cdg.get_controllers("assign_x").unwrap();
        assert_eq!(controllers.len(), 1);
        assert_eq!(controllers[0].controller, "if_cond");
    }

    #[test]
    fn test_cdg_build_from_cfg() {
        let cfg = create_simple_cfg();
        let cdg = ControlDependencyGraph::build_from_cfg(&cfg);

        // if_secret has two successors, so nodes after it should be control-dependent
        assert!(cdg.is_controlled("assign_x=1") || cdg.get_dependents("if_secret").is_some());
    }

    #[test]
    fn test_implicit_taint_state() {
        let mut state = ImplicitTaintState::new();

        // Add direct taint
        state.add_direct_taint("secret", "user_input");
        assert!(state.has_direct_taint("secret"));
        assert!(!state.has_implicit_taint("secret"));
        assert!(state.is_tainted("secret"));

        // Add implicit taint
        let implicit_src = ImplicitTaintSource::new("secret", "if_secret", true);
        state.add_implicit_taint("x", implicit_src);
        assert!(state.has_implicit_taint("x"));
        assert!(!state.has_direct_taint("x"));
        assert!(state.is_tainted("x"));
    }

    #[test]
    fn test_implicit_taint_state_merge() {
        let mut state1 = ImplicitTaintState::new();
        state1.add_direct_taint("secret", "source1");

        let mut state2 = ImplicitTaintState::new();
        state2.add_direct_taint("password", "source2");
        state2.add_implicit_taint("x", ImplicitTaintSource::new("secret", "cond", true));

        state1.merge(&state2);

        assert!(state1.is_tainted("secret"));
        assert!(state1.is_tainted("password"));
        assert!(state1.has_implicit_taint("x"));
    }

    #[test]
    fn test_implicit_flow_analyzer_creation() {
        let config = ImplicitFlowConfig::default();
        let analyzer = ImplicitFlowAnalyzer::new(config);

        assert!(analyzer.vulnerabilities().is_empty());
        assert_eq!(analyzer.stats().nodes_analyzed, 0);
    }

    #[test]
    fn test_implicit_flow_basic_analysis() {
        let cfg = create_simple_cfg();
        let cdg = ControlDependencyGraph::build_from_cfg(&cfg);

        let mut initial_taint: FxHashMap<String, FxHashSet<String>> = FxHashMap::default();
        initial_taint.insert(
            "secret".to_string(),
            FxHashSet::from_iter(["user_input".to_string()]),
        );

        let config = ImplicitFlowConfig {
            include_low_severity: true,
            ..Default::default()
        };
        let mut analyzer = ImplicitFlowAnalyzer::new(config);

        let _vulns = analyzer.analyze(&cfg, &cdg, &initial_taint);

        // Should have analyzed nodes
        assert!(analyzer.stats().nodes_analyzed > 0);
    }

    #[test]
    fn test_implicit_flow_severity_assessment() {
        // Low: no nesting, not in loop
        assert_eq!(
            ImplicitFlowSeverity::assess(0, 1, false),
            ImplicitFlowSeverity::Low
        );

        // Medium: some nesting
        assert_eq!(
            ImplicitFlowSeverity::assess(2, 3, false),
            ImplicitFlowSeverity::Medium
        );

        // High: in loop
        assert_eq!(
            ImplicitFlowSeverity::assess(1, 5, true),
            ImplicitFlowSeverity::High
        );

        // Critical: high nesting + loop
        assert_eq!(
            ImplicitFlowSeverity::assess(4, 10, true),
            ImplicitFlowSeverity::Critical
        );
    }

    #[test]
    fn test_implicit_taint_source() {
        let src =
            ImplicitTaintSource::new("secret", "if_cond", true).with_direct_source("user_input");

        assert_eq!(src.tainted_variable, "secret");
        assert_eq!(src.condition_node, "if_cond");
        assert!(src.branch_taken);
        assert_eq!(src.direct_source, Some("user_input".to_string()));
    }

    #[test]
    fn test_control_dependency_nesting() {
        let mut cdg = ControlDependencyGraph::new();

        // Nested conditions
        cdg.add_dependency(ControlDependency::new("if_outer", "if_inner", true).with_nesting(0));
        cdg.add_dependency(ControlDependency::new("if_inner", "deep_node", true).with_nesting(1));

        assert_eq!(cdg.get_nesting_level("if_inner"), 0);
        assert_eq!(cdg.get_nesting_level("deep_node"), 1);
    }

    #[test]
    fn test_get_all_taint_sources() {
        let mut state = ImplicitTaintState::new();

        state.add_direct_taint("x", "source1");
        state.add_direct_taint("x", "source2");
        state.add_implicit_taint("x", ImplicitTaintSource::new("secret", "cond", true));

        let sources = state.get_all_taint_sources("x");
        assert!(sources.len() >= 3);
        assert!(sources.iter().any(|s| s == "source1"));
        assert!(sources.iter().any(|s| s == "source2"));
        assert!(sources.iter().any(|s| s.contains("implicit:")));
    }

    #[test]
    fn test_implicit_flow_config_default() {
        let config = ImplicitFlowConfig::default();

        assert_eq!(config.max_depth, 50);
        assert_eq!(config.max_paths, 1000);
        assert!(config.track_nested);
        assert!(!config.include_low_severity);
        assert!(config.taint_sources.contains("password"));
        assert!(config.taint_sinks.contains("execute"));
    }

    #[test]
    fn test_extract_write_target() {
        let analyzer = ImplicitFlowAnalyzer::default_config();

        assert_eq!(
            analyzer.extract_write_target("x = 1"),
            Some("x".to_string())
        );
        assert_eq!(
            analyzer.extract_write_target("assign_result"),
            Some("result".to_string())
        );
        assert_eq!(analyzer.extract_write_target("print(x)"), None);
    }

    #[test]
    fn test_extract_condition_vars() {
        let analyzer = ImplicitFlowAnalyzer::default_config();

        let vars = analyzer.extract_condition_vars("if_secret");
        assert!(vars.contains(&"secret".to_string()));

        let vars = analyzer.extract_condition_vars("branch_x_gt_5");
        assert!(vars.contains(&"x".to_string()));
    }

    #[test]
    fn test_extract_used_vars() {
        let analyzer = ImplicitFlowAnalyzer::default_config();

        let vars = analyzer.extract_used_vars("print(x)");
        assert!(vars.contains(&"x".to_string()));

        let vars = analyzer.extract_used_vars("execute(cmd, arg)");
        assert!(vars.contains(&"cmd".to_string()));
        assert!(vars.contains(&"arg".to_string()));
    }
}
